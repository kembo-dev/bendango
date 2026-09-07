import os
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from tracker.models import PriceListing, Product, Retailer
from tracker.services import (
    ExtractedProductData,
    _collect_search_urls,
    _is_category_or_listing_url,
    _is_homepage_url,
    _is_low_quality_source_url,
    ensure_retailer_for_site,
    normalize_site_filter,
    process_url_and_save,
    search_and_scrape_product,
)


class CustomSiteSearchTests(TestCase):
    def test_normalize_site_filter_accepts_domain_without_scheme(self):
        domain, base_url = normalize_site_filter("example.com")

        self.assertEqual(domain, "example.com")
        self.assertEqual(base_url, "https://example.com")

    def test_normalize_site_filter_accepts_full_url(self):
        domain, base_url = normalize_site_filter("https://www.example.com/path")

        self.assertEqual(domain, "example.com")
        self.assertEqual(base_url, "https://www.example.com")

    def test_ensure_retailer_for_site_creates_retailer(self):
        retailer = ensure_retailer_for_site("https://www.example.com")

        self.assertIsNotNone(retailer)
        self.assertTrue(Retailer.objects.filter(base_url="https://www.example.com").exists())
        self.assertEqual(retailer.name, "Example.com")

    @override_settings(
        LLM_CONFIG={
            "provider": "bedrock",
            "default_model": "us.meta.llama3-1-70b-instruct-v1:0",
            "models": ["us.meta.llama3-1-70b-instruct-v1:0", "us.google.gemma-3-12b-it-v1:0"],
            "region": "us-east-1",
            "access_key_id": "test-access-key",
            "secret_access_key": "test-secret-key",
        }
    )
    def test_llm_config_is_loaded_from_settings(self):
        from tracker.services import get_llm_config

        config = get_llm_config()

        self.assertEqual(config["provider"], "bedrock")
        self.assertEqual(config["default_model"], "us.meta.llama3-1-70b-instruct-v1:0")
        self.assertIn("us.meta.llama3-1-70b-instruct-v1:0", config["models"])
        self.assertEqual(config["region"], "us-east-1")
        self.assertEqual(config["access_key_id"], "test-access-key")

    def test_bedrock_model_alias_resolves_to_gemma_v1(self):
        from tracker.services import resolve_bedrock_model_id

        self.assertEqual(resolve_bedrock_model_id("google.gemma-3-12b-it", "us-east-1"), "google.gemma-3-12b-it")
        self.assertEqual(resolve_bedrock_model_id("us.meta.llama3-1-70b-instruct-v1:0", "us-east-1"), "us.meta.llama3-1-70b-instruct-v1:0")

    @override_settings(LLM_CONFIG={})
    @patch.dict(
        os.environ,
        {"LLM_MODEL": "openai.gpt-oss-120b", "LLM_MODELS": "google.gemma-3-12b-it"},
        clear=False,
    )
    def test_stale_llm_model_does_not_override_valid_llm_models(self):
        from tracker.services import get_llm_config

        config = get_llm_config()

        self.assertEqual(config["default_model"], "google.gemma-3-12b-it")
        self.assertEqual(config["models"][0], "google.gemma-3-12b-it")

    @patch("tracker.services.requests.Session.get")
    def test_process_url_and_save_rejects_category_pages(self, mock_get):
        from tracker.services import process_url_and_save

        category_url = "https://cd.coinafrique.com/categorie/jeux-video-et-consoles"

        listing, error = process_url_and_save(category_url, model_name="google.gemma-3-12b-it")

        self.assertIsNone(listing)
        self.assertIn("liste", error.lower())
        mock_get.assert_not_called()

    @patch("tracker.services.extract_with_llm")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_accepts_drcmart_product_url(self, mock_fetch, mock_extract):
        mock_fetch.return_value = """
            <html><body>
            <h1>iPhone 15</h1>
            <div>Prix : 999 USD</div>
            <p>En stock</p>
            <button>Ajouter au panier</button>
            </body></html>
        """
        mock_extract.return_value = ExtractedProductData(
            product_name="iPhone 15",
            price=999,
            currency="USD",
            in_stock=True,
            sku_or_ean="IP15-001",
        )

        listing, error = process_url_and_save(
            "https://drcmart.com/produit/iphone-15",
            expected_query="iPhone 15",
            allowed_hosts=["drcmart.com"],
        )

        self.assertIsNone(error)
        self.assertIsNotNone(listing)
        self.assertEqual(listing.product.name, "iPhone 15")

    def test_homepage_is_rejected(self):
        self.assertTrue(_is_homepage_url("https://example.com/"))

    def test_category_url_is_rejected(self):
        self.assertTrue(_is_category_or_listing_url("https://example.com/category/phones/"))

    def test_low_quality_blog_url_is_rejected(self):
        self.assertTrue(_is_low_quality_source_url("https://example.com/blog/iphone-review"))

    @patch("tracker.services.DDGS")
    def test_collect_search_urls_filters_invalid_results(self, mock_ddgs):
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.return_value = [
            {"href": "https://example.com/"},
            {"href": "https://example.com/blog/iphone-review"},
            {"href": "https://example.com/product/iphone-15"},
        ]

        urls = _collect_search_urls("iphone 15", max_results=3)

        self.assertEqual(urls, ["https://example.com/product/iphone-15"])

    @patch("tracker.services._collect_search_urls")
    @patch("tracker.services.process_url_and_save")
    def test_search_and_scrape_product_uses_results(self, mock_process, mock_collect):
        product = Product.objects.create(name="iPhone 15")
        retailer = Retailer.objects.create(name="Example", base_url="https://example.com")
        listing = PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url="https://example.com/product/iphone-15",
            price=999,
            currency="USD",
        )
        mock_collect.return_value = [listing.url]
        mock_process.return_value = (listing, None)

        results, errors = search_and_scrape_product("iPhone 15", max_results=3)

        self.assertEqual(results, [listing])
        self.assertEqual(errors, [])


# Keep the original repository tests below this marker if additional coverage
# is appended locally. This file intentionally contains the core regression
# tests required by the clean V2 branch.
