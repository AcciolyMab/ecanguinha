#!/bin/sh

set -e  # Encerra o script ao primeiro erro

echo "⏳ Aguardando serviços dependentes estarem prontos..."

# (Opcional) Espera por PostgreSQL, se estiver usando
# if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
#   until nc -z "$DB_HOST" "$DB_PORT"; do
#     echo "🔄 Aguardando banco de dados em $DB_HOST:$DB_PORT..."
#     sleep 1
#   done
# fi

# (Opcional) Espera pelo Redis (se quiser aguardar explicitamente)
# if [ -n "$REDIS_URL" ]; then
#   REDIS_HOST=$(echo $REDIS_URL | sed -E 's|redis://([^:/]+).*|\1|')
#   REDIS_PORT=$(echo $REDIS_URL | sed -E 's|.*:([0-9]+)/[0-9]+|\1|')
#   until nc -z "$REDIS_HOST" "$REDIS_PORT"; do
#     echo "🔄 Aguardando Redis em $REDIS_HOST:$REDIS_PORT..."
#     sleep 1
#   done
# fi

echo "✅ Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

echo "🚀 Iniciando serviço: $@"
exec "$@"
