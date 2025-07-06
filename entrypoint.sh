#!/bin/sh

# O entrypoint é um script que executa antes do comando principal do contêiner.
# É útil para tarefas de inicialização, como esperar o banco de dados e aplicar migrações.

# Neste exemplo simples, vamos apenas aplicar as migrações.
# Em um projeto real, você adicionaria aqui um loop para esperar o banco de dados (Postgres, etc.)
# ficar disponível antes de continuar.

echo "Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

# O comando 'exec "$@"' executa o comando que foi passado para o contêiner.
# Por exemplo, no serviço 'web', ele executará 'gunicorn ...'
# No serviço 'worker', ele executará 'celery ...'
exec "$@"
