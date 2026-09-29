from django.test import SimpleTestCase, override_settings

from tracker.adaptive_engine import _max_scrape_jobs, _partial_async_coverage_exhausted
from tracker.adaptive_search import build_global_fallback_terms
from tracker.product_matching import match_product
from tracker.services import (
    _is_category_or_listing_url,
    _is_low_quality_source_url,
    _safe_price_decimal,
)


class SearchRecoveryRegressionTests(SimpleTestCase):
    def test_global_fallback_terms_are_country_agnostic(self):
        terms = build_global_fallback_terms('Samsung Galaxy A56 5G 8GB 256GB')
        self.assertTrue(terms)
        self.assertTrue(any('buy' in term or 'shop' in term for term in terms))
        self.assertFalse(any('RDC' in term or 'Kinshasa' in term for term in terms))

    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=False)
    def test_partial_async_coverage_does_not_stop_recovery(self):
        self.assertFalse(_partial_async_coverage_exhausted(object()))

    @override_settings(ADAPTIVE_MAX_SCRAPE_JOBS=30)
    def test_adaptive_job_budget_restores_broader_capacity(self):
        limit, existing = _max_scrape_jobs(None, 3)
        self.assertEqual(limit, 30)
        self.assertEqual(existing, 0)

    def test_nested_shop_product_url_is_not_treated_as_shop_index(self):
        url = 'https://example.com/shop/samsung-galaxy-a56-5g-256gb-786'
        self.assertFalse(_is_category_or_listing_url(url))
        self.assertTrue(_is_category_or_listing_url('https://example.com/shop/'))

    def test_comparison_editorial_source_is_rejected_at_service_boundary(self):
        self.assertTrue(
            _is_low_quality_source_url(
                'https://www.lesnumeriques.com/telephone-portable/samsung-galaxy-a56-p76132.html'
            )
        )

    def test_non_finite_prices_are_rejected_before_quantize(self):
        self.assertIsNone(_safe_price_decimal(float('nan')))
        self.assertIsNone(_safe_price_decimal(float('inf')))
        self.assertIsNone(_safe_price_decimal(float('-inf')))

    def test_ram_conflict_is_not_hidden_by_shared_storage(self):
        result = match_product(
            'Samsung Galaxy A56 5G 8GB 256GB',
            'Samsung Galaxy A56 5G 12GB 256GB',
        )
        self.assertFalse(result.is_match)
        self.assertEqual(result.reason, 'configuration mémoire différente')
