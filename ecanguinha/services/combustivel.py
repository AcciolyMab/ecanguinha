import logging
import concurrent
import pandas as pd
from django.core.cache import cache
from typing import Optional
import psutil

logger = logging.getLogger(__name__)

def calcular_media_combustivel(df: pd.DataFrame) -> float:
    if df.empty or 'VALOR' not in df.columns:
        logger.warning("⚠️ DataFrame inválido ou sem coluna 'VALOR'.")
        return 0.0

    try:
        df_validos = pd.to_numeric(df['VALOR'], errors='coerce')  # Força conversão
        media = df_validos.dropna().mean()
        media_float = float(round(media, 2)) if not pd.isna(media) else 0.0
        logger.info(f"✅ Média calculada: {media_float}")
        return media_float
    except Exception as e:
        logger.exception(f"Erro ao calcular média do combustível: {e}")
        return 0.0


def consultar_combustivel(tipo_combustivel: int, raio: float, lat: float, lon: float, dias: int) -> Optional[pd.DataFrame]:
    """
    Consulta preços de combustível a partir da base da SEFAZ-AL ou cache local.

    Parâmetros:
        tipo_combustivel (int): Tipo de combustível (1: Gasolina, 2: Etanol, 3: Diesel, etc.)
        raio (float): Raio da busca em quilômetros.
        lat (float): Latitude do ponto de origem.
        lon (float): Longitude do ponto de origem.
        dias (int): Número de dias para busca retroativa.

    Retorno:
        pd.DataFrame: Dados dos postos e preços encontrados.
    """
    cache_key = f"combustivel:{tipo_combustivel}:{raio}:{round(lat, 3)}:{round(lon, 3)}:{dias}"
    logger.info(f"📦 Consultando cache com chave: {cache_key}")

    try:
        resultado = cache.get(cache_key)
        if resultado is not None:
            logger.info("✅ Cache HIT - retornando dados de combustível do Redis.")
            return resultado
        else:
            logger.warning("⚠️ Cache MISS - necessário consultar fonte externa.")
            # Aqui deveria estar a lógica de consulta à API da SEFAZ
            # resultado = consultar_api_sefaz(...)
            # cache.set(cache_key, resultado, timeout=300)
            return pd.DataFrame()  # Simulação provisória
    except Exception as e:
        logger.exception(f"Erro ao consultar combustível: {e}")
        return pd.DataFrame()

def obter_preco_combustivel_por_gtin(gtin, tipo_combustivel, raio, lat, lon, dias):
    """
    Consulta o preço do combustível pelo GTIN, com uso de cache e fallback para média.

    Args:
        gtin (str): Código do produto.
        tipo_combustivel (int): Tipo de combustível (ex: gasolina, etanol).
        raio (int): Raio da busca em km.
        lat (float): Latitude de referência.
        lon (float): Longitude de referência.
        dias (int): Quantidade de dias para busca.

    Returns:
        Tuple[float, dict]: Preço encontrado e dicionário com detalhes do mercado.
    """
    chave_cache = f"gtin:{gtin}:{tipo_combustivel}:{raio}:{round(lat, 3)}:{round(lon, 3)}:{dias}"
    dados_cache = cache.get(chave_cache)

    if dados_cache:
        logger.info(f"✅ GTIN Cache HIT: {chave_cache}")
        return dados_cache["VALOR"], dados_cache

    logger.warning(f"⚠️ GTIN Cache MISS: {chave_cache}")
    df = consultar_combustivel(tipo_combustivel, raio, lat, lon, dias)

    if df.empty:
        logger.warning(f"Nenhum conteúdo encontrado ou resposta inválida para o GTIN {gtin}.")
        return 0.0, {}

    df_filtrado = df[df["GTIN"] == gtin]

    if not df_filtrado.empty:
        linha = df_filtrado.iloc[0].to_dict()
        cache.set(chave_cache, linha, timeout=3600)
        return linha["VALOR"], linha

    media = calcular_media_combustivel(df)
    linha_fallback = df.iloc[0].to_dict()
    linha_fallback["VALOR"] = media
    cache.set(chave_cache, linha_fallback, timeout=3600)
    logger.warning(f"🔄 GTIN {gtin} não encontrado. Usando preço médio como fallback.")
    return media, linha_fallback

def update_progresso_cache(session_key: str, gtin: str, concluido: int, total: int) -> None:
    if not session_key:
        logger.warning("⚠️ Chave de sessão vazia ao atualizar progresso.")
        return

    cache_key = f"progresso_{session_key}"
    progresso = int((concluido / total) * 100)
    cache.set(cache_key, progresso, timeout=300)

def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
    if not request.session.session_key:
        request.session.save()
    resultados = []
    total = len(gtin_list)
    session_key = f"progresso_{request.session.session_key}"

    logger.warning(f"🔑 Chave da sessão: {request.session.session_key}")
    logger.warning(f"📦 Progresso será salvo em: {session_key}")

    if not gtin_list:
        logger.warning("Lista de GTIN está vazia.")
        return pd.DataFrame()

    data_list = []
    max_workers = min(2, len(gtin_list))

    logger.info(f"📊 Uso de memória antes das requisições: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

    cache.set(session_key, 0, timeout=300)
    concluídos = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # lógica da chamada à API e preenchimento de `data_list`
        pass

    return pd.DataFrame(data_list)

