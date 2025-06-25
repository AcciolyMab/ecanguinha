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
from geopy.distance import geodesic
import os
import concurrent.futures
from math import floor
from math import ceil
import gc  # opcional se quiser forçar liberação de memória
import time
import gc
import psutil
import pandas as pd
import logging



from django.contrib import messages

LOG_LEVEL = 'DEBUG' if os.getenv('DEBUG', 'False') == 'True' else 'INFO'

# # Define um valor padrão, mas permite sobrescrever via variável de ambiente
# DEFAULT_MAX_WORKERS_PRODUCTS = 2
# MAX_WORKERS_PRODUCTS = int(os.getenv('MAX_WORKERS_PRODUCTS', str(DEFAULT_MAX_WORKERS_PRODUCTS)))

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(levelname)s %(asctime)s %(message)s',
    force=True  # 🔥 força reconfiguração mesmo se já tiver sido setado
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
    'CAFE 250G': (7896005800027, 7896224808101, 7896224803069, 7898286200060, 7896005213018),
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

# Dicionário invertido para mapeamento rápido de GTIN -> categoria e nome
gtin_to_category = {}
gtin_to_product_name = {}

for category, gtins in category_map.items():
    for gtin in gtins:
        gtin_to_category[gtin] = category
        gtin_to_product_name[gtin] = category

# Criamos uma sessão global para reaproveitar conexões
SEFAZ_SESSION = requests.Session()

# Configura o adaptador HTTP com controle de pool e retry
adapter = HTTPAdapter(
    pool_connections=30,
    pool_maxsize=30,
    max_retries=Retry(
        total=3,                # Tenta 3 vezes em caso de erro
        backoff_factor=0.3,     # Atraso progressivo entre tentativas
        status_forcelist=[500, 502, 503, 504]  # Somente para esses erros
    )
)

SEFAZ_SESSION.mount("http://", adapter)
SEFAZ_SESSION.mount("https://", adapter)

# Configurações adicionais da sessão
SEFAZ_SESSION.verify = False
SEFAZ_SESSION.headers.update({
    "Content-Type": "application/json",
    "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
})

# ------------------------------------------------------------------------------
# Definição da função auxiliar síncrona (não altere o nome):
def _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias):
    """
    Função auxiliar que faz a requisição para a API SEFAZ usando a sessão global.
    Retorna (response_json, gtin) ou lança exceção em caso de erro HTTP.
    """
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    data = {
        "produto": {"gtin": str(gtin)},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": float(my_lat),
                "longitude": float(my_lon),
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50
    }
    resp = SEFAZ_SESSION.post(url, json=data)
    resp.raise_for_status()
    return resp.json(), gtin

# def _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias, max_attempts=3):
#     # 🔹 Arredonda coordenadas para evitar fragmentação de cache
#     lat = round(float(my_lat), 3)
#     lon = round(float(my_lon), 3)

#     # 🔹 Cria chave única para o cache
#     cache_key = f"gtin:{gtin}:{raio}:{lat}:{lon}:{dias}"
#     cached = cache.get(cache_key)
#     if cached:
#         logger.info(f"✅ GTIN Cache HIT: {cache_key}")
#         return cached, gtin

#     logger.warning(f"⚠️ GTIN Cache MISS: {cache_key}")

#     url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
#     data = {
#         "produto": {"gtin": str(gtin)},
#         "estabelecimento": {
#             "geolocalizacao": {
#                 "latitude": lat,
#                 "longitude": lon,
#                 "raio": int(raio)
#             }
#         },
#         "dias": int(dias),
#         "pagina": 1,
#         "registrosPorPagina": 50
#     }


#     for attempt in range(1, max_attempts + 1):
#         try:
#             resp = SEFAZ_SESSION.post(url, json=data, timeout=30)
#             resp.raise_for_status()
#             response_json = resp.json()

#             # 🔸 Salva no cache por 2 horas
#             cache.set(cache_key, response_json, timeout=60 * 60 * 2)
#             return response_json, gtin

#         except (requests.exceptions.Timeout, 
#                 requests.exceptions.ConnectionError, 
#                 requests.exceptions.HTTPError) as e:
#             logger.warning(f"⚠️ Erro ao consultar GTIN {gtin}, tentativa {attempt}: {e}")
            
#             if attempt == max_attempts:
#                 logger.error(f"❌ Todas as tentativas falharam para GTIN {gtin}")
#                 return None, gtin  # ou `raise` se quiser parar o fluxo

#             time.sleep(0.5 * attempt)


