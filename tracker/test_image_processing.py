from io import BytesIO, StringIO
from pathlib import Path
import tempfile
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings
from tracker.image_processing import prepare_photo
from tracker.models import BusinessProfile, Offer, OfferMedia


def upload(size=(80, 60), mode='RGB', color='blue', exif=None):
    out = BytesIO()
    Image.new(mode, size, color).save(out, format='PNG', **({'exif':exif} if exif else {}))
    return SimpleUploadedFile('photo.png',out.getvalue(),content_type='image/png')


class PhotoProcessingTests(SimpleTestCase):
    def test_landscape_and_portrait_keep_proportions_bounded_at_1600(self):
        for original, expected in [((4000,2000),(1600,800)), ((2000,4000),(800,1600))]:
            with self.subTest(size=original):
                prepared=prepare_photo(upload(size=original))
                with Image.open(prepared) as main:
                    self.assertEqual(main.size, expected); self.assertEqual(main.format,'WEBP')
                with Image.open(BytesIO(prepared.offer_thumbnail)) as thumb:
                    self.assertEqual(thumb.size,(320,320)); self.assertEqual(thumb.format,'WEBP')

    def test_small_photo_is_not_upscaled_and_thumbnail_has_padding(self):
        prepared=prepare_photo(upload(size=(80,60)))
        with Image.open(prepared) as main:
            self.assertEqual(main.size,(80,60))
        with Image.open(BytesIO(prepared.offer_thumbnail)) as thumb:
            self.assertEqual(thumb.getpixel((0,0))[3],0)
            self.assertEqual(thumb.getpixel((160,160))[3],255)

    def test_orientation_corrected_and_metadata_removed(self):
        exif=Image.Exif(); exif[274]=6; exif[315]='camera metadata'
        prepared=prepare_photo(upload(size=(120,80),exif=exif))
        with Image.open(prepared) as main:
            self.assertEqual(main.size,(80,120)); self.assertFalse(main.getexif())

    def test_transparency_preserved(self):
        prepared=prepare_photo(upload(mode='RGBA',color=(200,0,0,0)))
        with Image.open(prepared) as main:
            self.assertEqual(main.getpixel((0,0))[3],0)


class PhotoRenditionStorageTests(TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        config=override_settings(MEDIA_ROOT=tmp.name);config.enable();self.addCleanup(config.disable)
        user=User.objects.create_user(username='photo-owner')
        business=BusinessProfile.objects.create(user=user,business_name='Photo test')
        self.offer=Offer.objects.create(business=business,title='Photo test')

    def test_new_upload_has_optimized_main_and_distinct_thumbnail(self):
        media=OfferMedia.objects.create(offer=self.offer,file=prepare_photo(upload(size=(800,400))))
        self.assertTrue(media.file.name.endswith('.webp'))
        self.assertIn('/thumbnails/',media.thumbnail_url)
        self.assertNotEqual(media.url,media.thumbnail_url)
        with media.file.open('rb') as f, Image.open(f) as main:
            self.assertEqual(main.size,(800,400))
        with media.thumbnail_file.open('rb') as f, Image.open(f) as thumb:
            self.assertEqual(thumb.size,(320,320))

    def legacy(self):
        media=OfferMedia.objects.create(offer=self.offer)
        source=upload(size=(1800,900));original=source.read()
        name=media.file.storage.save('offers/legacy.png',ContentFile(original))
        OfferMedia.objects.filter(pk=media.pk).update(file=name)
        media.refresh_from_db()
        return media,original

    def test_existing_image_is_preserved_and_backfill_is_idempotent(self):
        media,original=self.legacy();name=media.file.name
        self.assertTrue(media.optimize_existing())
        media.refresh_from_db();self.assertEqual(media.file.name,name)
        with media.file.open('rb') as f:self.assertEqual(f.read(),original)
        self.assertEqual(media.url,media.optimized_file.url)
        with media.optimized_file.open('rb') as f,Image.open(f) as image:self.assertEqual(image.size,(1600,800))
        count=len(list(Path(media.file.storage.location).rglob('*.webp')))
        self.assertFalse(media.optimize_existing())
        self.assertEqual(len(list(Path(media.file.storage.location).rglob('*.webp'))),count)

    def test_command_dry_run_does_not_write_and_apply_generates_variants(self):
        media,_=self.legacy();out=StringIO()
        call_command('optimize_offer_images',stdout=out)
        media.refresh_from_db();self.assertFalse(media.optimized_file);self.assertFalse(media.thumbnail_file)
        call_command('optimize_offer_images',apply=True,stdout=out)
        media.refresh_from_db();self.assertTrue(media.optimized_file);self.assertTrue(media.thumbnail_file)

    def test_external_image_is_unchanged(self):
        media=OfferMedia.objects.create(offer=self.offer,external_url='https://example.com/photo.png')
        self.assertFalse(media.optimize_existing())
        self.assertEqual(media.url,media.external_url);self.assertEqual(media.thumbnail_url,media.url)

    def test_gallery_uses_thumbnail_and_deletion_removes_generated_files(self):
        from django.urls import reverse
        media=OfferMedia.objects.create(offer=self.offer,file=prepare_photo(upload()))
        second=OfferMedia.objects.create(offer=self.offer,file=prepare_photo(upload()))
        response=self.client.get(reverse('public_offer',args=[self.offer.slug]))
        self.assertContains(response,media.thumbnail_url)
        self.client.force_login(self.offer.business.user)
        path=Path(media.thumbnail_file.path);source_path=Path(media.file.path)
        self.client.post(reverse('pro_offer_media_action',args=[self.offer.pk,media.pk,'delete']))
        self.assertFalse(path.exists());self.assertFalse(source_path.exists())
