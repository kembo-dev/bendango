import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.test import SimpleTestCase, TestCase

from config.llm import DISABLED_REFERENCE, load_policy
from tracker.models import SearchRun, PriceListing, ScrapeJob
from tracker.services import (
    LLMRequiredError, _extract_llm_only, extract_with_llm,
    get_llm_model_reference, process_url_and_save,
)
from tracker.test_llm_config import DOCUMENT, DATA


class PolicyFixture:
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'llm.toml'
        self.path.write_text(DOCUMENT)
        override = self.settings(LLM_CONFIG_FILE=self.path, LLM_CONFIG={})
        override.enable()
        self.addCleanup(override.disable)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def policy(self, mode='auto', fallback='', paid=False):
        self.path.write_text(DOCUMENT + f'\n[policy]\nmode="{mode}"\nfallback_profile="{fallback}"\nallow_paid_fallback={str(paid).lower()}\n')


class LLMPolicyTests(PolicyFixture, SimpleTestCase):
    def test_auto_is_default_and_policy_can_be_hot_reloaded(self):
        self.assertEqual(load_policy(self.path)['mode'], 'auto')
        self.policy('disabled')
        self.assertEqual(get_llm_model_reference(), DISABLED_REFERENCE)
        self.policy('auto')
        self.assertEqual(get_llm_model_reference(), 'local::local-model')

    def test_private_policy_overrides_shared_defaults(self):
        self.path.with_suffix('.local.toml').write_text('[policy]\nmode="disabled"\n')
        self.assertEqual(load_policy(self.path)['mode'], 'disabled')
        self.assertFalse(load_policy(self.path)['allow_paid_fallback'])

    def test_invalid_policy_is_rejected(self):
        for value in ['mode="unknown"', 'allow_paid_fallback="true"', 'fallback_profile=42', 'secret="private"']:
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                self.path.write_text(DOCUMENT + '\n[policy]\n' + value)
                load_policy(self.path)

    @patch('tracker.services.requests.post')
    @patch('tracker.services.boto3.client')
    def test_disabled_never_calls_provider_even_with_explicit_model(self, boto, post):
        self.policy('disabled', 'aws', True)
        self.assertIsNone(_extract_llm_only('<html/>', 'aws::model'))
        post.assert_not_called()
        boto.assert_not_called()

    @patch('tracker.services.requests.post')
    def test_missing_file_or_model_uses_no_llm(self, post):
        for content in [None, 'active_profile="legacy"\n']:
            if content is None:
                self.path.unlink(missing_ok=True)
            else:
                self.path.write_text(content)
            self.assertEqual(get_llm_model_reference(), DISABLED_REFERENCE)
            self.assertIsNone(_extract_llm_only('<html/>'))
        post.assert_not_called()

    @patch('tracker.services.requests.post')
    def test_missing_api_key_is_optional_and_logged_without_secret(self, post):
        self.path.write_text(DOCUMENT.replace('active_profile = "local"', 'active_profile = "api"'))
        with self.assertLogs('tracker.services', level='WARNING') as logs:
            self.assertEqual(get_llm_model_reference(), DISABLED_REFERENCE)
            self.assertIsNone(_extract_llm_only('<html/>'))
        self.assertIn('Clé API', ' '.join(logs.output))
        post.assert_not_called()

    @patch('tracker.services.requests.post')
    def test_disabled_queued_reference_stays_disabled_after_configuration(self, post):
        self.path.write_text('active_profile="legacy"\n')
        ref = get_llm_model_reference()
        self.path.write_text(DOCUMENT)
        self.assertIsNone(_extract_llm_only('<html/>', ref))
        post.assert_not_called()

    @patch('tracker.services.requests.post', side_effect=TimeoutError('secret-response'))
    def test_provider_timeout_returns_none_in_auto_and_sanitizes_log(self, post):
        with self.assertLogs('tracker.services', level='WARNING') as logs:
            self.assertIsNone(_extract_llm_only('<html/>'))
        self.assertNotIn('secret-response', ' '.join(logs.output))
        post.assert_called_once()

    def test_required_missing_model_raises_controlled_failure(self):
        self.path.write_text('active_profile="legacy"\n[policy]\nmode="required"\n')
        with self.assertRaises(LLMRequiredError):
            get_llm_model_reference()
        with self.assertRaises(LLMRequiredError):
            _extract_llm_only('<html/>')

    @patch('tracker.services.requests.post', side_effect=TimeoutError())
    def test_required_provider_failure_raises(self, post):
        self.policy('required')
        with self.assertRaises(LLMRequiredError):
            _extract_llm_only('<html/>')

    @patch('tracker.services.requests.post')
    def test_required_keeps_successful_html_extraction(self, post):
        self.policy('required')
        result = extract_with_llm('<title>Guitare</title><div>Prix 199 USD</div>')
        self.assertEqual(result.price, 199)
        post.assert_not_called()

    @patch('tracker.services.requests.post', side_effect=TimeoutError())
    @patch('tracker.services.boto3.client')
    def test_remote_fallback_is_blocked_by_default(self, boto, post):
        self.policy(fallback='aws')
        self.assertIsNone(_extract_llm_only('<html/>'))
        post.assert_called_once()
        boto.assert_not_called()

    @patch('tracker.services.requests.post', side_effect=TimeoutError())
    @patch('tracker.services.boto3.client')
    def test_remote_fallback_requires_explicit_permission(self, boto, post):
        self.policy(fallback='aws', paid=True)
        boto.return_value.converse.return_value = {'output': {'message': {'content': [{'text': json.dumps(DATA)}]}}}
        self.assertEqual(_extract_llm_only('<html/>').price, 42)
        boto.assert_called_once()

    @patch('tracker.services.requests.post')
    def test_local_fallback_after_primary_timeout(self, post):
        self.policy(fallback='studio')
        with self.path.open('a') as f:
            f.write('[profiles.studio]\nprovider="openai-compatible"\nmodel="studio-model"\nbase_url="http://127.0.0.1:1234/v1"\nrequire_api_key=false\n')
        post.side_effect = [TimeoutError(), Mock(status_code=200, json=lambda: {'choices': [{'message': {'content': json.dumps(DATA)}}]})]
        self.assertEqual(_extract_llm_only('<html/>').price, 42)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['json']['model'], 'studio-model')

    @patch('tracker.services.requests.post', side_effect=TimeoutError())
    def test_same_profile_is_not_retried_as_its_own_fallback(self, post):
        self.policy(fallback='local')
        self.assertIsNone(_extract_llm_only('<html/>'))
        post.assert_called_once()

    def test_missing_primary_can_select_configured_local_fallback(self):
        self.policy(fallback='local')
        self.path.write_text(self.path.read_text().replace('active_profile = "local"', 'active_profile = "legacy"'))
        self.assertEqual(get_llm_model_reference(), 'local::local-model')

    def test_required_operator_check_is_controlled(self):
        self.path.write_text('active_profile="legacy"\n[policy]\nmode="required"\n')
        with self.assertRaises(CommandError):
            call_command('llm_config', '--check', stdout=io.StringIO())

    @patch('tracker.services.requests.post')
    def test_disabled_still_extracts_jsonld(self, post):
        self.policy('disabled')
        html = '<script type="application/ld+json">' + json.dumps({
            '@type': 'Product', 'name': 'Yamaha F310',
            'offers': {'@type': 'Offer', 'price': '199', 'priceCurrency': 'USD',
                       'availability': 'https://schema.org/InStock'}
        }) + '</script>'
        self.assertEqual(extract_with_llm(html).price, 199)
        post.assert_not_called()

    def test_operator_check_reports_disabled_mode_without_network(self):
        self.policy('disabled')
        out = io.StringIO()
        call_command('llm_config', '--check', stdout=out)
        self.assertIn('Mode : disabled', out.getvalue())
        self.assertIn('sans LLM', out.getvalue())


