# Imagem base com Python 3.10
FROM python:3.10-slim

# Diretório de trabalho
WORKDIR /app

# Copia o requirements.txt e instala dependências
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

# Coleta arquivos estáticos para a pasta `staticfiles/`
RUN python manage.py collectstatic --noinput

# Variável de ambiente padrão para Django
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s \
  CMD curl -f http://localhost:8000/ || exit 1


# Expõe a porta 8000 (usada pelo Gunicorn)
EXPOSE 8000

# Comando para iniciar o Gunicorn (usa $PORT se disponível, ou 8000)
CMD sh -c "gunicorn canguinaProject.wsgi:application --bind 0.0.0.0:${PORT:-8000} --timeout 720 --keep-alive 600 --log-level debug"
