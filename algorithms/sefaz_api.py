# algorithms/sefaz_api.py

import requests
import json
import logging
import time
from urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.core.cache import cache
import urllib3
import pandas as pd
import numpy as np
from django.http import JsonResponse
from django.conf import settings
from geopy.distance import geodesic
import os
import concurrent.futures
from math import floor
from math import ceil
import gc
import psutil
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ThreadTimeoutError
from hashlib import md5
from datetime import datetime, timedelta
import pytz  # Adicionado para a função de delay

from django.contrib import messages

LOG_LEVEL = 'DEBUG' if os.getenv('DEBUG', 'False') == 'True' else 'INFO'

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(levelname)s %(asctime)s %(message)s',
    force=True
)
logger = logging.getLogger(__name__)
SEFAZ_URL = "http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa"

# Suprimir warnings de InsecureRequest
urllib3.disable_warnings(InsecureRequestWarning)

# Mapeamento de GTIN para categorias personalizadas e nomes de produtos
category_map = {
    'FEIJAO': (7896006744115, 7893500007715, 7898383101000, 7898907040969, 7898902735167),
    'ARROZ': (7896006716112, 7893500024996, 7896012300213, 7898018160082, 7896084700027),
    'MACARRAO': (7896213005184, 7896532701576, 7896022200879, 7896005030530, 7896016411021),
    'FARINHA MANDIOCA': (7898994092216, 7898902735099, 7898272919211, 7898272919068, 7898277160021),
    'CAFE 250G': (7896005800027, 7898286200039, 7897443410250, 7898286200060, 7898945133012),
    'BOLACHA': (7896213006266, 7896005030356, 7898657832173, 7896003738636, 7891962014982),
    'FLOCAO MILHO': (7896481130106, 7891091010718, 7898366932973, 7898932426042, 7898366930023),
    'MARGARINA': (7894904271733, 7893000979932, 7894904929108, 7891152506815, 7891515901066),
    'MANTEIGA': (7898912485496, 7896596000059, 7896010400885, 7898939253399, 7898043230798),
    'LEITE PO': (7898215152330, 7896051130079, 7898949565017, 7896259410133, 7898403780918),
    'LEITE UHT': (7896259412861, 7898118390860, 7898403782394, 7898387120380, 7896085393488),
    'OLEO DE SOJA': (7891107101621, 7892300001428, 7898247780075, 7896036090244, 7892300030060),
    'ACUCAR CRISTAL': (7896065200072, 7896215300591, 7896065200065, 7897261800011, 7897154430103),
    'OVOS': (7898644760175, 7898903159078, 7897146402064, 7898968933156, 7897146401067),
    'SARDINHA 125G': (7891167021013, 7891167023017, 7891167023024, 7896009301063, 7891167021075)
}

gtin_to_category = {gtin: cat for cat, gtins in category_map.items() for gtin in gtins}
gtin_to_product_name = {gtin: cat for cat, gtins in category_map.items() for gtin in gtins}

SEFAZ_SESSION = requests.Session()
adapter = HTTPAdapter(
    pool_connections=30,
    pool_maxsize=30,
    max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
)
SEFAZ_SESSION.mount("http://", adapter)
SEFAZ_SESSION.mount("https://", adapter)
SEFAZ_SESSION.verify = False
SEFAZ_SESSION.headers.update({
    "Content-Type": "application/json",
    "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
})

def _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias, max_attempts=3):
    lat = round(float(my_lat), 6)
    lon = round(float(my_lon), 6)
    cache_key = f"gtin:{gtin}:{raio}:{lat}:{lon}:{dias}"
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"✅ GTIN Cache HIT: {cache_key}")
        return cached, gtin
    logger.warning(f"⚠️ GTIN Cache MISS: {cache_key}")
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    data = {
        "produto": {"gtin": str(gtin)},
        "estabelecimento": {"geolocalizacao": {"latitude": lat, "longitude": lon, "raio": int(raio)}},
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50
    }
    headers = {"Content-Type": "application/json", "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"}
    for attempt in range(1, max_attempts + 1):
        try:
            # CORREÇÃO: Usa a sessão global pré-configurada
            response = SEFAZ_SESSION.post(url, json=data, headers=headers, timeout=120)
            response.raise_for_status()
            response_json = response.json()
            cache.set(cache_key, response_json, timeout=7200)
            logger.info(f"💾 GTIN Cache SET: {cache_key}")
            return response_json, gtin
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            logger.warning(f"⚠️ Erro ao consultar GTIN {gtin}, tentativa {attempt}: {e}")
            if attempt == max_attempts:
                logger.error(f"❌ Todas as tentativas falharam para GTIN {gtin}")
                return None, gtin
            time.sleep(0.5 * attempt)
        except Exception as e:
            logger.error(f"❌ Erro inesperado para GTIN {gtin}: {e}")
            return None, gtin

