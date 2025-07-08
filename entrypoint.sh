#!/bin/sh

# Encerra o script imediatamente se um comando falhar.
set -e

echo "⏳ Preparando o ambiente da aplicação..."

echo "📦 Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "🎯 Coletando arquivos estáticos..."
# O comando --clear já lida com a limpeza do diretório de destino de forma segura.
# Remover os comandos 'rm' e 'mkdir' manuais torna o processo mais robusto.
python manage.py collectstatic --noinput --clear

echo "📂 Verificando arquivos coletados..."
# Esta verificação continua sendo uma boa prática.
find /app/staticfiles -type f | sort | grep -E 'canguinhalogo_oficial|styles.css|\.png|\.css|\.js' || echo "⚠️ Nenhum arquivo estático encontrado!"

echo "✅ Ambiente pronto! Iniciando o servidor..."

# Executa o comando principal (gunicorn, celery, etc.)
exec "$@"