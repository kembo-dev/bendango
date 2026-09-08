from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('tracker', '0006_retailer_trust_score')]

    operations = [
        migrations.CreateModel(
            name='SearchDiagnostic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('query', models.CharField(db_index=True, max_length=255)),
                ('site_filter', models.CharField(default='all', max_length=255)),
                ('search_terms_count', models.PositiveIntegerField(default=0)),
                ('candidate_urls_count', models.PositiveIntegerField(default=0)),
                ('processed_urls_count', models.PositiveIntegerField(default=0)),
                ('fallback_urls_count', models.PositiveIntegerField(default=0)),
                ('offers_count', models.PositiveIntegerField(default=0)),
                ('merchant_count', models.PositiveIntegerField(default=0)),
                ('target_merchants', models.PositiveIntegerField(default=1)),
                ('coverage_ratio', models.FloatField(default=0)),
                ('rejection_reasons', models.JSONField(blank=True, default=dict)),
                ('duration_ms', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['created_at', 'coverage_ratio'], name='tracker_sea_created_coverage_idx')],
            },
        ),
    ]
