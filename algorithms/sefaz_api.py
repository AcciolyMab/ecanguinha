import requests
import json
import logging
import time
from urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.core.cache import cache # Certifique-se de que o Django e o Redis estão configurados
import urllib3
import pandas as pd
from geopy.distance import geodesic
import os
import concurrent.futures
from math import floor
from math import ceil
import gc  # opcional se quiser forçar liberação de memória
import time
import psutil # Para monitoramento de memória, útil em debug
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ThreadTimeoutError


from django.contrib import messages

LOG_LEVEL = 'DEBUG' if os.getenv('DEBUG', 'False') == 'True' else 'INFO'

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
    "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d" # Substitua pelo seu token real
})

# ------------------------------------------------------------------------------
# Implementação da função auxiliar síncrona com cache e retries:
def _request_produto_sefaz(gtin, raio, my_lat, my_lon, dias, max_attempts=3):
    """
    Função auxiliar que faz a requisição para a API SEFAZ usando a sessão global.
    Inclui cache, timeouts e retries com backoff exponencial.
    Retorna (response_json, gtin) ou lança exceção em caso de falha persistente.
    """
    # Arredonda coordenadas para evitar fragmentação de cache e para corresponder ao manual 
    lat = round(float(my_lat), 3)
    lon = round(float(my_lon), 3)

    # Cria chave única para o cache
    cache_key = f"gtin:{gtin}:{raio}:{lat}:{lon}:{dias}"
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"✅ GTIN Cache HIT: {cache_key}")
        return cached, gtin

    logger.warning(f"⚠️ GTIN Cache MISS: {cache_key}")

    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    data = {
        "produto": {"gtin": str(gtin)},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": lat,
                "longitude": lon,
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50 # Manual permite até 5.000, mas 50 é conservador para memória.
    }

    headers = {
        "Content-Type": "application/json",
        "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
    }

    for attempt in range(1, max_attempts + 1):
        try:
            # Adiciona timeout explícito para evitar workers presos 
            response = requests.post(url, json=data, headers=headers, timeout=120)
            response.raise_for_status()
            return response.json(), gtin

            # Salva no cache por 2 horas (7200 segundos) 
            cache.set(cache_key, response_json, timeout=60 * 60 * 2)
            return response_json, gtin

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as e:
            logger.warning(f"⚠️ Erro ao consultar GTIN {gtin}, tentativa {attempt}: {e}")

            if attempt == max_attempts:
                logger.error(f"❌ Todas as tentativas falharam para GTIN {gtin}")
                # Retorna None para que o chamador possa lidar com isso graciosamente
                return None, gtin

            time.sleep(0.5 * attempt) # Backoff exponencial

        except Exception as e:
            logger.error(f"❌ Erro inesperado para GTIN {gtin}: {e}")
            return None, gtin
#------------------------------------------------------------------------------

# def consultar_combustivel(descricao, raio, my_lat, my_lon, dias, max_attempts=3, timeout_exec=20):
#     """
#     Executa a chamada à API da SEFAZ de forma segura em thread, com timeout externo à requests.
#     """

#     def executar_requisicao():
#         lat = round(float(my_lat), 3)
#         lon = round(float(my_lon), 3)

#         cache_key = f"combustivel:{descricao}:{raio}:{lat}:{lon}:{dias}"
#         cached_data = cache.get(cache_key)
#         if cached_data:
#             logger.info(f"✅ Cache HIT: {cache_key}")
#             return cached_data

#         logger.warning(f"⚠️ Cache MISS: {cache_key}")

#         url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
#         payload = {
#             "produto": {"descricao": descricao},
#             "estabelecimento": {
#                 "geolocalizacao": {
#                     "latitude": lat,
#                     "longitude": lon,
#                     "raio": int(raio)
#                 }
#             },
#             "dias": int(dias),
#             "pagina": 1,
#             "registrosPorPagina": 50
#         }

#         for attempt in range(1, max_attempts + 1):
#             try:
#                 logger.info(f"🔁 Tentativa {attempt} - consultando combustível: {descricao}")
#                 response = SEFAZ_SESSION.post(url, json=payload, timeout=10)  # Timeout menor por tentativa
#                 response.raise_for_status()
#                 data = response.json()

#                 if not data or "conteudo" not in data or not data["conteudo"]:
#                     logger.warning(f"⚠️ Resposta sem dados válidos para {descricao}")
#                     return {"error": "Resposta sem dados válidos"}

#                 cache.set(cache_key, data, timeout=60 * 60 * 2)
#                 logger.info(f"📦 Resposta armazenada em cache: {cache_key}")
#                 return data

#             except requests.exceptions.Timeout:
#                 logger.warning(f"⏱️ Timeout na tentativa {attempt} para '{descricao}'")
#             except requests.exceptions.ConnectionError:
#                 logger.warning(f"🚫 Erro de conexão na tentativa {attempt} para '{descricao}'")
#             except requests.exceptions.HTTPError as err:
#                 logger.error(f"❌ Erro HTTP na tentativa {attempt} para '{descricao}': {err}")
#             except Exception as e:
#                 logger.error(f"❌ Erro inesperado na tentativa {attempt} para '{descricao}': {e}")

