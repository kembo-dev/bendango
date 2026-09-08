from django.test import TestCase

from tracker.catalog_matching import resolve_canonical_product
from tracker.models import Product


class CanonicalProductMatchingTests(TestCase):
    def test_resolves_equivalent_merchant_title(self):
        canonical = Product.objects.create(name="Tecno Spark 40 8GB 256GB")
        result = resolve_canonical_product("TECNO Spark 40 8+256 256GB")
        self.assertEqual(result.product, canonical)

    def test_does_not_merge_different_storage(self):
        Product.objects.create(name="Tecno Spark 40 8GB 128GB")
        result = resolve_canonical_product("Tecno Spark 40 8GB 256GB")
        self.assertIsNone(result.product)

    def test_does_not_merge_pro_with_base_variant(self):
        Product.objects.create(name="Tecno Spark 40 Pro 256GB")
        result = resolve_canonical_product("Tecno Spark 40 256GB")
        self.assertIsNone(result.product)

    def test_sku_has_priority_over_title_variation(self):
        canonical = Product.objects.create(name="Apple iPhone 15 128GB", sku_or_ean="ABC-123")
        result = resolve_canonical_product("iPhone quinze téléphone", sku_or_ean="ABC-123")
        self.assertEqual(result.product, canonical)
        self.assertEqual(result.score, 1.0)
