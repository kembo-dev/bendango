import time

from django.core.management.base import BaseCommand

from tracker.job_queue import claim_next_job, complete_job, fail_job
from tracker.services import process_url_and_save


class Command(BaseCommand):
    help = 'Process Bendango ScrapeJob records from the database queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one job and exit.')
        parser.add_argument('--max-jobs', type=int, default=0, help='Stop after N jobs; 0 means unlimited.')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds to wait when the queue is empty.')

    def handle(self, *args, **options):
        processed = 0
        while True:
            job = claim_next_job()
            if job is None:
                if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                    break
                time.sleep(max(options['poll_interval'], 0.1))
                continue

            try:
                listing, error = process_url_and_save(
                    job.url,
                    model_name=job.model_name or None,
                    expected_query=job.query or None,
                )
                if listing:
                    complete_job(job, listing=listing, fetch_status='processed')
                    self.stdout.write(self.style.SUCCESS(f'job {job.pk}: success'))
                else:
                    retryable = error == 'Impossible de récupérer le contenu de la page web.'
                    fail_job(job, error or "Échec de traitement.", retryable=retryable, fetch_status='processing_failure')
                    self.stdout.write(self.style.WARNING(f'job {job.pk}: {job.status} - {job.last_error}'))
            except Exception as exc:
                fail_job(job, str(exc), retryable=True, fetch_status='worker_exception')
                self.stderr.write(f'job {job.pk}: {job.status} - {exc}')

            processed += 1
            if options['once'] or (options['max_jobs'] and processed >= options['max_jobs']):
                break
