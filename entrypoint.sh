#!/bin/sh

# Encerra o script imediatamente se um comando falhar.
set -e

echo "⏳ Preparando o ambiente da aplicação..."

# 🐢 (Opcional) Aguarda serviços como banco/redis
# if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
#   until nc -z "$DB_HOST" "$DB_PORT"; do
#     echo "🔄 Aguardando banco de dados em $DB_HOST:$DB_PORT..."
#     sleep 1
#   done
# fi

echo "📦 Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "🧼 Limpando arquivos estáticos antigos..."
rm -rf /app/staticfiles/

echo "🎯 Coletando arquivos estáticos com --clear..."
python manage.py collectstatic --noinput --clear

echo "📂 Verificando arquivos coletados..."
find /app/staticfiles -type f | sort | grep -E 'canguinhalogo_oficial|styles.css|\.png|\.css|\.js' || echo "⚠️ Nenhum arquivo estático encontrado!"

echo "✅ Ambiente pronto! Iniciando o servidor..."

# Executa o comando principal (gunicorn, celery, etc.)
exec "$@"
