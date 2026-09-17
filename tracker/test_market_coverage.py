from types import SimpleNamespace

from django.test import SimpleTestCase

from tracker.market_coverage import distinct_merchant_count, merchant_key


class MarketCoverageMerchantIdentityTests(SimpleTestCase):
    @staticmethod
    def listing(base_url: str, url: str = ""):
        retailer = SimpleNamespace(id=None, base_url=base_url)
        return SimpleNamespace(retailer=retailer, url=url or base_url)

    def test_country_and_language_storefronts_count_as_one_merchant(self):
        be = self.listing("https://fr.knivesandtools.be")
        fr = self.listing("https://www.knivesandtools.fr")

        self.assertEqual(merchant_key(be), "merchant:knivesandtools")
        self.assertEqual(merchant_key(fr), "merchant:knivesandtools")
        self.assertEqual(distinct_merchant_count([be, fr]), 1)

    def test_different_storefront_brands_remain_distinct(self):
        knives = self.listing("https://www.knivesandtools.fr")
        kinshasa = self.listing("https://store-kinshasa.online")

        self.assertEqual(distinct_merchant_count([knives, kinshasa]), 2)

    def test_common_country_suffix_uses_storefront_brand(self):
        amazon_uk = self.listing("https://www.amazon.co.uk")
        amazon_fr = self.listing("https://www.amazon.fr")

        self.assertEqual(merchant_key(amazon_uk), "merchant:amazon")
        self.assertEqual(merchant_key(amazon_fr), "merchant:amazon")
        self.assertEqual(distinct_merchant_count([amazon_uk, amazon_fr]), 1)
