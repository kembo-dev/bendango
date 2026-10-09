from django.db import migrations


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model('tracker', 'Currency')
    currencies = [
        ('CDF', 'Franc congolais', 'FC'),
        ('USD', 'Dollar américain', '$'),
        ('EUR', 'Euro', '€'),
        ('XOF', 'Franc CFA (Afrique de l’Ouest)', 'CFA'),
        ('XAF', 'Franc CFA (Afrique centrale)', 'CFA'),
        ('MAD', 'Dirham marocain', 'DH'),
        ('CAD', 'Dollar canadien', 'CA$'),
        ('KES', 'Shilling kényan', 'KSh'),
        ('NGN', 'Naira nigérian', '₦'),
        ('TZS', 'Shilling tanzanien', 'TSh'),
    ]
    for order, (code, name, symbol) in enumerate(currencies):
        Currency.objects.using(schema_editor.connection.alias).get_or_create(
            code=code, defaults={'name': name, 'symbol': symbol, 'sort_order': order * 10})


class Migration(migrations.Migration):
    dependencies = [('tracker', '0023_currency')]
    operations = [migrations.RunPython(seed_currencies, migrations.RunPython.noop)]
