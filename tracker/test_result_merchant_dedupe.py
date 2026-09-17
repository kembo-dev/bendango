from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from tracker.models import PriceListing, Product, Retailer, ScrapeJob, SearchRun
from tracker.views import _best_listing_per_merchant, _run_state


class ResultMerchantDeduplicationTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name="Produit test")

    def _listing(self, retailer_name, base_url, url, price):
        retailer = Retailer.objects.create(name=retailer_name, base_url=base_url)
        return PriceListing.objects.create(
            product=self.product,
            retailer=retailer,
            url=url,
            price=Decimal(price),
            currency="USD",
            in_stock=True,
        )

    def test_best_listing_per_merchant_keeps_first_ranked_offer(self):
        preferred = self._listing(
            "KnivesAndTools FR",
            "https://www.knivesandtools.fr",
            "https://www.knivesandtools.fr/fr/ct/tournevis.htm",
            "10.00",
        )
        duplicate_storefront = self._listing(
            "KnivesAndTools BE",
            "https://fr.knivesandtools.be",
            "https://fr.knivesandtools.be/fr/ct/tournevis.htm",
            "12.00",
        )
        other = self._listing(
            "Kinshasa Store",
            "https://store-kinshasa.online",
            "https://store-kinshasa.online/products/tournevis",
            "15.00",
        )

        result = _best_listing_per_merchant([preferred, duplicate_storefront, other])

        self.assertEqual(result, [preferred, other])

    def test_run_state_uses_normalized_merchant_identity(self):
        first = self._listing(
            "KnivesAndTools FR",
            "https://www.knivesandtools.fr",
            "https://www.knivesandtools.fr/fr/ct/tournevis.htm",
            "10.00",
        )
        second = self._listing(
            "KnivesAndTools BE",
            "https://fr.knivesandtools.be",
            "https://fr.knivesandtools.be/fr/ct/tournevis.htm",
            "12.00",
        )
        third = self._listing(
            "Kinshasa Store",
            "https://store-kinshasa.online",
            "https://store-kinshasa.online/products/tournevis",
            "15.00",
        )
        run = SearchRun.objects.create(
            query="tournevis",
            site_filter="all",
            target_merchants=3,
            status=SearchRun.STATUS_RUNNING,
        )
        for listing in (first, second, third):
            ScrapeJob.objects.create(
                search_run=run,
                url=listing.url,
                query=run.query,
                status=ScrapeJob.STATUS_SUCCESS,
                listing=listing,
                finished_at=timezone.now(),
            )

        state = _run_state(run)

        self.assertEqual(state["offers"], 3)
        self.assertEqual(state["merchants"], 2)
        self.assertFalse(state["coverage_reached"])
        self.assertEqual(state["progress"], 67)
