from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from tracker.reliable_collection import fetch_html


@override_settings(COLLECTION_DOMAIN_MIN_INTERVAL=0, COLLECTION_BACKOFF_BASE=0, COLLECTION_HTML_CACHE_TTL=300)
class ReliableCollectionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("tracker.reliable_collection.requests.Session.get")
    def test_success_is_cached(self, get):
        response = Mock(status_code=200, content=b"<html><body>Produit 100 USD</body></html>", encoding="utf-8")
        get.return_value = response
        first = fetch_html("https://merchant.example/products/test")
        second = fetch_html("https://merchant.example/products/test")
        self.assertEqual(first.status, "success")
        self.assertEqual(second.status, "cache_hit")
        self.assertTrue(second.from_cache)
        self.assertEqual(get.call_count, 1)

    @patch("tracker.reliable_collection.requests.Session.get")
    def test_transient_503_is_retried(self, get):
        failed = Mock(status_code=503, content=b"", encoding="utf-8")
        success = Mock(status_code=200, content=b"<html><body>Produit 100 USD</body></html>", encoding="utf-8")
        get.side_effect = [failed, success]
        result = fetch_html("https://merchant.example/products/retry")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempts, 2)

    @patch("tracker.reliable_collection.requests.Session.get")
    def test_permanent_404_is_not_retried(self, get):
        get.return_value = Mock(status_code=404, content=b"not found", encoding="utf-8")
        result = fetch_html("https://merchant.example/products/missing")
        self.assertEqual(result.status, "http_error")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(get.call_count, 1)

    @patch("tracker.reliable_collection.requests.Session.get")
    def test_anti_bot_page_is_detected(self, get):
        get.return_value = Mock(status_code=200, content=b"<html>Verify you are human - CAPTCHA</html>", encoding="utf-8")
        result = fetch_html("https://merchant.example/products/protected")
        self.assertEqual(result.status, "anti_bot")
        self.assertIsNone(result.html)

    @patch("tracker.reliable_collection.requests.Session.get")
    def test_network_failure_is_retried_then_reported(self, get):
        get.side_effect = requests.Timeout("timeout")
        result = fetch_html("https://merchant.example/products/timeout")
        self.assertEqual(result.status, "network_failure")
        self.assertEqual(result.attempts, 3)
