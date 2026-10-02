from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, PriceListing, Product, Retailer
from tracker.unified_search import build_unified_results


class UnifiedSearchTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='unifiedowner', password='StrongPass123!')
        BusinessAccountRequest.objects.create(
            user=user,
            business_name='Unified Store',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=user)

    def test_merges_bendango_web_and_social_with_visible_origins(self):
        offer = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Samsung Galaxy A56 5G 8GB 256GB',
            price=Decimal('325.00'),
            currency='USD',
            market_code='CD',
        )
        offer.search_score = 0.96

        retailer = Retailer.objects.create(
            name='External Shop',
            base_url='https://external.example',
            trust_score=Decimal('0.90'),
            trust_level='verified',
            is_active=True,
        )
        product = Product.objects.create(name='Samsung Galaxy A56 5G 8GB 256GB')
        listing = PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url='https://external.example/a56',
            price=Decimal('330.00'),
            currency='USD',
            confidence_score=Decimal('0.95'),
            match_score=Decimal('0.95'),
            in_stock=True,
            is_active=True,
        )
        listing.offer_quality_score = 0.91

        social = [{
            'url': 'https://facebook.com/example/a56',
            'platform': 'Facebook',
            'title': 'Samsung Galaxy A56 5G 8GB 256GB disponible',
            'snippet': 'Vente à Kinshasa',
            'relevance_score': 0.88,
            'source_type': 'Réseau social',
        }]

        results = build_unified_results([offer], [listing], social)

        self.assertEqual([item.source_kind for item in results], ['bendango', 'web', 'social'])
        self.assertEqual(results[0].source_label, 'Bendango')
        self.assertEqual(results[1].source_label, 'Web marchand')
        self.assertEqual(results[2].source_label, 'Réseau social')
        self.assertTrue(results[1].verified)

    def test_does_not_duplicate_price_listing_already_bridged_to_offer(self):
        retailer = self.profile.ensure_retailer()
        product = Product.objects.create(name='Aquafina 500ml')
        listing = PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url='https://example.com/aquafina',
            price=Decimal('1.50'),
            currency='USD',
            confidence_score=Decimal('1.00'),
            match_score=Decimal('1.00'),
            in_stock=True,
            is_active=True,
        )
        offer = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Aquafina 500ml',
            price=Decimal('1.50'),
            currency='USD',
            product=product,
            price_listing=listing,
        )

        results = build_unified_results([offer], [listing], [])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_kind, 'bendango')

    def test_social_results_never_become_verified_offers(self):
        results = build_unified_results([], [], [{
            'url': 'https://tiktok.com/@seller/video/1',
            'platform': 'TikTok',
            'title': 'Aquafina à vendre',
            'snippet': 'Contact vendeur',
            'relevance_score': 0.73,
            'source_type': 'Réseau social',
        }])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_kind, 'social')
        self.assertFalse(results[0].verified)
        self.assertEqual(results[0].badge, 'Réseau social')

    def test_keeps_multiple_web_merchants_for_price_comparison(self):
        product = Product.objects.create(name='iPhone 16 Pro 256GB')
        listings = []
        for index, price in enumerate(('1000.00', '1020.00'), start=1):
            retailer = Retailer.objects.create(
                name=f'Shop {index}',
                base_url=f'https://shop{index}.example',
                trust_score=Decimal('0.80'),
                trust_level='trusted',
                is_active=True,
            )
            listing = PriceListing.objects.create(
                product=product,
                retailer=retailer,
                url=f'https://shop{index}.example/iphone',
                price=Decimal(price),
                currency='USD',
                confidence_score=Decimal('0.90'),
                match_score=Decimal('0.95'),
                in_stock=True,
                is_active=True,
            )
            listing.offer_quality_score = 0.85
            listings.append(listing)

        results = build_unified_results([], listings, [])

        self.assertEqual(len(results), 2)
        self.assertEqual({item.provider for item in results}, {'Shop 1', 'Shop 2'})
