from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.domain_health import domain_fetch_circuit_open
from tracker.job_queue import claim_job, defer_job, enqueue_scrape_job
from tracker.models import ScrapeJob


@override_settings(DOMAIN_FETCH_CIRCUIT_FAILURES=2, DOMAIN_FETCH_CIRCUIT_MINUTES=10)
class DomainFetchCooldownTests(TestCase):
    def _terminal_job(self, url, status, fetch_status, minutes_ago=0):
        job = ScrapeJob.objects.create(
            url=url,
            query="guitare",
            status=status,
            fetch_status=fetch_status,
            attempts=1,
            max_attempts=3,
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
        )
        ScrapeJob.objects.filter(pk=job.pk).update(
            finished_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
        return job

    def test_opens_after_two_recent_transport_failures(self):
        self._terminal_job(
            "https://merchant.example/product/a",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
        )
        self._terminal_job(
            "https://merchant.example/product/b",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
        )

        self.assertTrue(domain_fetch_circuit_open("merchant.example"))

    def test_recent_success_closes_circuit(self):
        self._terminal_job(
            "https://merchant.example/product/a",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
        )
        self._terminal_job(
            "https://merchant.example/product/b",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
        )
        self._terminal_job(
            "https://merchant.example/product/c",
            ScrapeJob.STATUS_SUCCESS,
            "processed",
        )

        self.assertFalse(domain_fetch_circuit_open("merchant.example"))

    def test_old_failures_expire_out_of_cooldown_window(self):
        self._terminal_job(
            "https://merchant.example/product/a",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
            minutes_ago=20,
        )
        self._terminal_job(
            "https://merchant.example/product/b",
            ScrapeJob.STATUS_FAILED,
            "fetch_failed",
            minutes_ago=20,
        )

        self.assertFalse(domain_fetch_circuit_open("merchant.example"))

    def test_non_transport_failures_do_not_open_circuit(self):
        self._terminal_job(
            "https://merchant.example/product/a",
            ScrapeJob.STATUS_FAILED,
            "product_mismatch",
        )
        self._terminal_job(
            "https://merchant.example/product/b",
            ScrapeJob.STATUS_FAILED,
            "extraction_failed",
        )

        self.assertFalse(domain_fetch_circuit_open("merchant.example"))

    def test_defer_releases_claim_without_consuming_attempt(self):
        job = enqueue_scrape_job(
            "https://merchant.example/product/a",
            query="guitare",
            max_attempts=3,
        )
        claimed = claim_job(job.pk)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.attempts, 1)

        before = timezone.now()
        deferred = defer_job(claimed, 600, reason="domain_cooldown")

        self.assertEqual(deferred.status, ScrapeJob.STATUS_RETRY)
        self.assertEqual(deferred.attempts, 0)
        self.assertEqual(deferred.fetch_status, "domain_cooldown")
        self.assertIsNone(deferred.started_at)
        self.assertGreaterEqual(deferred.available_at, before + timedelta(seconds=599))