# def _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias, max_attempts=3):
#     cache_key = f"gtin:{gtin}:{raio}:{my_lat}:{my_lon}:{dias}"
#     cached = cache.get(cache_key)
#     if cached:
#         logger.info(f"✅ GTIN Cache HIT: {cache_key}")
#         return cached, gtin

#     logger.info(f"⚠️ GTIN Cache MISS: {cache_key}")

#     url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
#     data = {
#         "produto": {"gtin": str(gtin)},
#         "estabelecimento": {
#             "geolocalizacao": {
#                 "latitude": float(my_lat),
#                 "longitude": float(my_lon),
#                 "raio": int(raio)
#             }
#         },
#         "dias": int(dias),
#         "pagina": 1,
#         "registrosPorPagina": 300
#     }

#     for attempt in range(1, max_attempts + 1):
#         try:
#             resp = SEFAZ_SESSION.post(url, json=data)
#             resp.raise_for_status()
#             return resp.json(), gtin
#         except Exception as e:
#             if attempt == max_attempts:
#                 raise
#             time.sleep(0.5 * attempt)  # backoff exponencial

# ------------------------------------------------------------------------------
# Funções assíncronas (opcionais)
import asyncio
import aiohttp

async def _request_produto_sefaz_async(session, gtin, raio, my_lat, my_lon, dias):
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    data = {
        "produto": {"gtin": str(gtin)},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": float(my_lat),
                "longitude": float(my_lon),
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50
    }
    async with session.post(url, json=data) as response:
        response.raise_for_status()
        return await response.json(), gtin

