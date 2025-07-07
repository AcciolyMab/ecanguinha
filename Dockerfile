# ===============================
# 🚧 Estágio 1: Build das dependências
# ===============================
FROM python:3.10-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=canguinaProject.settings

# Instala apenas o necessário
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /wheels/*

# Copia todo o projeto
COPY . .

# Copia e torna o entrypoint executável
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expõe a porta usada pelo Gunicorn
EXPOSE 8000

# Ponto de entrada padrão
ENTRYPOINT ["/entrypoint.sh"]
