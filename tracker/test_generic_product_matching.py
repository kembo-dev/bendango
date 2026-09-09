from django.test import SimpleTestCase

from tracker.product_matching import match_product


class GenericProductMatchingTests(SimpleTestCase):
    def test_generic_hard_drive_query_accepts_detailed_product(self):
        result = match_product("disque dur", "Disque dur externe Toshiba 1TB")
        self.assertTrue(result.is_match)
        self.assertGreaterEqual(result.score, 0.86)

    def test_generic_hard_drive_query_accepts_ssd_product(self):
        result = match_product("disque dur", "Disque dur SSD KingSpec P3 1TB 2.5 SATA")
        self.assertTrue(result.is_match)

    def test_generic_hard_drive_query_rejects_enclosure_accessory(self):
        result = match_product("disque dur", "Boîtier disque dur externe USB 3.0")
        self.assertFalse(result.is_match)
        self.assertIn("accessoire", result.reason)

    def test_capacity_conflict_still_rejected(self):
        result = match_product("disque dur 1TB", "Disque dur externe Toshiba 2TB")
        self.assertFalse(result.is_match)
        self.assertEqual(result.reason, "capacité différente")

    def test_phone_query_rejects_case(self):
        result = match_product("iPhone 15", "Coque de protection iPhone 15")
        self.assertFalse(result.is_match)
        self.assertIn("accessoire", result.reason)
