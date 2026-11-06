import os
from pathlib import Path
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost,pcookson.pythonanywhere.com,www.avonmoor.co.uk,avonmoor.co.uk').split(',')

TIME_ZONE = 'Europe/London'

USE_TZ = True

CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in config(
    'CSRF_TRUSTED_ORIGINS', default='https://www.avonmoor.co.uk,https://avonmoor.co.uk'
).split(',') if origin.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'contact',
    'water_survey',
    'water_calculator',
    'office',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'avonmoor.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'avonmoor.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', cast=bool, default=True)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', cast=bool, default=True)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', cast=bool, default=True)

# Email settings
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default='587', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_IMAP_HOST = config(
    'EMAIL_IMAP_HOST',
    default=(EMAIL_HOST.replace('smtp.', 'imap.', 1) if EMAIL_HOST else ''),
)
EMAIL_IMAP_PORT = config('EMAIL_IMAP_PORT', default='993', cast=int)
EMAIL_SENT_FOLDER = config('EMAIL_SENT_FOLDER', default='').strip()
NOTIFICATION_RECIPIENTS = [EMAIL_HOST_USER]
NOTIFICATION_BACKUP_EMAIL = config(
    'NOTIFICATION_BACKUP_EMAIL', default=''
).strip()
if (
    NOTIFICATION_BACKUP_EMAIL
    and NOTIFICATION_BACKUP_EMAIL not in NOTIFICATION_RECIPIENTS
):
    NOTIFICATION_RECIPIENTS.append(NOTIFICATION_BACKUP_EMAIL)

# This browser-visible key must be restricted to Avonmoor web referrers and the
# Maps JavaScript API in Google Cloud Console.
GOOGLE_MAPS_API_KEY = config('GOOGLE_MAPS_API_KEY', default='')

# Read-only Monzo connection used by Avonmoor Office payment reconciliation.
# The credentials belong to a confidential server-side OAuth client.
MONZO_CLIENT_ID = config('MONZO_CLIENT_ID', default='').strip()
MONZO_CLIENT_SECRET = config('MONZO_CLIENT_SECRET', default='').strip()
MONZO_REDIRECT_URI = config('MONZO_REDIRECT_URI', default='').strip()
MONZO_API_BASE_URL = 'https://api.monzo.com'
MONZO_AUTHORIZE_URL = 'https://auth.monzo.com/'


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Europe/London'

USE_I18N = True

USE_TZ = True

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/
STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = config(
    'STATICFILES_STORAGE',
    default='whitenoise.storage.CompressedManifestStaticFilesStorage',
)

# Directory to hold user-uploaded files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'office:dashboard'
LOGOUT_REDIRECT_URL = 'login'
