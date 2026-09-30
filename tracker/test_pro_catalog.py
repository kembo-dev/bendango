from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.catalog import find_fresh_cached_listings
from tracker.models import BusinessAccountRequest, BusinessProfile, PriceListing


class ProCatalogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='catalogowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=self.user,
            business_name='Catalog Business',
            business_type='E-commerce',
            website='https://catalog-business.example',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=self.user)
        self.profile.market_code = 'CD'
        self.profile.country = 'RDC'
        self.profile.save(update_fields=['market_code', 'country'])
        self.client.login(username='catalogowner', password='StrongPass123!')

    def _payload(self, **overrides):
        data = {
            'name': 'Samsung Galaxy A56 5G 8GB 256GB',
            'brand': 'Samsung',
            'model': 'Galaxy A56 5G',
            'sku_or_ean': 'A56-8-256',
            'category': 'Smartphones',
            'image_url': 'https://catalog-business.example/a56.jpg',
            'price': '325.00',
            'currency': 'USD',
            'in_stock': 'on',
            'sale_url': 'https://catalog-business.example/products/a56-8-256',
        }
        data.update(overrides)
        return data

    def test_verified_business_can_add_catalog_product(self):
        response = self.client.post(reverse('pro_product_create'), self._payload())

        self.assertRedirects(response, reverse('pro_products'))
        listing = PriceListing.objects.get(retailer=self.profile.ensure_retailer())
        self.assertEqual(listing.product.name, 'Samsung Galaxy A56 5G 8GB 256GB')
        self.assertEqual(str(listing.price), '325.00')
        self.assertEqual(listing.currency, 'USD')
        self.assertTrue(listing.in_stock)
        self.assertTrue(listing.is_active)

    def test_business_can_edit_and_toggle_own_listing(self):
        self.client.post(reverse('pro_product_create'), self._payload())
        listing = PriceListing.objects.get(retailer=self.profile.ensure_retailer())

        response = self.client.post(
            reverse('pro_product_edit', args=[listing.pk]),
            self._payload(price='299.99', in_stock=''),
        )
        self.assertRedirects(response, reverse('pro_products'))
        listing.refresh_from_db()
        self.assertEqual(str(listing.price), '299.99')
        self.assertFalse(listing.in_stock)

        response = self.client.post(reverse('pro_product_toggle', args=[listing.pk]))
        self.assertRedirects(response, reverse('pro_products'))
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)

    def test_business_cannot_edit_another_business_listing(self):
        other_user = User.objects.create_user(
            username='othercatalog',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=other_user,
            business_name='Other Catalog',
            website='https://other-catalog.example',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        other_profile = BusinessProfile.objects.get(user=other_user)
        other_retailer = other_profile.ensure_retailer()

        self.client.post(reverse('pro_product_create'), self._payload())
        own_listing = PriceListing.objects.get(retailer=self.profile.ensure_retailer())
        own_listing.retailer = other_retailer
        own_listing.save(update_fields=['retailer'])

        response = self.client.get(reverse('pro_product_edit', args=[own_listing.pk]))
        self.assertEqual(response.status_code, 404)

    def test_verified_pro_offer_is_visible_in_matching_market_cache(self):
        self.client.post(reverse('pro_product_create'), self._payload())

        cd_results = find_fresh_cached_listings(
            'Samsung Galaxy A56 5G 8GB 256GB',
            market_code='CD',
            minimum_confidence=0.7,
        )
        fr_results = find_fresh_cached_listings(
            'Samsung Galaxy A56 5G 8GB 256GB',
            market_code='FR',
            minimum_confidence=0.7,
        )
        global_results = find_fresh_cached_listings(
            'Samsung Galaxy A56 5G 8GB 256GB',
            market_code='GLOBAL',
            minimum_confidence=0.7,
        )

        self.assertEqual(len(cd_results), 1)
        self.assertEqual(fr_results, [])
        self.assertEqual(len(global_results), 1)

    def test_unapproved_user_cannot_open_catalog(self):
        pending = User.objects.create_user(
            username='pendingcatalog',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=pending,
            business_name='Pending Catalog',
            status=BusinessAccountRequest.STATUS_PENDING,
        )
        self.client.logout()
        self.client.login(username='pendingcatalog', password='StrongPass123!')

        response = self.client.get(reverse('pro_products'))
        self.assertRedirects(response, reverse('business_account_request'))
