import requests
import json
import logging
import time
from urllib3.exceptions import InsecureRequestWarning
import urllib3
import pandas as pd
import requests

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from django.contrib.messages.storage import session
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from django.contrib import messages

import os

LOG_LEVEL = 'DEBUG' if os.getenv('DEBUG', 'False') == 'True' else 'INFO'
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

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
    'OVOS': (7897146402019, 7897146405010, 7897146402033, 7898903159085, 7896414410121),
    'SARDINHA 125G': (7891167021013, 7891167023017, 7891167023024, 7896009301063, 7891167021075)
}

# Dicionário invertido para mapeamento rápido de GTIN para categoria e nome do produto
gtin_to_category = {}
gtin_to_product_name = {}

for category, gtins in category_map.items():
    for gtin in gtins:
        gtin_to_category[gtin] = category
        gtin_to_product_name[gtin] = category  # Usaremos o nome da categoria como nome do produto

def consultar_produto(request, gtin, raio, my_lat, my_lon, dias):
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'
    data = {
        "produto": {
            "gtin": str(gtin)
        },
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

    headers = {
        "Content-Type": "application/json",
        "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
    }

    try:
        # Fazer a requisição para a API
        response = requests.post(url, json=data, headers=headers, verify=False)
        response.raise_for_status()
        logger.debug(f"Resposta recebida: {response.text}")
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error ao consultar o GTIN {gtin}: {http_err}")
        messages.error(request, f"Erro HTTP ao consultar o GTIN {gtin}.")
        return None
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Erro de conexão ao consultar o GTIN {gtin}: {conn_err}")
        messages.error(request, f"Erro de conexão ao consultar o GTIN {gtin}.")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao consultar o GTIN {gtin}: {e}")
        messages.error(request, f"Erro inesperado ao consultar o GTIN {gtin}.")
        return None

# Função para obter produtos e criar o DataFrame
def obter_produtos(request, gtin_list, raio, my_lat, my_lon, dias):
    response_list = []
    for gtin in gtin_list:
        response = consultar_produto(request, gtin, raio, my_lat, my_lon, dias)
        if response and 'conteudo' in response:
            if response['conteudo']:
                response_list.append(response)
            else:
                logger.warning(f"Nenhum conteúdo encontrado para o GTIN {gtin}.")
                messages.warning(request, f"Nenhum conteúdo encontrado para o GTIN {gtin}.")
        else:
            logger.warning(f"Resposta inválida para o GTIN {gtin}.")
            messages.warning(request, f"Resposta inválida para o GTIN {gtin}.")

    if not response_list:
        logger.warning("Nenhum dado válido foi retornado pela API.")
        messages.warning(request, "Nenhum dado válido foi retornado pela API.")
        return pd.DataFrame()

    # Processamento dos dados e criação do DataFrame
    data_list = []
    for response in response_list:
        for item in response.get('conteudo', []):
            produto = item.get('produto', {})
            estabelecimento = item.get('estabelecimento', {})
            endereco = estabelecimento.get('endereco', {})
            gtin = produto.get('gtin')

            if not gtin:
                logger.warning("GTIN ausente no item.")
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
        logger.warning("Nenhum dado processado para criar o DataFrame.")
        messages.warning(request, "Nenhum dado processado para criar o DataFrame.")
        return pd.DataFrame()

    df = pd.DataFrame(data_list)
    return df