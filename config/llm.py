"""Hot-read LLM profiles. Secrets are resolved from the process environment only."""

import math
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

PROVIDERS = {'bedrock', 'ollama', 'openai-compatible'}
FIELDS = {
    'provider', 'model', 'models', 'model_env', 'base_url', 'base_url_env',
    'api_key_env', 'require_api_key', 'region', 'region_env', 'json_mode',
    'timeout', 'temperature', 'max_tokens', 'max_input_chars',
}
DEFAULTS = {'timeout': 20.0, 'temperature': 0.1, 'max_tokens': 1024, 'max_input_chars': 24000}
NAME = re.compile(r'^[a-zA-Z0-9_-]+$')
ENV_NAME = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _read(path, optional=False):
    try:
        with Path(path).open('rb') as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        if optional:
            return {}
        raise ImproperlyConfigured('Fichier de configuration LLM introuvable.') from None
    except (OSError, tomllib.TOMLDecodeError):
        raise ImproperlyConfigured('Fichier de configuration LLM illisible ou TOML invalide.') from None
    if set(data) - {'active_profile', 'defaults', 'profiles'}:
        raise ImproperlyConfigured('Section LLM inconnue ; utiliser active_profile, defaults ou profiles.')
    if not isinstance(data.get('defaults', {}), dict) or not isinstance(data.get('profiles', {}), dict):
        raise ImproperlyConfigured('defaults et profiles doivent être des tables TOML.')
    for name, profile in data.get('profiles', {}).items():
        if not NAME.fullmatch(name) or name == 'legacy' or not isinstance(profile, dict):
            raise ImproperlyConfigured('Nom ou table de profil LLM invalide.')
        if set(profile) - FIELDS:
            raise ImproperlyConfigured('Option LLM inconnue ; les secrets doivent référencer une variable *_env.')
    if set(data.get('defaults', {})) - set(DEFAULTS):
        raise ImproperlyConfigured('Option defaults LLM inconnue.')
    return data


def read_document(path):
    """Overlay local preferences without changing the shared repository config."""
    document = _read(path)
    local = _read(Path(path).with_suffix('.local.toml'), optional=True)
    return {
        'active_profile': local.get('active_profile', document.get('active_profile', 'legacy')),
        'defaults': {**DEFAULTS, **document.get('defaults', {}), **local.get('defaults', {})},
        'profiles': {
            name: {**document.get('profiles', {}).get(name, {}), **local.get('profiles', {}).get(name, {})}
            for name in document.get('profiles', {}).keys() | local.get('profiles', {}).keys()
        },
    }


def _env_value(profile, field, default=''):
    name = profile.get(f'{field}_env')
    if name is not None and (not isinstance(name, str) or not ENV_NAME.fullmatch(name)):
        raise ImproperlyConfigured('Nom de variable de configuration LLM invalide.')
    value = os.environ.get(name, '') if name else ''
    value = value or profile.get(field, default)
    if not isinstance(value, str):
        raise ImproperlyConfigured('Les noms de modèle, URL et région LLM doivent être des chaînes.')
    return value.strip()


def _legacy(configured):
    def value(key, *names, default=''):
        return configured.get(key) or next((os.environ[n] for n in names if os.environ.get(n)), default)
    model = str(value('default_model', 'LLM_MODEL')).strip()
    models = configured.get('models') or [p.strip() for p in os.environ.get('LLM_MODELS', '').split(',') if p.strip()]
    return {
        'provider': str(value('provider', 'LLM_PROVIDER', default='bedrock')).lower().strip(),
        'default_model': model, 'models': list(models) if isinstance(models, list) else [str(models)],
        'region': value('region', 'AWS_REGION', 'AWS_DEFAULT_REGION', default='us-east-1'),
        'base_url': value('base_url', 'OPENAI_BASE_URL', 'OLLAMA_HOST'),
        'api_key': value('api_key', 'LLM_API_KEY', 'OPENAI_API_KEY'),
        'require_api_key': True, 'json_mode': 'object',
        'access_key_id': value('access_key_id', 'AWS_ACCESS_KEY_ID', 'BEDROCK_ACCESS_KEY_ID'),
        'secret_access_key': value('secret_access_key', 'AWS_SECRET_ACCESS_KEY', 'BEDROCK_SECRET_ACCESS_KEY'),
        'session_token': value('session_token', 'AWS_SESSION_TOKEN', 'BEDROCK_SESSION_TOKEN'),
        'bearer_token': value('bearer_token', 'AWS_BEARER_TOKEN_BEDROCK'),
    }


