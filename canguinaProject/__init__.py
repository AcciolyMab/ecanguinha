# Este __init__.py deve estar no mesmo diretório que o settings.py

# Importa a app Celery para que seja descoberta pelo Django
from .celery import app as celery_app

__all__ = ('celery_app',)