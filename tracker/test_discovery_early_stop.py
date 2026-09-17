from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from tracker.adaptive_engine import _process_urls, _search_terms_into_urls
from tracker.models import ScrapeJob, SearchRun


class SearchRunEarlyStopTests(TestCase):
    def setUp(self):
        self.run = SearchRun.objects.create(
            query="Produit test",
            site_filter="all",
            target_merchants=3,
            status=SearchRun.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )

    @patch("tracker.adaptive_engine.collect_search_candidates")
    def test_completed_run_does_not_issue_more_web_searches(self, mock_collect):
        diagnostics = MagicMock()
        urls = []
        search_errors = []

        _search_terms_into_urls(
            ["Produit test prix RDC", "Produit test acheter Kinshasa"],
            urls,
            diagnostics,
            search_errors,
            candidate_limit=15,
            product_query="Produit test",
            search_run=self.run,
        )

        mock_collect.assert_not_called()
        diagnostics.record_search_term.assert_not_called()
        self.assertEqual(urls, [])
        self.assertEqual(search_errors, [])

    @patch("tracker.adaptive_engine.enqueue_scrape_job")
    def test_completed_run_does_not_enqueue_more_scrape_jobs(self, mock_enqueue):
        diagnostics = MagicMock()

        _process_urls(
            ["https://merchant.example/product/produit-test"],
            processed_urls=set(),
            results=[],
            errors=[],
            diagnostics=diagnostics,
            selected="test-model",
            product_query="Produit test",
            allowed_hosts=[],
            target_merchants=3,
            site_filters=[],
            search_run=self.run,
        )

        mock_enqueue.assert_not_called()
        diagnostics.record_processed.assert_not_called()
        self.assertEqual(ScrapeJob.objects.filter(search_run=self.run).count(), 0)
