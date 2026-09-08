from django.test import TestCase

from tracker.catalog_matching import capacity_profile, has_variant_conflict, resolve_canonical_product
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

    def test_does_not_merge_different_ram(self):
        Product.objects.create(name="Tecno Spark 40 8GB RAM 256GB")
        result = resolve_canonical_product("Tecno Spark 40 12GB RAM 256GB")
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

    def test_storage_alias_go_and_gb_are_equivalent(self):
        self.assertFalse(has_variant_conflict("iPhone 16e 128 Go", "iPhone 16e 128GB"))

    def test_slash_capacity_detects_ram_and_storage(self):
        profile = capacity_profile("Tecno Spark 40 8/256GB")
        self.assertEqual(profile.ram_gb, 8)
        self.assertEqual(profile.storage_gb, 256)
        self.assertTrue(has_variant_conflict("Tecno Spark 40 8/256GB", "Tecno Spark 40 12/256GB"))

    def test_single_small_capacity_is_not_assumed_to_be_storage(self):
        self.assertFalse(has_variant_conflict("Téléphone 8GB", "Téléphone 12GB"))
