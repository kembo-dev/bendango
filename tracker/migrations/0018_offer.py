from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def backfill_existing_catalog(apps, schema_editor):
    BusinessProfile = apps.get_model('tracker', 'BusinessProfile')
    Offer = apps.get_model('tracker', 'Offer')
    PriceListing = apps.get_model('tracker', 'PriceListing')

    used_slugs = set(Offer.objects.values_list('slug', flat=True))
    for profile in BusinessProfile.objects.exclude(retailer__isnull=True).order_by('pk'):
        listings = PriceListing.objects.filter(retailer_id=profile.retailer_id).select_related('product')
        for listing in listings:
            if Offer.objects.filter(price_listing_id=listing.pk).exists():
                continue
            product = listing.product
            base = slugify(f"{profile.business_name}-{product.name}")[:210] or f"offer-{listing.pk}"
            candidate = base
            suffix = 2
            while candidate in used_slugs:
                candidate = f"{base[:200]}-{suffix}"
                suffix += 1
            used_slugs.add(candidate)
            Offer.objects.create(
                business_id=profile.pk,
                offer_type='product',
                title=product.name,
                slug=candidate,
                category=product.category or '',
                price=listing.price,
                currency=listing.currency,
                availability='available' if listing.in_stock else 'unavailable',
                primary_image_url=product.image_url or '',
                external_url=listing.url or '',
                whatsapp=profile.whatsapp or profile.phone or '',
                contact_method='external' if listing.url else 'business',
                market_code=profile.market_code or 'CD',
                city=profile.city or '',
                attributes=product.attributes or {},
                product_id=product.pk,
                price_listing_id=listing.pk,
                is_public=bool(profile.is_public),
                is_active=bool(listing.is_active and profile.is_active),
            )


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0017_generalize_businessprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('offer_type', models.CharField(choices=[('product', 'Produit'), ('service', 'Service'), ('accommodation', 'Hôtel / logement'), ('restaurant', 'Restaurant / menu'), ('health', 'Santé / pharmacie'), ('transport', 'Transport'), ('real_estate', 'Immobilier'), ('other', 'Autre')], db_index=True, default='product', max_length=24)),
                ('title', models.CharField(max_length=255)),
                ('slug', models.SlugField(blank=True, max_length=240, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('category', models.CharField(blank=True, default='', max_length=120)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('currency', models.CharField(blank=True, default='USD', max_length=10)),
                ('price_unit', models.CharField(blank=True, default='', max_length=60)),
                ('availability', models.CharField(choices=[('available', 'Disponible'), ('unavailable', 'Indisponible'), ('on_request', 'Sur demande')], db_index=True, default='available', max_length=16)),
                ('primary_image_url', models.URLField(blank=True, default='', max_length=2048)),
                ('external_url', models.URLField(blank=True, default='', max_length=2048)),
                ('whatsapp', models.CharField(blank=True, default='', max_length=40)),
                ('contact_method', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('phone', 'Téléphone'), ('external', 'Lien externe'), ('business', 'Contacter le business')], default='business', max_length=16)),
                ('market_code', models.CharField(db_index=True, default='CD', max_length=8)),
                ('city', models.CharField(blank=True, default='', max_length=120)),
                ('attributes', models.JSONField(blank=True, default=dict)),
                ('is_public', models.BooleanField(db_index=True, default=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='tracker.businessprofile')),
                ('price_listing', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='business_offer', to='tracker.pricelisting')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='business_offers', to='tracker.product')),
            ],
            options={
                'ordering': ['-updated_at', '-created_at'],
                'indexes': [
                    models.Index(fields=['business', 'is_active'], name='tracker_offer_biz_active_idx'),
                    models.Index(fields=['offer_type', 'market_code'], name='tracker_offer_type_market_idx'),
                    models.Index(fields=['title'], name='tracker_offer_title_idx'),
                ],
            },
        ),
        migrations.RunPython(backfill_existing_catalog, migrations.RunPython.noop),
    ]