async def obter_produtos_async(gtin_list, raio, my_lat, my_lon, dias):
    headers = {
        "Content-Type": "application/json",
        "AppToken": "seu_token_aqui"
    }
    async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
        tasks = [
            _request_produto_sefaz_async(session, gtin, raio, my_lat, my_lon, dias)
            for gtin in gtin_list
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

# ------------------------------------------------------------------------------
def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
    """
    Faz consultas concorrentes à API SEFAZ para cada GTIN em gtin_list e
    retorna um DataFrame com os dados consolidados.
    """
    if not gtin_list:
        logger.warning("Lista de GTIN está vazia.")
        messages.warning(request, "Lista de GTIN está vazia.")
        return pd.DataFrame()

    response_list = []

    # ✅ Número fixo de workers sem uso de multiprocessing
    max_workers = min(2, len(gtin_list))  # define limite seguro para ambientes limitados

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_request_produto_sefaz, gtin, raio, my_lat, my_lon, dias): gtin
            for gtin in gtin_list
        }
        for future in concurrent.futures.as_completed(future_map):
            gtin = future_map[future]
            try:
                resp_json, used_gtin = future.result()
                if resp_json and 'conteudo' in resp_json and resp_json['conteudo']:
                    response_list.append(resp_json)
                else:
                    messages.warning(request, f"Nenhum conteúdo encontrado para o GTIN {gtin}.")
            except requests.exceptions.HTTPError as http_err:
                messages.error(request, f"Erro HTTP ao consultar o GTIN {gtin}.")
            except requests.exceptions.ConnectionError as conn_err:
                messages.error(request, f"Erro de conexão ao consultar o GTIN {gtin}.")
            except Exception as e:
                messages.error(request, f"Erro inesperado ao consultar o GTIN {gtin}.")

    if not response_list:
        messages.warning(request, "Nenhum dado válido foi retornado pela API.")
        return pd.DataFrame()

    data_list = []
    for response in response_list:
        for item in response.get('conteudo', []):
            produto = item.get('produto', {})
            estabelecimento = item.get('estabelecimento', {})
            endereco = estabelecimento.get('endereco', {})
            gtin = produto.get('gtin')
            if not gtin:
                logger.warning("GTIN ausente em um item.")
                continue
            try:
                data_entry = {
                    'CODIGO_BARRAS': int(gtin),
                    'CATEGORIA': gtin_to_category.get(int(gtin), "OUTROS"),
                    'PRODUTO': gtin_to_product_name.get(int(gtin), "OUTROS"),
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
                logger.error(f"Erro ao processar item com GTIN {gtin}: {e}")
                messages.error(request, f"Erro ao processar item com GTIN {gtin}: {e}")

    if not data_list:
        messages.warning(request, "Nenhum dado processado para criar o DataFrame.")
        return pd.DataFrame()

    return pd.DataFrame(data_list)


# def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
#     """
#     Faz consultas concorrentes à API SEFAZ para cada GTIN em gtin_list e
#     retorna um DataFrame com os dados consolidados.
#     """
#     if not gtin_list:
#         logger.warning("Lista de GTIN está vazia.")
#         messages.warning(request, "Lista de GTIN está vazia.")
#         return pd.DataFrame()

#     response_list = []
    
#     # Ajuste: aumentar o número de workers para aproveitar as 32 vCPU
#     #max_workers = 30
#     cpu_cores = multiprocessing.cpu_count()
#     max_workers = min(5 * cpu_cores, len(gtin_list))

#     with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
#         future_map = {
#             executor.submit(_request_produto_sefaz, gtin, raio, my_lat, my_lon, dias): gtin
#             for gtin in gtin_list
#         }
#         for future in concurrent.futures.as_completed(future_map):
#             gtin = future_map[future]
#             try:
#                 resp_json, used_gtin = future.result()
#                 if resp_json and 'conteudo' in resp_json and resp_json['conteudo']:
#                     response_list.append(resp_json)
#                 else:
#                     #logger.warning(f"Nenhum conteúdo encontrado para o GTIN {gtin}.")
#                     messages.warning(request, f"Nenhum conteúdo encontrado para o GTIN {gtin}.")
#             except requests.exceptions.HTTPError as http_err:
#                 #logger.error(f"HTTP error ao consultar o GTIN {gtin}: {http_err}")
#                 messages.error(request, f"Erro HTTP ao consultar o GTIN {gtin}.")
#             except requests.exceptions.ConnectionError as conn_err:
#                 #logger.error(f"Erro de conexão ao consultar o GTIN {gtin}: {conn_err}")
#                 messages.error(request, f"Erro de conexão ao consultar o GTIN {gtin}.")
#             except Exception as e:
#                 #logger.error(f"Erro inesperado ao consultar o GTIN {gtin}: {e}")
#                 messages.error(request, f"Erro inesperado ao consultar o GTIN {gtin}.")

#     if not response_list:
#         #logger.warning("Nenhum dado válido foi retornado pela API.")
#         messages.warning(request, "Nenhum dado válido foi retornado pela API.")
#         return pd.DataFrame()

#     data_list = []
#     for response in response_list:
#         for item in response.get('conteudo', []):
#             produto = item.get('produto', {})
#             estabelecimento = item.get('estabelecimento', {})
#             endereco = estabelecimento.get('endereco', {})
#             gtin = produto.get('gtin')
#             if not gtin:
#                 logger.warning("GTIN ausente em um item.")
#                 continue
#             try:
#                 data_entry = {
#                     'CODIGO_BARRAS': int(gtin),
#                     'CATEGORIA': gtin_to_category.get(int(gtin), "OUTROS"),
#                     'PRODUTO': gtin_to_product_name.get(int(gtin), "OUTROS"),
#                     'VALOR': produto.get('venda', {}).get('valorVenda', 0.0),
#                     'CNPJ': estabelecimento.get('cnpj', 'Desconhecido'),
#                     'MERCADO': estabelecimento.get('razaoSocial', 'Desconhecido'),
#                     'ENDERECO': endereco.get('nomeLogradouro', 'Desconhecido'),
#                     'NUMERO': endereco.get('numeroImovel', 'S/N'),
#                     'BAIRRO': endereco.get('bairro', 'Desconhecido'),
#                     'LAT': endereco.get('latitude', 0.0),
#                     'LONG': endereco.get('longitude', 0.0)
#                 }
#                 data_list.append(data_entry)
#             except Exception as e:
#                 logger.error(f"Erro ao processar item com GTIN {gtin}: {e}")
#                 messages.error(request, f"Erro ao processar item com GTIN {gtin}: {e}")

#     if not data_list:
#         #logger.warning("Nenhum dado processado para criar o DataFrame.")
#         messages.warning(request, "Nenhum dado processado para criar o DataFrame.")
#         return pd.DataFrame()

#     df = pd.DataFrame(data_list)
#     return df
# ------------------------------------------------------------------------------


logger = logging.getLogger(__name__)

# def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
#     """
#     Consulta sequencialmente a API SEFAZ para cada GTIN.
#     Retorna um DataFrame com os dados consolidados.
#     """

#     if not gtin_list:
#         messages.warning(request, "Lista de GTIN está vazia.")
#         return pd.DataFrame()

#     response_list = []

#     logger.warning(f"📦 Antes das requisições: Memória usada = {psutil.Process().memory_info().rss / (1024*1024):.2f} MB")

#     for i, gtin in enumerate(gtin_list, 1):
#         logger.warning(f"🚨 Consultando GTIN {gtin} ({i}/{len(gtin_list)}) - Memória = {psutil.Process().memory_info().rss / (1024*1024):.2f} MB")

#         try:
#             resp_json, _ = _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias)
#             if resp_json and 'conteudo' in resp_json and resp_json['conteudo']:
#                 response_list.append(resp_json)
#                 logger.info(f"✅ GTIN {gtin} retornou com sucesso ({len(resp_json['conteudo'])} registros)")
#             else:
#                 logger.warning(f"⚠️ Nenhum conteúdo encontrado para o GTIN {gtin}.")
#         except Exception as e:
#             messages.error(request, f"Erro ao consultar o GTIN {gtin}: {str(e)}")

#         gc.collect()  # Força coleta após cada requisição

#     logger.info(f"📊 Uso de memória após obter produtos: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

#     if not response_list:
#         messages.warning(request, "Nenhum dado válido foi retornado pela API.")
#         return pd.DataFrame()

#     data_list = []
#     for response in response_list:
#         for item in response.get('conteudo', []):
#             produto = item.get('produto', {})
#             estabelecimento = item.get('estabelecimento', {})
#             endereco = estabelecimento.get('endereco', {})
#             gtin = produto.get('gtin')
#             if not gtin:
#                 logger.warning("GTIN ausente em um item.")
#                 continue
#             try:
#                 data_entry = {
#                     'CODIGO_BARRAS': int(gtin),
#                     'CATEGORIA': gtin_to_category.get(int(gtin), "OUTROS"),
#                     'PRODUTO': gtin_to_product_name.get(int(gtin), "OUTROS"),
#                     'VALOR': produto.get('venda', {}).get('valorVenda', 0.0),
#                     'CNPJ': estabelecimento.get('cnpj', 'Desconhecido'),
#                     'MERCADO': estabelecimento.get('razaoSocial', 'Desconhecido'),
#                     'ENDERECO': endereco.get('nomeLogradouro', 'Desconhecido'),
#                     'NUMERO': endereco.get('numeroImovel', 'S/N'),
#                     'BAIRRO': endereco.get('bairro', 'Desconhecido'),
#                     'LAT': endereco.get('latitude', 0.0),
#                     'LONG': endereco.get('longitude', 0.0)
#                 }
#                 data_list.append(data_entry)
#             except Exception as e:
#                 logger.error(f"Erro ao processar item com GTIN {gtin}: {e}")
#                 messages.error(request, f"Erro ao processar item com GTIN {gtin}: {e}")

#     if not data_list:
#         messages.warning(request, "Nenhum dado processado para criar o DataFrame.")
#         return pd.DataFrame()

#     return pd.DataFrame(data_list)


# ------------------------------------------------------------------------------

# def agrupar_coordenada(coord, precisao=0.002):
#     return round(floor(coord / precisao) * precisao, 3)

# def consultar_combustivel(descricao, raio, latitude, longitude, dias, max_attempts=3):
#     """
#     Consulta resiliente à API da SEFAZ para combustíveis, com tentativas, timeout e cache.
#     """
#     cache_key = f"combustivel:{descricao}:{raio}:{round(latitude, 3)}:{round(longitude, 3)}:{dias}"
#     cached_data = cache.get(cache_key)

#     if cached_data:
#         logger.info(f"✅ Cache HIT: {cache_key}")
#         return cached_data

#     logger.warning(f"⚠️ Cache MISS: {cache_key}")

#     payload = {
#         "produto": {"descricao": descricao},
#         "estabelecimento": {
#             "geolocalizacao": {
#                 "latitude": latitude,
#                 "longitude": longitude,
#                 "raio": raio
#             }
#         },
#         "dias": dias,
#         "pagina": 1,
#         "registrosPorPagina": 50
#     }

#     for attempt in range(1, max_attempts + 1):
#         try:
#             logger.info(f"🔁 Tentativa {attempt} - consultando combustível: {descricao}")
#             response = requests.post(SEFAZ_URL, json=payload, timeout=30)
#             response.raise_for_status()
#             data = response.json()

#             if not data or "conteudo" not in data:
#                 logger.warning(f"⚠️ Resposta sem dados válidos para {descricao}")
#                 return None

#             cache.set(cache_key, data, timeout=60 * 60 * 2)
#             logger.info(f"📦 Resposta armazenada em cache: {cache_key}")
#             return data

#         except requests.exceptions.Timeout:
#             logger.warning(f"⏱️ Timeout na tentativa {attempt}")
#         except requests.exceptions.RequestException as err:
#             logger.error(f"❌ Erro ao consultar combustível: tentativa {attempt} - {err}")

#         time.sleep(1.5 * attempt)

#     logger.error(f"🚫 Todas as tentativas falharam para o combustível: {descricao}")
#     return None
def consultar_combustivel(descricao, raio, my_lat, my_lon, dias):
    """
    Consulta a API da SEFAZ Alagoas para buscar preços de combustíveis com base na descrição,
    localização (latitude e longitude) e tempo de busca em dias.
    """
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    payload = {
        "produto": {"descricao": descricao},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": float(my_lat),
                "longitude": float(my_lon),
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50
    }

    try:
        response = SEFAZ_SESSION.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        #logger.debug(f"Resposta da API para '{descricao}': {data}")
        return data

    except requests.exceptions.HTTPError as http_err:
        #logger.error(f"Erro HTTP ao buscar '{descricao}': {http_err}")
        return {"error": f"Erro HTTP ao buscar '{descricao}': {str(http_err)}"}
    except requests.exceptions.ConnectionError as conn_err:
        #logger.error(f"Erro de conexão ao buscar '{descricao}': {conn_err}")
        return {"error": f"Erro de conexão ao buscar '{descricao}': {str(conn_err)}"}
    except requests.exceptions.Timeout as timeout_err:
        #logger.error(f"Erro de timeout ao buscar '{descricao}': {timeout_err}")
        return {"error": f"Erro de timeout ao buscar '{descricao}': {str(timeout_err)}"}
    except Exception as e:
        #logger.error(f"Erro inesperado ao buscar '{descricao}': {e}")
        return {"error": f"Erro inesperado ao buscar '{descricao}': {str(e)}"}

# ------------------------------------------------------------------------------
def obter_combustiveis(descricao, raio, my_lat, my_lon, dias):
    """
    Obtém os 3 estabelecimentos mais próximos que vendem o combustível especificado.
    """
    response = consultar_combustivel(descricao, raio, my_lat, my_lon, dias)

    if not response or 'conteudo' not in response:
        #logger.warning(f"Nenhum dado válido foi retornado para '{descricao}'.")
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
                'DISTANCIA_KM': round(distancia, 2)
            }
            data_list.append(data_entry)
        except Exception as e:
            logger.error(f"Erro ao processar item '{descricao}': {e}")

    if not data_list:
        logger.warning(f"Nenhum dado processado para '{descricao}'.")
        return pd.DataFrame()

    df = pd.DataFrame(data_list)
    df = df.sort_values(by='DISTANCIA_KM').head(3)
    return df



