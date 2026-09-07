from decimal import Decimal

from django.test import TestCase, override_settings

from tracker.currency import convert_price
from tracker.extraction import extract_jsonld_product
from tracker.models import PriceHistory, PriceListing, Product, Retailer
from tracker.product_matching import product_match_score


class ProductMatchingV2Tests(TestCase):
    def test_accessory_is_not_the_requested_phone(self):
        result = product_match_score("Coque pour iPhone 15 Pro 256GB", "iPhone 15 Pro 256GB")
        self.assertFalse(result.is_match)

    def test_storage_mismatch_is_rejected(self):
        self.assertFalse(product_match_score("Samsung Galaxy S24 128GB", "Samsung Galaxy S24 256GB").is_match)

    def test_same_product_with_local_wording_matches(self):
        self.assertTrue(product_match_score("Apple iPhone 15 Pro Max 256 Go", "iPhone 15 Pro Max 256GB").is_match)


@override_settings(BENDANGO_FX_RATES={"USD": "1", "CDF": "2800", "EUR": "0.86"})
class CurrencyTests(TestCase):
    def test_cdf_and_usd_are_comparable(self):
        self.assertEqual(convert_price(280000, "CDF", "USD"), Decimal("100.00"))


class StructuredExtractionTests(TestCase):
    def test_jsonld_product_is_preferred(self):
        html = '''<html><body><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Tecno Spark 40","sku":"TEC40","brand":{"@type":"Brand","name":"Tecno"},"offers":{"@type":"Offer","price":"299","priceCurrency":"USD","availability":"https://schema.org/InStock"}}</script><h1>Tecno Spark 40</h1></body></html>'''
        data = extract_jsonld_product(html)
        self.assertEqual(data["product_name"], "Tecno Spark 40")
        self.assertEqual(data["price"], 299.0)
        self.assertEqual(data["source"], "jsonld")


class PriceHistoryTests(TestCase):
    def test_saving_listing_keeps_each_observation(self):
        product = Product.objects.create(name="Tecno Spark 40")
        retailer = Retailer.objects.create(name="Example", base_url="https://example.com")
        listing = PriceListing.objects.create(product=product, retailer=retailer, url="https://example.com/product/tecno", price=Decimal("300"), currency="USD")
        listing.price = Decimal("280")
        listing.save()
        self.assertEqual(PriceHistory.objects.filter(listing=listing).count(), 2)
        self.assertEqual(listing.normalized_price, Decimal("280.00"))
