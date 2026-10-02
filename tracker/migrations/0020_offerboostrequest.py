from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0019_offermedia'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OfferBoostRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('duration_days', models.PositiveSmallIntegerField(choices=[(7, '7 jours'), (14, '14 jours'), (30, '30 jours')], default=7)),
                ('note', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('approved', 'Approuvée'), ('rejected', 'Refusée')], db_index=True, default='pending', max_length=16)),
                ('starts_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='boost_requests', to='tracker.offer')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offer_boost_requests', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_offer_boost_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', 'created_at'], name='trk_boost_status_created'),
                    models.Index(fields=['offer', 'status'], name='trk_boost_offer_status'),
                    models.Index(fields=['starts_at', 'ends_at'], name='trk_boost_window'),
                ],
            },
        ),
    ]
