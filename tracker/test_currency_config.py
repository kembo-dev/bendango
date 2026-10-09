from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from tracker.forms import MobilePublishForm, OfferEditForm, ProCatalogProductForm, QuickOfferForm
from tracker.models import Currency, Offer
from tracker.test_mobile_publish import photo


class CurrencyConfigurationTests(TestCase):
    def payload(self, **changes):
        data = {'title': 'Vélo', 'offer_type': 'product', 'price': '25', 'currency': 'USD',
                'city': 'Kinshasa', 'market_code': 'CD', 'whatsapp': '+243999111222'}
        data.update(changes)
        return data

    def test_migration_seeds_market_currencies(self):
        from tracker.markets import MARKETS
        self.assertEqual(set(Currency.objects.values_list('code', flat=True)),
                         {market.currency for market in MARKETS.values() if market.currency})

    def test_configuration_is_shared_and_reloaded_without_restart(self):
        Currency.objects.create(code='GBP', name='Livre sterling', symbol='£', sort_order=1)
        for form_type in (MobilePublishForm, QuickOfferForm, OfferEditForm, ProCatalogProductForm):
            self.assertIn(('GBP', 'GBP — Livre sterling'), form_type().fields['currency'].choices)
        Currency.objects.filter(code='GBP').update(is_active=False)
        self.assertNotIn('GBP', dict(MobilePublishForm().fields['currency'].choices))

    def test_preferred_currency_and_database_fallback_order(self):
        self.assertEqual(MobilePublishForm(initial={'currency': 'USD'}).initial['currency'], 'USD')
        Currency.objects.filter(code='CDF').update(is_active=False)
        self.assertEqual(MobilePublishForm(initial={'currency': 'CDF'}).initial['currency'], 'USD')

    def test_lowercase_is_normalized_before_validation(self):
        form = MobilePublishForm(self.payload(currency='usd'), editing=True)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['currency'], 'USD')

    def test_inactive_or_invented_currency_is_rejected(self):
        Currency.objects.filter(code='USD').update(is_active=False)
        for value in ('USD', 'XYZ', '$'):
            form = MobilePublishForm(self.payload(currency=value), editing=True)
            self.assertFalse(form.is_valid())
            self.assertIn('currency', form.errors)

    def test_edit_preserves_only_the_existing_inactive_or_legacy_currency(self):
        Currency.objects.filter(code__in=['USD', 'EUR']).update(is_active=False)
        form = MobilePublishForm(self.payload(), editing=True, current_currency='USD')
        self.assertTrue(form.is_valid(), form.errors)
        other = MobilePublishForm(self.payload(currency='EUR'), editing=True, current_currency='USD')
        self.assertFalse(other.is_valid())
        legacy = MobilePublishForm(self.payload(currency='$'), editing=True, current_currency='$')
        self.assertTrue(legacy.is_valid(), legacy.errors)

    def test_empty_configuration_reports_unavailability_and_blocks_creation(self):
        Currency.objects.update(is_active=False)
        form = MobilePublishForm(self.payload(), editing=True)
        self.assertFalse(form.is_valid())
        self.assertIn('aucune devise', form.fields['currency'].help_text)
        self.assertEqual(MobilePublishForm().initial['currency'], '')

    def test_code_validation(self):
        for value in ('$', 'US', 'usd'):
            with self.assertRaises(ValidationError):
                Currency(code=value, name='Invalide').full_clean()

    def test_publish_uses_database_and_edit_keeps_disabled_currency(self):
        user = User.objects.create_user(username='currency-seller')
        self.client.force_login(user)
        response = self.client.get(reverse('publish_offer'))
        self.assertContains(response, '<select name="currency"')
        self.assertContains(response, 'CDF — Franc congolais')
        data = self.payload(photos=[photo()])
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.assertRedirects(self.client.post(reverse('publish_offer'), data), reverse('my_announcements'))
            offer = Offer.objects.get()
            Currency.objects.filter(code='USD').update(is_active=False)
            self.assertRedirects(self.client.post(reverse('edit_announcement', args=[offer.pk]), self.payload(title='Vélo modifié')),
                                 reverse('my_announcements'))
            offer.refresh_from_db()
            self.assertEqual(offer.currency, 'USD')
            self.assertEqual(offer.title, 'Vélo modifié')
            response = self.client.post(reverse('publish_offer'), self.payload(photos=[photo()]))
            self.assertContains(response, 'Choisissez une devise disponible')
            self.assertEqual(Offer.objects.count(), 1)

    def test_configuration_admin_requires_staff(self):
        self.client.force_login(User.objects.create_user(username='ordinary-seller'))
        response = self.client.get(reverse('admin:tracker_currency_changelist'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
