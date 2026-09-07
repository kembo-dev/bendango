import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import PriceListing, Product, Retailer
from tracker.services import (
    ExtractedProductData,
    cleanup_stale_listings,
    ensure_retailer_for_site,
    fetch_and_clean_html,
    normalize_site_filter,
    process_url_and_save,
    search_and_scrape_product,
)


class CustomSiteSearchTests(TestCase):
    def test_normalize_site_filter_accepts_custom_domain_and_url(self):
        self.assertEqual(normalize_site_filter("example.com"), ("example.com", "https://example.com"))
        self.assertEqual(normalize_site_filter("https://www.example.com/shop"), ("example.com", "https://www.example.com"))

    def test_ensure_retailer_for_site_creates_missing_retailer(self):
        self.assertFalse(Retailer.objects.filter(base_url="https://www.example.com").exists())

        retailer = ensure_retailer_for_site("www.example.com")

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

    @patch("tracker.services.DDGS")
    def test_collect_search_urls_skips_locale_homepage_and_collection_pages(self, mock_ddgs):
        from tracker.services import _collect_search_urls

        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://www.drcmart.com/fr"},
            {"href": "https://www.drcmart.com/fr/collections/villaon-mobile-phone"},
            {"href": "https://www.drcmart.com/fr/products/tecno-spark-40-8gb-256gb"},
        ]

        urls = _collect_search_urls("tecno spark 40", max_results=10)

        self.assertEqual(urls, ["https://www.drcmart.com/fr/products/tecno-spark-40-8gb-256gb"])

    @patch("tracker.services.extract_with_llm")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_accepts_drcmart_product_url(self, mock_fetch, mock_extract):
        from tracker.services import process_url_and_save

        mock_fetch.return_value = "<html><body><h1>Tecno Spark 40 8GB 256GB</h1><div>299,99 €</div><p>En stock</p></body></html>"
        mock_extract.return_value = ExtractedProductData(
            product_name="Tecno Spark 40 8GB 256GB",
            price=299.99,
            currency="EUR",
            in_stock=True,
            sku_or_ean="TEC-40-256",
        )

        listing, error = process_url_and_save(
            "https://www.drcmart.com/fr/products/tecno-spark-40-8gb-256gb",
            expected_query="tecno spark 40",
            allowed_hosts=["drcmart.com"],
        )

        self.assertIsNotNone(listing)
        self.assertIsNone(error)
        self.assertEqual(listing.product.name, "Tecno Spark 40 8GB 256GB")
        self.assertEqual(float(listing.price), 299.99)

    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_404_drc_pages_before_llm(self, mock_fetch):
        from tracker.services import process_url_and_save

        mock_fetch.return_value = "<html><head><title>404 Page introuvable</title></head><body>Page introuvable</body></html>"

        listing, error = process_url_and_save(
            "https://www.drcmart.com/fr/products/tecno-spark-40-8gb-256gb",
            expected_query="tecno spark 40",
            allowed_hosts=["drcmart.com"],
        )

        self.assertIsNone(listing)
        self.assertIn("introuvable", error.lower())

    @patch("tracker.services.extract_with_llm")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_unstructured_site_pages_before_llm(self, mock_fetch, mock_extract):
        from tracker.services import process_url_and_save

        mock_fetch.return_value = "<html><body><div class='layout'><header>Bienvenue</header><p>Contenu générique sans produit.</p></div></body></html>"

        listing, error = process_url_and_save(
            "https://www.example.com/product/abc",
            expected_query="smartphone",
            allowed_hosts=["example.com"],
        )

        self.assertIsNone(listing)
        self.assertIn("structure", error.lower())
        mock_extract.assert_not_called()

    @patch("tracker.services.extract_with_llm")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_generic_landing_page_even_with_price_words(self, mock_fetch, mock_extract):
        from tracker.services import process_url_and_save

        mock_fetch.return_value = """
        <html>
          <head><title>Accueil</title></head>
          <body>
            <header>Bienvenue sur notre boutique</header>
            <h1>Smartphone</h1>
            <p>Nous avons des offres et des prix sur demande.</p>
            <div>Découvrez nos promotions</div>
          </body>
        </html>
        """

        listing, error = process_url_and_save(
            "https://www.example.com/landing/smartphone-promo",
            expected_query="smartphone",
            allowed_hosts=["example.com"],
        )

        self.assertIsNone(listing)
        self.assertIn("structure", error.lower())
        mock_extract.assert_not_called()

    @unittest.skipUnless(
        os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"),
        "AWS Bedrock credentials not configured",
    )
    def test_bedrock_model_is_actually_callable(self):
        from tracker.services import get_llm_config

        import boto3

        config = get_llm_config()
        model_id = config["default_model"]
       
        client = boto3.client(
            "bedrock-runtime",
            region_name=config["region"],
            aws_access_key_id=config["access_key_id"],
            aws_secret_access_key=config["secret_access_key"],
            aws_session_token=config["session_token"] or None,
        )

        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Réponds en une phrase: Bedrock fonctionne-t-il ?"}],
                }
            ],
            inferenceConfig={"temperature": 0.1, "maxTokens": 20},
        )

        content = response["output"]["message"]["content"]
        self.assertTrue(content)
        self.assertIn("Bedrock", "".join(block.get("text", "") for block in content))


