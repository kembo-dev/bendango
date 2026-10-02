from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, PriceListing
from tracker.offer_search import find_matching_offers


class OfferPlatformTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='offerowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=self.user,
            business_name='Kin Services',
            business_type='Services',
            phone='+243999111222',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=self.user)
        self.profile.whatsapp = '+243999111222'
        self.profile.city = 'Kinshasa'
        self.profile.market_code = 'CD'
        self.profile.save(update_fields=['whatsapp', 'city', 'market_code'])
        self.client.login(username='offerowner', password='StrongPass123!')

    def _quick_payload(self, **overrides):
        data = {
            'offer_type': 'service',
            'title': 'Coiffure femme premium',
            'price': '25000.00',
            'currency': 'CDF',
            'price_unit': 'service',
            'primary_image_url': 'https://example.com/coiffure.jpg',
            'availability': 'available',
            'whatsapp': '+243999111222',
            'external_url': '',
            'description': 'Coiffure sur rendez-vous à Kinshasa.',
        }
        data.update(overrides)
        return data

    def test_quick_publish_does_not_require_website(self):
        response = self.client.post(reverse('pro_offer_create'), self._quick_payload())

        self.assertRedirects(response, reverse('pro_offers'))
        offer = Offer.objects.get(business=self.profile)
        self.assertEqual(offer.title, 'Coiffure femme premium')
        self.assertEqual(offer.external_url, '')
        self.assertEqual(offer.contact_method, 'whatsapp')
        self.assertEqual(offer.market_code, 'CD')
        self.assertEqual(offer.city, 'Kinshasa')
        self.assertIsNone(offer.price_listing)

    def test_product_offer_with_sale_url_keeps_price_listing_bridge(self):
        response = self.client.post(reverse('pro_offer_create'), self._quick_payload(
            offer_type='product',
            title='Samsung Galaxy A56 5G 8GB 256GB',
            price='325.00',
            currency='USD',
            price_unit='unité',
            external_url='https://example.com/samsung-a56',
        ))

        self.assertRedirects(response, reverse('pro_offers'))
        offer = Offer.objects.get(title='Samsung Galaxy A56 5G 8GB 256GB')
        self.assertIsNotNone(offer.product_id)
        self.assertIsNotNone(offer.price_listing_id)
        listing = PriceListing.objects.get(pk=offer.price_listing_id)
        self.assertEqual(listing.url, 'https://example.com/samsung-a56')
        self.assertEqual(str(listing.price), '325.00')

    def test_public_offer_page_is_whatsapp_first(self):
        self.client.post(reverse('pro_offer_create'), self._quick_payload())
        offer = Offer.objects.get(business=self.profile)

        response = self.client.get(reverse('public_offer', args=[offer.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coiffure femme premium')
        self.assertContains(response, 'Contacter sur WhatsApp')
        self.assertContains(response, 'Kin Services')
        self.assertContains(response, '25000.00')

    def test_business_cannot_edit_another_business_offer(self):
        self.client.post(reverse('pro_offer_create'), self._quick_payload())
        offer = Offer.objects.get(business=self.profile)

        other = User.objects.create_user(
            username='otherofferowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=other,
            business_name='Other Business',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.client.logout()
        self.client.login(username='otherofferowner', password='StrongPass123!')

        response = self.client.get(reverse('pro_offer_edit', args=[offer.pk]))
        self.assertEqual(response.status_code, 404)

    def test_first_party_offer_search_respects_market(self):
        self.client.post(reverse('pro_offer_create'), self._quick_payload(
            offer_type='product',
            title='Samsung Galaxy A56 5G 8GB 256GB',
            price='325.00',
            currency='USD',
        ))

        cd = find_matching_offers('Samsung Galaxy A56 5G 8GB 256GB', market_code='CD')
        fr = find_matching_offers('Samsung Galaxy A56 5G 8GB 256GB', market_code='FR')
        global_results = find_matching_offers('Samsung Galaxy A56 5G 8GB 256GB', market_code='GLOBAL')

        self.assertEqual(len(cd), 1)
        self.assertEqual(fr, [])
        self.assertEqual(len(global_results), 1)

    def test_compare_page_shows_first_party_offer_before_external_completion(self):
        self.client.post(reverse('pro_offer_create'), self._quick_payload(
            offer_type='product',
            title='Samsung Galaxy A56 5G 8GB 256GB',
            price='325.00',
            currency='USD',
        ))

        response = self.client.get(reverse('scrape_view'), {
            'q': 'Samsung Galaxy A56 5G 8GB 256GB',
            'market': 'CD',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bendango + Web + réseaux sociaux')
        self.assertContains(response, 'Samsung Galaxy A56 5G 8GB 256GB')
        self.assertContains(response, 'Publié sur Bendango')
        self.assertContains(response, 'Résultats unifiés')