def consultar_combustivel(tipo_combustivel, raio, my_lat, my_lon, dias):
    logger.debug(f"🛠️ [consultar_combustivel] tipo_combustivel={tipo_combustivel}, raio={raio}, lat={my_lat}, lon={my_lon}, dias={dias}")
    lat = round(float(my_lat), 3)
    lon = round(float(my_lon), 3)
    cache_key = f"combustivel:{tipo_combustivel}:{raio}:{lat}:{lon}:{dias}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"✅ Cache HIT: {cache_key}")
        return cached_data
    logger.warning(f"⚠️ Cache MISS: {cache_key}")
    tipo_combustivel = int(tipo_combustivel)
    latitude = round(float(lat), 6)
    longitude = round(float(lon), 6)
    raio = int(raio)
    dias = int(dias)
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/combustivel/pesquisa'
    data = {
        "produto": {"tipoCombustivel": tipo_combustivel},
        "estabelecimento": {"geolocalizacao": {"latitude": latitude, "longitude": longitude, "raio": raio}},
        "dias": dias,
        "pagina": 1,
        "registrosPorPagina": 50
    }
    headers = {"Content-Type": "application/json", "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"}
    try:
        # CORREÇÃO: Usa a sessão global pré-configurada
        response = SEFAZ_SESSION.post(url, json=data, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        if "conteudo" not in data or not data["conteudo"]:
            return {"error": "Nenhum dado encontrado"}
        cache.set(cache_key, data, timeout=7200)
        logger.info(f"💾 Cache SET: {cache_key}")
        return data
    except requests.exceptions.Timeout:
        logger.warning(f"⏱️ Timeout na requisição para tipo {tipo_combustivel}")
    except Exception as e:
        logger.error(f"❌ Erro consultando combustível tipo {tipo_combustivel}: {e}")
    return {"error": f"Falha na requisição para tipo {tipo_combustivel}"}

def obter_produtos(session_key_raw, gtin_list, raio, my_lat, my_lon, dias, progress_id):
    total = len(gtin_list)
    session_key = f"progresso_{session_key_raw}_{progress_id}"
    cache.set(session_key, 0, timeout=600)
    logger.warning(f"🔑 Chave da sessão recebida: {session_key_raw}")
    logger.warning(f"📦 Progresso será salvo em: {session_key}")

    if not gtin_list:
        logger.warning("Lista de GTIN está vazia.")
        return {
            "error": "Lista de produtos vazia. Nenhuma busca foi realizada.",
            "gtins": [],
            "dados": []
        }

    data_list = []
    max_workers = min(2, len(gtin_list))
    logger.info(f"📊 Uso de memória antes das requisições: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

    fallback_ativado = False
    cache.set(session_key, 0, timeout=300)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_request_produto_sefaz, gtin, raio, my_lat, my_lon, dias): gtin
            for gtin in gtin_list
        }

        for i, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            gtin = future_map[future]
            try:
                resp_json, used_gtin = future.result()

                # Tenta novamente com dias dinâmicos se resposta estiver vazia
                if (not resp_json or not resp_json.get('conteudo')) and not fallback_ativado:
                    logger.warning(f"⚠️ Nenhum conteúdo para GTIN {gtin} com dias={dias}. Tentando fallback dinâmico.")
                    dias_fallback = calcular_dias_validos_dinamicamente(gtin, raio, my_lat, my_lon)
                    fallback_ativado = True
                    resp_json, used_gtin = _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias_fallback)

                if resp_json and 'conteudo' in resp_json and resp_json['conteudo']:
                    for item in resp_json.get('conteudo', []):
                        produto = item.get('produto', {})
                        estabelecimento = item.get('estabelecimento', {})
                        endereco = estabelecimento.get('endereco', {})
                        item_gtin = produto.get('gtin')
                        if not item_gtin:
                            logger.warning(f"GTIN ausente em item da resposta para GTIN {gtin}.")
                            continue
                        try:
                            data_entry = {
                                'CODIGO_BARRAS': int(item_gtin),
                                'CATEGORIA': gtin_to_category.get(int(item_gtin), "OUTROS"),
                                'PRODUTO': gtin_to_product_name.get(int(item_gtin), "OUTROS"),
                                'VALOR': produto.get('venda', {}).get('valorVenda', 0.0),
                                'CNPJ': estabelecimento.get('cnpj', 'Desconhecido'),
                                'MERCADO': estabelecimento.get('razaoSocial', 'Desconhecido'),
                                'ENDERECO': endereco.get('nomeLogradouro', 'Desconhecido'),
                                'NUMERO': endereco.get('numeroImovel', 'S/N'),
                                'BAIRRO': endereco.get('bairro', 'Desconhecido'),
                                'LAT': endereco.get('latitude', 0.0),
                                'LONG': endereco.get('longitude', 0.0)
                            }
                            data_list.append(data_entry)
                        except Exception as e:
                            logger.error(f"Erro ao processar item com GTIN {item_gtin}: {e}")
                else:
                    logger.warning(f"❌ Conteúdo vazio da SEFAZ para o GTIN {gtin}. Resposta: {resp_json}")
            except Exception as e:
                logger.error(f"Erro ao consultar o GTIN {gtin}: {e}")

            progresso = int((i / total) * 100)
            cache.set(session_key, progresso, timeout=300)
            logger.warning(f"📊 Progresso atualizado: {progresso}% (GTIN: {gtin})")

    if not data_list:
        logger.warning("❌ Nenhum dado retornado ou processado de forma válida.")
        return {
            "error": "Nenhum dado foi retornado pela API da SEFAZ.",
            "sugestao": "Tente aumentar o raio ou o número de dias. Verifique também se os GTINs são válidos.",
            "possiveis_causas": [
                "GTINs sem movimentação recente",
                "Delay da SEFAZ (verifique com verificar_delay_sefaz)",
                "Raio geográfico muito pequeno",
                "GTINs incorretos ou sem venda recente"
            ],
            "gtins_processados": gtin_list,
            "fallback_dinamico_usado": fallback_ativado
        }

    df = pd.DataFrame(data_list)

    for col in ['CODIGO_BARRAS', 'NUMERO']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int32')
    for col in ['VALOR', 'LAT', 'LONG']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float32')
    for col in ['CATEGORIA', 'PRODUTO', 'CNPJ', 'MERCADO', 'ENDERECO', 'BAIRRO']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    logger.info(f"📊 Uso de memória após criar DataFrame: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")
    return df

