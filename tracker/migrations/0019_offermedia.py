from django.db import migrations, models
import django.db.models.deletion


def backfill_primary_media(apps, schema_editor):
    Offer = apps.get_model('tracker', 'Offer')
    OfferMedia = apps.get_model('tracker', 'OfferMedia')
    for offer in Offer.objects.exclude(primary_image_url='').order_by('pk'):
        if OfferMedia.objects.filter(offer_id=offer.pk).exists():
            continue
        OfferMedia.objects.create(
            offer_id=offer.pk,
            external_url=offer.primary_image_url,
            alt_text=offer.title,
            position=0,
            is_primary=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0018_offer'),
    ]

    operations = [
        migrations.CreateModel(
            name='OfferMedia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(blank=True, upload_to='offers/%Y/%m/')),
                ('external_url', models.URLField(blank=True, default='', max_length=2048)),
                ('alt_text', models.CharField(blank=True, default='', max_length=255)),
                ('position', models.PositiveIntegerField(default=0)),
                ('is_primary', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media', to='tracker.offer')),
            ],
            options={
                'ordering': ['position', 'created_at', 'pk'],
                'indexes': [
                    models.Index(fields=['offer', 'position'], name='tracker_media_offer_pos_idx'),
                    models.Index(fields=['offer', 'is_primary'], name='tracker_media_offer_primary_idx'),
                ],
            },
        ),
        migrations.RunPython(backfill_primary_media, migrations.RunPython.noop),
    ]
