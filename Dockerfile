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

# 🔧 Variáveis padrão para produção
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=canguinaProject.settings \
    ENVIRONMENT=production \
    PYTHONPATH="/app"

# 📦 Instala dependências
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /wheels/*

# 🔒 Copia apenas os diretórios essenciais
COPY ecanguinha/ ./ecanguinha/
COPY canguinaProject/ ./canguinaProject/
COPY algorithms/ ./algorithms/
COPY templates/ ./templates/
COPY manage.py .
COPY entrypoint.sh /entrypoint.sh

# 🧹 (Opcional) Remove arquivos de build para manter imagem leve
# RUN rm -rf /wheels

# 🔧 Permissões
RUN chmod +x /entrypoint.sh

# 🌐 Porta do Gunicorn
EXPOSE 8000

# 🚀 Entrypoint padrão
ENTRYPOINT ["/entrypoint.sh"]
