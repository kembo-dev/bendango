from django.db import migrations, models


def _ensure_index(schema_editor, model, old_name, new_name, fields):
    table_name = model._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, table_name)

    if new_name in constraints:
        return

    new_index = models.Index(fields=fields, name=new_name)

    if old_name in constraints:
        old_index = models.Index(fields=fields, name=old_name)
        schema_editor.rename_index(model, old_index, new_index)
        return

    schema_editor.add_index(model, new_index)


def align_generated_indexes(apps, schema_editor):
    price_history = apps.get_model('tracker', 'PriceHistory')
    search_diagnostic = apps.get_model('tracker', 'SearchDiagnostic')

    _ensure_index(
        schema_editor,
        price_history,
        'tracker_pri_listing_98f640_idx',
        'tracker_pri_listing_f97029_idx',
        ['listing', 'recorded_at'],
    )
    _ensure_index(
        schema_editor,
        search_diagnostic,
        'tracker_sea_created_coverage_idx',
        'tracker_sea_created_6d2240_idx',
        ['created_at', 'coverage_ratio'],
    )


class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0007_searchdiagnostic'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(align_generated_indexes, migrations.RunPython.noop),
            ],
            state_operations=[
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
            ],
        ),
    ]
