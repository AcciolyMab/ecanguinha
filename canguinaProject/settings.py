"""
Django settings for canguinaProject project.

Generated by 'django-admin startproject' using Django 5.1.2.
"""

from pathlib import Path
import dj_database_url
import os
from decouple import config
import logging
logger = logging.getLogger(__name__)
from django.core.cache import cache

try:
    cache.set('teste_log', 'valor_log', timeout=60)
    valor = cache.get('teste_log')
    print(f"Valor do cache: {valor}")  # Deve mostrar 'valor_log'
except Exception as e:
    print(f"Erro ao acessar o cache: {e}")


# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent
print("DEBUG - REDIS_URL_PROD:", os.getenv("REDIS_URL_PROD"))
# Chave Secreta
SECRET_KEY = config('SECRET_KEY', default='django-insecure-o!f&%cc+m5r#4atn@28$b%dve1477nvc((4k^%3uxyde)w1+_5')

# Debug Mode
DEBUG = config('DEBUG', default=False, cast=bool)

ASGI_APPLICATION = None

# Allowed Hosts
### ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.herokuapp.com', 'canguinhaal.com.br', 'www.canguinhaal.com.br']
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.herokuapp.com',
    'canguinhaal.com.br',
    'www.canguinhaal.com.br',
    'web-production-6a008.up.railway.app',
    '.railway.app'
]

APPEND_SLASH = False

# Application Definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ecanguinha.apps.EcanguinhaConfig',
    'whitenoise.runserver_nostatic',  # Whitenoise para arquivos estáticos
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Whitenoise para servir arquivos estáticos
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

# Configuração de Cache com Django-Redis
if DEBUG:  # Ambiente local
    # Configuração de Cache com Django-Redis
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'SERIALIZER': 'django_redis.serializers.pickle.PickleSerializer',
                'IGNORE_EXCEPTIONS': DEBUG,
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 100,
                    'socket_timeout': 20
                }
            }
        }
    }
else:  # Ambiente de Produção
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL_PROD'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
                'IGNORE_EXCEPTIONS': True,
            }
        }
    }

# Configuração para usar o Redis como backend de sessão
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Configuração de Banco de Dados usando SQLite para todos os ambientes
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Validação de Senha
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internacionalização
LANGUAGE_CODE = 'pt-BR'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Redirecionamento para HTTPS em produção
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Arquivos Estáticos e Mídia
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "ecanguinha/static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Configuração para Whitenoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Configurações adicionais
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',  # Mudança de DEBUG para WARNING
    },
    'django': {
        'handlers': ['console'],
        'level': 'WARNING',  # Mudança de INFO para WARNING
        'propagate': True,
    },
    'urllib3': {
        'handlers': ['console'],
        'level': 'ERROR',
        'propagate': False,
    },
    'requests': {
        'handlers': ['console'],
        'level': 'ERROR',
        'propagate': False,
    },
}
