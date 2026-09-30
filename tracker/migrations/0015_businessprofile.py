from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0014_searchrun_user_businessaccountrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(max_length=180)),
                ('business_type', models.CharField(blank=True, default='', max_length=120)),
                ('website', models.URLField(blank=True, default='', max_length=2048)),
                ('phone', models.CharField(blank=True, default='', max_length=40)),
                ('country', models.CharField(blank=True, default='', max_length=100)),
                ('address', models.CharField(blank=True, default='', max_length=255)),
                ('logo_url', models.URLField(blank=True, default='', max_length=2048)),
                ('description', models.TextField(blank=True, default='')),
                ('is_verified', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_request', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activated_profile', to='tracker.businessaccountrequest')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='business_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['business_name'],
                'indexes': [
                    models.Index(fields=['business_name'], name='tracker_biz_name_idx'),
                    models.Index(fields=['is_verified'], name='tracker_biz_verified_idx'),
                ],
            },
        ),
    ]
