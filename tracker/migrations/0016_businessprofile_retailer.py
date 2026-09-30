from django.db import migrations, models
import django.db.models.deletion


def attach_existing_business_retailers(apps, schema_editor):
    BusinessProfile = apps.get_model('tracker', 'BusinessProfile')
    Retailer = apps.get_model('tracker', 'Retailer')
    for profile in BusinessProfile.objects.filter(is_verified=True, retailer__isnull=True):
        base_url = (profile.website or '').strip()
        if not base_url:
            base_url = f"https://bendango.local/business/{profile.pk}/"
        retailer, _ = Retailer.objects.get_or_create(
            base_url=base_url,
            defaults={
                'name': profile.business_name[:100],
                'trust_score': '0.8500',
                'trust_level': 'verified',
                'is_active': True,
            },
        )
        profile.retailer_id = retailer.pk
        profile.save(update_fields=['retailer'])


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0015_businessprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='retailer',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='business_profile',
                to='tracker.retailer',
            ),
        ),
        migrations.RunPython(
            attach_existing_business_retailers,
            migrations.RunPython.noop,
        ),
    ]
