from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('tracker', '0002_alter_retailer_base_url_alter_retailer_name_and_more')]

    operations = [
        migrations.AddField(model_name='product', name='brand', field=models.CharField(blank=True, default='', max_length=120)),
        migrations.AddField(model_name='product', name='model', field=models.CharField(blank=True, default='', max_length=160)),
        migrations.AddField(model_name='product', name='category', field=models.CharField(blank=True, default='', max_length=120)),
        migrations.AddField(model_name='product', name='image_url', field=models.URLField(blank=True, default='', max_length=800)),
        migrations.AddField(model_name='product', name='attributes', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='product', name='updated_at', field=models.DateTimeField(auto_now=True)),
        migrations.AlterField(model_name='pricelisting', name='price', field=models.DecimalField(decimal_places=2, max_digits=14)),
        migrations.AlterField(model_name='pricelisting', name='currency', field=models.CharField(default='USD', max_length=10)),
        migrations.AddField(model_name='pricelisting', name='normalized_price', field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField(model_name='pricelisting', name='normalized_currency', field=models.CharField(default='USD', max_length=10)),
        migrations.AddField(model_name='pricelisting', name='confidence_score', field=models.DecimalField(decimal_places=4, default=0.5, max_digits=5)),
        migrations.AddField(model_name='pricelisting', name='extraction_source', field=models.CharField(default='llm', max_length=30)),
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
                ('observed_at', models.DateTimeField(auto_now_add=True)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='tracker.pricelisting')),
            ],
            options={'ordering': ['-observed_at']},
        ),
        migrations.AddIndex(model_name='product', index=models.Index(fields=['brand', 'model'], name='tracker_pro_brand_m_9bc9da_idx')),
        migrations.AddIndex(model_name='pricelisting', index=models.Index(fields=['product', 'normalized_price'], name='tracker_pri_product_8f1885_idx')),
        migrations.AddIndex(model_name='pricelisting', index=models.Index(fields=['is_active', 'scraped_at'], name='tracker_pri_is_acti_d68f29_idx')),
        migrations.AddIndex(model_name='pricehistory', index=models.Index(fields=['listing', 'observed_at'], name='tracker_pri_listing_63db74_idx')),
    ]
