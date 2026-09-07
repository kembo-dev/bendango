from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0004_bendango_v2_catalog_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelisting',
            name='extraction_source',
            field=models.CharField(
                choices=[
                    ('jsonld', 'JSON-LD'),
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
        migrations.AddField(
            model_name='pricelisting',
            name='match_score',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=5),
        ),
    ]
