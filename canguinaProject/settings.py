"""
Django settings for canguinaProject project.
Gerado por 'django-admin startproject' usando Django 5.1.2. 
"""

import os
import logging
from pathlib import Path
from urllib.parse import urlparse

from decouple import config
import dj_database_url

logger = logging.getLogger(__name__)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "canguinaProject.settings")

BASE_DIR = Path(__file__).resolve().parent.parent

# ========================
# 🔐 SEGURANÇA
# ========================
DEBUG = config('DEBUG', default=False, cast=bool)

# SECRET_KEY: fallback inseguro só em dev; em produção, exige a env var
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-placeholder' if DEBUG else None,
)
if not SECRET_KEY:
    raise ValueError("❌ SECRET_KEY é obrigatória em produção")

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,0.0.0.0,canguinhaal.com.br,www.canguinhaal.com.br,web-production-6a008.up.railway.app",
).split(",")

CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS
    if not host.startswith("0.") and not host.startswith("127.")
]

APPEND_SLASH = True

# ========================
# 🔁 MIDDLEWARE
# ========================
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

ROOT_URLCONF = 'canguinaProject.urls'

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
            'debug': DEBUG,
        },
    },
]

WSGI_APPLICATION = 'canguinaProject.wsgi.application'

# ========================
# 🗄️ BANCO DE DADOS
# ========================
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
    DATABASES['default']['CONN_MAX_AGE'] = 600
    DATABASES['default']['CONN_HEALTH_CHECKS'] = True  # evita OperationalError em conexões inválidas
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ========================
# 🚀 REDIS & CACHE
# ========================
# Uma única REDIS_URL por ambiente.
# Em dev: definida no .env local.
# Em produção (Railway): injetada automaticamente pelo serviço Redis.
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379').strip()

parsed_url = urlparse(REDIS_URL)
if not parsed_url.hostname or not parsed_url.scheme:
    raise ValueError(f"❌ REDIS_URL inválida: {REDIS_URL}")

# URL completa (com auth) para uso interno
RAW_REDIS_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"

# Versão mascarada para logs (não expõe a senha)
_redis_userinfo = f"{parsed_url.username}:***@" if parsed_url.username else ""
_redis_port = f":{parsed_url.port}" if parsed_url.port else ""
REDIS_URL_MASKED = f"{parsed_url.scheme}://{_redis_userinfo}{parsed_url.hostname}{_redis_port}"

logger.warning(
    f"🛠️ Ambiente: {'PRODUÇÃO' if not DEBUG else 'DESENVOLVIMENTO'} "
    f"| Redis em uso: {REDIS_URL_MASKED}"
)

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"{RAW_REDIS_URL}/1",
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SERIALIZER': (
                'django_redis.serializers.pickle.PickleSerializer' if DEBUG
                else 'django_redis.serializers.json.JSONSerializer'
            ),
            # Em produção, falha de cache NÃO derruba a request — só loga.
            # Em dev, queremos ver o erro para corrigir.
            'IGNORE_EXCEPTIONS': not DEBUG,
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 100,
                'socket_timeout': 120
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        }
    }
}

# Sessão híbrida: cache (Redis) + db (Postgres). Se o Redis cair,
# usuários não são deslogados — fonte de verdade é o banco.
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'

# ========================
# 🔐 SENHAS E SEGURANÇA
# ========================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-BR'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# ========================
# 📁 ARQUIVOS ESTÁTICOS E MÍDIA
# ========================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static_custom"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Django 4.2+: usar STORAGES (substitui STATICFILES_STORAGE/DEFAULT_FILE_STORAGE)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ========================
# ✅ APPS INSTALADOS
# ========================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'whitenoise.runserver_nostatic',
    'ecanguinha.apps.EcanguinhaConfig',
]

if DEBUG:
    INSTALLED_APPS += ['django_extensions']

# ========================
# 📦 CELERY CONFIG
# ========================
CELERY_BROKER_URL = f"{RAW_REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{RAW_REDIS_URL}/0"

if not CELERY_BROKER_URL.startswith(('redis://', 'rediss://')):
    raise ValueError(f"❌ CELERY_BROKER_URL inválido: {CELERY_BROKER_URL}")
if not CELERY_RESULT_BACKEND.startswith(('redis://', 'rediss://')):
    raise ValueError(f"❌ CELERY_RESULT_BACKEND inválido: {CELERY_RESULT_BACKEND}")

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Tuning para tarefas longas (ALNS pode levar dezenas de minutos):
CELERY_TASK_ACKS_LATE = True                       # ack só após terminar — não perde tarefa se worker morrer
CELERY_WORKER_PREFETCH_MULTIPLIER = 1               # crítico: 1 tarefa pesada por worker, não acumula fila
CELERY_TASK_REJECT_ON_WORKER_LOST = True            # re-enfileira se worker for morto (OOM, deploy, etc.)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True    # silencia warning do Celery 6+

logger.info(f"🚀 Celery Broker: {REDIS_URL_MASKED}/0")
logger.info(f"🗄️ Celery Backend: {REDIS_URL_MASKED}/0")
logger.info(f"🔧 Cache Redis configurado com: {REDIS_URL_MASKED}/1")

# ========================
# 🪵 LOGGING
# ========================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.template': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'requests': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'redis': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'propagate': False,
        },
        # Seu app — mantém DEBUG em dev, INFO em produção
        'ecanguinha': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    }
}