def obter_combustiveis(tipo_combustivel, raio, my_lat, my_lon, dias):
    logger.debug(f"🚦 [obter_combustiveis] tipo_combustivel={tipo_combustivel} | type={type(tipo_combustivel)} | raio={raio} | lat={my_lat} | lon={my_lon} | dias={dias}")
    response = consultar_combustivel(tipo_combustivel, raio, my_lat, my_lon, dias)
    if not isinstance(response, dict) or 'conteudo' not in response or 'error' in response:
        logger.warning(f"Nenhum dado válido foi retornado para '{tipo_combustivel}'. Erro: {response.get('error', 'Desconhecido')}")
        return pd.DataFrame()
    estabelecimentos = response.get('conteudo', [])
    data_list = []
    for item in estabelecimentos:
        produto = item.get('produto', {})
        estabelecimento = item.get('estabelecimento', {})
        endereco = estabelecimento.get('endereco', {})
        try:
            lat_estab = float(endereco.get('latitude', 0.0))
            lon_estab = float(endereco.get('longitude', 0.0))
            distancia = geodesic((my_lat, my_lon), (lat_estab, lon_estab)).km
            data_entry = {
                'DESCRICAO': produto.get('descricao', 'Desconhecido'),
                'VALOR': produto.get('venda', {}).get('valorVenda', 0.0),
                'CNPJ': estabelecimento.get('cnpj', 'Desconhecido'),
                'MERCADO': estabelecimento.get('razaoSocial', 'Desconhecido'),
                'ENDERECO': endereco.get('nomeLogradouro', 'Desconhecido'),
                'NUMERO': endereco.get('numeroImovel', 'S/N'),
                'BAIRRO': endereco.get('bairro', 'Desconhecido'),
                'LAT': lat_estab,
                'LONG': lon_estab,
                'DISTANCIA_KM': round(distancia, 2),
                'dataVenda': produto.get('venda', {}).get('dataVenda') # Adicionado para verificação de delay
            }
            data_list.append(data_entry)
        except Exception as e:
            logger.error(f"Erro ao processar item para '{tipo_combustivel}': {e}")
    if not data_list:
        logger.warning(f"Nenhum dado processado para '{tipo_combustivel}'. Total de registros recebidos: {len(estabelecimentos)}")
        return pd.DataFrame()
    df = pd.DataFrame(data_list)
    for col in ['VALOR', 'LAT', 'LONG', 'DISTANCIA_KM']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float32')
    for col in ['DESCRICAO', 'CNPJ', 'MERCADO', 'ENDERECO', 'NUMERO', 'BAIRRO']:
        if col in df.columns:
            df[col] = df[col].astype('category')     
    return df

