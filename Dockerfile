# Imagem base com Python 3.11.9
FROM python:3.11.9-slim

# Evita prompts durante instalação de pacotes
ENV DEBIAN_FRONTEND=noninteractive

# Diretório de trabalho
WORKDIR /app

# Copia o requirements.txt e instala dependências
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

# Variável de ambiente padrão para Django
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expõe a porta (usada localmente ou por $PORT via CMD)
EXPOSE 8000

# Comando para iniciar o Gunicorn (usa $PORT se disponível, ou 8000)
CMD gunicorn canguinaProject.wsgi:application --bind 0.0.0.0:${PORT:-8000}
