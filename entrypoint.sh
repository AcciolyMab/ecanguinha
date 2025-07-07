#!/bin/sh

# Encerra o script imediatamente se um comando falhar.
set -e

echo "⏳ Preparando o ambiente da aplicação..."

# A lógica abaixo (comentada) é uma ótima prática para aguardar
# por serviços como banco de dados ou Redis. Para usá-la,
# garanta que 'netcat' esteja instalado no seu Dockerfile final.
# Ex: RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*
#
# if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
#   until nc -z "$DB_HOST" "$DB_PORT"; do
#     echo "🔄 Aguardando banco de dados em $DB_HOST:$DB_PORT..."
#     sleep 1
#   done
# fi

echo "📦 Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

# A flag --clear garante que arquivos estáticos antigos sejam removidos.
echo "🎯 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

echo "✅ Ambiente pronto. Iniciando a aplicação..."

# Executa o comando principal passado para o contêiner (gunicorn, celery, etc.).
exec "$@"