class LLMOptionalSearchTests(PolicyFixture, TestCase):
    def test_post_name_without_model_still_creates_search(self):
        self.path.write_text('active_profile="legacy"\n')
        response = self.client.post('/', {'query': 'Yamaha F310', 'site': '', 'market': 'CD'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SearchRun.objects.get().model_name, DISABLED_REFERENCE)

    def test_required_missing_configuration_returns_friendly_error(self):
        self.path.write_text('active_profile="legacy"\n[policy]\nmode="required"\n')
        response = self.client.post('/', {'query': 'Yamaha F310', 'site': '', 'market': 'CD'})
        self.assertContains(response, 'La collecte complémentaire est indisponible')
        self.assertNotContains(response, 'LLM_MODEL')
        self.assertFalse(SearchRun.objects.exists())

    @patch('tracker.services.fetch_and_clean_html', return_value='<title>Yamaha F310</title><h1>Yamaha F310</h1><div>Prix 199 USD</div>')
    @patch('tracker.services.requests.post')
    def test_price_can_be_saved_without_llm_configuration(self, post, fetch):
        self.path.write_text('active_profile="legacy"\n')
        listing, error = process_url_and_save('https://merchant.example/product/yamaha-f310')
        self.assertIsNone(error)
        self.assertEqual(listing.extraction_source, 'html')
        self.assertEqual(float(listing.price), 199)
        post.assert_not_called()

    @patch('tracker.services.fetch_and_clean_html', return_value='<title>Yamaha F310</title><h1>Yamaha F310</h1><div>Prix sur demande</div>')
    @patch('tracker.services.requests.post')
    def test_no_price_is_created_when_optional_extraction_is_insufficient(self, post, fetch):
        self.path.write_text('active_profile="legacy"\n')
        listing, error = process_url_and_save('https://merchant.example/product/yamaha-f310')
        self.assertIsNone(listing)
        self.assertIn('résultats peuvent être incomplets', error)
        self.assertFalse(PriceListing.objects.exists())
        post.assert_not_called()

    def test_partial_search_warning_is_visible_on_results_and_history_detail(self):
        user = User.objects.create_user(username='policy-user', password='testing-only')
        self.client.force_login(user)
        run = SearchRun.objects.create(user=user, query='Yamaha F310', status=SearchRun.STATUS_COMPLETED,
                                       completed_at=timezone.now(), discovery_finished_at=timezone.now())
        ScrapeJob.objects.create(search_run=run, query=run.query, url='https://merchant.example/product/f310',
                                 status=ScrapeJob.STATUS_FAILED, last_error='Extraction insuffisante')
        for url in [f'/?q=Yamaha+F310&run={run.pk}', f'/searches/{run.pk}/']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'Les résultats peuvent être incomplets.')
                self.assertNotContains(response, 'Modèle IA')
