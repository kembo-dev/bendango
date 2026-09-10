from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0008_rename_generated_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScrapeJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(db_index=True, max_length=2048)),
                ('query', models.CharField(blank=True, default='', max_length=255)),
                ('model_name', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('retry', 'Retry'), ('success', 'Success'), ('failed', 'Failed')], db_index=True, default='pending', max_length=16)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('max_attempts', models.PositiveIntegerField(default=3)),
                ('last_error', models.TextField(blank=True, default='')),
                ('fetch_status', models.CharField(blank=True, default='', max_length=32)),
                ('http_status', models.PositiveIntegerField(blank=True, null=True)),
                ('duration_ms', models.PositiveIntegerField(default=0)),
                ('from_cache', models.BooleanField(default=False)),
                ('available_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('listing', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scrape_jobs', to='tracker.pricelisting')),
            ],
            options={'ordering': ['available_at', 'created_at']},
        ),
        migrations.AddIndex(model_name='scrapejob', index=models.Index(fields=['status', 'available_at'], name='tracker_scr_status_avail_idx')),
        migrations.AddIndex(model_name='scrapejob', index=models.Index(fields=['url', 'status'], name='tracker_scr_url_status_idx')),
    ]
