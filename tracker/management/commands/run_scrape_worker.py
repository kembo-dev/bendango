import time

from django.conf import settings
from django.core.management.base import BaseCommand

from tracker.domain_health import domain_fetch_circuit_open, domain_from_url, url_fetch_budget
from tracker.job_outcomes import classify_processing_error, should_retry_job
from tracker.job_queue import claim_next_job, complete_job, defer_job, fail_job, recover_stale_running_jobs
from tracker.reliable_collection import (
    clear_last_fetch_result,
    get_last_fetch_result,
    reset_fetch_policy,
    set_fetch_policy,
)
from tracker.services import process_url_and_save


class Command(BaseCommand):
    help = 'Process Bendango ScrapeJob records from the database queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one job and exit.')
        parser.add_argument('--max-jobs', type=int, default=0, help='Stop after N jobs; 0 means unlimited.')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds to wait when the queue is empty.')
        parser.add_argument('--exit-when-empty', action='store_true', help='Exit when no available job remains.')
        parser.add_argument('--stale-timeout', type=int, default=None, help='Seconds before a running job is considered abandoned.')

    @staticmethod
    def _timing_label(total_ms, fetch_result, listing=None):
        fetch_ms = int(getattr(fetch_result, 'duration_ms', 0) or 0)
        process_ms = max(0, int(total_ms) - fetch_ms)
        source = getattr(listing, 'extraction_source', '') or '-'
        return f'fetch_ms={fetch_ms}, process_ms={process_ms}, source={source}'

    def handle(self, *args, **options):
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

            domain = domain_from_url(job.url)
            if domain_fetch_circuit_open(domain):
                cooldown_seconds = max(60, int(getattr(settings, 'DOMAIN_FETCH_CIRCUIT_MINUTES', 10)) * 60)
                defer_job(job, cooldown_seconds, reason='domain_cooldown')
                self.stdout.write(self.style.WARNING(
                    f'job {job.pk}: retry/domain_cooldown (domain={domain}, delay={cooldown_seconds}s)'
                ))
                processed += 1
                if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                    break
                continue

            started = time.monotonic()
            budget = url_fetch_budget(job.url)
            budget = {**budget, 'use_cache': True}
            policy_token = set_fetch_policy(budget)
            clear_last_fetch_result()
            try:
                listing, error = process_url_and_save(
                    job.url,
                    model_name=job.model_name or None,
                    expected_query=job.query or None,
                    allowed_hosts=[],
                )
                duration_ms = max(1, int((time.monotonic() - started) * 1000))
                fetch_result = get_last_fetch_result()
                from_cache = bool(getattr(fetch_result, 'from_cache', False))
                http_status = getattr(fetch_result, 'http_status', None)
                timing = self._timing_label(duration_ms, fetch_result, listing)
                if listing:
                    complete_job(
                        job,
                        listing=listing,
                        fetch_status='processed',
                        http_status=http_status,
                        duration_ms=duration_ms,
                        from_cache=from_cache,
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f'job {job.pk}: success ({duration_ms}ms, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing})'
                    ))
                else:
                    fetch_status, retryable = classify_processing_error(error)
                    retryable = should_retry_job(fetch_status, job.attempts, retryable)
                    fail_job(
                        job,
                        error or "Échec de traitement.",
                        retryable=retryable,
                        fetch_status=fetch_status,
                        http_status=http_status,
                        duration_ms=duration_ms,
                        from_cache=from_cache,
                    )
                    self.stdout.write(self.style.WARNING(
                        f'job {job.pk}: {job.status}/{job.fetch_status} ({duration_ms}ms, fetch={budget["tier"]}, cache={"hit" if from_cache else "miss"}, {timing}) - {job.last_error}'
                    ))
            except Exception as exc:
                duration_ms = max(1, int((time.monotonic() - started) * 1000))
                fetch_result = get_last_fetch_result()
                from_cache = bool(getattr(fetch_result, 'from_cache', False))
                http_status = getattr(fetch_result, 'http_status', None)
                timing = self._timing_label(duration_ms, fetch_result)
                fail_job(
                    job,
                    str(exc),
                    retryable=True,
                    fetch_status='worker_exception',
                    http_status=http_status,
                    duration_ms=duration_ms,
                    from_cache=from_cache,
                )
                self.stderr.write(
                    f'job {job.pk}: {job.status}/worker_exception ({duration_ms}ms, cache={"hit" if from_cache else "miss"}, {timing}) - {exc}'
                )
            finally:
                reset_fetch_policy(policy_token)

            processed += 1
            if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                break
