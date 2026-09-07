import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

def get_env_bool(name, default=False):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {'1','true','yes','on'}

def _split_csv(value):
    return [part.strip() for part in (value or '').split(',') if part.strip()]

DEBUG = get_env_bool('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG: SECRET_KEY = 'dev-secret-key-change-me'
    else: raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set in production.')
ALLOWED_HOSTS = _split_csv(os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1'))
CSRF_TRUSTED_ORIGINS = _split_csv(os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS'))
if DEBUG:
    SECURE_SSL_REDIRECT = SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False
else:
    SECURE_SSL_REDIRECT = get_env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = get_env_bool('DJANGO_SESSION_COOKIE_SECURE', True)
    CSRF_COOKIE_SECURE = get_env_bool('DJANGO_CSRF_COOKIE_SECURE', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = True

LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'bedrock')
LLM_MODELS = _split_csv(os.environ.get('LLM_MODELS'))
LLM_DEFAULT_MODEL = LLM_MODELS[0] if LLM_MODELS else (os.environ.get('LLM_MODEL') or 'google.gemma-3-12b-it')
LLM_MODELS = LLM_MODELS or [LLM_DEFAULT_MODEL]
LLM_CONFIG = {'provider': LLM_PROVIDER, 'default_model': LLM_DEFAULT_MODEL, 'models': LLM_MODELS, 'region': os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1', 'access_key_id': os.environ.get('AWS_ACCESS_KEY_ID') or '', 'secret_access_key': os.environ.get('AWS_SECRET_ACCESS_KEY') or '', 'session_token': os.environ.get('AWS_SESSION_TOKEN') or ''}

INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','tracker']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'

# SQLite remains the zero-config development database. Production can switch to PostgreSQL with DB_ENGINE=postgresql.
if os.environ.get('DB_ENGINE', '').lower() in {'postgres', 'postgresql'}:
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('DB_NAME','bendango'),'USER':os.environ.get('DB_USER','bendango'),'PASSWORD':os.environ.get('DB_PASSWORD',''),'HOST':os.environ.get('DB_HOST','localhost'),'PORT':os.environ.get('DB_PORT','5432'),'CONN_MAX_AGE':60}}
else:
    DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR / 'db.sqlite3'}}

AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Kinshasa'
USE_I18N = USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_SEARCH_COUNTRY = os.environ.get('DEFAULT_SEARCH_COUNTRY', 'RDC')
LOCAL_SEARCH_DOMAINS = _split_csv(os.environ.get('LOCAL_SEARCH_DOMAINS')) or ['drcmart.com','mobile-rdc.com']
LISTING_STALE_DAYS = int(os.environ.get('LISTING_STALE_DAYS', '30'))
BENDANGO_FX_RATES = {'USD': os.environ.get('FX_USD_PER_USD', '1'), 'CDF': os.environ.get('FX_CDF_PER_USD', '2800'), 'EUR': os.environ.get('FX_EUR_PER_USD', '0.86')}
MAILERS = {'default': {'BACKEND':'django.core.mail.backends.console.EmailBackend'}}
