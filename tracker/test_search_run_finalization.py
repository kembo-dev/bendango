from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from tracker.job_queue import finalize_exhausted_search_run
from tracker.models import PriceListing, Product, Retailer, ScrapeJob, SearchRun
from tracker.views import _run_state


class SearchRunFinalizationTests(TestCase):
    def setUp(self):
        self.run = SearchRun.objects.create(
            query='Samsung Galaxy A56 5G 8GB 256GB',
            site_filter='all',
            target_merchants=3,
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_RUNNING,
            discovery_finished_at=timezone.now(),
        )

    def _listing(self):
        product = Product.objects.create(name='Samsung Galaxy A56 5G 8GB 256GB')
        retailer = Retailer.objects.create(
            name='Marchand finalisation',
            base_url='https://marchand-finalisation.example',
        )
        return PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url='https://marchand-finalisation.example/product/a56',
            price=Decimal('300.00'),
            currency='USD',
            in_stock=True,
        )

    def test_run_state_finishes_partial_coverage_when_no_active_jobs_remain(self):
        listing = self._listing()
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url=listing.url,
            status=ScrapeJob.STATUS_SUCCESS,
            listing=listing,
            finished_at=timezone.now(),
        )

        state = _run_state(self.run)

        self.assertEqual(state['status'], 'finished')
        self.assertEqual(state['merchants'], 1)
        self.assertEqual(state['active'], 0)

    def test_finalizer_persists_completed_for_partial_success(self):
        listing = self._listing()
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url=listing.url,
            status=ScrapeJob.STATUS_SUCCESS,
            listing=listing,
            finished_at=timezone.now(),
        )

        status = finalize_exhausted_search_run(self.run.pk)
        self.run.refresh_from_db()

        self.assertEqual(status, SearchRun.STATUS_COMPLETED)
        self.assertEqual(self.run.status, SearchRun.STATUS_COMPLETED)
        self.assertIsNotNone(self.run.completed_at)

    def test_finalizer_persists_failed_when_all_jobs_failed(self):
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url='https://echec.example/product/a56',
            status=ScrapeJob.STATUS_FAILED,
            fetch_status='fetch_failed',
            finished_at=timezone.now(),
        )

        status = finalize_exhausted_search_run(self.run.pk)
        self.run.refresh_from_db()

        self.assertEqual(status, SearchRun.STATUS_FAILED)
        self.assertEqual(self.run.status, SearchRun.STATUS_FAILED)
        self.assertIsNotNone(self.run.completed_at)
