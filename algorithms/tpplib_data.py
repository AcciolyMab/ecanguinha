import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox

def create_tpplib_data(dataframe, buyer_lat, buyer_lon, media_preco=0.0, raio_busca=5.0):
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
    consumo_veiculo_km_por_litro = 9.5
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
        data['pik'][(mercado_id, produto_id)] = float(row.VALOR)
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
    center_lat, center_lon = np.mean(all_lats), np.mean(all_lons)
    
    print("Construindo o grafo da região, aguarde...")
    # Constrói o grafo usando o raio de busca (convertendo km para metros)
    G = ox.graph_from_point((center_lat, center_lon), dist=raio_busca*1000, network_type='drive')
    
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
    
    for i, origin_node in enumerate(node_ids):
        for j, dest_node in enumerate(node_ids):
            if i == j:
                distancias_km[i, j] = 0
                custos_viagem[i, j] = 0
            else:
                try:
                    # Calcula a distância em metros e converte para km
                    dist_km = nx.shortest_path_length(G, origin_node, dest_node, weight='length') / 1000.0
                    distancias_km[i, j] = dist_km
                    custos_viagem[i, j] = dist_km * valor_medio_km
                except nx.NetworkXNoPath:
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