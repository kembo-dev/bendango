# Generated manually for long e-commerce product URLs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0002_alter_retailer_base_url_alter_retailer_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pricelisting',
            name='url',
            field=models.URLField(max_length=2048),
        ),
    ]
