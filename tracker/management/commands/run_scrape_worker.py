import time

from django.core.management.base import BaseCommand

from tracker.domain_health import url_fetch_budget
from tracker.job_outcomes import classify_processing_error, should_retry_job
from tracker.job_queue import claim_next_job, complete_job, fail_job, recover_stale_running_jobs
from tracker.reliable_collection import reset_fetch_policy, set_fetch_policy
from tracker.services import process_url_and_save


class Command(BaseCommand):
    help = 'Process Bendango ScrapeJob records from the database queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one job and exit.')
        parser.add_argument('--max-jobs', type=int, default=0, help='Stop after N jobs; 0 means unlimited.')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds to wait when the queue is empty.')
        parser.add_argument('--exit-when-empty', action='store_true', help='Exit when no available job remains.')
        parser.add_argument('--stale-timeout', type=int, default=None, help='Seconds before a running job is considered abandoned.')

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

            started = time.monotonic()
            budget = url_fetch_budget(job.url)
            policy_token = set_fetch_policy(budget)
            try:
                listing, error = process_url_and_save(
                    job.url,
                    model_name=job.model_name or None,
                    expected_query=job.query or None,
                    allowed_hosts=[],
                )
                duration_ms = max(1, int((time.monotonic() - started) * 1000))
                if listing:
                    complete_job(job, listing=listing, fetch_status='processed', duration_ms=duration_ms)
                    self.stdout.write(self.style.SUCCESS(
                        f'job {job.pk}: success ({duration_ms}ms, fetch={budget["tier"]})'
                    ))
                else:
                    fetch_status, retryable = classify_processing_error(error)
                    retryable = should_retry_job(fetch_status, job.attempts, retryable)
                    fail_job(
                        job,
                        error or "Échec de traitement.",
                        retryable=retryable,
                        fetch_status=fetch_status,
                        duration_ms=duration_ms,
                    )
                    self.stdout.write(self.style.WARNING(
                        f'job {job.pk}: {job.status}/{job.fetch_status} ({duration_ms}ms, fetch={budget["tier"]}) - {job.last_error}'
                    ))
            except Exception as exc:
                duration_ms = max(1, int((time.monotonic() - started) * 1000))
                fail_job(job, str(exc), retryable=True, fetch_status='worker_exception', duration_ms=duration_ms)
                self.stderr.write(f'job {job.pk}: {job.status}/worker_exception ({duration_ms}ms) - {exc}')
            finally:
                reset_fetch_policy(policy_token)

            processed += 1
            if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                break
