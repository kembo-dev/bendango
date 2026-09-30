from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


DEFAULT_CATEGORIES = [
    ('Boutique', 'boutique', 10),
    ('Vendeur indépendant', 'vendeur-independant', 20),
    ('Pharmacie', 'pharmacie', 30),
    ('Supermarché', 'supermarche', 40),
    ('Restaurant', 'restaurant', 50),
    ('Hôtel / logement', 'hotel-logement', 60),
    ('Mode', 'mode', 70),
    ('Beauté', 'beaute', 80),
    ('Électronique', 'electronique', 90),
    ('Alimentation', 'alimentation', 100),
    ('Services', 'services', 110),
    ('Transport', 'transport', 120),
    ('Immobilier', 'immobilier', 130),
    ('Santé', 'sante', 140),
    ('Autre', 'autre', 999),
]


def seed_categories_and_slugs(apps, schema_editor):
    BusinessCategory = apps.get_model('tracker', 'BusinessCategory')
    BusinessProfile = apps.get_model('tracker', 'BusinessProfile')

    for name, slug, sort_order in DEFAULT_CATEGORIES:
        BusinessCategory.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': True,
            },
        )

    used = set(
        BusinessProfile.objects.exclude(slug='').values_list('slug', flat=True)
    )
    for profile in BusinessProfile.objects.order_by('pk'):
        if profile.slug:
            used.add(profile.slug)
            continue
        base = slugify(profile.business_name)[:190] or f'business-{profile.pk}'
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base[:180]}-{suffix}"
            suffix += 1
        profile.slug = candidate
        profile.save(update_fields=['slug'])
        used.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0016_businessprofile_retailer'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('slug', models.SlugField(max_length=140, unique=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='slug',
            field=models.CharField(blank=True, default='', max_length=220),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='businesses', to='tracker.businesscategory'),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='whatsapp',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='public_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='facebook_url',
            field=models.URLField(blank=True, default='', max_length=2048),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='instagram_url',
            field=models.URLField(blank=True, default='', max_length=2048),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='tiktok_url',
            field=models.URLField(blank=True, default='', max_length=2048),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='city',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='cover_image_url',
            field=models.URLField(blank=True, default='', max_length=2048),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='opening_hours',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='verification_level',
            field=models.CharField(choices=[('unverified', 'Non vérifié'), ('identity', 'Identité vérifiée'), ('business', 'Business vérifié'), ('partner', 'Partenaire Bendango')], db_index=True, default='business', max_length=16),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='phone_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='address_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='documents_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='is_public',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(
            seed_categories_and_slugs,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='businessprofile',
            name='slug',
            field=models.SlugField(blank=True, max_length=220, unique=True),
        ),
        migrations.AddIndex(
            model_name='businessprofile',
            index=models.Index(fields=['slug'], name='tracker_biz_slug_idx'),
        ),
        migrations.AddIndex(
            model_name='businessprofile',
            index=models.Index(fields=['market_code', 'city'], name='tracker_biz_market_city_idx'),
        ),
    ]
