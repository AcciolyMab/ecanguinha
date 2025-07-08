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

# Define variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=canguinaProject.settings \
    ENVIRONMENT=production \
    PYTHONPATH="/app"

# Cria um usuário não-root para rodar a aplicação
RUN addgroup --system app && adduser --system --group app

# Instala as dependências pré-compiladas
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /wheels/*

# Copia os arquivos da aplicação
COPY . .

# Dá a propriedade dos arquivos para o novo usuário
RUN chown -R app:app /app

# Muda para o usuário não-root
USER app

# Expõe a porta
EXPOSE 8000