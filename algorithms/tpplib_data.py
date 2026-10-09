import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import logging
import os
import time
from pathlib import Path

from algorithms.custos import CONSUMO_KM_POR_LITRO

logger = logging.getLogger(__name__)

# Servidores Overpass usados pelo OSMnx para baixar o mapa viário, em ordem de preferência.
# O primeiro que responder vira o preferido das próximas buscas. Configurável por OVERPASS_URLS (separados por vírgula).
OVERPASS_URLS = [u.strip().rstrip("/") for u in os.environ.get(
    "OVERPASS_URLS",
    "https://overpass.openstreetmap.fr/api,https://overpass-api.de/api,https://maps.mail.ru/osm/tools/overpass/api,"
    "https://overpass.kumi.systems/api,https://overpass.private.coffee/api").split(",") if u.strip()]
ox.settings.http_user_agent = "CanguinhaAL/1.0 (+https://www.canguinhaal.com.br)"
ox.settings.http_referer = "https://www.canguinhaal.com.br"
ox.settings.requests_timeout = 60
# Mapa viário local (gerado uma vez por scripts/baixar_mapa.py): evita baixar o mapa do Overpass a cada busca.
ARQUIVO_MAPA = Path(os.environ.get("MAPA_VIARIO_PATH") or Path(__file__).resolve().parent.parent / "data" / "mapas" / "maceio_metro.graphml")
MARGEM_MAPA_GRAUS = 0.003        # ~300 m de folga ao testar se um ponto está dentro do mapa local
_mapa_local = None               # (grafo, (min_lat, min_lon, max_lat, max_lon)) carregado sob demanda, 1x por processo
_mapa_local_tentado = False
_overpass_preferido = None
_overpass_falhas = {}            # url -> instante da última falha (evita insistir em servidor fora do ar)
PAUSA_APOS_FALHA_S = 600
FATOR_DESVIO_RETA = 1.35         # distância viária ~ 1,35 x linha reta (usado só sem o mapa)


def _carregar_mapa_local():
    """Carrega o mapa viário local uma vez por processo; None se o arquivo não existir ou estiver inválido."""
    global _mapa_local, _mapa_local_tentado
    if _mapa_local_tentado:
        return _mapa_local
    _mapa_local_tentado = True
    if not ARQUIVO_MAPA.exists():
        logger.info(f"Mapa viário local não encontrado em {ARQUIVO_MAPA}; usando o Overpass.")
        return None
    try:
        inicio = time.time()
        G = ox.load_graphml(ARQUIVO_MAPA)
        ys = [d["y"] for _, d in G.nodes(data=True)]
        xs = [d["x"] for _, d in G.nodes(data=True)]
        _mapa_local = (G, (min(ys), min(xs), max(ys), max(xs)))
        logger.info(f"Mapa viário local carregado em {time.time() - inicio:.0f}s: {len(G)} nós.")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Falha ao carregar o mapa viário local ({ARQUIVO_MAPA}): {e}")
    return _mapa_local


def _mapa_local_cobre(pontos):
    """Devolve o grafo local se todos os pontos (lat, lon) estiverem dentro dele; senão None."""
    carregado = _carregar_mapa_local()
    if not carregado:
        return None
    G, (min_lat, min_lon, max_lat, max_lon) = carregado
    m = MARGEM_MAPA_GRAUS
    if all(min_lat - m <= lat <= max_lat + m and min_lon - m <= lon <= max_lon + m for lat, lon in pontos):
        return G
    return None


def _grafo_com_fallback(centro, raio_m):
    """ox.graph_from_point tentando os servidores Overpass em sequência.

    Mapas já em cache não usam a rede. Devolve None quando nenhum servidor responde; nesse caso
    create_tpplib_data estima as distâncias em linha reta, em vez de abortar a busca.
    """
    global _overpass_preferido
    agora = time.time()
    urls = [u for u in OVERPASS_URLS if agora - _overpass_falhas.get(u, 0) > PAUSA_APOS_FALHA_S]
    urls.sort(key=lambda u: u != _overpass_preferido)
    for url in urls:
        ox.settings.overpass_url = url
        inicio = time.time()
        try:
            G = ox.graph_from_point(centro, dist=raio_m, network_type='drive')
            _overpass_preferido = url
            return G
        except Exception as e:  # noqa: BLE001 - qualquer falha de rede/servidor tenta o próximo
            _overpass_falhas[url] = time.time()
            logger.warning(f"Overpass {url} falhou após {time.time() - inicio:.0f}s: {type(e).__name__}: {str(e)[:120]}")
    logger.warning("Nenhum servidor Overpass respondeu: distâncias serão estimadas em linha reta.")
    return None


