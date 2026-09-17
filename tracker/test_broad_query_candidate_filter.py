from django.test import SimpleTestCase

from tracker.candidate_filter import is_low_value_candidate_url


class BroadQueryCandidateFilterTests(SimpleTestCase):
    def test_recommendation_page_is_rejected(self):
        self.assertTrue(is_low_value_candidate_url(
            'https://www.shoppingparticipatif.com/recommandations/string-femme',
            query='string femme',
        ))

    def test_short_category_slug_is_rejected_for_broad_query(self):
        self.assertTrue(is_low_value_candidate_url(
            'https://zeshoes.com/fr/1672-string-femme',
            query='string femme',
        ))

    def test_explicit_product_path_remains_allowed(self):
        self.assertFalse(is_low_value_candidate_url(
            'https://boutique.example/product/string-femme-dentelle-noir',
            query='string femme',
        ))

    def test_model_specific_product_url_remains_allowed(self):
        self.assertFalse(is_low_value_candidate_url(
            'https://mobile.example/phones/infinix-hot-60-pro-x6885',
            query='Infinix Hot 60 Pro X6885',
        ))
