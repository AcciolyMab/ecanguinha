#!/bin/sh

set -e  # Interrompe em caso de erro

echo "⏳ Aguardando dependências estarem prontas..."

# (Opcional) Espera banco de dados PostgreSQL se necessário — descomente se usar DB externo
# until nc -z $DB_HOST $DB_PORT; do
#   echo "🔄 Aguardando banco de dados em $DB_HOST:$DB_PORT..."
#   sleep 1
# done

echo "✅ Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

echo "🚀 Iniciando serviço: $@"
exec "$@"