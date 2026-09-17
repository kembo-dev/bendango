from django.test import SimpleTestCase

from tracker.product_matching import match_product


class ProductVariantMatchingTests(SimpleTestCase):
    def test_pro_does_not_match_pro_plus(self):
        result = match_product(
            "Infinix Hot 60 Pro 8GB 256GB",
            "Infinix Hot 60 Pro Plus 4G 8GB RAM 256GB",
        )
        self.assertFalse(result.is_match)
        self.assertEqual(result.reason, "variante produit différente")

    def test_pro_does_not_match_plain_model(self):
        result = match_product(
            "Infinix Hot 60 Pro 8GB 256GB",
            "Infinix Hot 60 8GB 256GB",
        )
        self.assertFalse(result.is_match)
        self.assertEqual(result.reason, "variante produit différente")

    def test_plain_model_does_not_match_pro(self):
        result = match_product(
            "Samsung Galaxy S24 256GB",
            "Samsung Galaxy S24 Pro 256GB",
        )
        self.assertFalse(result.is_match)
        self.assertEqual(result.reason, "variante produit différente")

    def test_same_pro_variant_still_matches(self):
        result = match_product(
            "Infinix Hot 60 Pro 8GB 256GB",
            "Infinix Hot 60 Pro 256GB 8GB RAM",
        )
        self.assertTrue(result.is_match)

    def test_same_ultra_variant_still_matches(self):
        result = match_product(
            "Samsung Galaxy S24 Ultra 256GB",
            "Samsung Galaxy S24 Ultra 256GB Smartphone",
        )
        self.assertTrue(result.is_match)
