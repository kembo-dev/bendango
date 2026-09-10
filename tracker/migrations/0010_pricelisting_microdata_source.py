from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0009_scrapejob'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pricelisting',
            name='extraction_source',
            field=models.CharField(
                choices=[
                    ('jsonld', 'JSON-LD'),
                    ('microdata', 'Schema.org microdata'),
                    ('shopify', 'Shopify JSON'),
                    ('meta', 'Meta tags'),
                    ('llm', 'LLM'),
                    ('html', 'HTML fallback'),
                    ('cache', 'Cached listing'),
                    ('unknown', 'Unknown'),
                ],
                default='unknown',
                max_length=20,
            ),
        ),
    ]
