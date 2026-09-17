from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tracker.catalog import find_fresh_cached_listings
from tracker.models import PriceListing, Product, Retailer, ScrapeJob, SearchRun


class AsyncSearchRunCacheTests(TestCase):
    def setUp(self):
        self.query = "Tecno Spark 40 8GB 256GB"
        self.product = Product.objects.create(
            name=self.query,
            sku_or_ean="TEC-SPARK40-256",
        )

        self.listings = []
        merchants = [
            ("Soumari.com", "https://www.soumari.com", "https://www.soumari.com/produit/tecno-spark-40-256-go-ram-8-go/", "149.00"),
            ("Mobile-rdc.com", "https://mobile-rdc.com", "https://mobile-rdc.com/produit/tecno-spark-40-256-gb/", "155.00"),
            ("Ayshamart.com", "https://ayshamart.com", "https://ayshamart.com/product/tecno-spark-40-8gb-256gb/", "159.00"),
        ]
        for name, base_url, url, price in merchants:
            retailer = Retailer.objects.create(name=name, base_url=base_url)
            listing = PriceListing.objects.create(
                product=self.product,
                retailer=retailer,
                url=url,
                price=Decimal(price),
                currency="USD",
                in_stock=True,
                confidence_score=Decimal("0.95"),
                extraction_source="jsonld",
            )
            self.listings.append(listing)

    def _validate_listings_for_market(self, market_code="CD"):
        previous_run = SearchRun.objects.create(
            query=self.query,
            site_filter="all",
            target_merchants=3,
            model_name="test-model",
            market_code=market_code,
            market_currency="CDF" if market_code == "CD" else "EUR",
            status=SearchRun.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )
        for listing in self.listings:
            ScrapeJob.objects.create(
                search_run=previous_run,
                query=self.query,
                url=listing.url,
                model_name="test-model",
                status=ScrapeJob.STATUS_SUCCESS,
                attempts=1,
                listing=listing,
                fetch_status="processed",
                finished_at=timezone.now(),
            )
        return previous_run

    @patch("tracker.management.commands.run_search_worker.discover_social_sources", return_value=[])
    def test_fresh_cache_completes_async_run_with_success_jobs(self, _mock_social):
        self._validate_listings_for_market("CD")
        search_run = SearchRun.objects.create(
            query=self.query,
            site_filter="all",
            target_merchants=3,
            model_name="test-model",
            market_code="CD",
            market_currency="CDF",
            status=SearchRun.STATUS_QUEUED,
        )

        call_command("run_search_worker", "--once")

        search_run.refresh_from_db()
        self.assertEqual(search_run.status, SearchRun.STATUS_COMPLETED)
        self.assertIsNotNone(search_run.completed_at)
        self.assertEqual(search_run.discovery_error, "")

        jobs = list(search_run.jobs.order_by("id"))
        self.assertEqual(len(jobs), 3)
        self.assertTrue(all(job.status == ScrapeJob.STATUS_SUCCESS for job in jobs))
        self.assertTrue(all(job.from_cache for job in jobs))
        self.assertTrue(all(job.fetch_status == "cache" for job in jobs))
        self.assertEqual(
            {job.listing_id for job in jobs},
            {listing.id for listing in self.listings},
        )

    def test_cache_from_another_market_is_not_reused(self):
        self._validate_listings_for_market("FR")

        self.assertEqual(
            find_fresh_cached_listings(self.query, market_code="CD"),
            [],
        )
        self.assertEqual(
            {listing.id for listing in find_fresh_cached_listings(self.query, market_code="FR")},
            {listing.id for listing in self.listings},
        )