def calcular_dias_validos_dinamicamente(gtin_exemplo, raio, lat, lon, max_dias=10, tipo_combustivel=None):
    for dias in range(2, max_dias + 1):
        try:
            payload = {
                "produto": {"tipoCombustivel": 2},
                "estabelecimento": {"geolocalizacao": {"latitude": lat, "longitude": lon, "raio": int(raio)}},
                "dias": dias,
                "pagina": 1,
                "registrosPorPagina": 20
            }
            # CORREÇÃO: Usa a sessão global pré-configurada
            response = SEFAZ_SESSION.post(
                'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/combustivel/pesquisa',
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                # CORREÇÃO: A chave de resposta correta é 'conteudo'
                if data.get("conteudo"):
                    return dias
        except Exception as e:
            logger.warning(f"❌ Erro na tentativa com {dias} dias: {e}")
        time.sleep(0.5)
    return max_dias

# --- NOVA FUNÇÃO PARA VERIFICAÇÃO DE DELAY ---
def verificar_delay_sefaz(latitude, longitude, raio=5):
    """Verifica o atraso (delay) da API da SEFAZ de forma mais robusta."""
    logger.info(f"Verificando delay da API da SEFAZ para lat={latitude}, lon={longitude}")
    
    fuso_horario_br = pytz.timezone('America/Sao_Paulo')
    
    # Usa a função obter_combustiveis para fazer a chamada à API
    df = obter_combustiveis(tipo_combustivel=1, raio=raio, my_lat=latitude, my_lon=longitude, dias=10)

    if df.empty or 'dataVenda' not in df.columns:
        logger.warning("Verificação de delay: Nenhum dado de combustível ou coluna 'dataVenda' retornado.")
        return 99
    
    logger.debug(f"Amostra de 'dataVenda' recebida para verificação de delay: {df['dataVenda'].dropna().head().tolist()}")

    # O formato da API é ISO 8601 com 'Z' (UTC).
    # O pandas lida com isso automaticamente. O 'utc=True' garante
    # que o objeto datetime resultante seja timezone-aware (UTC).
    datas_venda_utc = pd.to_datetime(df['dataVenda'], utc=True, errors='coerce').dropna()

    if datas_venda_utc.empty:
        logger.error("Verificação de delay: Nenhuma data de venda válida encontrada após a conversão.")
        return 99

    # Pega a data mais recente (já está em UTC)
    data_mais_recente_utc = datas_venda_utc.max()
    
    # Compara com a data atual no fuso horário correto
    data_atual_br = datetime.now(fuso_horario_br)
    
    # Converte a data da API para o fuso do Brasil para comparar as datas (dia/mês/ano)
    delay = (data_atual_br.date() - data_mais_recente_utc.astimezone(fuso_horario_br).date()).days
    
    logger.info(f"API da SEFAZ tem um delay de aproximadamente {delay} dia(s).")
    return int(delay)