#             time.sleep(0.5 * attempt)

#         logger.error(f"🚫 Todas as tentativas falharam para o combustível: {descricao}")
#         return {"error": f"Todas as tentativas falharam para o combustível: {descricao}"}

#     # Executa a lógica protegida por timeout global
#     with ThreadPoolExecutor(max_workers=1) as executor:
#         future = executor.submit(executar_requisicao)
#         try:
#             return future.result(timeout=timeout_exec)  # Timeout total para toda a função
#         except ThreadTimeoutError:
#             logger.critical(f"🔥 Timeout total excedido ({timeout_exec}s) para consulta de '{descricao}'")
#             return {"error": f"Timeout total excedido para '{descricao}'"}

def consultar_combustivel(tipo_combustivel, raio, my_lat, my_lon, dias):
    """
    Consulta a API da SEFAZ Alagoas para buscar preços de combustíveis com base no tipo (1 a 6).
    """

    lat = round(float(my_lat), 3)
    lon = round(float(my_lon), 3)

    cache_key = f"combustivel:{tipo_combustivel}:{raio}:{lat}:{lon}:{dias}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"✅ Cache HIT: {cache_key}")
        return cached_data

    logger.warning(f"⚠️ Cache MISS: {cache_key}")

    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/combustivel/pesquisa'
    payload = {
        "produto": {"tipoCombustivel": int(tipo_combustivel)},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": lat,
                "longitude": lon,
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 100
    }

    headers = {
        "Content-Type": "application/json",
        "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
    }

    try:
        response = SEFAZ_SESSION.post(url, json=payload, headers=headers, timeout=120)  # Timeout de 120 segundos
        response.raise_for_status()
        data = response.json()

        if "conteudo" not in data or not data["conteudo"]:
            return {"error": "Nenhum dado encontrado"}

        cache.set(cache_key, data, timeout=60 * 60 * 2)
        return data

    except requests.exceptions.Timeout:
        logger.warning(f"⏱️ Timeout na requisição para tipo {tipo_combustivel}")
    except Exception as e:
        logger.error(f"❌ Erro consultando combustível tipo {tipo_combustivel}: {e}")

    return {"error": f"Falha na requisição para tipo {tipo_combustivel}"}




