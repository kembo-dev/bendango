from io import BytesIO
from PIL import Image

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, OfferMedia


class OfferMediaTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='bendango-media-test-')
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

        self.user = User.objects.create_user(
            username='mediaowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=self.user,
            business_name='Media Business',
            phone='+243999111333',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=self.user)
        self.profile.whatsapp = '+243999111333'
        self.profile.city = 'Kinshasa'
        self.profile.market_code = 'CD'
        self.profile.save(update_fields=['whatsapp', 'city', 'market_code'])
        self.client.login(username='mediaowner', password='StrongPass123!')

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _image(self, name):
        output = BytesIO()
        Image.new('RGB', (30, 20), 'green').save(output, format='JPEG')
        return SimpleUploadedFile(name, output.getvalue(), content_type='image/jpeg')

    def _payload(self, **overrides):
        data = {
            'offer_type': 'service',
            'title': 'Service avec photos',
            'price': '15000.00',
            'currency': 'CDF',
            'price_unit': 'service',
            'primary_image_url': '',
            'availability': 'available',
            'whatsapp': '+243999111333',
            'external_url': '',
            'description': 'Offre test avec galerie.',
        }
        data.update(overrides)
        return data

    def test_quick_publish_accepts_multiple_uploaded_images(self):
        data = self._payload()
        data['photos'] = [
            self._image('photo-1.jpg'),
            self._image('photo-2.jpg'),
        ]

        response = self.client.post(reverse('pro_offer_create'), data)

        self.assertRedirects(response, reverse('pro_offers'))
        offer = Offer.objects.get(title='Service avec photos')
        media = list(offer.media.order_by('position'))
        self.assertEqual(len(media), 2)
        self.assertTrue(media[0].is_primary)
        self.assertFalse(media[1].is_primary)
        self.assertTrue(media[0].file.name.startswith('offers/'))
        self.assertIn('/media/offers/', offer.display_image_url)

    def test_public_offer_page_uses_uploaded_primary_and_gallery(self):
        data = self._payload()
        data['photos'] = [
            self._image('front.jpg'),
            self._image('detail.jpg'),
        ]
        self.client.post(reverse('pro_offer_create'), data)
        offer = Offer.objects.get(title='Service avec photos')

        response = self.client.get(reverse('public_offer', args=[offer.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Galerie')
        self.assertContains(response, 'front')
        self.assertContains(response, 'detail')

    def test_owner_can_change_primary_reorder_and_delete_media(self):
        offer = Offer.objects.create(
            business=self.profile,
            offer_type='service',
            title='Galerie contrôlable',
            price='12000.00',
            currency='CDF',
            whatsapp=self.profile.whatsapp,
        )
        first = OfferMedia.objects.create(
            offer=offer,
            file=self._image('first.jpg'),
            position=0,
            is_primary=True,
        )
        second = OfferMedia.objects.create(
            offer=offer,
            file=self._image('second.jpg'),
            position=1,
            is_primary=False,
        )

        response = self.client.post(
            reverse('pro_offer_media_action', args=[offer.pk, second.pk, 'primary'])
        )
        self.assertRedirects(response, reverse('pro_offer_edit', args=[offer.pk]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

        self.client.post(
            reverse('pro_offer_media_action', args=[offer.pk, second.pk, 'up'])
        )
        second.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(second.position, 0)
        self.assertEqual(first.position, 1)

        response = self.client.post(
            reverse('pro_offer_media_action', args=[offer.pk, second.pk, 'delete'])
        )
        self.assertRedirects(response, reverse('pro_offer_edit', args=[offer.pk]))
        self.assertFalse(OfferMedia.objects.filter(pk=second.pk).exists())
        first.refresh_from_db()
        self.assertTrue(first.is_primary)

    def test_business_cannot_manage_another_business_media(self):
        offer = Offer.objects.create(
            business=self.profile,
            offer_type='service',
            title='Offre privée',
        )
        media = OfferMedia.objects.create(
            offer=offer,
            file=self._image('private.jpg'),
            is_primary=True,
        )

        other = User.objects.create_user(
            username='othermediaowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=other,
            business_name='Other Media Business',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.client.logout()
        self.client.login(username='othermediaowner', password='StrongPass123!')

        response = self.client.post(
            reverse('pro_offer_media_action', args=[offer.pk, media.pk, 'delete'])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(OfferMedia.objects.filter(pk=media.pk).exists())

    def test_upload_rejects_non_image_file(self):
        data = self._payload()
        data['photos'] = [
            SimpleUploadedFile('document.txt', b'not-an-image', content_type='text/plain')
        ]

        response = self.client.post(reverse('pro_offer_create'), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Seuls les fichiers image sont acceptés.')
        self.assertFalse(Offer.objects.filter(title='Service avec photos').exists())

    def test_gallery_starts_with_primary_then_keeps_media_order(self):
        offer = Offer.objects.create(business=self.profile, title='Galerie ordonnée')
        first = OfferMedia.objects.create(offer=offer, external_url='https://example.com/first.jpg', position=0)
        cover = OfferMedia.objects.create(offer=offer, external_url='https://example.com/cover.jpg', position=1, is_primary=True)
        last = OfferMedia.objects.create(offer=offer, external_url='https://example.com/last.jpg', position=2)
        response = self.client.get(reverse('public_offer', args=[offer.slug]))
        self.assertEqual([image['url'] for image in response.context['gallery_images']], [cover.url, first.url, last.url])
        self.assertContains(response, 'aria-label="Photo suivante"')
        self.assertContains(response, 'data-gallery-play')

    def test_gallery_uses_external_fallback_without_navigation_for_one_image(self):
        offer = Offer.objects.create(business=self.profile, title='Photo unique', primary_image_url='https://example.com/solo.jpg')
        response = self.client.get(reverse('public_offer', args=[offer.slug]))
        self.assertEqual(response.context['gallery_images'], [{'url': offer.primary_image_url, 'alt': offer.title}])
        self.assertNotContains(response, 'data-gallery-next')
        self.assertNotContains(response, 'data-gallery-play')

    def test_gallery_without_images_does_not_render_empty_controls(self):
        offer = Offer.objects.create(business=self.profile, title='Sans photo')
        OfferMedia.objects.create(offer=offer, is_primary=True)
        response = self.client.get(reverse('public_offer', args=[offer.slug]))
        self.assertEqual(response.context['gallery_images'], [])
        self.assertNotContains(response, 'data-offer-gallery')
