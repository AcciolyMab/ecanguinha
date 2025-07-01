import os
from django.core.cache import cache

def testar_redis_em_debug():
    redis_url = os.getenv("REDIS_URL", "NÃO DEFINIDO")
    print(f"DEBUG - REDIS_URL: {redis_url}")
    try:
        cache.set('teste_log', 'valor_log', timeout=60)
        valor = cache.get('teste_log')
        print(f"🧪 Redis funcionando: {valor}")
    except Exception as e:
        print(f"❌ Falha ao acessar Redis em modo DEBUG: {e}")
