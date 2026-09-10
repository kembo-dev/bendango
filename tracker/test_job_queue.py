from django.test import TestCase
from django.utils import timezone

from tracker.job_queue import claim_next_job, complete_job, enqueue_scrape_job, fail_job
from tracker.models import ScrapeJob


class ScrapeJobQueueTests(TestCase):
    def test_enqueue_deduplicates_active_url_and_query(self):
        first = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        second = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ScrapeJob.objects.count(), 1)

    def test_claim_marks_job_running_and_increments_attempts(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        claimed = claim_next_job()
        self.assertEqual(claimed.pk, job.pk)
        self.assertEqual(claimed.status, ScrapeJob.STATUS_RUNNING)
        self.assertEqual(claimed.attempts, 1)
        self.assertIsNotNone(claimed.started_at)

    def test_complete_marks_job_success(self):
        enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        job = claim_next_job()
        complete_job(job, fetch_status='cache_hit', duration_ms=12, from_cache=True)
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_SUCCESS)
        self.assertEqual(job.fetch_status, 'cache_hit')
        self.assertTrue(job.from_cache)
        self.assertIsNotNone(job.finished_at)

    def test_retryable_failure_is_rescheduled(self):
        enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur', max_attempts=3)
        job = claim_next_job()
        before = timezone.now()
        fail_job(job, 'timeout', retryable=True, fetch_status='network_failure')
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_RETRY)
        self.assertGreater(job.available_at, before)

    def test_failure_stops_after_max_attempts(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur', max_attempts=1)
        job = claim_next_job()
        fail_job(job, 'timeout', retryable=True)
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_FAILED)
