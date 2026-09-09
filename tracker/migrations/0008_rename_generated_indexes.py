from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0007_searchdiagnostic'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='pricehistory',
            old_name='tracker_pri_listing_98f640_idx',
            new_name='tracker_pri_listing_f97029_idx',
        ),
        migrations.RenameIndex(
            model_name='searchdiagnostic',
            old_name='tracker_sea_created_coverage_idx',
            new_name='tracker_sea_created_6d2240_idx',
        ),
    ]
