FROM python:3.11-slim

# Configurações de ambiente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia a aplicação
COPY . .

# Cria o script start.sh que interpreta $PORT corretamente
RUN echo '#!/bin/sh\nexec gunicorn --bind 0.0.0.0:${PORT:-8080} canguinaProject.wsgi:application' > /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8080

# Aqui está a chave: usamos o shell para interpretar $PORT
CMD ["/app/start.sh"]