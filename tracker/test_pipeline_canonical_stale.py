from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from tracker.models import PriceListing, Product, Retailer
from tracker.services import cleanup_stale_listings, process_url_and_save


class CanonicalPipelineTests(TestCase):
    def test_process_url_reuses_canonical_product(self):
        canonical = Product.objects.create(name="Apple iPhone 16e 128GB")
        html = """
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"Apple iPhone 16e 128 GB",
         "offers":{"@type":"Offer","price":"1000","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
        </script></head><body><h1>Apple iPhone 16e 128 GB</h1><p>1000 USD</p></body></html>
        """
        with patch("tracker.services.fetch_and_clean_html", return_value=html):
            listing, error = process_url_and_save(
                "https://shop.example.com/products/iphone-16e",
                expected_query="Apple iPhone 16e 128GB",
            )
        self.assertIsNone(error)
        self.assertIsNotNone(listing)
        self.assertEqual(listing.product_id, canonical.id)
        self.assertEqual(Product.objects.count(), 1)

    def test_mismatched_product_is_rejected_even_on_allowed_host(self):
        html = """
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"Samsung Galaxy S25 Ultra",
         "offers":{"@type":"Offer","price":"1200","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
        </script></head><body><h1>Samsung Galaxy S25 Ultra</h1><p>1200 USD</p></body></html>
        """
        with patch("tracker.services.fetch_and_clean_html", return_value=html):
            listing, error = process_url_and_save(
                "https://shop.example.com/products/galaxy-s25-ultra",
                expected_query="iPhone 16e",
                allowed_hosts=["shop.example.com"],
            )
        self.assertIsNone(listing)
        self.assertIn("Produit non pertinent", error)


class StaleListingTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name="Test Phone")
        self.retailer = Retailer.objects.create(name="Example", base_url="https://example.com")
        self.listing = PriceListing.objects.create(
            product=self.product,
            retailer=self.retailer,
            url="https://example.com/products/test-phone",
            price="100.00",
            currency="USD",
            confidence_score="0.9000",
            match_score="1.0000",
        )

    def test_cleanup_deactivates_instead_of_deleting(self):
        PriceListing.objects.filter(pk=self.listing.pk).update(
            scraped_at=timezone.now() - timezone.timedelta(days=60)
        )
        count = cleanup_stale_listings(days=30)
        self.assertEqual(count, 1)
        self.listing.refresh_from_db()
        self.assertFalse(self.listing.is_active)
        self.assertTrue(PriceListing.objects.filter(pk=self.listing.pk).exists())

    def test_not_found_page_deactivates_existing_listing(self):
        with patch("tracker.services.fetch_and_clean_html", return_value="<html><body>404 page introuvable</body></html>"):
            listing, error = process_url_and_save(
                self.listing.url,
                expected_query="Test Phone",
            )
        self.assertIsNone(listing)
        self.assertIn("Page introuvable", error)
        self.listing.refresh_from_db()
        self.assertFalse(self.listing.is_active)
