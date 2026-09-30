from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import (
    BusinessAccountRequest,
    BusinessCategory,
    BusinessProfile,
    PriceListing,
    Product,
)


class BusinessPlatformTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='businesspublic',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=self.user,
            business_name='Pharmacie Espoir',
            business_type='Pharmacie',
            website='https://pharmacie-espoir.example',
            phone='+243999000111',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=self.user)
        self.profile.whatsapp = '+243999000111'
        self.profile.country = 'RDC'
        self.profile.city = 'Kinshasa'
        self.profile.description = 'Pharmacie et produits de santé.'
        self.profile.save()

    def test_business_profile_generates_unique_slug(self):
        self.assertEqual(self.profile.slug, 'pharmacie-espoir')

        other_user = User.objects.create_user(
            username='businesspublic2',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=other_user,
            business_name='Pharmacie Espoir',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        other_profile = BusinessProfile.objects.get(user=other_user)

        self.assertNotEqual(other_profile.slug, self.profile.slug)
        self.assertTrue(other_profile.slug.startswith('pharmacie-espoir-'))

    def test_seeded_business_categories_are_available(self):
        self.assertTrue(BusinessCategory.objects.filter(slug='pharmacie').exists())
        self.assertTrue(BusinessCategory.objects.filter(slug='hotel-logement').exists())
        self.assertTrue(BusinessCategory.objects.filter(slug='vendeur-independant').exists())

    def test_public_business_page_displays_contact_and_offer(self):
        retailer = self.profile.ensure_retailer()
        product = Product.objects.create(
            name='Paracetamol 500mg',
            brand='Generic',
            category='Santé',
        )
        PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url='https://pharmacie-espoir.example/paracetamol',
            price=Decimal('5000.00'),
            currency='CDF',
            confidence_score=Decimal('1.0'),
            match_score=Decimal('1.0'),
            in_stock=True,
            is_active=True,
        )

        response = self.client.get(
            reverse('public_business', args=[self.profile.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pharmacie Espoir')
        self.assertContains(response, 'Kinshasa')
        self.assertContains(response, 'Contacter sur WhatsApp')
        self.assertContains(response, 'Paracetamol 500mg')
        self.assertContains(response, '5000.00')

    def test_private_or_inactive_business_is_not_public(self):
        self.profile.is_public = False
        self.profile.save(update_fields=['is_public'])

        response = self.client.get(
            reverse('public_business', args=[self.profile.slug])
        )

        self.assertEqual(response.status_code, 404)
