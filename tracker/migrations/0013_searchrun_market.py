from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0012_searchrun_async_discovery'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchrun',
            name='market_code',
            field=models.CharField(db_index=True, default='CD', max_length=8),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='market_currency',
            field=models.CharField(default='CDF', max_length=8),
        ),
    ]
