from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0003_alter_pricelisting_url'),
    ]

    operations = [
        migrations.AddField(model_name='product', name='brand', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='product', name='model', field=models.CharField(blank=True, default='', max_length=150)),
        migrations.AddField(model_name='product', name='category', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='product', name='image_url', field=models.URLField(blank=True, default='', max_length=2048)),
        migrations.AddField(model_name='product', name='attributes', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='product', name='updated_at', field=models.DateTimeField(auto_now=True)),
        migrations.AlterField(model_name='pricelisting', name='price', field=models.DecimalField(decimal_places=2, max_digits=14)),
        migrations.AddField(model_name='pricelisting', name='normalized_price', field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField(model_name='pricelisting', name='normalized_currency', field=models.CharField(default='USD', max_length=10)),
        migrations.AddField(model_name='pricelisting', name='confidence_score', field=models.DecimalField(decimal_places=4, default=0, max_digits=5)),
        migrations.AddField(model_name='pricelisting', name='is_active', field=models.BooleanField(default=True)),
        migrations.CreateModel(
            name='PriceHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=14)),
                ('currency', models.CharField(max_length=10)),
                ('normalized_price', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('normalized_currency', models.CharField(default='USD', max_length=10)),
                ('in_stock', models.BooleanField(default=True)),
                ('recorded_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='tracker.pricelisting')),
            ],
            options={'ordering': ['-recorded_at']},
        ),
        migrations.AddIndex(model_name='pricehistory', index=models.Index(fields=['listing', 'recorded_at'], name='tracker_pri_listing_98f640_idx')),
    ]