def _validate(config):
    if not isinstance(config['provider'], str) or config['provider'] not in PROVIDERS:
        raise ImproperlyConfigured('Fournisseur LLM non supporté.')
    if not isinstance(config['default_model'], str) or not config['default_model'].strip():
        raise ImproperlyConfigured('Définir le modèle du profil LLM ou LLM_MODEL en mode legacy.')
    if '::' in config['default_model'] or len(f"{config['profile']}::{config['default_model']}") > 255:
        raise ImproperlyConfigured('Nom de modèle LLM invalide ou trop long.')
    if not isinstance(config['models'], list) or any(not isinstance(m, str) or not m.strip() for m in config['models']):
        raise ImproperlyConfigured('models doit contenir des noms de modèles non vides.')
    if config['default_model'] not in config['models']:
        config['models'].insert(0, config['default_model'])
    for key, low, high in [('timeout', 1, 120), ('temperature', 0, 2), ('max_tokens', 1, 32768), ('max_input_chars', 100, 200000)]:
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ImproperlyConfigured(f'Paramètre LLM {key} hors limites.')
        if key in {'max_tokens', 'max_input_chars'} and not isinstance(value, int):
            raise ImproperlyConfigured(f'Paramètre LLM {key} doit être entier.')
    if not isinstance(config['json_mode'], str) or config['json_mode'] not in {'object', 'none'} or not isinstance(config['require_api_key'], bool):
        raise ImproperlyConfigured('Options de réponse ou authentification LLM invalides.')
    if config['provider'] != 'bedrock':
        if not config['base_url']:
            config['base_url'] = 'http://127.0.0.1:11434' if config['provider'] == 'ollama' else 'https://api.openai.com/v1'
        try:
            url = urlsplit(config['base_url'])
            _ = url.port
        except ValueError:
            raise ImproperlyConfigured('URL de fournisseur LLM invalide.') from None
        loopback = url.hostname in {'localhost', '127.0.0.1', '::1'}
        if not url.hostname or url.username or url.password or url.query or url.fragment or url.scheme not in {'http', 'https'} or (url.scheme == 'http' and not loopback):
            raise ImproperlyConfigured('URL LLM : HTTPS obligatoire, sauf serveur local ; aucun identifiant dans l’URL.')
    return config


def load_config(path, configured=None, reference=None, profile=None):
    document = read_document(path)
    selected_model = None
    if reference is not None:
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 255:
            raise ImproperlyConfigured('Référence de modèle LLM invalide.')
        reference = reference.strip()
    if reference and '::' in reference:
        profile, selected_model = reference.split('::', 1)
        if not selected_model.strip() or '::' in selected_model or len(reference) > 255:
            raise ImproperlyConfigured('Référence de modèle LLM invalide.')
    name = profile or os.environ.get('LLM_PROFILE') or document['active_profile']
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ImproperlyConfigured('Profil LLM actif invalide.')
    defaults = document['defaults']
    if name == 'legacy':
        config = {**defaults, **_legacy(configured or {})}
    else:
        if name not in document['profiles']:
            raise ImproperlyConfigured('Profil LLM demandé introuvable.')
        raw = document['profiles'][name]
        config = {
            **defaults, **{k: v for k, v in raw.items() if k in DEFAULTS},
            'provider': raw.get('provider', ''), 'default_model': _env_value(raw, 'model'),
            'models': raw.get('models', []).copy() if isinstance(raw.get('models', []), list) else raw['models'],
            'base_url': _env_value(raw, 'base_url'), 'region': _env_value(raw, 'region', 'us-east-1'),
            'api_key': _env_value(raw, 'api_key'), 'require_api_key': raw.get('require_api_key', True),
            'json_mode': raw.get('json_mode', 'object'),
            'access_key_id': '', 'secret_access_key': '', 'session_token': '', 'bearer_token': '',
        }
        if config['provider'] == 'bedrock':
            config.update({k: v for k, v in _legacy({}).items() if k in {'access_key_id', 'secret_access_key', 'session_token', 'bearer_token'}})
    config['profile'] = name
    config = _validate(config)
    config['selected_model'] = (selected_model or reference or config['default_model']).strip()
    return config


def model_reference(config):
    return f"{config['profile']}::{config['default_model']}"
