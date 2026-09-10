from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.adaptive_engine import _process_urls
from tracker.models import ScrapeJob


class _Diagnostics:
    def __init__(self):
        self.processed = 0
        self.errors = []

    def record_processed(self):
        self.processed += 1

    def record_error(self, error):
        self.errors.append(error)


class AdaptiveQueueIntegrationTests(TestCase):
    def _call(self, url='https://merchant.example/products/disk-1tb'):
        diagnostics = _Diagnostics()
        results = []
        errors = []
        _process_urls(
            [url], set(), results, errors, diagnostics,
            'model', 'disque dur', [], 3, [],
        )
        return diagnostics, results, errors

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False)
    def test_async_mode_enqueues_candidate_without_scraping(self):
        with patch('tracker.adaptive_engine.process_url_and_save') as process:
            diagnostics, results, errors = self._call()
        self.assertFalse(process.called)
        self.assertEqual(ScrapeJob.objects.count(), 1)
        self.assertEqual(ScrapeJob.objects.get().status, ScrapeJob.STATUS_PENDING)
        self.assertEqual(diagnostics.processed, 1)
        self.assertEqual(results, [])
        self.assertEqual(errors, [])

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=True)
    def test_sync_fallback_runs_job_and_persists_failure(self):
        with patch('tracker.adaptive_engine.process_url_and_save', return_value=(None, 'Page sans structure de produit exploitable.')):
            diagnostics, results, errors = self._call()
        job = ScrapeJob.objects.get()
        self.assertEqual(job.status, ScrapeJob.STATUS_FAILED)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertTrue(diagnostics.errors)

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False)
    def test_async_mode_reuses_completed_listing_job(self):
        from tracker.models import PriceListing, Product, Retailer
        product = Product.objects.create(name='Disque dur 1TB')
        retailer = Retailer.objects.create(name='Merchant', base_url='https://merchant.example')
        listing = PriceListing.objects.create(product=product, retailer=retailer, url='https://merchant.example/products/disk-1tb', price='50', currency='USD')
        ScrapeJob.objects.create(
            url=listing.url,
            query='disque dur',
            model_name='model',
            status=ScrapeJob.STATUS_SUCCESS,
            attempts=1,
            listing=listing,
            available_at=timezone.now(),
            finished_at=timezone.now(),
        )
        diagnostics, results, errors = self._call(listing.url)
        self.assertEqual(results, [listing])
        self.assertEqual(errors, [])
