from django.test import SimpleTestCase

from tracker.extractors import extract_structured_product
from tracker.product_matching import match_product, product_match_score


class StructuredExtractionTests(SimpleTestCase):
    def test_extracts_jsonld_product_offer(self):
        html = '''
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Product",
          "name": "Tecno Spark 40 8GB 256GB",
          "sku": "TEC-40-256",
          "brand": {"@type": "Brand", "name": "Tecno"},
          "image": "https://example.com/spark40.jpg",
          "offers": {
            "@type": "Offer",
            "price": "299.99",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock"
          }
        }
        </script></head><body></body></html>
        '''
        data = extract_structured_product(html)
        self.assertIsNotNone(data)
        self.assertEqual(data.product_name, "Tecno Spark 40 8GB 256GB")
        self.assertEqual(str(data.price), "299.99")
        self.assertEqual(data.currency, "USD")
        self.assertTrue(data.in_stock)
        self.assertEqual(data.sku_or_ean, "TEC-40-256")
        self.assertEqual(data.brand, "Tecno")

    def test_extracts_meta_product(self):
        html = '''
        <html><head>
          <meta property="og:title" content="Samsung Galaxy A56 256GB">
          <meta property="product:price:amount" content="450,00">
          <meta property="product:price:currency" content="USD">
          <meta property="product:availability" content="in stock">
        </head></html>
        '''
        data = extract_structured_product(html)
        self.assertIsNotNone(data)
        self.assertEqual(str(data.price), "450.00")
        self.assertEqual(data.currency, "USD")


class ProductMatchingStage2Tests(SimpleTestCase):
    def test_query_matches_enriched_merchant_title(self):
        result = match_product("tecno spark 40", "Tecno Spark 40 8GB 256GB")
        self.assertTrue(result.is_match)
        self.assertGreaterEqual(result.score, 0.72)

    def test_accessory_is_not_main_product(self):
        result = match_product("iphone 15", "Coque de protection iPhone 15")
        self.assertFalse(result.is_match)

    def test_different_phone_model_is_rejected(self):
        result = match_product("iphone 15", "iPhone 16 256GB")
        self.assertFalse(result.is_match)

    def test_score_remains_numeric_api(self):
        score = product_match_score("samsung galaxy a56", "Samsung Galaxy A56 256GB")
        self.assertIsInstance(score, float)
        self.assertGreater(score, 0.5)
