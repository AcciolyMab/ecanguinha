import os
from celery import Celery

# Define o módulo de configurações do Django para o Celery.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'canguinaProject.settings')

app = Celery('canguinaProject')

# Usa as configurações do Django. A string 'django.conf:settings' é a forma correta.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega módulos de tarefas de todas as aplicações Django registradas.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')