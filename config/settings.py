import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    if not path.exists(): return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key, value = line.split('=', 1); key = key.strip(); value = value.strip().strip('"').strip("'")
        if key: os.environ.setdefault(key, value)


def _split_csv(value): return [part.strip() for part in (value or '').split(',') if part.strip()]

_load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', '1').lower() in {'1', 'true', 'yes', 'on'}
ALLOWED_HOSTS = _split_csv(os.environ.get('DJANGO_ALLOWED_HOSTS')) or ['127.0.0.1', 'localhost']
CSRF_TRUSTED_ORIGINS = _split_csv(os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS'))

INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','tracker']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'

LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'bedrock').strip().lower()
LLM_MODEL = os.environ.get('LLM_MODEL', '').strip()
if not LLM_MODEL: raise ImproperlyConfigured('LLM_MODEL must be set in .env.')
LLM_MODELS = _split_csv(os.environ.get('LLM_MODELS')) or [LLM_MODEL]
if LLM_MODEL not in LLM_MODELS: LLM_MODELS.insert(0, LLM_MODEL)
LLM_CONFIG = {'provider':LLM_PROVIDER,'default_model':LLM_MODEL,'models':LLM_MODELS,'region':os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION','us-east-1')).strip(),'access_key_id':os.environ.get('AWS_ACCESS_KEY_ID', os.environ.get('BEDROCK_ACCESS_KEY_ID','')).strip(),'secret_access_key':os.environ.get('AWS_SECRET_ACCESS_KEY', os.environ.get('BEDROCK_SECRET_ACCESS_KEY','')).strip(),'session_token':os.environ.get('AWS_SESSION_TOKEN','').strip(),'bearer_token':os.environ.get('AWS_BEARER_TOKEN_BEDROCK','').strip(),'base_url':os.environ.get('OPENAI_BASE_URL','').strip()}

LISTING_STALE_DAYS = int(os.environ.get('LISTING_STALE_DAYS','30'))
MARKET_COVERAGE_TARGET = int(os.environ.get('MARKET_COVERAGE_TARGET','3'))
CATALOG_CACHE_MINUTES = int(os.environ.get('CATALOG_CACHE_MINUTES','60'))
CATALOG_CACHE_MIN_CONFIDENCE = float(os.environ.get('CATALOG_CACHE_MIN_CONFIDENCE','0.70'))
SCRAPE_QUEUE_SYNC_FALLBACK = os.environ.get('SCRAPE_QUEUE_SYNC_FALLBACK','0').lower() in {'1','true','yes','on'}
SCRAPE_JOB_MAX_ATTEMPTS = int(os.environ.get('SCRAPE_JOB_MAX_ATTEMPTS','3'))
SCRAPE_JOB_RETRY_BASE_SECONDS = int(os.environ.get('SCRAPE_JOB_RETRY_BASE_SECONDS','5'))
SCRAPE_JOB_STALE_SECONDS = int(os.environ.get('SCRAPE_JOB_STALE_SECONDS','120'))
SCRAPE_JOB_MAX_BACKOFF_SECONDS = int(os.environ.get('SCRAPE_JOB_MAX_BACKOFF_SECONDS','300'))
SCRAPE_FETCH_TIMEOUT = float(os.environ.get('SCRAPE_FETCH_TIMEOUT','8'))
SCRAPE_FETCH_CONNECT_TIMEOUT = float(os.environ.get('SCRAPE_FETCH_CONNECT_TIMEOUT','3'))
SCRAPE_FETCH_MAX_ATTEMPTS = int(os.environ.get('SCRAPE_FETCH_MAX_ATTEMPTS','2'))
SCRAPE_FETCH_BACKOFF_SECONDS = float(os.environ.get('SCRAPE_FETCH_BACKOFF_SECONDS','0.75'))
SCRAPE_DOMAIN_MIN_INTERVAL_SECONDS = float(os.environ.get('SCRAPE_DOMAIN_MIN_INTERVAL_SECONDS','0.5'))
SCRAPE_MAX_WORKERS = int(os.environ.get('SCRAPE_MAX_WORKERS','4'))
SCRAPE_DOMAIN_LOCK_TIMEOUT = int(os.environ.get('SCRAPE_DOMAIN_LOCK_TIMEOUT','30'))
SCRAPE_DOMAIN_BUSY_DELAY = int(os.environ.get('SCRAPE_DOMAIN_BUSY_DELAY','2'))
SCRAPE_DOMAIN_LOCK_DIR = os.environ.get('SCRAPE_DOMAIN_LOCK_DIR','').strip()
DOMAIN_FETCH_CIRCUIT_MINUTES = int(os.environ.get('DOMAIN_FETCH_CIRCUIT_MINUTES','10'))
ADAPTIVE_MAX_SCRAPE_JOBS = int(os.environ.get('ADAPTIVE_MAX_SCRAPE_JOBS','15'))
ADAPTIVE_INITIAL_SCRAPE_JOBS = int(os.environ.get('ADAPTIVE_INITIAL_SCRAPE_JOBS','8'))
ADAPTIVE_EXPANSION_SCRAPE_JOBS = int(os.environ.get('ADAPTIVE_EXPANSION_SCRAPE_JOBS','5'))
ADAPTIVE_BATCH_WAIT_SECONDS = float(os.environ.get('ADAPTIVE_BATCH_WAIT_SECONDS','8'))
ADAPTIVE_BATCH_POLL_SECONDS = float(os.environ.get('ADAPTIVE_BATCH_POLL_SECONDS','0.5'))
ADAPTIVE_MAX_FAILURES_PER_DOMAIN = int(os.environ.get('ADAPTIVE_MAX_FAILURES_PER_DOMAIN','2'))
ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN = int(os.environ.get('ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN','3'))
DDGS_SEARCH_TIMEOUT = int(os.environ.get('DDGS_SEARCH_TIMEOUT','8'))

DB_ENGINE = os.environ.get('DB_ENGINE','sqlite').strip().lower()
if DB_ENGINE in {'postgres','postgresql','psql'}:
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('POSTGRES_DB','bendango'),'USER':os.environ.get('POSTGRES_USER','bendango'),'PASSWORD':os.environ.get('POSTGRES_PASSWORD',''),'HOST':os.environ.get('POSTGRES_HOST','127.0.0.1'),'PORT':os.environ.get('POSTGRES_PORT','5432'),'CONN_MAX_AGE':int(os.environ.get('POSTGRES_CONN_MAX_AGE','60')),'OPTIONS':{'connect_timeout':int(os.environ.get('POSTGRES_CONNECT_TIMEOUT','5'))}}}
else: DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'db.sqlite3'}}