class SearchResultDisplayTests(TestCase):
    @patch("tracker.views.search_and_scrape_product")
    def test_scrape_view_renders_listings_for_each_result(self, mock_search):
        retailer = Retailer.objects.create(name="Test Shop", base_url="https://example.com")
        product = Product.objects.create(name="Produit test", sku_or_ean="ABC123")
        mock_search.return_value = (
            [
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer,
                    url="https://example.com/produit",
                    price="99.99",
                    currency="EUR",
                    in_stock=False,
                )
            ],
            [],
        )

        response = self.client.post(
            reverse("scrape_view"),
            {
                "site": "",
                "query": "Produit test",
                "model_name": "qwen2.5-coder:7b",
            },
        )

        self.assertContains(response, "Produit test")
        self.assertContains(response, "Test Shop")
        self.assertContains(response, "Rupture")
        self.assertContains(response, "https://example.com/produit")

    @patch("tracker.views.search_and_scrape_product")
    def test_scrape_view_marks_best_price(self, mock_search):
        retailer_a = Retailer.objects.create(name="Shop A", base_url="https://shop-a.example")
        retailer_b = Retailer.objects.create(name="Shop B", base_url="https://shop-b.example")
        product = Product.objects.create(name="Produit test", sku_or_ean="XYZ789")
        mock_search.return_value = (
            [
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer_b,
                    url="https://shop-b.example/produit",
                    price="199.99",
                    currency="EUR",
                    in_stock=True,
                ),
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer_a,
                    url="https://shop-a.example/produit",
                    price="99.99",
                    currency="EUR",
                    in_stock=True,
                ),
            ],
            [],
        )

        response = self.client.post(
            reverse("scrape_view"),
            {
                "site": "",
                "query": "Produit test",
                "model_name": "qwen2.5-coder:7b",
            },
        )

        self.assertContains(response, "Meilleur prix")
        self.assertContains(response, "99.99 EUR")

    @patch("tracker.views.search_and_scrape_product")
    def test_scrape_view_prefers_in_stock_offer_over_cheaper_out_of_stock(self, mock_search):
        retailer_a = Retailer.objects.create(name="Shop A", base_url="https://shop-a.example")
        retailer_b = Retailer.objects.create(name="Shop B", base_url="https://shop-b.example")
        product = Product.objects.create(name="Produit stock test", sku_or_ean="XYZ790")
        mock_search.return_value = (
            [
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer_a,
                    url="https://shop-a.example/produit",
                    price="89.99",
                    currency="EUR",
                    in_stock=False,
                ),
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer_b,
                    url="https://shop-b.example/produit",
                    price="95.00",
                    currency="EUR",
                    in_stock=True,
                ),
            ],
            [],
        )

        response = self.client.post(
            reverse("scrape_view"),
            {
                "site": "",
                "query": "Produit stock test",
                "model_name": "qwen2.5-coder:7b",
            },
        )

        self.assertContains(response, "95.00 EUR")
        self.assertContains(response, "En stock")

    @patch("tracker.views.search_and_scrape_product")
    def test_scrape_view_hides_error_banner_when_valid_results_exist(self, mock_search):
        retailer = Retailer.objects.create(name="Shop Valid", base_url="https://shop-valid.example")
        product = Product.objects.create(name="Produit valide", sku_or_ean="VAL-001")
        mock_search.return_value = (
            [
                PriceListing.objects.create(
                    product=product,
                    retailer=retailer,
                    url="https://shop-valid.example/produit",
                    price="59.99",
                    currency="EUR",
                    in_stock=True,
                )
            ],
            ["https://autre.example/produit: Données extraites invalides ou page non exploitable."],
        )

        response = self.client.post(
            reverse("scrape_view"),
            {
                "site": "",
                "query": "Produit valide",
                "model_name": "qwen2.5-coder:7b",
            },
        )

        self.assertContains(response, "Produit valide")
        self.assertNotContains(response, "Aucun résultat exploitable")

    @patch("tracker.services.time.sleep")
    @patch("tracker.services.requests.Session")
    def test_fetch_and_clean_html_retries_with_backoff_on_transient_errors(self, mock_session_cls, mock_sleep):
        mock_session = mock_session_cls.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body><script>bad()</script><h1>Produit test</h1></body></html>"
        mock_session.get.side_effect = [requests.HTTPError("HTTP 429"), mock_response]

        result = fetch_and_clean_html("https://example.com/produit")

        self.assertIn("Produit test", result)
        self.assertEqual(mock_session.get.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("tracker.services.requests.Session")
    def test_fetch_and_clean_html_replaces_invalid_bytes_in_remote_html(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.encoding = "utf-8"
        mock_response.content = b"<html><body><h1>Produit \x80\xff test</h1><p>299,99 EUR</p></body></html>"
        mock_session.get.return_value = mock_response

        result = fetch_and_clean_html("https://example.com/produit")

        self.assertIn("Produit", result)
        self.assertIn("299,99", result)
        self.assertIsNotNone(result)

    @patch("tracker.services.ollama.chat")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_falls_back_to_html_parsing_when_ollama_fails(self, mock_fetch, mock_ollama):
        mock_fetch.return_value = "<html><body><h1>Smartphone X</h1><div>299,99 €</div><p>En stock</p></body></html>"
        mock_ollama.side_effect = Exception("ollama unavailable")

        listing, error = process_url_and_save("https://example.com/produit")

        self.assertIsNotNone(listing)
        self.assertIsNone(error)
        self.assertEqual(listing.product.name, "Smartphone X")
        self.assertEqual(float(listing.price), 299.99)

    @patch("tracker.services.extract_with_ollama")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_unknown_or_zero_price_results(self, mock_fetch, mock_extract):
        mock_fetch.return_value = "<html><body>ok</body></html>"
        mock_extract.return_value = ExtractedProductData(
            product_name="Unknown",
            price=0.0,
            currency="Unknown",
            in_stock=False,
            sku_or_ean=None,
        )

        listing, error = process_url_and_save("https://mobile-rdc.com/produit")

        self.assertIsNone(listing)
        self.assertIn("invalides", error.lower())

    @patch("tracker.services.extract_with_ollama")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_unrealistic_prices(self, mock_fetch, mock_extract):
        mock_fetch.return_value = "<html><body>ok</body></html>"
        mock_extract.return_value = ExtractedProductData(
            product_name="Téléphone test",
            price=150000.0,
            currency="USD",
            in_stock=True,
            sku_or_ean="TEL-999",
        )

        listing, error = process_url_and_save("https://www.example.com/produit")

        self.assertIsNone(listing)
        self.assertIn("invalides", error.lower())

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_deduplicates_and_skips_homepage_results(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://example.com/"},
            {"href": "https://example.com/produit"},
            {"href": "https://example.com/produit"},
            {"href": "https://example.com/other"},
        ]
        mock_process_url.return_value = (SimpleNamespace(price=100), None)

        results, errors = search_and_scrape_product("iPhone 15", max_results=10)

        self.assertIsInstance(results, list)
        self.assertEqual(mock_process_url.call_count, 2)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://example.com/produit")
        self.assertEqual(mock_process_url.call_args_list[1].args[0], "https://example.com/other")
        self.assertEqual(errors, [])

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_prioritizes_local_drc_sources_before_global_web(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.side_effect = [
            [{"href": "https://drcmart.com/produit/iphone-15"}],
            [{"href": "https://shop.example/iphone-15"}],
        ]
        mock_process_url.return_value = (
            SimpleNamespace(price=120.00, in_stock=True),
            None,
        )

        results, errors = search_and_scrape_product("iPhone 15", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_ddgs.return_value.__enter__.return_value.text.call_count, 1)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://drcmart.com/produit/iphone-15")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_falls_back_to_global_search_when_rdc_has_no_results(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.side_effect = [
            [],
            [{"href": "https://shop.example/iphone-15"}],
        ]
        mock_process_url.return_value = (
            SimpleNamespace(price=120.00, in_stock=True),
            None,
        )

        results, errors = search_and_scrape_product("iPhone 15", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_ddgs.return_value.__enter__.return_value.text.call_count, 2)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://shop.example/iphone-15")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_stays_limited_to_selected_site(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = []

        results, errors = search_and_scrape_product("iPhone 15", site_filter="example.com", max_results=5)

        self.assertEqual(results, [])
        self.assertIn("Aucune page exploitable", errors[0])
        self.assertEqual(mock_process_url.call_count, 0)
        self.assertEqual(mock_ddgs.return_value.__enter__.return_value.text.call_count, 1)

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_does_not_fallback_when_selected_site_results_are_invalid(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [{"href": "https://example.com/produit"}]
        mock_process_url.return_value = (None, "Données extraites invalides ou page non exploitable.")

        results, errors = search_and_scrape_product("iPhone 15", site_filter="example.com", max_results=5)

        self.assertEqual(results, [])
        self.assertIn("Données extraites invalides", errors[0])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://example.com/produit")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_supports_multiple_site_filters(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.side_effect = [
            [{"href": "https://www.example.com/produit"}],
            [{"href": "https://shop.net/produit"}],
        ]
        mock_process_url.side_effect = [
            (SimpleNamespace(price=150), None),
            (SimpleNamespace(price=120), None),
        ]

        results, errors = search_and_scrape_product("iPhone 15", site_filter="example.com, shop.net", max_results=5)

        self.assertEqual(len(results), 2)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 2)
        self.assertEqual(mock_ddgs.return_value.__enter__.return_value.text.call_count, 2)

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_skips_comparator_pages(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://comparateur-prix.example/iphone-15"},
            {"href": "https://shop.example/iphone-15"},
        ]
        mock_process_url.return_value = (
            SimpleNamespace(price=120.00, in_stock=True),
            None,
        )

        results, errors = search_and_scrape_product("iPhone 15", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://shop.example/iphone-15")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_skips_low_quality_sources(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://forum.example/topic/iphone-15"},
            {"href": "https://shop.example/iphone-15"},
        ]
        mock_process_url.return_value = (
            SimpleNamespace(price=120.00, in_stock=True),
            None,
        )

        results, errors = search_and_scrape_product("iPhone 15", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://shop.example/iphone-15")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_keeps_social_commerce_product_pages(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://www.tiktok.com/@shop/video/12345"},
            {"href": "https://www.instagram.com/reel/abcde/"},
            {"href": "https://www.facebook.com/marketplace/item/12345"},
        ]
        mock_process_url.return_value = (
            SimpleNamespace(price=120.00, in_stock=True),
            None,
        )

        results, errors = search_and_scrape_product("iPhone 15", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(mock_process_url.call_count, 1)
        self.assertEqual(mock_process_url.call_args_list[0].args[0], "https://www.tiktok.com/@shop/video/12345")

    @patch("tracker.services.process_url_and_save")
    @patch("tracker.services.DDGS")
    def test_search_and_scrape_product_deduplicates_same_offer_across_sources(self, mock_ddgs, mock_process_url):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = [
            {"href": "https://dup.example/produit"},
            {"href": "https://dup.example/produit?ref=alt"},
        ]
        mock_process_url.side_effect = [
            (
                SimpleNamespace(
                    product_id=1,
                    retailer_id=1,
                    url="https://dup.example/produit",
                    price=120.00,
                    in_stock=True,
                ),
                None,
            ),
            (
                SimpleNamespace(
                    product_id=1,
                    retailer_id=1,
                    url="https://dup.example/produit",
                    price=115.00,
                    in_stock=True,
                ),
                None,
            ),
        ]

        results, errors = search_and_scrape_product("Produit doublé", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(float(results[0].price), 115.00)

    def test_duplicate_price_listing_is_rejected(self):
        retailer = Retailer.objects.create(name="Duplicate Shop", base_url="https://duplicate.example")
        product = Product.objects.create(name="Produit dupliqué", sku_or_ean="DUP-001")
        PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url="https://duplicate.example/produit",
            price="99.99",
            currency="EUR",
            in_stock=True,
        )

        with self.assertRaises(ValidationError):
            PriceListing.objects.create(
                product=product,
                retailer=retailer,
                url="https://duplicate.example/produit",
                price="129.99",
                currency="EUR",
                in_stock=True,
            )

    def test_cleanup_stale_listings_removes_old_entries(self):
        retailer = Retailer.objects.create(name="Old Shop", base_url="https://old.example")
        product = Product.objects.create(name="Produit historique", sku_or_ean="OLD-001")
        PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url="https://old.example/produit",
            price="150.00",
            currency="EUR",
            in_stock=True,
        )

        listing = PriceListing.objects.get(product=product, retailer=retailer)
        PriceListing.objects.filter(pk=listing.pk).update(
            scraped_at=timezone.now() - timezone.timedelta(days=45)
        )

        deleted = cleanup_stale_listings(days=30)

        self.assertEqual(deleted, 1)
        self.assertFalse(PriceListing.objects.filter(pk=listing.pk).exists())

    def test_process_url_and_save_rejects_homepage_urls(self):
        listing, error = process_url_and_save("https://example.com/")

        self.assertIsNone(listing)
        self.assertIn("accueil", error.lower())

    @patch("tracker.services.extract_with_ollama")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_rejects_unrelated_product_name(self, mock_fetch, mock_extract):
        mock_fetch.return_value = "<html><body>ok</body></html>"
        mock_extract.return_value = ExtractedProductData(
            product_name="Casque Bluetooth",
            price=79.9,
            currency="EUR",
            in_stock=True,
            sku_or_ean="C-101",
        )

        listing, error = process_url_and_save(
            "https://www.example.com/produit",
            expected_query="iPhone 15",
        )

        self.assertIsNone(listing)
        self.assertIn("non pertinent", error.lower())

    @patch("tracker.services.extract_with_ollama")
    @patch("tracker.services.fetch_and_clean_html")
    def test_process_url_and_save_defaults_for_missing_extraction_values(self, mock_fetch, mock_extract):
        mock_fetch.return_value = "<html><body>ok</body></html>"
        mock_extract.return_value = ExtractedProductData(
            product_name="",
            price=12.5,
            currency="",
            in_stock=False,
            sku_or_ean=None,
        )

        listing, error = process_url_and_save("https://www.example.com/produit")

        self.assertIsNone(listing)
        self.assertIn("invalides", error.lower())
