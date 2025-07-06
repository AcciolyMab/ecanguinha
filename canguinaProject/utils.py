import os
from django.core.cache import cache
import pandas as pd
import concurrent.futures
import logging
import psutil
from django.contrib import messages
from ecanguinha.services.combustivel import consultar_combustivel
logger = logging.getLogger(__name__)

def testar_redis_em_debug():
    redis_url = os.getenv("REDIS_URL", "NÃO DEFINIDO")
    print(f"DEBUG - REDIS_URL: {redis_url}")
    try:
        cache.set('teste_log', 'valor_log', timeout=60)
        valor = cache.get('teste_log')
        print(f"🧪 Redis funcionando: {valor}")
    except Exception as e:
        print(f"❌ Falha ao acessar Redis em modo DEBUG: {e}")


import logging
from ecanguinha.services.combustivel import consultar_combustivel

logger = logging.getLogger(__name__)

# Função para calcular dinamicamente o número de dias válidos
def calcular_dias_validos_dinamicamente(raio, tipo_combustivel, lat, lon, max_dias=10):
    """
    Tenta encontrar o menor número de dias que retorna dados válidos da API de combustível.
    Itera do menor para o maior (2 até max_dias).
    Retorna None se não encontrar dados dentro do limite.
    """
    # Itera de 2 até o dia máximo para encontrar o menor atraso possível
    for dias in range(2, max_dias + 1):
        logger.info(f"Tentando obter dados de combustível com dias={dias}")
        response = consultar_combustivel(
            tipo_combustivel=tipo_combustivel,
            raio=raio,
            lat=lat,
            lon=lon,
            dias=dias,
        )
        if response and isinstance(response, list) and len(response) > 0:
            logger.info(f"✅ Dados de combustível encontrados com dias={dias}")
            return dias
        else:
            logger.warning(f"⚠️ Nenhum dado de combustível encontrado com dias={dias}")

    # Se o loop terminar sem sucesso, sinaliza a falha
    logger.error(f"❌ Nenhum dado de combustível encontrado em até {max_dias} dias.")
    return None  # Retorna None para indicar falha total


def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
    """
    Função para realizar consultas paralelas à API da SEFAZ com cache, logs e progresso.
    """
    if not request.session.session_key:
        request.session.save()

    resultados = []
    total = len(gtin_list)
    session_key = f"progresso_{request.session.session_key}"

    logger.warning(f"🔑 Chave da sessão: {request.session.session_key}")
    logger.warning(f"📦 Progresso será salvo em: {session_key}")

    if not gtin_list:
        logger.warning("Lista de GTIN está vazia.")
        messages.warning(request, "Lista de GTIN está vazia.")
        return pd.DataFrame()

    max_workers = min(2, len(gtin_list))
    concluídos = 0

    logger.info(f"📊 Uso de memória antes das requisições: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

    # Inicializa progresso no cache
    cache.set(session_key, 0, timeout=300)

    def worker(gtin):
        nonlocal concluídos
        try:
            resultado = consultar_combustivel(
                tipo_combustivel=1,
                raio=raio,
                lat=my_lat,
                lon=my_lon,
                dias=dias,
                gtin=gtin
            )
            return resultado
        except Exception as e:
            logger.warning(f"Erro ao consultar GTIN {gtin}: {e}")
            return None
        finally:
            concluídos += 1
            progresso = int((concluídos / total) * 100)
            cache.set(session_key, progresso, timeout=300)
            logger.warning(f"📊 Progresso atualizado: {progresso}% (GTIN: {gtin})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        resultados = list(executor.map(worker, gtin_list))

    logger.warning("✅ Finalizou obtenção de produtos.")
    return pd.DataFrame([r for r in resultados if r])

def update_progresso_cache(session_key: str, progresso: int):
    """
    Atualiza o progresso no cache com base na chave de sessão.
    """
    cache_key = f"progresso_{session_key}"
    cache.set(cache_key, progresso, timeout=300)
    logger.warning(f"📊 Progresso atualizado: {progresso}% (Chave: {cache_key})")
