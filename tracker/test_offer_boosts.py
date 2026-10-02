from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, OfferBoostRequest
from tracker.offer_search import find_matching_offers
from tracker.unified_search import build_unified_results


class OfferBoostWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='boostowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=self.owner,
            business_name='Boost Store',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=self.owner)
        self.profile.market_code = 'CD'
        self.profile.city = 'Kinshasa'
        self.profile.save(update_fields=['market_code', 'city'])
        self.offer = Offer.objects.create(
            business=self.profile,
            offer_type=Offer.TYPE_PRODUCT,
            title='Samsung Galaxy A56 5G 8GB 256GB',
            price='325.00',
            currency='USD',
            market_code='CD',
            city='Kinshasa',
        )
        self.client.login(username='boostowner', password='StrongPass123!')

    def test_business_can_request_boost_for_own_product(self):
        response = self.client.post(
            reverse('pro_offer_boost_request', args=[self.offer.pk]),
            {
                'duration_days': '14',
                'note': 'Mettre ce produit en avant cette semaine.',
            },
        )

        self.assertRedirects(response, reverse('pro_offers'))
        request = OfferBoostRequest.objects.get(offer=self.offer)
        self.assertEqual(request.requested_by, self.owner)
        self.assertEqual(request.duration_days, 14)
        self.assertEqual(request.status, OfferBoostRequest.STATUS_PENDING)
        self.assertIsNone(request.starts_at)
        self.assertIsNone(request.ends_at)

    def test_non_product_offer_cannot_request_boost(self):
        service = Offer.objects.create(
            business=self.profile,
            offer_type=Offer.TYPE_SERVICE,
            title='Coiffure premium',
            price='25000.00',
            currency='CDF',
        )

        response = self.client.get(
            reverse('pro_offer_boost_request', args=[service.pk]),
        )

        self.assertRedirects(response, reverse('pro_offers'))
        self.assertFalse(OfferBoostRequest.objects.filter(offer=service).exists())

    def test_business_cannot_request_boost_for_another_business_product(self):
        other = User.objects.create_user(
            username='otherboostowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=other,
            business_name='Other Boost Store',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        other_profile = BusinessProfile.objects.get(user=other)
        other_offer = Offer.objects.create(
            business=other_profile,
            offer_type=Offer.TYPE_PRODUCT,
            title='iPhone 16 Pro 256GB',
            price='1000.00',
            currency='USD',
        )

        response = self.client.get(
            reverse('pro_offer_boost_request', args=[other_offer.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_duplicate_pending_boost_request_is_blocked(self):
        OfferBoostRequest.objects.create(
            offer=self.offer,
            requested_by=self.owner,
            duration_days=7,
        )

        response = self.client.post(
            reverse('pro_offer_boost_request', args=[self.offer.pk]),
            {'duration_days': '30', 'note': 'Deuxième demande'},
        )

        self.assertRedirects(response, reverse('pro_offers'))
        self.assertEqual(OfferBoostRequest.objects.filter(offer=self.offer).count(), 1)

    def test_admin_approval_activates_boost_window(self):
        admin = User.objects.create_superuser(
            username='boostadmin',
            email='admin@example.com',
            password='StrongPass123!',
        )
        request = OfferBoostRequest.objects.create(
            offer=self.offer,
            requested_by=self.owner,
            duration_days=7,
        )

        request.approve(reviewer=admin)
        request.refresh_from_db()

        self.assertEqual(request.status, OfferBoostRequest.STATUS_APPROVED)
        self.assertEqual(request.reviewed_by, admin)
        self.assertIsNotNone(request.starts_at)
        self.assertIsNotNone(request.ends_at)
        self.assertTrue(request.is_active)
        self.assertGreater(request.ends_at, request.starts_at)

    def test_approved_boost_is_labeled_sponsored_publicly(self):
        request = OfferBoostRequest.objects.create(
            offer=self.offer,
            requested_by=self.owner,
            duration_days=7,
        )
        request.approve()
        self.offer.refresh_from_db()

        response = self.client.get(reverse('public_offer', args=[self.offer.slug]))

        self.assertContains(response, 'Sponsorisé')

    def test_approved_boost_prioritizes_first_party_product(self):
        second = Offer.objects.create(
            business=self.profile,
            offer_type=Offer.TYPE_PRODUCT,
            title='Samsung Galaxy A56 5G 8GB 256GB promo',
            price='320.00',
            currency='USD',
            market_code='CD',
            city='Kinshasa',
        )
        boost = OfferBoostRequest.objects.create(
            offer=self.offer,
            requested_by=self.owner,
            duration_days=7,
        )
        boost.approve()

        results = find_matching_offers(
            'Samsung Galaxy A56 5G 8GB 256GB',
            market_code='CD',
        )

        self.assertEqual(results[0].pk, self.offer.pk)
        self.assertTrue(results[0].is_boosted)
        self.assertIn(second.pk, [item.pk for item in results])

    def test_unified_result_marks_approved_boost_as_promoted(self):
        boost = OfferBoostRequest.objects.create(
            offer=self.offer,
            requested_by=self.owner,
            duration_days=7,
        )
        boost.approve()
        self.offer.search_score = 0.90

        results = build_unified_results([self.offer], [], [])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].promoted)
        self.assertGreaterEqual(results[0].ranking_score, 0.90)
