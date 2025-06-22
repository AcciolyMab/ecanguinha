# Imagem base com Python
FROM python:3.11-slim

# Evita criação de .pyc e força log no console
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8080

# Diretório de trabalho no container
WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia o restante do projeto
COPY . /app

# Cria script de inicialização para o gunicorn
RUN echo '#!/bin/sh\nexec gunicorn --bind 0.0.0.0:${PORT:-8080} canguinaProject.wsgi:application' > /app/start.sh
RUN chmod +x /app/start.sh

# Expõe a porta esperada pelo Railway (ou usa $PORT do ambiente)
EXPOSE 8080

# Comando padrão que será executado no container
CMD ["/app/start.sh"]