# ------------------------------------------------------------------------------
def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
    """
    Faz consultas concorrentes à API SEFAZ para cada GTIN em gtin_list e
    retorna um DataFrame com os dados consolidados.
    Implementa processamento eficiente para menor uso de memória.
    """
    if not gtin_list:
        logger.warning("Lista de GTIN está vazia.")
        messages.warning(request, "Lista de GTIN está vazia.")
        return pd.DataFrame()

    data_list = [] # Acumulará dicionários para o DataFrame

    # O número de workers pode ser ajustado com base nos recursos do servidor e testes.
    # 2 workers é um valor conservador e seguro.
    max_workers = min(2, len(gtin_list))

    logger.info(f"📊 Uso de memória antes das requisições: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

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
                    # Processa o conteúdo diretamente para evitar acumular JSONs grandes
                    for item in resp_json.get('conteudo', []):
                        produto = item.get('produto', {})
                        estabelecimento = item.get('estabelecimento', {})
                        endereco = estabelecimento.get('endereco', {})
                        item_gtin = produto.get('gtin')
                        if not item_gtin:
                            logger.warning(f"GTIN ausente em um item da resposta para GTIN {gtin}.")
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
                            logger.error(f"Erro ao processar item com GTIN {item_gtin} da resposta para GTIN {gtin}: {e}")
                            messages.error(request, f"Erro ao processar item com GTIN {item_gtin}: {e}")
                    # Força a liberação do objeto JSON grande após processar [opcional]
                    del resp_json
                    gc.collect()

                else:
                    messages.warning(request, f"Nenhum conteúdo encontrado ou resposta inválida para o GTIN {gtin}.")
            except requests.exceptions.HTTPError as http_err:
                messages.error(request, f"Erro HTTP ao consultar o GTIN {gtin}.")
            except requests.exceptions.ConnectionError as conn_err:
                messages.error(request, f"Erro de conexão ao consultar o GTIN {gtin}.")
            except requests.exceptions.Timeout as timeout_err:
                messages.error(request, f"Tempo limite excedido ao consultar o GTIN {gtin}.")
            except Exception as e:
                messages.error(request, f"Erro inesperado ao consultar o GTIN {gtin}.")

    logger.info(f"📊 Uso de memória após obter produtos e antes do DataFrame: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

    if not data_list:
        messages.warning(request, "Nenhum dado válido foi retornado pela API ou processado.")
        return pd.DataFrame()

    # Cria o DataFrame e otimiza tipos de dados para reduzir consumo de memória
    df = pd.DataFrame(data_list)

    # Downcast numérico
    for col in ['CODIGO_BARRAS', 'NUMERO']: # Adicione colunas de int se aplicável
        if col in df.columns:
            # Converte para string primeiro para lidar com 'S/N' ou outros não-numéricos, depois para numérico
            # e então downcast, se puder.
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int32')

    for col in ['VALOR', 'LAT', 'LONG']: # Adicione colunas de float se aplicável
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float32')

    # Converte strings repetitivas para tipo 'category'
    for col in ['CATEGORIA', 'PRODUTO', 'CNPJ', 'MERCADO', 'ENDERECO', 'BAIRRO']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    logger.info(f"📊 Uso de memória após criar DataFrame: {psutil.Process().memory_info().rss / (1024 * 1024):.2f} MB")

    return df

# ------------------------------------------------------------------------------
# Implementação da função auxiliar consultar_combustivel com cache e retries:
# def consultar_combustivel(descricao, raio, my_lat, my_lon, dias, max_attempts=3):
#     """
#     Consulta resiliente à API da SEFAZ para combustíveis, com tentativas, timeout e cache.
#     """
#     # Arredonda coordenadas para evitar fragmentação de cache e para corresponder ao manual 
#     lat = round(float(my_lat), 3)
#     lon = round(float(my_lon), 3)

#     cache_key = f"combustivel:{descricao}:{raio}:{lat}:{lon}:{dias}"
#     cached_data = cache.get(cache_key)

#     if cached_data:
#         logger.info(f"✅ Cache HIT: {cache_key}")
#         return cached_data

#     logger.warning(f"⚠️ Cache MISS: {cache_key}")

#     url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa' # O manual indica o mesmo endpoint para produtos e combustíveis para pesquisa 
#     payload = {
#         "produto": {"descricao": descricao}, # O manual mostra 'descricao' para pesquisa de combustíveis também 
#         "estabelecimento": {
#             "geolocalizacao": {
#                 "latitude": lat,
#                 "longitude": lon,
#                 "raio": int(raio)
#             }
#         },
#         "dias": int(dias),
#         "pagina": 1,
#         "registrosPorPagina": 50 # Manual permite até 5.000, mas 50 é conservador 
#     }

#     for attempt in range(1, max_attempts + 1):
#         try:
#             logger.info(f"🔁 Tentativa {attempt} - consultando combustível: {descricao}")
#             # Adiciona timeout explícito 
#             response = SEFAZ_SESSION.post(url, json=payload, timeout=30)
#             response.raise_for_status()
#             data = response.json()

#             if not data or "conteudo" not in data:
#                 logger.warning(f"⚠️ Resposta sem dados válidos para {descricao}")
#                 return {"error": "Resposta sem dados válidos"}

#             cache.set(cache_key, data, timeout=60 * 60 * 2) # Cache por 2 horas 
#             logger.info(f"📦 Resposta armazenada em cache: {cache_key}")
#             return data

#         except requests.exceptions.Timeout:
#             logger.warning(f"⏱️ Timeout na tentativa {attempt} para '{descricao}'")
#         except requests.exceptions.ConnectionError:
#             logger.warning(f"🚫 Erro de conexão na tentativa {attempt} para '{descricao}'")
#         except requests.exceptions.HTTPError as err:
#             logger.error(f"❌ Erro HTTP na tentativa {attempt} para '{descricao}': {err}")
#         except Exception as e:
#             logger.error(f"❌ Erro inesperado na tentativa {attempt} para '{descricao}': {e}")

#         if attempt == max_attempts:
#             logger.error(f"🚫 Todas as tentativas falharam para o combustível: {descricao}")
#             return {"error": f"Todas as tentativas falharam para o combustível: {descricao}"}

#         time.sleep(0.5 * attempt) # Backoff exponencial

#     return {"error": "Falha desconhecida na consulta de combustível"}


# ------------------------------------------------------------------------------
def obter_combustiveis(descricao, raio, my_lat, my_lon, dias):
    """
    Obtém os 3 estabelecimentos mais próximos que vendem o combustível especificado.
    """
    response = consultar_combustivel(descricao, raio, my_lat, my_lon, dias)

    if not response or 'conteudo' not in response or 'error' in response:
        logger.warning(f"Nenhum dado válido foi retornado para '{descricao}'. Erro: {response.get('error', 'Desconhecido')}")
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
            logger.error(f"Erro ao processar item para '{descricao}': {e}")

    if not data_list:
        logger.warning(f"Nenhum dado processado para '{descricao}'.")
        return pd.DataFrame()

    df = pd.DataFrame(data_list)
    # Otimização de tipos de dados para o DataFrame de combustíveis
    for col in ['VALOR', 'LAT', 'LONG', 'DISTANCIA_KM']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float32')
    for col in ['DESCRICAO', 'CNPJ', 'MERCADO', 'ENDERECO', 'NUMERO', 'BAIRRO']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    df = df.sort_values(by='DISTANCIA_KM').head(3)
    return df