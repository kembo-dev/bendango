import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from config.llm import load_config, model_reference
from tracker.services import _extract_llm_only, get_llm_config

DOCUMENT = '''active_profile = "local"
[defaults]
timeout = 7
max_tokens = 256
max_input_chars = 100
[profiles.local]
provider = "ollama"
model = "local-model"
base_url = "http://127.0.0.1:11434"
[profiles.api]
provider = "openai-compatible"
model = "api-model"
base_url = "https://llm.example/v1"
api_key_env = "TEST_LLM_KEY"
[profiles.aws]
provider = "bedrock"
model = "bedrock-model"
'''
DATA = {'product_name': 'Produit', 'price': 42, 'currency': 'USD', 'in_stock': True, 'sku_or_ean': None}


class LLMProfileTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'llm.toml'
        self.path.write_text(DOCUMENT)
        self.settings_override = self.settings(LLM_CONFIG_FILE=self.path, LLM_CONFIG={})
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_local_profile_needs_no_cloud_credentials_or_env_model(self):
        config = get_llm_config()
        self.assertEqual(config['provider'], 'ollama')
        self.assertEqual(config['default_model'], 'local-model')
        self.assertEqual(config['api_key'], '')

    def test_file_changes_are_applied_without_settings_reload(self):
        self.assertEqual(get_llm_config()['default_model'], 'local-model')
        self.path.write_text(DOCUMENT.replace('local-model', 'new-model'))
        self.assertEqual(get_llm_config()['default_model'], 'new-model')

    def test_local_override_merges_profile_and_defaults(self):
        self.path.with_suffix('.local.toml').write_text('[defaults]\ntimeout=10\n[profiles.local]\nmodel="private-model"\n')
        config = get_llm_config()
        self.assertEqual(config['default_model'], 'private-model')
        self.assertEqual(config['timeout'], 10)
        self.assertEqual(config['base_url'], 'http://127.0.0.1:11434')

    def test_queued_model_reference_keeps_provider_when_active_profile_changes(self):
        reference = model_reference(get_llm_config())
        self.path.write_text(DOCUMENT.replace('active_profile = "local"', 'active_profile = "api"'))
        self.assertEqual(get_llm_config()['provider'], 'openai-compatible')
        queued = get_llm_config(reference)
        self.assertEqual(queued['provider'], 'ollama')
        self.assertEqual(queued['selected_model'], 'local-model')

    def test_removed_queued_profile_fails_instead_of_using_wrong_provider(self):
        self.path.write_text('active_profile="api"\n[profiles.api]\nprovider="openai-compatible"\nmodel="model"\n')
        with self.assertRaises(ImproperlyConfigured):
            get_llm_config('local::old-model')

    def test_profile_environment_override_and_legacy_settings_compatibility(self):
        with patch.dict(os.environ, {'LLM_PROFILE': 'legacy'}):
            config = load_config(self.path, {'default_model': 'test-model', 'provider': 'bedrock', 'models': ['second'], 'access_key_id': 'test-access'})
        self.assertEqual(config['default_model'], 'test-model')
        self.assertEqual(config['access_key_id'], 'test-access')
        self.assertEqual(config['models'], ['test-model', 'second'])

    def test_model_and_key_environment_references(self):
        self.path.write_text(DOCUMENT.replace('api_key_env = "TEST_LLM_KEY"', 'api_key_env = "TEST_LLM_KEY"\nmodel_env="TEST_MODEL"'))
        with patch.dict(os.environ, {'TEST_LLM_KEY': 'test-secret', 'TEST_MODEL': 'chosen-model'}):
            config = load_config(self.path, profile='api')
        self.assertEqual(config['default_model'], 'chosen-model')
        self.assertEqual(config['api_key'], 'test-secret')

    def test_invalid_configuration_is_rejected_without_echoing_values(self):
        cases = [
            DOCUMENT + '\napi_key="test-secret"',
            DOCUMENT.replace('provider = "ollama"', 'provider = "unknown"'),
            DOCUMENT.replace('provider = "ollama"', 'provider = ["ollama"]'),
            DOCUMENT.replace('timeout = 7', 'timeout = 0'),
            DOCUMENT.replace('max_tokens = 256', 'max_tokens = 1.5'),
            DOCUMENT.replace('max_input_chars = 100', 'max_input_chars = 0'),
            DOCUMENT.replace('http://127.0.0.1:11434', 'http://remote.example'),
            DOCUMENT.replace('http://127.0.0.1:11434', 'https://user:test-secret@remote.example'),
            DOCUMENT.replace('http://127.0.0.1:11434', 'https://remote.example/?key=test-secret'),
            'invalid = ["test-secret"',
        ]
        for content in cases:
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaises(ImproperlyConfigured) as error:
                    get_llm_config()
                self.assertNotIn('test-secret', str(error.exception))

    def test_malformed_qualified_reference_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            load_config(self.path, reference='local::model::extra')

    def test_unknown_profile_and_missing_model_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            load_config(self.path, profile='missing')
        self.path.write_text(DOCUMENT.replace('model = "local-model"', 'model = ""'))
        with self.assertRaises(ImproperlyConfigured):
            get_llm_config()

    def test_use_command_keeps_custom_local_config_and_is_immediately_effective(self):
        local = self.path.with_suffix('.local.toml')
        local.write_text('# [example] in a comment\n  active_profile="local"\n[profiles.local]\nmodel="custom"\n')
        call_command('llm_config', '--use', 'aws', stdout=io.StringIO())
        self.assertEqual(get_llm_config()['provider'], 'bedrock')
        self.assertEqual(load_config(self.path, profile='local')['default_model'], 'custom')
        call_command('llm_config', '--use', 'local', stdout=io.StringIO())
        self.assertEqual(get_llm_config()['default_model'], 'custom')

    def test_check_api_requires_key_and_does_not_print_it(self):
        with self.assertRaises(CommandError):
            call_command('llm_config', '--profile', 'api', '--check', stdout=io.StringIO())
        output = io.StringIO()
        with patch.dict(os.environ, {'TEST_LLM_KEY': 'test-secret'}):
            call_command('llm_config', '--profile', 'api', '--check', stdout=output)
        self.assertNotIn('test-secret', output.getvalue())
        self.assertIn('présente', output.getvalue())

    def test_environment_override_prevents_misleading_use(self):
        with patch.dict(os.environ, {'LLM_PROFILE': 'local'}):
            with self.assertRaises(CommandError):
                call_command('llm_config', '--use', 'aws', stdout=io.StringIO())
        self.assertFalse(self.path.with_suffix('.local.toml').exists())

    @patch('tracker.services.requests.post')
    def test_ollama_request_schema_limits_and_json_response(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'message': {'content': json.dumps(DATA)}}
        product = _extract_llm_only('x' * 500)
        self.assertEqual(product.price, 42)
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'http://127.0.0.1:11434/api/chat')
        self.assertFalse(kwargs['json']['stream'])
        self.assertEqual(kwargs['json']['options']['num_predict'], 256)
        self.assertEqual(kwargs['timeout'], (5, 7))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertTrue(kwargs['json']['messages'][1]['content'].endswith('x' * 100))
        self.assertNotIn('x' * 101, kwargs['json']['messages'][1]['content'])

    @patch('tracker.services.requests.post')
    def test_api_key_only_in_header_and_payload_uses_plain_model(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'choices': [{'message': {'content': '```json\n' + json.dumps(DATA) + '\n```'}}]}
        with patch.dict(os.environ, {'TEST_LLM_KEY': 'test-secret'}):
            result = _extract_llm_only('HTML', 'api::api-model')
        self.assertEqual(result.product_name, 'Produit')
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://llm.example/v1/chat/completions')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-secret')
        self.assertEqual(kwargs['json']['model'], 'api-model')
        self.assertNotIn('test-secret', json.dumps(kwargs['json']))

    @patch('tracker.services.requests.post')
    def test_missing_api_key_does_not_make_network_request(self, post):
        self.assertIsNone(_extract_llm_only('HTML', 'api::api-model'))
        post.assert_not_called()

    @patch('tracker.services.requests.post')
    def test_local_compatible_server_can_disable_authentication_and_json_mode(self, post):
        self.path.write_text(DOCUMENT.replace('https://llm.example/v1', 'http://127.0.0.1:1234/v1').replace('api_key_env = "TEST_LLM_KEY"', 'require_api_key=false\njson_mode="none"'))
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'choices': [{'message': {'content': json.dumps(DATA)}}]}
        self.assertIsNotNone(_extract_llm_only('HTML', 'api::api-model'))
        kwargs = post.call_args.kwargs
        self.assertNotIn('Authorization', kwargs['headers'])
        self.assertNotIn('response_format', kwargs['json'])

    @patch('tracker.services.requests.post')
    def test_failures_do_not_log_provider_body_or_secrets(self, post):
        post.return_value = Mock(status_code=401, text='test-secret')
        with self.assertLogs('tracker.services', level='WARNING') as logs:
            self.assertIsNone(_extract_llm_only('HTML'))
        self.assertNotIn('test-secret', str(logs.output))
        post.return_value.status_code = 302
        self.assertIsNone(_extract_llm_only('HTML'))

    @patch('tracker.services.requests.post')
    def test_malformed_result_returns_no_product(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'message': {'content': '{"price":"not-a-number"}'}}
        self.assertIsNone(_extract_llm_only('HTML'))

    @patch('tracker.services.boto3.client')
    def test_bedrock_profile_keeps_region_timeout_and_output_budget(self, client):
        client.return_value.converse.return_value = {'output': {'message': {'content': [{'text': json.dumps(DATA)}]}}}
        result = _extract_llm_only('HTML', 'aws::bedrock-model')
        self.assertEqual(result.currency, 'USD')
        self.assertEqual(client.call_args.kwargs['region_name'], 'us-east-1')
        self.assertEqual(client.call_args.kwargs['config'].read_timeout, 7)
        self.assertEqual(client.return_value.converse.call_args.kwargs['modelId'], 'bedrock-model')
        self.assertEqual(client.return_value.converse.call_args.kwargs['inferenceConfig']['maxTokens'], 256)
