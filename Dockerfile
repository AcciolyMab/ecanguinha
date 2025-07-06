# --- Estágio 1: Builder ---
# Usado para instalar dependências e compilar pacotes.
FROM python:3.10-slim AS builder

# Define o diretório de trabalho
WORKDIR /app

# Previne a criação de arquivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Instala dependências do sistema necessárias para compilar pacotes Python
# e netcat para o script de entrypoint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de requisitos e instala as dependências em um "wheelhouse"
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- Estágio 2: Final ---
# A imagem final que será usada para rodar a aplicação.
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Previne a criação de arquivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE=canguinaProject.settings

# Copia as dependências pré-compiladas do estágio builder
COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt .
# Instala as dependências a partir dos wheels, o que é mais rápido
RUN pip install --no-cache /wheels/*

# Copia o código da aplicação e o script de entrypoint
COPY . .
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Coleta os arquivos estáticos
RUN python manage.py collectstatic --noinput

# Expõe a porta que o Gunicorn vai usar
EXPOSE 8000

# Define o script de entrypoint como o ponto de entrada do contêiner.
# Ele irá executar o comando passado pelo docker-compose (CMD).
ENTRYPOINT ["/entrypoint.sh"]
