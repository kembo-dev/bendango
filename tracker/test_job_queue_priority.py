from unittest.mock import patch

from django.test import SimpleTestCase

from tracker.job_queue import _local_market_bonus, _queue_priority
from tracker.models import ScrapeJob


class LocalMerchantPriorityTests(SimpleTestCase):
    def test_cd_domain_gets_strong_local_bonus(self):
        self.assertEqual(_local_market_bonus("https://www.oui.cd/product/ps4"), 18.0)

    def test_local_market_hint_in_domain_gets_bonus(self):
        self.assertEqual(_local_market_bonus("https://kinshasa-shop.com/produit/ps4"), 12.0)

    def test_local_hint_in_path_gets_smaller_bonus(self):
        self.assertEqual(_local_market_bonus("https://example.com/kinshasa/ps4"), 6.0)

    def test_global_domain_has_no_local_bonus(self):
        self.assertEqual(_local_market_bonus("https://example.com/product/ps4"), 0.0)

    @patch("tracker.job_queue.product_url_score", return_value=2.0)
    @patch("tracker.job_queue.url_domain_health_score", return_value=0.5)
    def test_local_candidate_ranks_above_equal_global_candidate(self, _health, _product):
        local = ScrapeJob(url="https://www.oui.cd/product/ps4", query="ps4")
        global_candidate = ScrapeJob(url="https://example.com/product/ps4", query="ps4")

        local_score = _queue_priority(local, set(), {})
        global_score = _queue_priority(global_candidate, set(), {})

        self.assertGreater(local_score, global_score)
