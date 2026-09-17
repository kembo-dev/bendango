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
from tracker.job_queue import cancel_same_domain_run_jobs, cancel_satisfied_run_jobs, claim_next_job, complete_job, defer_job, discard_running_job, fail_job, job_coverage_reached, recover_stale_running_jobs
from tracker.reliable_collection import clear_last_fetch_result, get_last_fetch_result, reset_fetch_policy, set_fetch_policy
from tracker.services import process_url_and_save


class DomainLock:
    def __init__(self, domain: str):
        self.domain = domain or 'unknown'
        digest = hashlib.sha256(self.domain.encode('utf-8')).hexdigest()
        self.cache_key = f'scrape-domain-lock:{digest}'
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
                self.redis_lock = client.lock(self.cache_key, timeout=timeout, blocking_timeout=0, thread_local=False)
                return bool(self.redis_lock.acquire(blocking=False))
            except Exception:
                self.redis_lock = None
                return False
        self.handle = open(self.path, 'a+', encoding='utf-8')
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
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
            self.redis_lock = None
            return
        if self.handle is not None:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None


class Command(BaseCommand):
    help = 'Process Bendango ScrapeJob records from the database queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--max-jobs', type=int, default=0)
        parser.add_argument('--poll-interval', type=float, default=1.0)
        parser.add_argument('--exit-when-empty', action='store_true')
        parser.add_argument('--stale-timeout', type=int, default=None)
        parser.add_argument('--workers', type=int, default=1)
        parser.add_argument('--child-worker', action='store_true')

    @staticmethod
    def _timing_label(total_ms, fetch_result, listing=None):
        fetch_ms = int(getattr(fetch_result, 'duration_ms', 0) or 0)
        return f'fetch_ms={fetch_ms}, process_ms={max(0, int(total_ms) - fetch_ms)}, source={getattr(listing, "extraction_source", "") or "-"}'

    @staticmethod
    def _allow_queue_retry(fetch_status: str, attempts: int, retryable: bool, budget: dict) -> bool:
        allowed = should_retry_job(fetch_status, attempts, retryable)
        if not allowed:
            return False
        if fetch_status == 'fetch_failed' and budget.get('tier') in {'low', 'limited'}:
            return False
        return True

    def _run_parallel_supervisor(self, options):
        count = max(1, min(int(options['workers']), int(getattr(settings, 'SCRAPE_MAX_WORKERS', 4))))
        manage_py = str(Path(settings.BASE_DIR) / 'manage.py')
        processes = []
        self.stdout.write(self.style.SUCCESS(f'Starting {count} Bendango scrape workers'))
        for index in range(count):
            command = [sys.executable, manage_py, 'run_scrape_worker', '--workers', '1', '--child-worker', '--poll-interval', str(options['poll_interval'])]
            if options['exit_when_empty']: command.append('--exit-when-empty')
            if options['once']: command.append('--once')
            if options['max_jobs']: command.extend(['--max-jobs', str(options['max_jobs'])])
            if options['stale_timeout'] is not None: command.extend(['--stale-timeout', str(options['stale_timeout'])])
            env = os.environ.copy(); env['BENDANGO_WORKER_INDEX'] = str(index + 1)
            processes.append(subprocess.Popen(command, cwd=str(settings.BASE_DIR), env=env))
        try:
            codes = [process.wait() for process in processes]
        except KeyboardInterrupt:
            for process in processes:
                if process.poll() is None: process.terminate()
            for process in processes: process.wait()
            raise
        if any(codes): raise SystemExit(next(code for code in codes if code))

    def handle(self, *args, **options):
        if max(1, int(options['workers'])) > 1 and not options['child_worker']:
            return self._run_parallel_supervisor(options)
        processed = 0
        recovered = recover_stale_running_jobs(options['stale_timeout'])
        if recovered: self.stdout.write(self.style.WARNING(f'{recovered} stale running job(s) recovered'))

        while True:
            job = claim_next_job()
            if job is None:
                if options['once'] or options['exit_when_empty'] or (options['max_jobs'] and processed >= options['max_jobs']): break
                time.sleep(max(options['poll_interval'], 0.1)); continue
            lane = getattr(job, 'queue_lane', 'unknown')
            domain = domain_from_url(job.url)
            run_label = str(job.search_run_id)[:8] if job.search_run_id else 'legacy'

            if job_coverage_reached(job):
                discard_running_job(job)
                self.stdout.write(self.style.SUCCESS(f'job {job.pk}: skipped/coverage_reached (lane={lane}, run={run_label})'))
                processed += 1; continue

            domain_lock = DomainLock(domain)
            if not domain_lock.acquire():
                delay = max(1, int(getattr(settings, 'SCRAPE_DOMAIN_BUSY_DELAY', 2)))
                defer_job(job, delay, reason='domain_busy')
                self.stdout.write(self.style.WARNING(f'job {job.pk}: retry/domain_busy (lane={lane}, run={run_label}, domain={domain}, delay={delay}s)'))
                processed += 1; continue
            try:
                if job_coverage_reached(job):
                    discard_running_job(job)
                    self.stdout.write(self.style.SUCCESS(f'job {job.pk}: skipped/coverage_reached (lane={lane}, run={run_label})'))
                    processed += 1; continue
                if domain_fetch_circuit_open(domain):
                    delay = max(60, int(getattr(settings, 'DOMAIN_FETCH_CIRCUIT_MINUTES', 10)) * 60)
                    defer_job(job, delay, reason='domain_cooldown')
                    self.stdout.write(self.style.WARNING(f'job {job.pk}: retry/domain_cooldown (lane={lane}, run={run_label}, domain={domain}, delay={delay}s)'))
                    processed += 1; continue

                started = time.monotonic()
                budget = {
                    **url_fetch_budget(job.url),
                    'use_cache': True,
                    'cancel_check': lambda current_job=job: job_coverage_reached(current_job),
                }
                token = set_fetch_policy(budget); clear_last_fetch_result()
                try:
                    listing, error = process_url_and_save(job.url, model_name=job.model_name or None, expected_query=job.query or None, allowed_hosts=[])
                    duration_ms = max(1, int((time.monotonic() - started) * 1000)); fetch_result = get_last_fetch_result()
                    from_cache = bool(getattr(fetch_result, 'from_cache', False)); http_status = getattr(fetch_result, 'http_status', None)
                    timing = self._timing_label(duration_ms, fetch_result, listing)

                    if getattr(fetch_result, 'status', '') == 'cancelled' or (not listing and job_coverage_reached(job)):
                        discard_running_job(job)
                        self.stdout.write(self.style.SUCCESS(f'job {job.pk}: skipped/coverage_reached ({duration_ms}ms, lane={lane}, run={run_label}, {timing})'))
                    elif listing:
                        complete_job(job, listing=listing, fetch_status='processed', http_status=http_status, duration_ms=duration_ms, from_cache=from_cache)
                        self.stdout.write(self.style.SUCCESS(f'job {job.pk}: success ({duration_ms}ms, lane={lane}, run={run_label}, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing})'))
                        same_domain_cancelled = cancel_same_domain_run_jobs(job)
                        if same_domain_cancelled:
                            self.stdout.write(self.style.SUCCESS(f'run {run_label}: cancelled {same_domain_cancelled} queued duplicate-domain job(s) for {domain}'))
                        cancelled = cancel_satisfied_run_jobs(job)
                        if cancelled:
                            self.stdout.write(self.style.SUCCESS(f'run {run_label} coverage reached: cancelled {cancelled} queued job(s) for {job.query!r}'))
                    else:
                        fetch_status, retryable = classify_processing_error(error)
                        retryable = False if job_coverage_reached(job) else self._allow_queue_retry(fetch_status, job.attempts, retryable, budget)
                        fail_job(job, error or 'Échec de traitement.', retryable=retryable, fetch_status=fetch_status, http_status=http_status, duration_ms=duration_ms, from_cache=from_cache)
                        self.stdout.write(self.style.WARNING(f'job {job.pk}: {job.status}/{job.fetch_status} ({duration_ms}ms, lane={lane}, run={run_label}, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing}) - {job.last_error}'))
                except Exception as exc:
                    duration_ms = max(1, int((time.monotonic() - started) * 1000)); fetch_result = get_last_fetch_result()
                    if getattr(fetch_result, 'status', '') == 'cancelled' or job_coverage_reached(job):
                        discard_running_job(job)
                        self.stdout.write(self.style.SUCCESS(f'job {job.pk}: skipped/coverage_reached ({duration_ms}ms, lane={lane}, run={run_label})'))
                    else:
                        retryable = budget.get('tier') not in {'low', 'limited'}
                        fail_job(job, str(exc), retryable=retryable, fetch_status='worker_exception', http_status=getattr(fetch_result, 'http_status', None), duration_ms=duration_ms, from_cache=bool(getattr(fetch_result, 'from_cache', False)))
                        self.stderr.write(f'job {job.pk}: {job.status}/worker_exception (lane={lane}, run={run_label}, fetch={budget["tier"]}) - {exc}')
                finally:
                    reset_fetch_policy(token)
            finally:
                domain_lock.release()
            processed += 1
            if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']): break