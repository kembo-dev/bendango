import fcntl
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

from tracker.domain_health import domain_fetch_circuit_open, domain_from_url, url_fetch_budget
from tracker.job_outcomes import classify_processing_error, should_retry_job
from tracker.job_queue import (
    cancel_satisfied_query_jobs,
    claim_next_job,
    complete_job,
    defer_job,
    fail_job,
    recover_stale_running_jobs,
)
from tracker.reliable_collection import (
    clear_last_fetch_result,
    get_last_fetch_result,
    reset_fetch_policy,
    set_fetch_policy,
)
from tracker.services import process_url_and_save


class DomainLock:
    """Per-domain lock using Redis when configured, with a local file fallback."""

    def __init__(self, domain: str):
        self.domain = domain or 'unknown'
        digest = hashlib.sha256(self.domain.encode('utf-8')).hexdigest()
        self.cache_key = f'scrape-domain-lock:{digest}'
        self.owner = f'{os.getpid()}:{time.time_ns()}'
        self.redis_lock = None
        root = Path(getattr(settings, 'SCRAPE_DOMAIN_LOCK_DIR', '') or (Path(tempfile.gettempdir()) / 'bendango-domain-locks'))
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f'{digest}.lock'
        self.handle = None

    def acquire(self) -> bool:
        if getattr(settings, 'REDIS_URL', ''):
            timeout = max(10, int(getattr(settings, 'SCRAPE_DOMAIN_LOCK_TIMEOUT', 30)))
            try:
                client = cache.client.get_client(write=True)
                self.redis_lock = client.lock(
                    self.cache_key,
                    timeout=timeout,
                    blocking_timeout=0,
                    thread_local=False,
                )
                return bool(self.redis_lock.acquire(blocking=False))
            except Exception:
                self.redis_lock = None
                return False

        self.handle = open(self.path, 'a+', encoding='utf-8')
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(f'{self.owner}\n')
            self.handle.flush()
            return True
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False

    def release(self):
        if self.redis_lock is not None:
            try:
                self.redis_lock.release()
            except Exception:
                pass
            finally:
                self.redis_lock = None
            return
        if self.handle is None:
            return
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


