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

# Variável de ambiente padrão para Django
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Comando para iniciar o Gunicorn (usa $PORT se disponível, ou 8000)
CMD ["gunicorn", "canguinaProject.wsgi:application", "--host", "0.0.0.0", "--port", "8000"]