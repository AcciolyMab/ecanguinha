# Imagem base com Python leve
FROM python:3.11-slim

# Variáveis de ambiente básicas
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório onde o código vai rodar no container
WORKDIR /app

# Instala o pip e dependências
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia todos os arquivos da aplicação
COPY . .

# Dá permissão de execução ao script de inicialização
RUN chmod +x /app/start.sh

# Exponha uma porta padrão (Railway vai sobrescrever com $PORT)
EXPOSE 8080

# Ponto de entrada: script que expande $PORT corretamente
CMD ["/app/start.sh"]