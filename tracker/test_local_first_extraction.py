from unittest.mock import patch

from django.test import TestCase

from tracker.services import ExtractedProductData, process_url_and_save


class LocalFirstExtractionTests(TestCase):
    @patch("tracker.services.refresh_retailer_trust")
    @patch("tracker.services._extract_llm_only")
    @patch("tracker.services.extract_structured_product", return_value=None)
    @patch("tracker.services.fetch_and_clean_html")
    def test_html_fallback_skips_llm_when_local_extraction_succeeds(
        self,
        fetch_mock,
        structured_mock,
        llm_mock,
        trust_mock,
    ):
        fetch_mock.return_value = """
            <html>
              <head><title>Guitare Yamaha F310</title></head>
              <body>
                <h1>Guitare Yamaha F310</h1>
                <div>Prix: 199 USD</div>
                <div>En stock - ajouter au panier</div>
              </body>
            </html>
        """

        listing, error = process_url_and_save(
            "https://merchant.example/product/yamaha-f310",
            expected_query="Yamaha F310",
            allowed_hosts=[],
        )

        self.assertIsNone(error)
        self.assertIsNotNone(listing)
        self.assertEqual(listing.extraction_source, "html")
        self.assertEqual(float(listing.price), 199.0)
        llm_mock.assert_not_called()

    @patch("tracker.services.refresh_retailer_trust")
    @patch("tracker.services._fallback_extract_html", return_value=None)
    @patch("tracker.services._extract_llm_only")
    @patch("tracker.services.extract_structured_product", return_value=None)
    @patch("tracker.services.fetch_and_clean_html")
    def test_llm_remains_last_resort_when_local_extraction_fails(
        self,
        fetch_mock,
        structured_mock,
        llm_mock,
        fallback_mock,
        trust_mock,
    ):
        fetch_mock.return_value = """
            <html>
              <head><title>Guitare Yamaha F310</title></head>
              <body>
                <h1>Guitare Yamaha F310</h1>
                <div>Produit disponible, price on request</div>
                <div>Ajouter au panier</div>
              </body>
            </html>
        """
        llm_mock.return_value = ExtractedProductData(
            product_name="Guitare Yamaha F310",
            price=205,
            currency="USD",
            in_stock=True,
        )

        listing, error = process_url_and_save(
            "https://merchant.example/product/yamaha-f310-llm",
            expected_query="Yamaha F310",
            allowed_hosts=[],
        )

        self.assertIsNone(error)
        self.assertIsNotNone(listing)
        self.assertEqual(listing.extraction_source, "llm")
        llm_mock.assert_called_once()
