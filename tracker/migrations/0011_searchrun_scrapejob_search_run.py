import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0010_pricelisting_microdata_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('query', models.CharField(db_index=True, max_length=255)),
                ('site_filter', models.CharField(default='all', max_length=255)),
                ('target_merchants', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['query', 'created_at'], name='tracker_run_query_created_idx')],
            },
        ),
        migrations.AddField(
            model_name='scrapejob',
            name='search_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs', to='tracker.searchrun'),
        ),
        migrations.AddIndex(
            model_name='scrapejob',
            index=models.Index(fields=['search_run', 'status'], name='tracker_scr_run_status_idx'),
        ),
    ]
