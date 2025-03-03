import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import time

#create_tpplib_data(dataframe, *args):
def create_tpplib_data(dataframe, avg_lat=None, avg_lon=None, media_preco=0.0):
    """
    Cria um dicionário `data` com a estrutura semelhante ao arquivo TPP, a partir de um DataFrame com as colunas
    'PRODUTO', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG', usando OSMnx para calcular distâncias viárias.

    Parâmetros:
    - dataframe (pd.DataFrame): DataFrame contendo as colunas 'PRODUTO', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG'.
    - *args: Argumentos adicionais ignorados para compatibilidade.

    Retorna:
    - dict: Dicionário `data` com as variáveis necessárias.
    """
    data = {}
    data['media_preco_combustivel'] = media_preco
    required_columns = {'PRODUTO', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG'}
    if not required_columns.issubset(dataframe.columns):
        raise ValueError(f"DataFrame não contém as colunas necessárias: {required_columns - set(dataframe.columns)}")

    # Atribuir IDs inteiros aos produtos, excluindo o depósito
    produtos_df = dataframe.copy()
    produto_ids, categorias_unicas = produtos_df['PRODUTO'].factorize()
    produto_ids += 1  # IDs dos produtos a partir de 1
    data['K'] = set(range(1, len(categorias_unicas) + 1))  # IDs inteiros para os produtos

    # Consumo Medio do veiculo
    consumo_veiculo_km_por_litro = 10.5

    # Custo Medio do Combustivel
    valor_medio_km = data['media_preco_combustivel'] / consumo_veiculo_km_por_litro

    # Atribuir IDs inteiros aos mercados
    mercado_ids, mercados_unicos = produtos_df['MERCADO'].factorize()
    mercado_ids += 1  # IDs dos mercados começam em 1
    data['M'] = set(mercado_ids)  # Conjunto de IDs inteiros para os mercados

    # Identificação do depósito (assumindo que o depósito é o primeiro mercado)
    data['depot'] = int(mercado_ids[0])  # ID do depósito
    data['V'] = data['M'].union({data['depot']})  # Conjunto de todos os nós

    # Construção de `dk` (demanda) para cada produto
    data['dk'] = {i: 1 for i in data['K']}  # Demanda fixa de 1 unidade por produto

    # Construção de `Mk`: mercados que oferecem cada produto
    data['Mk'] = {i: set() for i in data['K']}
    data['pik'] = {}
    data['qik'] = {}

    # Preenchimento de `Mk`, `pik` e `qik`
    for produto_id, mercado_id, row in zip(produto_ids, mercado_ids, produtos_df.itertuples()):
        mercado_id = int(mercado_id)
        data['Mk'][produto_id].add(mercado_id)  # Adiciona o mercado ao conjunto do produto

        # Armazenando `pik` (preço) e `qik` (quantidade disponível)
        data['pik'][(mercado_id, produto_id)] = float(row.VALOR)  # Preço do produto
        data['qik'][(mercado_id, produto_id)] = 1  # Disponibilidade fixa (ajustável conforme necessário)

    # Extração das coordenadas dos mercados com IDs inteiros
    data['node_coords'] = {int(mercado_ids[idx]): (row['LAT'], row['LONG'])
                           for idx, row in produtos_df.iterrows()}

    # Mapeamento dos nós
    data['node_index'] = {node_id: idx for idx, node_id in enumerate(sorted(data['V']))}

    # Obtenção do grafo da região para cálculo de distâncias viárias
    avg_lat, avg_lon = produtos_df[['LAT', 'LONG']].mean()
    print("Construindo o grafo da região, aguarde...")
    G = ox.graph_from_point((avg_lat, avg_lon), dist=5000, network_type='drive')

    # Identificação dos nós mais próximos e cálculo de distâncias na rede
    mercado_ids_sorted = sorted(data['V'])  # ex.: [1, 2, 3, ...]
    node_ids = []

    for mercado_id in mercado_ids_sorted:
        lat, lon = data['node_coords'][mercado_id]
        nearest_node = ox.distance.nearest_nodes(G, lon, lat)
        node_ids.append(nearest_node)

    # Agora, se mercado_ids_sorted[k] == m, então node_ids[k] é o "nearest_node" do mercado m
    # E data['node_index'][m] == k

    distancias = np.zeros((len(node_ids), len(node_ids)))

    for i, origin_node in enumerate(node_ids):
        for j, dest_node in enumerate(node_ids):
            if i == j:
                distancias[i, j] = 0
            else:
                try:
                    dist_km = nx.shortest_path_length(G, origin_node, dest_node, weight='length') / 1000
                    distancias[i, j] = dist_km * valor_medio_km
                except nx.NetworkXNoPath:
                    distancias[i, j] = float('inf')

    data['distancias'] = distancias.tolist()

    # node_ids = []
    # for mercado_id, (lat, lon) in data['node_coords'].items():
    #     nearest_node = ox.distance.nearest_nodes(G, lon, lat)
    #     node_ids.append(nearest_node)

    # time.sleep(1)  # Pausa para evitar sobrecarga na API do OSMnx
    # distancias = np.zeros((len(node_ids), len(node_ids)))
    # for i, origin in enumerate(node_ids):
    #     for j, destination in enumerate(node_ids):
    #         if i != j:
    #             try:
    #                 dist = nx.shortest_path_length(G, origin, destination, weight='length') / 1000
    #                 distancias[i, j] = dist * valor_medio_km  # Distância em quilômetros
    #             except nx.NetworkXNoPath:
    #                 distancias[i, j] = float('inf')  # Distância infinita se não houver caminho
    #         else:
    #             distancias[i, j] = 0

    # data['distancias'] = distancias.tolist()  # Convertendo para lista

    # Mapeamento de ID do produto para nome do produto
    data['produtos'] = {idx + 1: produto for idx, produto in enumerate(categorias_unicas)}

    # Mapeamento de ID do mercado para informações do mercado
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
