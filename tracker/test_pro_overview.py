from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, OfferBoostRequest


class ProAdministrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='business-admin', password='test-password')
        BusinessAccountRequest.objects.create(user=self.user, business_name='Atelier Kivu',
                                             status=BusinessAccountRequest.STATUS_APPROVED)
        self.profile = BusinessProfile.objects.get(user=self.user)
        self.client.force_login(self.user)

    def test_dashboard_counts_owned_offers_and_boosts_only(self):
        own = Offer.objects.create(business=self.profile, title='Notre produit', price=10)
        Offer.objects.create(business=self.profile, title='Offre privée', is_public=False)
        other_user = User.objects.create_user(username='another-business')
        other = BusinessProfile.objects.create(user=other_user, business_name='Entreprise tierce')
        other_offer = Offer.objects.create(business=other, title='Produit confidentiel tiers', price=20)
        now = timezone.now()
        OfferBoostRequest.objects.create(offer=own, requested_by=self.user, status='approved',
                                        starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1))
        OfferBoostRequest.objects.create(offer=other_offer, requested_by=other_user, status='pending')
        response = self.client.get('/pro/')
        self.assertEqual(response.context['offer_count'], 2)
        self.assertEqual(response.context['published_offer_count'], 1)
        self.assertEqual(response.context['unpublished_offer_count'], 1)
        self.assertEqual(response.context['active_boost_count'], 1)
        self.assertEqual(response.context['pending_boost_count'], 0)
        self.assertNotContains(response, 'Produit confidentiel tiers')
        self.assertContains(response, 'Administration du business')

    def test_hidden_business_has_no_public_offer_count(self):
        Offer.objects.create(business=self.profile, title='Produit prêt')
        self.profile.is_public = False
        self.profile.save(update_fields=['is_public'])
        response = self.client.get('/pro/')
        self.assertEqual(response.context['published_offer_count'], 0)
        self.assertContains(response, 'Page masquée')

    def test_expired_boost_is_not_counted_active(self):
        offer = Offer.objects.create(business=self.profile, title='Ancien boost')
        now = timezone.now()
        OfferBoostRequest.objects.create(offer=offer, requested_by=self.user, status='approved',
                                        starts_at=now-timedelta(days=8), ends_at=now-timedelta(days=1))
        self.assertEqual(self.client.get('/pro/').context['active_boost_count'], 0)

    def test_profile_section_and_invalid_submission_show_errors(self):
        self.assertContains(self.client.get('/pro/?section=profile'), 'Enregistrer les modifications')
        response = self.client.post('/pro/?section=profile', {'business_name': '', 'market_code': 'CD'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_profile'])
        self.assertTrue(response.context['form'].errors)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.business_name, 'Atelier Kivu')

    def test_catalog_and_offer_pages_share_administration_shell(self):
        for url in ['/pro/offers/', '/pro/products/', '/pro/offers/add/', '/pro/products/add/']:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'Administration du business')

    def test_unapproved_account_cannot_access_administration(self):
        outsider = User.objects.create_user(username='pending-business')
        self.client.force_login(outsider)
        self.assertRedirects(self.client.get('/pro/'), '/account/pro-request/')
