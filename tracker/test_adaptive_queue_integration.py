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
    def _call(self, url='https://merchant.example/products/disk-1tb', allowed_hosts=None):
        diagnostics = _Diagnostics()
        results = []
        errors = []
        _process_urls(
            [url], set(), results, errors, diagnostics,
            'model', 'disque dur', allowed_hosts or [], 3, [],
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

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=True)
    def test_sync_fallback_does_not_steal_running_job(self):
        ScrapeJob.objects.create(
            url='https://merchant.example/products/disk-1tb',
            query='disque dur',
            model_name='model',
            status=ScrapeJob.STATUS_RUNNING,
            attempts=1,
            available_at=timezone.now(),
            started_at=timezone.now(),
        )
        with patch('tracker.adaptive_engine.process_url_and_save') as process:
            diagnostics, results, errors = self._call()
        self.assertFalse(process.called)
        job = ScrapeJob.objects.get()
        self.assertEqual(job.status, ScrapeJob.STATUS_RUNNING)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(results, [])
        self.assertEqual(errors, [])

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=True)
    def test_sync_fallback_passes_allowed_hosts(self):
        with patch('tracker.adaptive_engine.process_url_and_save', return_value=(None, 'Page sans structure de produit exploitable.')) as process:
            self._call(allowed_hosts=['merchant.example'])
        self.assertEqual(process.call_args.kwargs['allowed_hosts'], ['merchant.example'])

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

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False, ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN=2)
    def test_global_search_caps_candidates_per_domain(self):
        diagnostics = _Diagnostics()
        urls = [
            'https://shop.example/products/a',
            'https://shop.example/products/b',
            'https://shop.example/products/c',
            'https://other.example/products/d',
        ]
        _process_urls(
            urls, set(), [], [], diagnostics,
            'model', 'disque dur', [], 10, [],
        )
        queued = list(ScrapeJob.objects.values_list('url', flat=True))
        self.assertEqual(len(queued), 3)
        self.assertIn('https://other.example/products/d', queued)
        self.assertNotIn('https://shop.example/products/c', queued)

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False, ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN=1)
    def test_selected_site_is_not_limited_by_global_domain_cap(self):
        diagnostics = _Diagnostics()
        urls = [
            'https://shop.example/products/a',
            'https://shop.example/products/b',
        ]
        _process_urls(
            urls, set(), [], [], diagnostics,
            'model', 'disque dur', ['shop.example'], 10, ['shop.example'],
        )
        self.assertEqual(ScrapeJob.objects.count(), 2)