REDIS_URL=os.environ.get('REDIS_URL','').strip()
if REDIS_URL:
    CACHES={'default':{'BACKEND':'django_redis.cache.RedisCache','LOCATION':REDIS_URL,'OPTIONS':{'CLIENT_CLASS':'django_redis.client.DefaultClient','SOCKET_CONNECT_TIMEOUT':float(os.environ.get('REDIS_CONNECT_TIMEOUT','2')),'SOCKET_TIMEOUT':float(os.environ.get('REDIS_SOCKET_TIMEOUT','2')),'IGNORE_EXCEPTIONS':False},'KEY_PREFIX':os.environ.get('REDIS_KEY_PREFIX','bendango'),'TIMEOUT':int(os.environ.get('REDIS_DEFAULT_TIMEOUT','300'))}}
else: CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'bendango-local-cache'}}

SEARCH_RUN_DISCOVERY_TIMEOUT=int(os.environ.get('SEARCH_RUN_DISCOVERY_TIMEOUT','300'))
SEARCH_RUN_EXECUTION_TIMEOUT=int(os.environ.get('SEARCH_RUN_EXECUTION_TIMEOUT','60'))
# Merchant discovery gets a smaller child-process budget so a blocked web-search
# call cannot consume the entire SearchRun. The remaining time is reserved for
# best-effort enrichment and deterministic finalization.
SEARCH_RUN_MERCHANT_TIMEOUT=int(os.environ.get('SEARCH_RUN_MERCHANT_TIMEOUT','45'))

AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='en-us'; TIME_ZONE='UTC'; USE_I18N=True; USE_TZ=True; STATIC_URL='static/'
DEFAULT_SEARCH_COUNTRY=os.environ.get('DEFAULT_SEARCH_COUNTRY','RDC')
LOCAL_SEARCH_DOMAINS=_split_csv(os.environ.get('LOCAL_SEARCH_DOMAINS')) or ['drcmart.com','mobile-rdc.com']
MAILERS={'default':{'BACKEND':'django.core.mail.backends.console.EmailBackend'}}
