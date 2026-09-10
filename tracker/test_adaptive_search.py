from collections import Counter
from unittest.mock import patch

from django.test import TestCase, override_settings

from tracker.adaptive_search import build_adaptive_search_terms, build_recovery_terms, is_broad_product_query, recent_failure_profile
from tracker.models import SearchDiagnostic


class AdaptiveSearchPlanningTests(TestCase):
    def test_product_mismatch_adds_exact_model_queries(self):
        terms = build_adaptive_search_terms(
            "iPhone 16e 256GB",
            country="RDC",
            diagnostics=Counter({"product_mismatch": 4}),
        )
        self.assertTrue(any("modèle exact" in term for term in terms))
        self.assertTrue(any('intitle:"iPhone 16e 256GB"' in term for term in terms))

    def test_structure_failures_add_product_page_queries(self):
        terms = build_adaptive_search_terms(
            "Samsung Galaxy S25",
            diagnostics=Counter({"no_product_structure": 3}),
        )
        self.assertTrue(any("fiche produit" in term for term in terms))
        self.assertTrue(any('"en stock"' in term for term in terms))

    def test_fetch_failures_diversify_merchant_intent(self):
        terms = build_adaptive_search_terms(
            "MacBook Air M4",
            country="RDC",
            diagnostics=Counter({"fetch_failed": 2}),
        )
        self.assertIn("MacBook Air M4 revendeur RDC", terms)
        self.assertIn("MacBook Air M4 shop price", terms)

    def test_broad_query_uses_transactional_terms(self):
        terms = build_adaptive_search_terms("guitare", country="RDC", diagnostics=Counter())
        self.assertTrue(is_broad_product_query("guitare"))
        self.assertTrue(any('"guitare"' in term and "acheter" in term for term in terms))
        self.assertTrue(any("ajouter au panier" in term for term in terms))
        self.assertNotIn("guitare prix", terms)

    def test_model_query_is_not_treated_as_broad(self):
        self.assertFalse(is_broad_product_query("iPhone 16e 256GB"))
        terms = build_adaptive_search_terms("iPhone 16e 256GB", diagnostics=Counter())
        self.assertIn("iPhone 16e 256GB prix", terms)

    def test_broad_mismatch_recovery_keeps_shopping_intent(self):
        terms = build_adaptive_search_terms(
            "guitare",
            country="RDC",
            diagnostics=Counter({"product_mismatch": 4}),
        )
        self.assertTrue(any("acheter produit prix" in term for term in terms))
        self.assertFalse(any("modèle exact" in term for term in terms))

    def test_recent_failure_profile_aggregates_diagnostics(self):
        SearchDiagnostic.objects.create(
            query="Pixel 10",
            rejection_reasons={"product_mismatch": 2, "fetch_failed": 1},
            target_merchants=3,
        )
        SearchDiagnostic.objects.create(
            query="Pixel 10",
            rejection_reasons={"product_mismatch": 1},
            target_merchants=3,
        )
        profile = recent_failure_profile("Pixel 10")
        self.assertEqual(profile["product_mismatch"], 3)
        self.assertEqual(profile["fetch_failed"], 1)

    def test_recovery_terms_classify_current_errors(self):
        terms = build_recovery_terms(
            "PlayStation 5 Pro",
            [
                "Produit non pertinent (variant mismatch, score=0.30).",
                "Impossible de récupérer le contenu de la page web.",
            ],
            country="RDC",
        )
        self.assertTrue(any("modèle exact" in term for term in terms))
        self.assertTrue(any("revendeur RDC" in term for term in terms))


class AdaptiveEngineTests(TestCase):
    @override_settings(SCRAPE_QUEUE_SYNC_FALLBACK=True)
    @patch("tracker.adaptive_engine.discover_product_urls", return_value=[])
    @patch("tracker.adaptive_engine.process_url_and_save")
    @patch("tracker.adaptive_engine._collect_search_urls")
    @patch("tracker.adaptive_engine.find_fresh_cached_listings", return_value=[])
    @patch("tracker.adaptive_engine.get_llm_config", return_value={"default_model": "test-model"})
    def test_engine_runs_recovery_pass_after_mismatch(
        self,
        mock_config,
        mock_cache,
        mock_collect,
        mock_process,
        mock_discover,
    ):
        initial_url = "https://wrong.example/item"
        recovery_url = "https://right.example/product"

        def collect(term, max_results):
            if "modèle exact" in term or "référence acheter" in term:
                return [recovery_url]
            return [initial_url]

        mock_collect.side_effect = collect
        mock_process.side_effect = [
            (None, "Produit non pertinent (variant mismatch, score=0.30)."),
            (None, "Produit non pertinent (variant mismatch, score=0.30)."),
        ]

        from tracker.adaptive_engine import search_and_scrape_product

        listings, errors = search_and_scrape_product("iPhone 16e 256GB", max_results=1)
        self.assertEqual(listings, [])
        self.assertTrue(errors)
        searched_terms = [call.args[0] for call in mock_collect.call_args_list]
        self.assertTrue(any("modèle exact" in term or "référence acheter" in term for term in searched_terms))
