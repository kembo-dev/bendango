from io import BytesIO
import tempfile
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from tracker.forms import MultipleImageFileField
from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, Retailer
from tracker.offer_search import find_matching_offers


def photo(name='phone.png'):
    output = BytesIO()
    image = Image.new('RGB', (40, 30), 'blue')
    exif = Image.Exif(); exif[315] = 'private camera owner'
    image.save(output, format='PNG', exif=exif)
    return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')


class MobilePublishingTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory(); self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name); override.enable(); self.addCleanup(override.disable)
        self.user = User.objects.create_user(username='mobile-seller', password='Test12345!')
        self.client.force_login(self.user)

    def payload(self, **extra):
        data = {'title': 'Sac bleu', 'offer_type': 'product', 'description': 'Comme neuf', 'price': '25',
                'currency': 'usd', 'city': 'Kinshasa', 'market_code': 'CD', 'whatsapp': '+243999111222', 'photos': [photo()]}
        data.update(extra); return data

    def test_anonymous_redirects_to_login_with_next(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('publish_offer')), reverse('login') + '?next=/publish/')

    def test_get_does_not_create_a_profile(self):
        response = self.client.get(reverse('publish_offer'))
        self.assertContains(response, 'capture="environment"')
        self.assertContains(response, '/static/tracker/js/quick-publish.')
        self.assertFalse(BusinessProfile.objects.filter(user=self.user).exists())

    def test_individual_publishes_visible_offer_without_pro_or_retailer(self):
        self.assertRedirects(self.client.post(reverse('publish_offer'), self.payload()), reverse('my_announcements'))
        profile = BusinessProfile.objects.get(user=self.user)
        self.assertTrue(profile.is_individual); self.assertFalse(profile.is_verified)
        self.assertEqual(profile.verification_level, 'unverified')
        self.assertFalse(Retailer.objects.exists()); self.assertFalse(BusinessAccountRequest.objects.exists())
        self.assertRedirects(self.client.get(reverse('pro_dashboard')), reverse('business_account_request'))
        offer = Offer.objects.get(business=profile)
        self.assertEqual(offer.currency, 'USD'); self.assertTrue(offer.media.get().is_primary)
        self.assertContains(self.client.get(reverse('public_offer', args=[offer.slug])), 'Sac bleu')
        self.assertContains(self.client.get(reverse('public_business', args=[profile.slug])), 'Particulier · Non vérifié')
        self.assertIn(offer, find_matching_offers('Sac bleu', market_code='CD'))
        self.assertContains(self.client.get(reverse('scrape_view')), 'Sac bleu')

    def test_missing_photo_or_invalid_contact_creates_nothing(self):
        response = self.client.post(reverse('publish_offer'), self.payload(photos=[], whatsapp='bonjour'))
        self.assertContains(response, 'Ajoutez au moins une photo')
        self.assertContains(response, 'numéro WhatsApp valide')
        self.assertFalse(Offer.objects.exists()); self.assertFalse(BusinessProfile.objects.exists())

    def test_fake_image_content_is_rejected_even_with_image_mime(self):
        response = self.client.post(reverse('publish_offer'), self.payload(photos=[SimpleUploadedFile('fake.jpg', b'<script>bad</script>', content_type='image/jpeg')]))
        self.assertContains(response, 'Photo invalide'); self.assertFalse(Offer.objects.exists())

    def test_photos_are_reencoded_without_exif(self):
        cleaned = MultipleImageFileField().clean([photo()])[0]
        with Image.open(cleaned) as image:
            self.assertEqual(image.format, 'WEBP'); self.assertFalse(image.getexif())

    def test_upload_limits_are_enforced(self):
        from django.core.exceptions import ValidationError
        with self.assertRaisesMessage(ValidationError, 'maximum 8 images'):
            MultipleImageFileField().clean([photo() for _ in range(9)])
        with self.assertRaisesMessage(ValidationError, 'maximum 8 Mo'):
            MultipleImageFileField().clean([SimpleUploadedFile('big.jpg', b'x' * (8 * 1024 * 1024 + 1), content_type='image/jpeg')])

    def test_owner_can_edit_without_reupload_and_hide_reactivate(self):
        self.client.post(reverse('publish_offer'), self.payload())
        offer = Offer.objects.get()
        response = self.client.post(reverse('edit_announcement', args=[offer.pk]), self.payload(title='Sac modifié', photos=[]))
        self.assertRedirects(response, reverse('my_announcements'))
        offer.refresh_from_db(); self.assertEqual(offer.title, 'Sac modifié'); self.assertEqual(offer.media.count(), 1)
        self.client.post(reverse('toggle_announcement', args=[offer.pk])); offer.refresh_from_db(); self.assertFalse(offer.is_active)
        self.assertEqual(self.client.get(reverse('public_offer', args=[offer.slug])).status_code, 404)
        self.client.post(reverse('toggle_announcement', args=[offer.pk])); offer.refresh_from_db(); self.assertTrue(offer.is_active)

    def test_other_user_cannot_list_edit_or_toggle(self):
        self.client.post(reverse('publish_offer'), self.payload()); offer = Offer.objects.get()
        other = User.objects.create_user(username='other'); self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse('my_announcements')), 'Sac bleu')
        self.assertEqual(self.client.post(reverse('edit_announcement', args=[offer.pk]), self.payload()).status_code, 404)
        self.assertEqual(self.client.post(reverse('toggle_announcement', args=[offer.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('toggle_announcement', args=[offer.pk])).status_code, 405)

    def test_suspended_or_revoked_business_cannot_bypass_pro_approval(self):
        profile = BusinessProfile.objects.create(user=self.user, business_name='Blocked', is_verified=False)
        self.assertRedirects(self.client.post(reverse('publish_offer'), self.payload()), reverse('my_announcements'))
        self.assertFalse(Offer.objects.exists())
        profile.is_individual=True; profile.is_active=False; profile.save()
        self.assertRedirects(self.client.post(reverse('publish_offer'), self.payload()), reverse('my_announcements'))
        self.assertFalse(Offer.objects.exists())

    def test_approval_upgrades_individual_and_keeps_announcements(self):
        self.client.post(reverse('publish_offer'), self.payload()); offer = Offer.objects.get()
        BusinessAccountRequest.objects.create(user=self.user, business_name='New Business', business_type='Commerce', status='approved')
        profile = BusinessProfile.objects.get(user=self.user)
        self.assertFalse(profile.is_individual); self.assertTrue(profile.is_verified)
        self.assertEqual(profile.business_name, 'New Business'); self.assertEqual(profile.verification_level, 'business')
        self.assertEqual(profile.business_type, 'Commerce')
        self.assertEqual(offer.business_id, profile.pk)
        self.assertEqual(self.client.get(reverse('pro_dashboard')).status_code, 200)

    def test_csrf_remains_required(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True); client.force_login(self.user)
        self.assertEqual(client.post(reverse('publish_offer'), self.payload()).status_code, 403)

    def test_image_pixel_limit_rejects_compressed_large_image(self):
        from django.core.exceptions import ValidationError
        output = BytesIO()
        Image.new('RGB', (5001, 5000)).save(output, format='PNG')
        upload = SimpleUploadedFile('large.png', output.getvalue(), content_type='image/png')
        with self.assertRaisesMessage(ValidationError, '25 mégapixels'):
            MultipleImageFileField().clean([upload])

    def test_edit_cannot_exceed_eight_photos_total(self):
        self.client.post(reverse('publish_offer'), self.payload(photos=[photo() for _ in range(8)]))
        offer = Offer.objects.get()
        response = self.client.post(reverse('edit_announcement', args=[offer.pk]), self.payload())
        self.assertContains(response, 'Une annonce peut contenir au maximum 8 photos.')
        self.assertEqual(offer.media.count(), 8)
