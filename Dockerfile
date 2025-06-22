FROM python:3.11-slim

# Configurações
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório de trabalho
WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia tudo, incluindo o start.sh criado
COPY . .

# Dá permissão de execução
RUN chmod +x /app/start.sh

# Exponha uma porta default (Railway sobrescreve com $PORT internamente)
EXPOSE 8080

# Ponto de entrada
CMD ["/app/start.sh"]