# def _processar_estabelecimento(item, descricao, my_lat, my_lon):
#     try:
#         produto = item.get('produto', {})
#         estabelecimento = item.get('estabelecimento', {})
#         endereco = estabelecimento.get('endereco', {})

#         lat_estab = float(endereco.get('latitude', 0.0))
#         lon_estab = float(endereco.get('longitude', 0.0))
#         distancia = geodesic((my_lat, my_lon), (lat_estab, lon_estab)).km

#         return {
#             'DESCRICAO': produto.get('descricao', 'Desconhecido'),
#             'VALOR': produto.get('venda', {}).get('valorVenda', 0.0),
#             'CNPJ': estabelecimento.get('cnpj', 'Desconhecido'),
#             'MERCADO': estabelecimento.get('razaoSocial', 'Desconhecido'),
#             'ENDERECO': endereco.get('nomeLogradouro', 'Desconhecido'),
#             'NUMERO': endereco.get('numeroImovel', 'S/N'),
#             'BAIRRO': endereco.get('bairro', 'Desconhecido'),
#             'LAT': lat_estab,
#             'LONG': lon_estab,
#             'DISTANCIA_KM': round(distancia, 2)
#         }
#     except Exception as e:
#         logger.error(f"Erro ao processar item '{descricao}': {e}")
#         return None


# def obter_combustiveis(descricao, raio, my_lat, my_lon, dias):
#     """
#     Obtém os 3 estabelecimentos mais próximos que vendem o combustível especificado.
#     Versão sequencial (sem multiprocessing).
#     """
#     response = consultar_combustivel(descricao, raio, my_lat, my_lon, dias)

#     if not response or 'conteudo' not in response:
#         return pd.DataFrame()

#     estabelecimentos = response.get('conteudo', [])

#     logger.warning(f"📦 Antes do processamento: Memória usada = {psutil.Process().memory_info().rss / (1024*1024):.2f} MB")

#     data_list = []
#     for item in estabelecimentos:
#         resultado = _processar_estabelecimento(item, descricao, my_lat, my_lon)
#         if resultado:
#             data_list.append(resultado)

#     if not data_list:
#         logger.warning(f"Nenhum dado processado para '{descricao}'.")
#         return pd.DataFrame()

#     df = pd.DataFrame(data_list)
#     df = df.sort_values(by='DISTANCIA_KM').head(3)
#     return df

