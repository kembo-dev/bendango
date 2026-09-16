from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0011_searchrun_scrapejob_search_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchrun',
            name='model_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='status',
            field=models.CharField(choices=[('queued', 'Queued'), ('discovering', 'Discovering'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], db_index=True, default='queued', max_length=16),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='discovery_sources',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='discovery_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='discovery_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='searchrun',
            name='discovery_finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='searchrun',
            index=models.Index(fields=['status', 'created_at'], name='tracker_run_status_created_idx'),
        ),
    ]
