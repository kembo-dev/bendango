from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0013_searchrun_market'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchrun',
            name='user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='search_runs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='BusinessAccountRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(max_length=180)),
                ('business_type', models.CharField(blank=True, default='', max_length=120)),
                ('website', models.URLField(blank=True, default='', max_length=2048)),
                ('phone', models.CharField(blank=True, default='', max_length=40)),
                ('description', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('approved', 'Approuvée'), ('rejected', 'Refusée')], db_index=True, default='pending', max_length=16)),
                ('admin_note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='business_account_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'created_at'], name='tracker_biz_user_created_idx'),
                    models.Index(fields=['status', 'created_at'], name='tracker_biz_status_created_idx'),
                ],
            },
        ),
    ]
