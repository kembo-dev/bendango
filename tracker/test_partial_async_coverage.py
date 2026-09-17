from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.adaptive_engine import _partial_async_coverage_exhausted, _successful_run_merchants
from tracker.models import PriceListing, Product, Retailer, ScrapeJob, SearchRun


@override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False)
class PartialAsyncCoverageTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name="Infinix Hot 60 Pro 8GB 256GB")
        self.retailer = Retailer.objects.create(
            name="Marchand test",
            base_url="https://marchand.cd",
        )
        self.listing = PriceListing.objects.create(
            product=self.product,
            retailer=self.retailer,
            url="https://marchand.cd/produit/infinix-hot-60-pro-8gb-256gb",
            price=Decimal("299.00"),
            currency="USD",
            in_stock=True,
        )
        self.run = SearchRun.objects.create(
            query="Infinix Hot 60 Pro 8GB 256GB",
            site_filter="all",
            target_merchants=3,
            status=SearchRun.STATUS_RUNNING,
        )

    def _success_job(self):
        return ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url=self.listing.url,
            status=ScrapeJob.STATUS_SUCCESS,
            listing=self.listing,
            finished_at=timezone.now(),
        )

    def test_partial_coverage_is_exhausted_when_success_exists_and_no_jobs_are_active(self):
        self._success_job()

        self.assertEqual(_successful_run_merchants(self.run), 1)
        self.assertTrue(_partial_async_coverage_exhausted(self.run))

    def test_partial_coverage_is_not_exhausted_while_pending_work_remains(self):
        self._success_job()
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url="https://autre-boutique.cd/produit/infinix-hot-60-pro",
            status=ScrapeJob.STATUS_PENDING,
        )

        self.assertFalse(_partial_async_coverage_exhausted(self.run))

    def test_partial_coverage_is_not_exhausted_without_any_success(self):
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url="https://echec.example/produit/infinix-hot-60-pro",
            status=ScrapeJob.STATUS_FAILED,
            fetch_status="fetch_failed",
            finished_at=timezone.now(),
        )

        self.assertEqual(_successful_run_merchants(self.run), 0)
        self.assertFalse(_partial_async_coverage_exhausted(self.run))
