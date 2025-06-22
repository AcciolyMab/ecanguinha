#!/bin/sh

if [ -z "$PORT" ]; then
  echo "ERRO: A variável \$PORT não está definida!"
  exit 1
fi

exec gunicorn --bind 0.0.0.0:$PORT canguinaProject.wsgi:application