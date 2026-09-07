# Generated manually for long e-commerce product URLs.

from django.db import migrations, models


def deduplicate_price_listings(apps, schema_editor):
    PriceListing = apps.get_model('tracker', 'PriceListing')
    duplicate_keys = (
        PriceListing.objects.values('product_id', 'retailer_id', 'url')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
    )

    for duplicate_key in duplicate_keys:
        rows = list(
            PriceListing.objects.filter(
                product_id=duplicate_key['product_id'],
                retailer_id=duplicate_key['retailer_id'],
                url=duplicate_key['url'],
            ).order_by('price', 'id')
        )
        for row in rows[1:]:
            row.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0002_alter_retailer_base_url_alter_retailer_name_and_more'),
    ]

    operations = [
        migrations.RunPython(deduplicate_price_listings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pricelisting',
            name='url',
            field=models.URLField(max_length=2048),
        ),
    ]
