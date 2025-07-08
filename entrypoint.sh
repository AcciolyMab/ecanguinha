#!/bin/sh

# Encerra o script imediatamente se um comando falhar.
set -e

echo "--- EXECUTANDO ENTRYPOINT ---"

echo "--> Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "--> Coletando arquivos estáticos..."
# A opção --clear garante que o diretório de destino seja limpo antes da coleta.
python manage.py collectstatic --noinput --clear

echo "--- ENTRYPOINT FINALIZADO. INICIANDO O SERVIDOR... ---"

# Executa o comando passado como argumentos para este script (o CMD do Dockerfile)
exec "$@"