def _matrizes_aproximadas(coords, valor_medio_km):
    """Distâncias (km) e custos (R$) entre pontos em linha reta x FATOR_DESVIO_RETA, sem o mapa viário."""
    from geopy.distance import geodesic
    n = len(coords)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            dist[i, j] = dist[j, i] = geodesic(coords[i], coords[j]).km * FATOR_DESVIO_RETA
    return dist, dist * valor_medio_km


def create_tpplib_data(dataframe, buyer_lat, buyer_lon, media_preco=0.0, raio_busca=5.0, centro_grafo=None):
    """
    Cria um dicionário `data` com a estrutura semelhante ao arquivo TPP, a partir de um DataFrame com as colunas
    'PRODUTO', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG', usando OSMnx para calcular distâncias viárias.
    
    Aqui, a localização do comprador (buyer_lat, buyer_lon) é considerada o depot (ponto de partida e chegada).
    
    Parâmetros:
      - dataframe (pd.DataFrame): DataFrame contendo as colunas necessárias.
      - buyer_lat (float): Latitude da localização do comprador (depot).
      - buyer_lon (float): Longitude da localização do comprador (depot).
      - media_preco (float): Média do preço do combustível.
      - raio_busca (float): Raio de busca em KM.
      - centro_grafo (tuple|None): (lat, lon) central do grafo viário; None usa a média dos pontos.
    
    Retorna:
      - dict: Dicionário `data` com as variáveis necessárias, incluindo:
            - 'distancias_km': matriz de distâncias (km) entre os nós.
            - 'custos_viagem': matriz de custos (R$) para cada trecho.
    """
    data = {}
    data['media_preco_combustivel'] = media_preco
    required_columns = {'PRODUTO', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG'}
    if not required_columns.issubset(dataframe.columns):
        raise ValueError(f"DataFrame não contém as colunas necessárias: {required_columns - set(dataframe.columns)}")
    
    # Atribuir IDs inteiros aos produtos
    produtos_df = dataframe.copy()
    produto_ids, categorias_unicas = produtos_df['PRODUTO'].factorize()
    produto_ids += 1  # IDs a partir de 1
    data['K'] = set(range(1, len(categorias_unicas) + 1))
    
    # Consumo médio do veículo
    consumo_veiculo_km_por_litro = CONSUMO_KM_POR_LITRO
    valor_medio_km = data['media_preco_combustivel'] / consumo_veiculo_km_por_litro
    
    # Atribuir IDs inteiros aos mercados (eles permanecem com seus IDs originais)
    mercado_ids, mercados_unicos = produtos_df['MERCADO'].factorize()
    mercado_ids += 1
    data['M'] = set(mercado_ids)
    
    # Definir o depot como a localização do comprador (buyer)
    buyer_id = 0  # Usamos 0 para identificar o depot
    data['depot'] = buyer_id
    
    # O conjunto de nós agora inclui os mercados e o depot
    data['V'] = data['M'].union({buyer_id})
    
    # Demanda fixa de 1 unidade por produto
    data['dk'] = {i: 1 for i in data['K']}
    
    # Construção de Mk, pik e qik para os produtos
    data['Mk'] = {i: set() for i in data['K']}
    data['pik'] = {}
    data['qik'] = {}
    
    for produto_id, mercado_id, row in zip(produto_ids, mercado_ids, produtos_df.itertuples()):
        mercado_id = int(mercado_id)
        data['Mk'][produto_id].add(mercado_id)
        # O modelo tem um preço por (mercado, produto). Havendo várias ofertas do mesmo item no mesmo mercado
        # (marcas/GTINs diferentes), vale a melhor: o deslocamento é igual, então só ela pode ser a escolha ótima.
        chave = (mercado_id, produto_id)
        data['pik'][chave] = min(float(row.VALOR), data['pik'].get(chave, float('inf')))
        data['qik'][(mercado_id, produto_id)] = 1
    
    # Extração das coordenadas dos mercados
    data['node_coords'] = {int(mercado_ids[idx]): (row['LAT'], row['LONG'])
                             for idx, row in produtos_df.iterrows()}
    
    # Adiciona a localização do comprador como o depot
    data['node_coords'][buyer_id] = (buyer_lat, buyer_lon)
    
    # Atualiza o mapeamento de índices dos nós (ordenação dos IDs)
    data['node_index'] = {node_id: idx for idx, node_id in enumerate(sorted(data['V']))}
    
    # Calcula o ponto central baseado em todas as coordenadas (mercados e depot)
    all_lats = [coord[0] for coord in data['node_coords'].values()]
    all_lons = [coord[1] for coord in data['node_coords'].values()]
    center_lat, center_lon = centro_grafo if centro_grafo else (np.mean(all_lats), np.mean(all_lons))
    
    print("Construindo o grafo da região, aguarde...")
    # Constrói o grafo usando o raio de busca (convertendo km para metros)
    G = _mapa_local_cobre(list(data['node_coords'].values()))
    if G is None:
        G = _grafo_com_fallback((center_lat, center_lon), raio_busca*1000)
    
    nos_ids_ordenados = sorted(data['V'])  # Ex.: [0, 1, 2, ...] onde 0 é o depot
    if G is None:
        distancias_km, custos_viagem = _matrizes_aproximadas(
            [data['node_coords'][i] for i in nos_ids_ordenados], valor_medio_km)
        data['distancias_aproximadas'] = True
    else:
        # Identificação dos nós mais próximos para cada ponto (mercados e depot)
        nos_ids_ordenados = sorted(data['V'])  # Ex.: [0, 1, 2, ...] onde 0 é o depot
        node_ids = []
        for no_id in nos_ids_ordenados:
            lat, lon = data['node_coords'][no_id]
            nearest_node = ox.distance.nearest_nodes(G, lon, lat)
            node_ids.append(nearest_node)
    
        # Cálculo das matrizes:
        #   - distancias_km: distância real (em km) entre os nós;
        #   - custos_viagem: custo (R$) para percorrer cada trecho = dist_km * valor_medio_km.
        n = len(node_ids)
        distancias_km = np.zeros((n, n))
        custos_viagem = np.zeros((n, n))
    
        por_no = {}  # pontos que caem no mesmo nó do mapa compartilham o mesmo Dijkstra
        for i, origin_node in enumerate(node_ids):
            # Um Dijkstra por origem (em vez de um por par): mesma distância, bem mais rápido.
            if origin_node not in por_no:
                por_no[origin_node] = nx.single_source_dijkstra_path_length(G, origin_node, weight='length')
            comprimentos = por_no[origin_node]
            for j, dest_node in enumerate(node_ids):
                if i == j:
                    distancias_km[i, j] = 0
                    custos_viagem[i, j] = 0
                elif dest_node in comprimentos:
                    dist_km = comprimentos[dest_node] / 1000.0
                    distancias_km[i, j] = dist_km
                    custos_viagem[i, j] = dist_km * valor_medio_km
                else:
                    distancias_km[i, j] = float('inf')
                    custos_viagem[i, j] = float('inf')

    # Armazena as matrizes separadas no dicionário data
    data['distancias_km'] = distancias_km.tolist()
    data['custos_viagem'] = custos_viagem.tolist()
    
    # Mapeamento de ID do produto para o nome do produto
    data['produtos'] = {idx + 1: produto for idx, produto in enumerate(categorias_unicas)}
    
    # Mapeamento de ID do mercado para informações (nome, endereço e coordenadas)
    data['mercados'] = {}
    for idx, row in produtos_df.iterrows():
        mercado_id = int(mercado_ids[idx])
        data['mercados'][mercado_id] = {
            'nome': row['MERCADO'],
            'endereco': row['ENDERECO'],
            'latitude': row['LAT'],
            'longitude': row['LONG']
        }
    
    return data