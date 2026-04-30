# ===============================
# 🚧 Estágio 1: Build das dependências
# ===============================
FROM python:3.10-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ===============================
# 🚀 Estágio 2: Imagem final da aplicação
# ===============================
FROM python:3.10-slim

WORKDIR /app

# Dependências de runtime para o psycopg (Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-root COM diretório home (evita HOME=/nonexistent)
RUN addgroup --system app && \
    adduser --system --group --home /home/app app

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=canguinaProject.settings \
    ENVIRONMENT=production \
    PYTHONPATH="/app" \
    HOME=/home/app \
    XDG_CACHE_HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib

# Instala as dependências pré-compiladas
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copia os arquivos da aplicação
COPY . .

# Garante diretórios graváveis e propriedade correta
RUN mkdir -p /home/app /tmp/matplotlib && \
    chown -R app:app /app /home/app /tmp/matplotlib

# Muda para o usuário não-root
USER app

# Expõe a porta
EXPOSE 8000

# Entrypoint que prepara o ambiente
ENTRYPOINT ["/app/entrypoint.sh"]

# Comando padrão executado pelo entrypoint
# --worker-tmp-dir /dev/shm: heartbeat dos workers em RAM (evita I/O em disco)
CMD ["gunicorn", "canguinaProject.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "120", \
     "--worker-tmp-dir", "/dev/shm"]