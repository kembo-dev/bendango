from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from tracker.currency import get_usd_rates, normalize_to_usd


class CurrencySafetyTests(SimpleTestCase):
    def test_non_finite_prices_are_rejected_without_decimal_exception(self):
        self.assertIsNone(normalize_to_usd(float('nan'), 'USD'))
        self.assertIsNone(normalize_to_usd(float('inf'), 'USD'))
        self.assertIsNone(normalize_to_usd(Decimal('NaN'), 'EUR'))

    @override_settings(BENDANGO_USD_RATES={'EUR': 'NaN', 'CDF': 'Infinity'})
    def test_non_finite_configured_rates_are_ignored(self):
        rates = get_usd_rates()
        self.assertEqual(rates['EUR'], Decimal('0.86'))
        self.assertEqual(rates['CDF'], Decimal('2850'))
