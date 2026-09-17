from django.test import SimpleTestCase

from tracker.discovery_sources import _is_relevant_discovery_result


class DiscoverySourceRelevanceTests(SimpleTestCase):
    def test_ps4_local_commercial_source_is_accepted(self):
        accepted, score = _is_relevant_discovery_result(
            "ps4",
            "TikTok",
            "PS4 disponible à Kinshasa",
            "Prix 250 USD, livraison à Kinshasa RDC",
        )
        self.assertTrue(accepted)
        self.assertGreaterEqual(score, 0.68)

    def test_playstation_2_is_rejected_for_ps4_query(self):
        accepted, _ = _is_relevant_discovery_result(
            "ps4",
            "TikTok",
            "Playstation 2 prix Kinshasa RDC",
            "Console disponible à Kinshasa",
        )
        self.assertFalse(accepted)

    def test_non_local_ps4_social_source_is_rejected(self):
        accepted, _ = _is_relevant_discovery_result(
            "ps4",
            "TikTok",
            "Kedai PS4 di Kota Kinabalu",
            "PS4 shop price available delivery",
        )
        self.assertFalse(accepted)

    def test_global_comparison_source_does_not_require_local_signal(self):
        accepted, score = _is_relevant_discovery_result(
            "ps4",
            "Idealo",
            "Sony PlayStation 4 PS4 au meilleur prix",
            "Comparatif et prix PlayStation 4",
        )
        self.assertTrue(accepted)
        self.assertGreaterEqual(score, 0.62)
