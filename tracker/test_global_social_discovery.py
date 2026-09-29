from django.test import SimpleTestCase

from tracker.discovery_sources import _is_relevant_discovery_result


class GlobalSocialDiscoveryTests(SimpleTestCase):
    def test_global_broad_social_result_does_not_require_local_market_signal(self):
        relevant, score = _is_relevant_discovery_result(
            'string',
            'Facebook',
            'String femme disponible - prix promo',
            'Acheter string femme en stock, livraison disponible',
            market_code='GLOBAL',
        )
        self.assertTrue(relevant)
        self.assertGreaterEqual(score, 0.82)

    def test_local_broad_social_result_still_requires_market_signal(self):
        relevant, _ = _is_relevant_discovery_result(
            'string',
            'Facebook',
            'String femme disponible - prix promo',
            'Acheter string femme en stock, livraison disponible',
            market_code='CD',
        )
        self.assertFalse(relevant)

    def test_local_broad_social_result_accepts_matching_market_signal(self):
        relevant, _ = _is_relevant_discovery_result(
            'string',
            'Facebook',
            'String femme Kinshasa disponible - prix promo',
            'Acheter string femme en stock, livraison disponible en RDC',
            market_code='CD',
        )
        self.assertTrue(relevant)
