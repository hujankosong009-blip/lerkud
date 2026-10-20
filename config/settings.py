import os
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY through the environment.')
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'service']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[], 'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','service.context_processors.branding']}}]
WSGI_APPLICATION = 'config.wsgi.application'
url = os.getenv('DATABASE_URL')
if url:
    u = urlparse(url)
    if u.scheme not in ('postgres', 'postgresql'):
        raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL.')
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':unquote(u.path.lstrip('/')),'USER':unquote(u.username or ''),'PASSWORD':unquote(u.password or ''),'HOST':u.hostname or parse_qs(u.query).get('host', [''])[0],'PORT':u.port or 5432,'CONN_MAX_AGE':60, 'OPTIONS': {'sslmode':os.getenv('DB_SSLMODE', 'verify-full')}}}
else:
    if not DEBUG:
        raise ImproperlyConfigured('Production requires a PostgreSQL DATABASE_URL.')
    DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':os.getenv('DJANGO_SQLITE_PATH', str(BASE_DIR / 'db.sqlite3'))}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'id'
TIME_ZONE = 'Asia/Jakarta'
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = 'DENY'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
DASHBOARD_URL = os.getenv('DASHBOARD_URL', '')
NOTIFICATION_MODE = os.getenv('NOTIFICATION_MODE', 'simulation')
NOTIFICATION_CHANNEL = os.getenv('NOTIFICATION_CHANNEL', 'bot')
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID', '')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')
TELEGRAM_SESSION = os.getenv('TELEGRAM_SESSION', '')
STALE_DAYS = int(os.getenv('STALE_DAYS', '7'))
# Do not log incoming updates, request bodies, database parameters or Telegram URLs.
LOGGING = {'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'}},'loggers':{'django.db.backends':{'handlers':['console'],'level':'CRITICAL','propagate':False}}}

CSRF_TRUSTED_ORIGINS = [x for x in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS','').split(',') if x]
if os.getenv('DJANGO_TRUST_PROXY_HTTPS','false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
