# ===============================
# 🚧 Estágio 1: Build das dependências
# ===============================
FROM python:3.10-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ===============================
# 🚀 Estágio 2: Imagem final da aplicação
# ===============================
FROM python:3.10-slim

WORKDIR /app

# 🔧 Variáveis padrão para ambiente de produção
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=canguinaProject.settings \
    ENVIRONMENT=production

# 📦 Instala dependências Python
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /wheels/*

# 🔒 Copia apenas os diretórios essenciais (mais seguro e performático)
COPY ecanguinha/ ./ecanguinha/
COPY canguinaProject/ ./canguinaProject/
COPY manage.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY entrypoint.sh /entrypoint.sh

# 🔧 Permissão de execução
RUN chmod +x /entrypoint.sh

# 🌐 Expõe a porta do Gunicorn
EXPOSE 8000

# 🚀 Entrypoint padrão
ENTRYPOINT ["/entrypoint.sh"]