class Command(BaseCommand):
    help = 'Process Bendango ScrapeJob records from the database queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one job and exit.')
        parser.add_argument('--max-jobs', type=int, default=0, help='Stop after N jobs; 0 means unlimited.')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds to wait when the queue is empty.')
        parser.add_argument('--exit-when-empty', action='store_true', help='Exit when no available job remains.')
        parser.add_argument('--stale-timeout', type=int, default=None, help='Seconds before a running job is considered abandoned.')
        parser.add_argument('--workers', type=int, default=1, help='Number of parallel worker processes to launch.')
        parser.add_argument('--child-worker', action='store_true', help='Internal flag used by the worker supervisor.')

    @staticmethod
    def _timing_label(total_ms, fetch_result, listing=None):
        fetch_ms = int(getattr(fetch_result, 'duration_ms', 0) or 0)
        process_ms = max(0, int(total_ms) - fetch_ms)
        source = getattr(listing, 'extraction_source', '') or '-'
        return f'fetch_ms={fetch_ms}, process_ms={process_ms}, source={source}'

    def _run_parallel_supervisor(self, options):
        worker_count = max(1, min(int(options['workers']), int(getattr(settings, 'SCRAPE_MAX_WORKERS', 4))))
        manage_py = str(Path(settings.BASE_DIR) / 'manage.py')
        processes = []
        self.stdout.write(self.style.SUCCESS(f'Starting {worker_count} Bendango scrape workers'))

        for index in range(worker_count):
            command = [sys.executable, manage_py, 'run_scrape_worker', '--workers', '1', '--child-worker', '--poll-interval', str(options['poll_interval'])]
            if options['exit_when_empty']:
                command.append('--exit-when-empty')
            if options['once']:
                command.append('--once')
            if options['max_jobs']:
                command.extend(['--max-jobs', str(options['max_jobs'])])
            if options['stale_timeout'] is not None:
                command.extend(['--stale-timeout', str(options['stale_timeout'])])
            env = os.environ.copy()
            env['BENDANGO_WORKER_INDEX'] = str(index + 1)
            processes.append(subprocess.Popen(command, cwd=str(settings.BASE_DIR), env=env))

        exit_code = 0
        try:
            for process in processes:
                code = process.wait()
                if code != 0:
                    exit_code = code
        except KeyboardInterrupt:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                process.wait()
            raise
        if exit_code:
            raise SystemExit(exit_code)

    def handle(self, *args, **options):
        requested_workers = max(1, int(options['workers']))
        if requested_workers > 1 and not options['child_worker']:
            return self._run_parallel_supervisor(options)

        processed = 0
        recovered = recover_stale_running_jobs(options['stale_timeout'])
        if recovered:
            self.stdout.write(self.style.WARNING(f'{recovered} stale running job(s) recovered'))

        while True:
            job = claim_next_job()
            if job is None:
                if options['once'] or options['exit_when_empty'] or (options['max_jobs'] and processed >= options['max_jobs']):
                    break
                time.sleep(max(options['poll_interval'], 0.1))
                continue

            lane = getattr(job, 'queue_lane', 'unknown')
            domain = domain_from_url(job.url)
            domain_lock = DomainLock(domain)
            if not domain_lock.acquire():
                busy_delay = max(1, int(getattr(settings, 'SCRAPE_DOMAIN_BUSY_DELAY', 2)))
                defer_job(job, busy_delay, reason='domain_busy')
                self.stdout.write(self.style.WARNING(f'job {job.pk}: retry/domain_busy (lane={lane}, domain={domain}, delay={busy_delay}s)'))
                processed += 1
                if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                    break
                continue

            try:
                if domain_fetch_circuit_open(domain):
                    cooldown_seconds = max(60, int(getattr(settings, 'DOMAIN_FETCH_CIRCUIT_MINUTES', 10)) * 60)
                    defer_job(job, cooldown_seconds, reason='domain_cooldown')
                    self.stdout.write(self.style.WARNING(f'job {job.pk}: retry/domain_cooldown (lane={lane}, domain={domain}, delay={cooldown_seconds}s)'))
                    processed += 1
                    if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                        break
                    continue

                started = time.monotonic()
                budget = {**url_fetch_budget(job.url), 'use_cache': True}
                policy_token = set_fetch_policy(budget)
                clear_last_fetch_result()
                try:
                    listing, error = process_url_and_save(job.url, model_name=job.model_name or None, expected_query=job.query or None, allowed_hosts=[])
                    duration_ms = max(1, int((time.monotonic() - started) * 1000))
                    fetch_result = get_last_fetch_result()
                    from_cache = bool(getattr(fetch_result, 'from_cache', False))
                    http_status = getattr(fetch_result, 'http_status', None)
                    timing = self._timing_label(duration_ms, fetch_result, listing)
                    if listing:
                        complete_job(job, listing=listing, fetch_status='processed', http_status=http_status, duration_ms=duration_ms, from_cache=from_cache)
                        self.stdout.write(self.style.SUCCESS(f'job {job.pk}: success ({duration_ms}ms, lane={lane}, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing})'))
                        cancelled = cancel_satisfied_query_jobs(job.query)
                        if cancelled:
                            self.stdout.write(self.style.SUCCESS(f'query coverage reached: cancelled {cancelled} queued job(s) for {job.query!r}'))
                    else:
                        fetch_status, retryable = classify_processing_error(error)
                        retryable = should_retry_job(fetch_status, job.attempts, retryable)
                        fail_job(job, error or "Échec de traitement.", retryable=retryable, fetch_status=fetch_status, http_status=http_status, duration_ms=duration_ms, from_cache=from_cache)
                        self.stdout.write(self.style.WARNING(f'job {job.pk}: {job.status}/{job.fetch_status} ({duration_ms}ms, lane={lane}, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing}) - {job.last_error}'))
                except Exception as exc:
                    duration_ms = max(1, int((time.monotonic() - started) * 1000))
                    fetch_result = get_last_fetch_result()
                    from_cache = bool(getattr(fetch_result, 'from_cache', False))
                    http_status = getattr(fetch_result, 'http_status', None)
                    timing = self._timing_label(duration_ms, fetch_result)
                    fail_job(job, str(exc), retryable=True, fetch_status='worker_exception', http_status=http_status, duration_ms=duration_ms, from_cache=from_cache)
                    self.stderr.write(f'job {job.pk}: {job.status}/worker_exception ({duration_ms}ms, lane={lane}, cache={"hit" if from_cache else "miss"}, {timing}) - {exc}')
                finally:
                    reset_fetch_policy(policy_token)
            finally:
                domain_lock.release()

            processed += 1
            if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                break
