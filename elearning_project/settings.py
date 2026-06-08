"""
Django settings for elearning_project project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

# Load environment variables
load_dotenv()

# Sentry Integration (Optional but highly recommended for production)
SENTRY_DSN = os.getenv('SENTRY_DSN')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=True
    )

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-key-not-for-production'
    else:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("SECRET_KEY environment variable is required in production")

# --- Dynamic Host & CSRF Configuration (Render-compatible) ---
# Reads from environment variables — format: comma-separated, no spaces.
_raw_hosts = os.getenv('ALLOWED_HOSTS', '')
_env_hosts = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# Force-include specific authorized portals only (No wildcards for shared domains)
_required_hosts = [
    'edustreamcalicut.onrender.com',
    'neolearner.onrender.com',
    'calicutadmin.onrender.com',
    'localhost',
    '127.0.0.1',
]
ALLOWED_HOSTS = list(set(_env_hosts + _required_hosts))

_raw_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
_env_csrf = [o.strip() for o in _raw_csrf.split(',') if o.strip()]
_required_csrf = [
    'https://edustreamcalicut.onrender.com',
    'https://neolearner.onrender.com',
    'https://calicutadmin.onrender.com',
]
CSRF_TRUSTED_ORIGINS = list(set(_env_csrf + _required_csrf))

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'custom_admin',
    'cloudinary_storage',
    'cloudinary',
    'axes',  # Brute-force protection
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

MIDDLEWARE += [
    'accounts.middleware.PortalSecurityMiddleware',
    'accounts.middleware.EnterpriseHardeningMiddleware',
    'accounts.middleware.SlowQueryMonitorMiddleware',
    'axes.middleware.AxesMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Axes Brute-Force Protection
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]

# Performance & Security Tweaks
DATA_UPLOAD_MAX_MEMORY_SIZE = 20971520  # 20MB (matches view-level check)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880   # 5MB — files larger go to /tmp disk (prevents RAM overflow on Render)
FILE_UPLOAD_TEMP_DIR = '/tmp'           # Ensure temp uploads go to disk, not RAM
RATELIMIT_ENABLE = True

ROOT_URLCONF = 'elearning_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.pending_counts',
            ],
        },
    },
]

WSGI_APPLICATION = 'elearning_project.wsgi.application'


# SSL/Proxy Configuration for Render
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Database
_db_url = os.getenv('DATABASE_URL')
if _db_url:
    DATABASES = {
        'default': dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }



REDIS_URL = os.getenv('REDIS_URL')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    # Fallback to local memory for cache if Redis is not provided
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = 'DENY'

# Browser Compatibility Settings
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_DOMAIN = None
SECURE_REFERRER_POLICY = 'same-origin'

# Stable Session & CSRF Management
# NOTE: SESSION_EXPIRE_AT_BROWSER_CLOSE is False so mobile students stay logged in for 3 hours.
# Admin and Teacher logins override this by calling session.set_expiry(0) manually.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 10800  # 3 hours (prevents mobile login loops for students)
SESSION_SAVE_EVERY_REQUEST = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keeps students logged in when switching apps on mobile
SESSION_COOKIE_NAME = 'neolearner_sessionid'

# Enterprise CSRF Hardening: Store token in session to prevent subdomain clashes
CSRF_USE_SESSIONS = True
CSRF_COOKIE_NAME = 'neolearner_csrftoken'
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv("CLOUDINARY_CLOUD_NAME"),
    'API_KEY': os.getenv("CLOUDINARY_API_KEY"),
    'API_SECRET': os.getenv("CLOUDINARY_API_SECRET"),
    'SECURE': True,
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.CustomUser'

LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'

# Email Configuration (Production-Ready)
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_TIMEOUT = 10  # 10 second timeout to avoid hanging

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', os.getenv('EMAIL_HOST_USER', 'noreply@neolearner.com'))

# Backup Configuration
BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'True') == 'True'
BACKUP_TIME = os.getenv('BACKUP_TIME', '02:00')
BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', '30'))
BACKUP_MAX_RETRIES = int(os.getenv('BACKUP_MAX_RETRIES', '3'))
BACKUP_VERIFY_SHA256 = os.getenv('BACKUP_VERIFY_SHA256', 'True') == 'True'
BACKUP_RESTORE_TEST_DAY = os.getenv('BACKUP_RESTORE_TEST_DAY', 'Sunday')
BACKUP_REPORT_EMAIL = os.getenv('BACKUP_REPORT_EMAIL', '')
BACKUP_DATABASE_FOLDER = os.getenv('BACKUP_DATABASE_FOLDER', 'Database')
BACKUP_SIGNUP_FOLDER = os.getenv('BACKUP_SIGNUP_FOLDER', 'Signup_Proofs')
BACKUP_RESOURCE_FOLDER = os.getenv('BACKUP_RESOURCE_FOLDER', 'Teacher_Resources')

# Production & Security Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'security_file': {
            'class': 'logging.FileHandler',
            'filename': 'security.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.security': {
            'handlers': ['security_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

