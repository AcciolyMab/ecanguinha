#!/bin/sh
exec gunicorn --bind 0.0.0.0:${PORT:-8080} canguinaProject.wsgi:application