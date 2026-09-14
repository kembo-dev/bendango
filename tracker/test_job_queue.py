from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from tracker.job_queue import claim_next_job, complete_job, enqueue_scrape_job, fail_job, recover_stale_running_jobs
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

    def test_running_job_cannot_be_claimed_twice(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        first = claim_next_job()
        second = claim_next_job()
        self.assertEqual(first.pk, job.pk)
        self.assertIsNone(second)
        job.refresh_from_db()
        self.assertEqual(job.attempts, 1)

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

    def test_retry_job_is_not_claimed_before_available_at(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur')
        job.status = ScrapeJob.STATUS_RETRY
        job.available_at = timezone.now() + timedelta(minutes=1)
        job.save()
        self.assertIsNone(claim_next_job())

    def test_failure_stops_after_max_attempts(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur', max_attempts=1)
        job = claim_next_job()
        fail_job(job, 'timeout', retryable=True)
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_FAILED)

    def test_stale_running_job_is_recovered_for_retry(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur', max_attempts=3)
        job = claim_next_job()
        ScrapeJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(recover_stale_running_jobs(timeout_seconds=60), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_RETRY)
        self.assertEqual(job.fetch_status, 'stale_worker')
        self.assertEqual(job.attempts, 1)

    def test_stale_running_job_fails_when_attempts_exhausted(self):
        job = enqueue_scrape_job('https://merchant.example/products/disk-1tb', 'disque dur', max_attempts=1)
        job = claim_next_job()
        ScrapeJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(recover_stale_running_jobs(timeout_seconds=60), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, ScrapeJob.STATUS_FAILED)
        self.assertEqual(job.fetch_status, 'stale_worker')

    @patch('tracker.job_queue.url_domain_health_score', return_value=0.5)
    def test_product_like_url_is_claimed_before_older_generic_url(self, health_mock):
        generic = enqueue_scrape_job('https://merchant-a.example/page/yamaha-f310', 'Yamaha F310')
        product = enqueue_scrape_job('https://merchant-b.example/product/yamaha-f310', 'Yamaha F310')
        claimed = claim_next_job()
        self.assertEqual(claimed.pk, product.pk)
        self.assertNotEqual(claimed.pk, generic.pk)

    @patch('tracker.job_queue.url_domain_health_score')
    def test_health_breaks_tie_between_similar_product_urls(self, health_mock):
        health_mock.side_effect = lambda url: 0.9 if 'healthy.example' in url else 0.1
        low = enqueue_scrape_job('https://low.example/product/yamaha-f310', 'Yamaha F310')
        healthy = enqueue_scrape_job('https://healthy.example/product/yamaha-f310', 'Yamaha F310')
        claimed = claim_next_job()
        self.assertEqual(claimed.pk, healthy.pk)
        self.assertNotEqual(claimed.pk, low.pk)

    @patch('tracker.job_queue.url_domain_health_score', return_value=0.5)
    def test_new_merchant_gets_diversity_bonus_for_same_query(self, health_mock):
        previous = ScrapeJob.objects.create(
            url='https://known.example/product/yamaha-old',
            query='Yamaha F310',
            status=ScrapeJob.STATUS_SUCCESS,
            fetch_status='processed',
            attempts=1,
            max_attempts=3,
            available_at=timezone.now(),
            finished_at=timezone.now(),
        )
        known = enqueue_scrape_job('https://known.example/product/yamaha-f310', 'Yamaha F310')
        fresh = enqueue_scrape_job('https://fresh.example/product/yamaha-f310', 'Yamaha F310')
        claimed = claim_next_job()
        self.assertEqual(previous.status, ScrapeJob.STATUS_SUCCESS)
        self.assertEqual(claimed.pk, fresh.pk)
        self.assertNotEqual(claimed.pk, known.pk)

    @patch('tracker.job_queue.url_domain_health_score')
    def test_fresh_pending_job_is_claimed_before_higher_scoring_retry(self, health_mock):
        health_mock.side_effect = lambda url: 1.0 if 'retry.example' in url else 0.0
        retry = enqueue_scrape_job('https://retry.example/product/yamaha-f310', 'Yamaha F310')
        retry.status = ScrapeJob.STATUS_RETRY
        retry.attempts = 1
        retry.available_at = timezone.now() - timedelta(seconds=30)
        retry.save()
        fresh = enqueue_scrape_job('https://fresh.example/page/yamaha-f310', 'Yamaha F310')

        claimed = claim_next_job()

        self.assertEqual(claimed.pk, fresh.pk)
        self.assertNotEqual(claimed.pk, retry.pk)

    @patch('tracker.job_queue.url_domain_health_score', return_value=0.5)
    def test_retry_is_claimed_when_no_fresh_job_is_ready(self, health_mock):
        retry = enqueue_scrape_job('https://retry.example/product/yamaha-f310', 'Yamaha F310')
        retry.status = ScrapeJob.STATUS_RETRY
        retry.attempts = 1
        retry.available_at = timezone.now() - timedelta(seconds=30)
        retry.save()

        claimed = claim_next_job()

        self.assertEqual(claimed.pk, retry.pk)
        self.assertEqual(claimed.status, ScrapeJob.STATUS_RUNNING)
