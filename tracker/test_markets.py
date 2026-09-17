from django.test import TestCase

from tracker.forms import SearchOrScrapeForm
from tracker.job_queue import _local_market_bonus
from tracker.markets import (
    get_market,
    is_global_market,
    market_search_label,
    normalize_market_code,
)


class SearchMarketTests(TestCase):
    def test_market_profiles_resolve_country_and_currency(self):
        france = get_market('FR')
        self.assertEqual(france.country, 'France')
        self.assertEqual(france.currency, 'EUR')
        self.assertEqual(normalize_market_code('fr'), 'FR')

    def test_unknown_market_falls_back_to_drc(self):
        self.assertEqual(normalize_market_code('XX'), 'CD')

    def test_global_market_has_no_geographic_constraints(self):
        global_market = get_market('GLOBAL')
        self.assertTrue(is_global_market('global'))
        self.assertEqual(global_market.country, '')
        self.assertEqual(global_market.currency, '')
        self.assertEqual(global_market.tlds, ())
        self.assertEqual(global_market.hints, ())
        self.assertEqual(global_market.cities, ())
        self.assertEqual(market_search_label('GLOBAL'), '')

    def test_local_bonus_follows_selected_market(self):
        self.assertGreater(_local_market_bonus('https://boutique.fr/produit/test', 'FR'), 0)
        self.assertEqual(_local_market_bonus('https://boutique.fr/produit/test', 'CD'), 0)
        self.assertGreater(_local_market_bonus('https://boutique.cd/produit/test', 'CD'), 0)
        self.assertEqual(_local_market_bonus('https://boutique.cd/produit/test', 'FR'), 0)
        self.assertEqual(_local_market_bonus('https://boutique.fr/produit/test', 'GLOBAL'), 0)
        self.assertEqual(_local_market_bonus('https://boutique.cd/produit/test', 'GLOBAL'), 0)

    def test_search_form_accepts_non_drc_market(self):
        form = SearchOrScrapeForm(data={
            'site': '',
            'query': 'PlayStation 5 Slim',
            'market': 'FR',
            'model_name': 'test-model',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['market'], 'FR')

    def test_search_form_accepts_global_web_market(self):
        form = SearchOrScrapeForm(data={
            'site': '',
            'query': 'PlayStation 5 Slim',
            'market': 'GLOBAL',
            'model_name': 'test-model',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['market'], 'GLOBAL')
