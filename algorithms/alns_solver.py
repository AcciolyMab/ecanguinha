import time
import copy
import random
import math
import logging
from typing import Dict, List, Tuple, Optional, Set

# Configuração do logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Route:
    def __init__(self, depot: str, markets: Optional[Set[str]] = None):
        """
        Inicializa a rota com o depósito e um conjunto opcional de mercados.
        """
        self.route: List[str] = [depot] + (list(markets) if markets else [])
        self.route_set: Set[str] = set(self.route)

    def add_market(self, market: str, position: Optional[int] = None):
        """
        Adiciona um mercado na posição especificada. Se a posição não for fornecida, adiciona ao final.
        """
        if market not in self.route_set:
            if position is None or position < 0 or position > len(self.route):
                self.route.append(market)
            else:
                self.route.insert(position, market)
            self.route_set.add(market)

    def remove_market(self, market: str):
        """
        Remove um mercado da rota.
        """
        if market in self.route_set:
            self.route.remove(market)
            self.route_set.remove(market)

    def __contains__(self, market: str) -> bool:
        """
        Permite verificar se um mercado está na rota usando a sintaxe 'market in route_obj'.
        """
        return market in self.route_set

    def get_route(self) -> List[str]:
        """
        Retorna a lista de mercados na rota.
        """
        return self.route

    def deepcopy(self):
        """
        Retorna uma cópia profunda do objeto Route.
        """
        return copy.deepcopy(self)


# def alns_solve_tpp(data: Dict, max_iterations: int, no_improve_limit: int):
#     # Extrair dados
#     K = data['K']  # Conjunto de produtos
#     M = data['M']  # Conjunto de mercados
#     depot = data['depot']

#     # Evitar duplicação do depósito em V
#     V = [depot] + [m for m in M if m != depot]  # Inclui o depósito apenas uma vez

#     Mk = data['Mk']  # Mercados que vendem cada produto k
#     pik_original = data['pik']  # Preço do produto k no mercado i
#     distancias = data['distancias']  # Matriz de distâncias

#     # Verificar se a matriz de distâncias está corretamente dimensionada
#     assert len(distancias) == len(V), "A matriz de distâncias deve ter uma linha para cada nó em V."
#     for idx, row in enumerate(distancias):
#         assert len(row) == len(V), f"A linha {idx} na matriz de distâncias não possui a dimensão correta."

#     node_index = {node_id: index for index, node_id in enumerate(V)}  # Mapeamento de nós para índices
#     if depot not in node_index:
#         node_index[depot] = len(node_index)  # Atribui um índice se `depot` não estiver presente

#     # Criar uma cópia local de 'pik' para evitar modificar 'data'
#     pik = pik_original.copy()

#     # Verificar os dados antes de iniciar
#     if not verificar_dados(K, Mk, pik):
#         logger.error("Os dados de entrada contêm erros. O algoritmo não pode ser executado.")
#         return None, None, None

#     # Parâmetros do ALNS
#     destroy_operators = [random_removal, worst_removal]
#     repair_operators = [greedy_insertion, random_insertion]
#     weights_destroy = [1] * len(destroy_operators)
#     weights_repair = [1] * len(repair_operators)
#     scores_destroy = [0] * len(destroy_operators)
#     scores_repair = [0] * len(repair_operators)
#     segment_length = 60
#     reaction_factor = 0.4

#     # Solução inicial
#     current_solution = initial_solution(K, M, depot, Mk, pik)
#     current_cost = calculate_cost(current_solution, distancias, node_index, pik)
#     best_solution = copy.deepcopy(current_solution)
#     best_cost = current_cost

#     iteration = 0
#     no_improve = 0
#     start_time = time.time()

#     while iteration < max_iterations and no_improve < no_improve_limit:
#         iteration += 1

#         # Selecionar operadores com base nos pesos
#         destroy_operator = random.choices(destroy_operators, weights=weights_destroy)[0]
#         repair_operator = random.choices(repair_operators, weights=weights_repair)[0]

#         # Aplicar operadores
#         partial_solution = destroy_operator(current_solution)
#         new_solution = repair_operator(partial_solution, K, Mk, pik, distancias, node_index, depot)

#         if new_solution is None:
#             # Se a solução é inválida, pula para a próxima iteração
#             no_improve += 1
#             continue

#         new_cost = calculate_cost(new_solution, distancias, node_index, pik)

#         # Aceitar a nova solução com base no critério de aceitação (simulated annealing)
#         if acceptance_criterion(current_cost, new_cost, iteration, max_iterations):
#             current_solution = new_solution
#             current_cost = new_cost

#             # Atualizar melhor solução
#             if new_cost < best_cost:
#                 best_solution = copy.deepcopy(new_solution)
#                 best_cost = new_cost
#                 no_improve = 0
#                 logger.info(f"Melhoria encontrada na iteração {iteration}: Custo = {best_cost}")
#             else:
#                 no_improve += 1
#         else:
#             no_improve += 1

#         # Atualizar pesos dos operadores a cada segmento
#         if iteration % segment_length == 0:
#             for i in range(len(weights_destroy)):
#                 weights_destroy[i] = (1 - reaction_factor) * weights_destroy[i] + reaction_factor * scores_destroy[i]
#                 scores_destroy[i] = 0
#             for i in range(len(weights_repair)):
#                 weights_repair[i] = (1 - reaction_factor) * weights_repair[i] + reaction_factor * scores_repair[i]
#                 scores_repair[i] = 0

#     end_time = time.time()
#     execution_time = end_time - start_time

#     if best_solution is None:
#         logger.error("Não foi possível encontrar uma solução viável.")
#         return None

#     return format_result(best_solution, best_cost, execution_time, distancias, node_index, data)

def alns_solve_tpp(data: Dict, max_iterations: int, no_improve_limit: int):
    # Extrair dados
    K = data['K']  # Conjunto de produtos
    M = data['M']  # Conjunto de mercados
    depot = data['depot']

    # Evitar duplicação do depósito em V
    V = [depot] + [m for m in M if m != depot]  # Inclui o depósito apenas uma vez

    Mk = data['Mk']  # Mercados que vendem cada produto k
    pik_original = data['pik']  # Preço do produto k no mercado i
    distancias = data['distancias']  # Matriz de distâncias

    # Verificar se a matriz de distâncias está corretamente dimensionada
    assert len(distancias) == len(V), "A matriz de distâncias deve ter uma linha para cada nó em V."
    for idx, row in enumerate(distancias):
        assert len(row) == len(V), f"A linha {idx} na matriz de distâncias não possui a dimensão correta."

    node_index = {node_id: index for index, node_id in enumerate(V)}  # Mapeamento de nós para índices
    if depot not in node_index:
        node_index[depot] = len(node_index)  # Atribui um índice se `depot` não estiver presente

    # Criar uma cópia local de 'pik' para evitar modificar 'data'
    pik = pik_original.copy()

    # Verificar os dados antes de iniciar
    if not verificar_dados(K, Mk, pik):
        logger.error("Os dados de entrada contêm erros. O algoritmo não pode ser executado.")
        return None, None, None

    # Parâmetros do ALNS
    destroy_operators = [random_removal, worst_removal]
    repair_operators = [greedy_insertion, random_insertion]
    weights_destroy = [1] * len(destroy_operators)
    weights_repair = [1] * len(repair_operators)
    scores_destroy = [0] * len(destroy_operators)
    scores_repair = [0] * len(repair_operators)
    segment_length = 60
    reaction_factor = 0.4

    # Solução inicial
    current_solution = initial_solution(K, M, depot, Mk, pik)
    current_cost = calculate_cost(current_solution, distancias, node_index, pik)
    best_solution = copy.deepcopy(current_solution)
    best_cost = current_cost

    iteration = 0
    # Controla iterações sem melhoria na melhor solução
    no_improve_best = 0

    # Novo: Contador de soluções inviáveis
    infeasible_count = 0
    max_infeasible_solutions = 50  # ou outro limite que faça sentido

    start_time = time.time()

    # Loop principal
    while (iteration < max_iterations 
           and no_improve_best < no_improve_limit
           and infeasible_count < max_infeasible_solutions):

        iteration += 1

        # Selecionar operadores com base nos pesos
        destroy_operator = random.choices(destroy_operators, weights=weights_destroy)[0]
        repair_operator = random.choices(repair_operators, weights=weights_repair)[0]

        # Aplicar operadores (Destruição + Reparo)
        # partial_solution = destroy_operator(current_solution)
        if destroy_operator == worst_removal:
            partial_solution = worst_removal(current_solution, distancias, node_index, pik, remove_fraction=0.2)
        else:
            partial_solution = destroy_operator(current_solution)
        new_solution = repair_operator(partial_solution, K, Mk, pik, distancias, node_index, depot)

        # Se a solução é inválida, tratamos separadamente, sem mexer em no_improve_best
        if new_solution is None:
            infeasible_count += 1
            continue  # pula para a próxima iteração
        else:
            # Se encontrarmos uma solução viável, zeramos o contador de inviáveis (caso seja "consecutivo")
            infeasible_count = 0

        new_cost = calculate_cost(new_solution, distancias, node_index, pik)

        # Critério de aceitação (Simulated Annealing)
        if acceptance_criterion(current_cost, new_cost, iteration, max_iterations):
            # Atualiza solução corrente, mesmo que seja pior
            current_solution = new_solution
            current_cost = new_cost

            # Verifica se houve melhoria global
            if new_cost < best_cost:
                best_solution = copy.deepcopy(new_solution)
                best_cost = new_cost
                no_improve_best = 0  # Zera pois melhorou a melhor solução
                logger.info(f"Melhoria encontrada na iteração {iteration}: Custo = {best_cost}")
            else:
                # Aceita mas não melhorou a melhor solução
                no_improve_best += 1
        else:
            # Solução não aceita => não há melhoria global
            no_improve_best += 1

        # Atualizar pesos dos operadores a cada "segment_length" iterações
        if iteration % segment_length == 0:
            for i in range(len(weights_destroy)):
                weights_destroy[i] = (1 - reaction_factor) * weights_destroy[i] + reaction_factor * scores_destroy[i]
                scores_destroy[i] = 0
            for i in range(len(weights_repair)):
                weights_repair[i] = (1 - reaction_factor) * weights_repair[i] + reaction_factor * scores_repair[i]
                scores_repair[i] = 0

    end_time = time.time()
    execution_time = end_time - start_time

    # Caso não tenha encontrado uma solução viável
    if best_solution is None:
        logger.error("Não foi possível encontrar uma solução viável.")
        return None, None, None

    # Formatar resultado final
    return format_result(best_solution, best_cost, execution_time, distancias, node_index, data)



def format_result(solution: Dict, best_cost: float, execution_time: float, distancias: List[List[float]],
                 node_index: Dict[str, int], data: Dict) -> Dict:
    route = solution['route_obj'].get_route()
    purchases = solution['purchases']
    total_distance = 0

    # Calcular a distância total percorrida
    for i in range(len(route) - 1):
        origem = route[i]
        destino = route[i + 1]
        total_distance += distancias[node_index[origem]][node_index[destino]]
    # Voltar para o depósito
    total_distance += distancias[node_index[route[-1]]][node_index[route[0]]]

    # Preparar as compras detalhadas e incluir coordenadas e endereço dos mercados
    compras_detalhadas = {}
    mercados_comprados = []

    for market, products in purchases.items():
        market_info = data['mercados'][market]
        market_name = market_info['nome']
        market_address = market_info['endereco']
        latitude = market_info['latitude']
        longitude = market_info['longitude']

        compras_detalhadas[f'Produtos comprados no {market_name}'] = []
        for k in products:
            nome_produto = data['produtos'][k]
            preco_produto = data['pik'][(market, k)]
            compras_detalhadas[f'Produtos comprados no {market_name}'].append({
                'produto': nome_produto,
                'preco': preco_produto
            })

        # Adicionar informações para o mapa
        mercados_comprados.append({
            'nome': market_name,
            'endereco': market_address,
            'latitude': latitude,
            'longitude': longitude
        })

    resultado = {
        'route': [data['depot']] + [m for m in route if m != data['depot']] + [data['depot']],
        'purchases': compras_detalhadas,
        'total_cost': round(best_cost, 2),
        'total_distance': round(total_distance, 2),
        'execution_time': round(execution_time, 2),
        'mercados_comprados': mercados_comprados  # Informação adicional para o mapa
    }

    logger.debug(f"Resultado formatado: {resultado}")
    return resultado


def verificar_dados(K: List[str], Mk: Dict[str, Set[str]], pik: Dict[Tuple[str, str], float]) -> bool:
    problemas = False

    for k in K:
        mercados_disponiveis = Mk.get(k, set())
        if not mercados_disponiveis:
            logger.warning(f"Aviso: Não há mercados que vendem o produto {k}.")
            problemas = True
        else:
            mercado_valido = False
            for mercado in mercados_disponiveis:
                if (mercado, k) in pik:
                    mercado_valido = True
                    break
            if not mercado_valido:
                logger.warning(f"Aviso: Nenhum mercado válido encontrado para o produto {k}.")
                problemas = True

    if problemas:
        logger.error("Erros encontrados nos dados de entrada. Por favor, corrija antes de prosseguir.")
        return False
    else:
        logger.info("Dados de entrada verificados com sucesso.")
        return True


def initial_solution(K: List[str], M: List[str], depot: str, Mk: Dict[str, Set[str]],
                    pik: Dict[Tuple[str, str], float]) -> Dict:
    # Solução construtiva inicial (por exemplo, compra em mercados aleatórios)
    purchases: Dict[str, List[str]] = {}
    markets_to_visit: Set[str] = set()

    for k in K:
        mercados_possiveis = Mk.get(k, set())
        mercados_validos = [i for i in mercados_possiveis if (i, k) in pik]
        if not mercados_validos:
            logger.warning(f"Produto {k} não tem mercados disponíveis na solução inicial.")
            continue  # Ou trate conforme necessário
        i = random.choice(mercados_validos)
        if i not in purchases:
            purchases[i] = []
        purchases[i].append(k)
        markets_to_visit.add(i)

    route_obj = Route(depot, markets_to_visit)

    solution = {'route_obj': route_obj, 'purchases': purchases}
    return solution


# def calculate_cost(solution: Dict, distancias: List[List[float]], node_index: Dict[str, int],
#                   pik: Dict[Tuple[str, str], float]) -> float:
#     if solution is None:
#         return float('inf')

#     route = solution['route_obj'].get_route()
#     purchases = solution['purchases']

#     # Custo de viagem
#     total_distance = 0
#     for i in range(len(route) - 1):
#         origem = route[i]
#         destino = route[i + 1]
#         total_distance += distancias[node_index[origem]][node_index[destino]]
#     # Voltar para o depósito
#     total_distance += distancias[node_index[route[-1]]][node_index[route[0]]]

#     # Custo de compra
#     total_purchase_cost = 0
#     for market, products in purchases.items():
#         for k in products:
#             if (market, k) in pik:
#                 total_purchase_cost += pik[(market, k)]
#             else:
#                 logger.error(f"Erro: Produto {k} não está disponível no mercado {market}.")
#                 return float('inf')  # Solução inviável

#     total_cost = total_distance + total_purchase_cost
#     return total_cost


# def acceptance_criterion(current_cost: float, new_cost: float, iteration: int, max_iterations: int) -> bool:
#     # Critério de aceitação usando Simulated Annealing
#     if new_cost < current_cost:
#         return True
#     else:
#         temperature = max(0.01, min(1, 1 - iteration / max_iterations))
#         probability = math.exp(-(new_cost - current_cost) / temperature)
#         return random.random() < probability

def acceptance_criterion(current_cost: float, new_cost: float, iteration: int, max_iterations: int) -> bool:
    """
    Critério de aceitação usando Simulated Annealing:
      - Se o novo custo é menor, aceita a solução.
      - Caso contrário, aceita com uma probabilidade que diminui conforme a 'temperatura' (derivada da iteração atual).
    """
    if new_cost < current_cost:
        return True
    else:
        # Calcula uma "temperatura" decrescente (mínimo de 0.01, máximo de 1)
        temperature = max(0.01, min(1, 1 - iteration / max_iterations))
        # Probabilidade de aceitar uma piora
        probability = math.exp(-(new_cost - current_cost) / temperature)
        return random.random() < probability
    
def calculate_cost(solution: Dict, distancias: List[List[float]], node_index: Dict[str, int],
                   pik: Dict[Tuple[str, str], float]) -> float:
    if solution is None:
        return float('inf')

    route = solution['route_obj'].get_route()
    purchases = solution['purchases']

    # Custo de viagem
    total_distance = 0
    for i in range(len(route) - 1):
        origem = route[i]
        destino = route[i + 1]
        total_distance += distancias[node_index[origem]][node_index[destino]]
    # Voltar para o depósito
    total_distance += distancias[node_index[route[-1]]][node_index[route[0]]]

    # Custo de compra
    total_purchase_cost = 0
    for market, products in purchases.items():
        for k in products:
            if (market, k) in pik:
                total_purchase_cost += pik[(market, k)]
            else:
                logger.error(f"Erro: Produto {k} não está disponível no mercado {market}.")
                return float('inf')  # Solução inviável

    # Penalizar mercados com apenas um item: para cada mercado com somente 1 produto, adiciona-se uma penalidade
    penalty_value = 100  # Valor de penalidade (ajuste conforme necessário)
    for market, products in purchases.items():
        if len(products) == 1:
            total_purchase_cost += penalty_value

    total_cost = total_distance + total_purchase_cost
    return total_cost



def random_removal(solution: Dict, remove_fraction: float = 0.2) -> Dict:
    """
    Remove aleatoriamente uma fração dos mercados da rota.
    """
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    num_to_remove = max(1, int(len(route_obj.get_route()) * remove_fraction))
    if len(route_obj.get_route()) <= num_to_remove + 1:
        return new_solution  # Não pode remover mais mercados

    # Evitar remover o depósito
    mercados_disponiveis = list(route_obj.route_set - {route_obj.route[0]})
    markets_to_remove = random.sample(mercados_disponiveis, min(num_to_remove, len(mercados_disponiveis)))

    for market in markets_to_remove:
        route_obj.remove_market(market)
        del purchases[market]

    return new_solution


# def worst_removal(solution: Dict, remove_fraction: float = 0.2) -> Dict:
#     """
#     Remove mercados com menor impacto no custo.
#     """
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']

#     num_to_remove = max(1, int(len(route_obj.get_route()) * remove_fraction))
#     if len(route_obj.get_route()) <= num_to_remove + 1:
#         return new_solution  # Não pode remover mais mercados

#     market_costs = {}
#     for market in route_obj.get_route()[1:]:  # Exclui o depósito
#         purchase_cost = len(purchases[market])  # Contar o número de produtos
#         market_costs[market] = purchase_cost

#     # Ordenar mercados pelo menor custo de compra
#     markets_sorted = sorted(market_costs.items(), key=lambda x: x[1])
#     markets_to_remove = [market for market, cost in markets_sorted[:num_to_remove]]

#     for market in markets_to_remove:
#         route_obj.remove_market(market)
#         del purchases[market]

#     return new_solution

def worst_removal(solution: Dict,
                  distancias: List[List[float]],
                  node_index: Dict[str, int],
                  pik: Dict[Tuple[str, str], float],
                  remove_fraction: float = 0.2) -> Dict:
    """
    Remove os mercados com maior impacto (custo total = custo de produtos + impacto na distância)
    em vez de simplesmente remover os mercados com menos produtos.
    """
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']
    route = route_obj.get_route()

    num_to_remove = max(1, int(len(route) * remove_fraction))
    # Se quase não há mercados para remover (além do depósito), encerra
    if len(route) <= num_to_remove + 1:
        return new_solution

    market_impact = {}
    
    # Percorre os mercados na rota (excluindo o depósito)
    # range(1, len(route) - 1) para não considerar o depósito na posição 0,
    # e, se necessário, ignorar também a volta final (caso não queira remover se for o último).
    # Se quiser considerar todos no meio (sem remover o primeiro e último se forem depósitos),
    # ajuste conforme a sua regra de negócio.
    for i in range(1, len(route)):
        market = route[i]
        # Se o mercado for o depósito, ignoramos
        if market == route[0]:
            continue
        # Custo de compra neste mercado (soma dos preços dos produtos)
        purchase_cost = sum(pik[(market, k)] for k in purchases[market]) if market in purchases else 0

        # Calcula o impacto em termos de distância
        # Se 'market' não for o último, o sucessor é route[i+1], senão voltamos ao depósito
        if i < len(route) - 1:
            successor = route[i + 1]
        else:
            successor = route[0]  # retorna ao depósito

        predecessor = route[i - 1]
        
        # Distância percorrida incluindo o mercado
        dist_with_market = (distancias[node_index[predecessor]][node_index[market]] +
                            distancias[node_index[market]][node_index[successor]])
        # Distância se pulássemos esse mercado
        dist_without_market = distancias[node_index[predecessor]][node_index[successor]]

        distance_impact = dist_with_market - dist_without_market

        # Impacto total = impacto de distância + custo de compra
        total_impact = distance_impact + purchase_cost
        market_impact[market] = total_impact

    # Ordena mercados do maior impacto para o menor
    sorted_by_impact = sorted(market_impact.items(), key=lambda x: x[1], reverse=True)
    markets_to_remove = [m for (m, _) in sorted_by_impact[:num_to_remove]]

    # Remove os mercados de maior impacto
    for market in markets_to_remove:
        if market in route_obj:
            route_obj.remove_market(market)
        if market in purchases:
            del purchases[market]

    return new_solution


# def greedy_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
#                     pik: Dict[Tuple[str, str], float], distancias: List[List[float]],
#                     node_index: Dict[str, int], depot: str) -> Optional[Dict]:
#     """
#     Insere mercados de forma gulosa para atender todos os produtos.
#     """
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']

#     products_needed = set(K)
#     for products in purchases.values():
#         products_needed -= set(products)

#     while products_needed:
#         best_market = None
#         best_product = None
#         best_cost = float('inf')
#         for k in products_needed:
#             for market in Mk.get(k, set()):
#                 if (market, k) in pik:
#                     if market in route_obj:
#                         additional_cost = 0
#                     else:
#                         # Custo de inserção do mercado na rota
#                         try:
#                             additional_cost = min(
#                                 (
#                                     distancias[node_index[route_obj.route[i]]][node_index[market]] +
#                                     distancias[node_index[market]][
#                                         node_index[route_obj.route[i + 1]] if i + 1 < len(route_obj.route) else node_index[depot]
#                                     ] -
#                                     distancias[node_index[route_obj.route[i]]][
#                                         node_index[route_obj.route[i + 1]] if i + 1 < len(route_obj.route) else node_index[depot]
#                                     ]
#                                 )
#                                 for i in range(len(route_obj.route))
#                             )
#                         except KeyError as e:
#                             logger.error(f"Erro no acesso às distâncias: {e}")
#                             return None

#                     total_cost = pik[(market, k)] + additional_cost
#                     if total_cost < best_cost:
#                         best_cost = total_cost
#                         best_market = market
#                         best_product = k

#         if best_market is None:
#             logger.warning("Não foi possível encontrar um mercado para um dos produtos necessários.")
#             # Remove produtos que não podem ser atendidos e continue
#             products_to_remove = [k for k in products_needed if not Mk.get(k, set())]
#             for k in products_to_remove:
#                 logger.warning(f"Removendo o produto {k} da lista de necessidades.")
#                 products_needed.remove(k)
#             continue

#         if best_market not in route_obj:
#             # Inserir mercado na melhor posição
#             best_position = None
#             min_increase = float('inf')
#             for i in range(len(route_obj.route)):
#                 prev_market = route_obj.route[i]
#                 next_market = route_obj.route[i + 1] if i + 1 < len(route_obj.route) else depot
#                 increase = distancias[node_index[prev_market]][node_index[best_market]] + \
#                            distancias[node_index[best_market]][node_index[next_market]] - \
#                            distancias[node_index[prev_market]][node_index[next_market]]
#                 if increase < min_increase:
#                     min_increase = increase
#                     best_position = i + 1
#             if best_position is not None:
#                 route_obj.add_market(best_market, best_position)
#             else:
#                 # Se não encontrar uma posição melhor, insere antes de retornar ao depósito
#                 route_obj.add_market(best_market, -1)

#         if best_market not in purchases:
#             purchases[best_market] = []
#         purchases[best_market].append(best_product)
#         products_needed.remove(best_product)

#     return new_solution

def greedy_insertion(solution: Dict,
                     K: List[str],
                     Mk: Dict[str, Set[str]],
                     pik: Dict[Tuple[str, str], float],
                     distancias: List[List[float]],
                     node_index: Dict[str, int],
                     depot: str) -> Optional[Dict]:
    """
    Versão otimizada para instâncias grandes:
    - Insere os mercados que faltam de forma "gulosa" em relação ao custo de produto
      e com inserção simplificada (no final da rota).
    - Evita iterar por todas as posições possíveis da rota, reduzindo a complexidade.

    Retorna a nova solução ou None em caso de erro.
    """

    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    # Produtos que ainda não foram comprados
    products_needed = set(K)
    for prods in purchases.values():
        products_needed -= set(prods)

    while products_needed:
        best_market = None
        best_product = None
        best_cost = float('inf')

        # Para cada produto que ainda precisamos comprar
        for k in products_needed:
            # Lista de mercados que vendem esse produto
            possible_markets = Mk.get(k, set())
            for market in possible_markets:
                # Só consideramos se realmente tiver preço pik
                if (market, k) not in pik:
                    continue

                # Custo de compra do produto
                product_cost = pik[(market, k)]

                if market in route_obj:
                    # Se o mercado já está na rota, "custo de inserção" é zero (já visitamos)
                    insertion_cost = 0
                else:
                    # Estratégia de inserção no final da rota (antes de voltar ao depósito)
                    last_node = route_obj.route[-1]  # Último da rota atual
                    # Se o último da rota for o depósito, podemos usar o penúltimo
                    # ou simplesmente considerar esse "último" mesmo.
                    if last_node == depot and len(route_obj.route) > 1:
                        last_node = route_obj.route[-2]

                    # Custo adicional de ir do 'last_node' ao 'market'
                    # e depois do 'market' até o depósito (fechando)
                    insertion_cost = (
                        distancias[node_index[last_node]][node_index[market]]
                        + distancias[node_index[market]][node_index[depot]]
                        - distancias[node_index[last_node]][node_index[depot]]
                    )

                total_cost = product_cost + insertion_cost

                # Verifica se é o melhor custo até agora
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_market = market
                    best_product = k

        # Se não encontrou nenhum mercado para algum produto, remover produto da lista
        if best_market is None:
            logger.warning("Não foi possível encontrar um mercado para um dos produtos necessários.")
            # Remove produtos que não podem ser atendidos e continue
            products_to_remove = [k for k in products_needed if not Mk.get(k, set())]
            for k in products_to_remove:
                logger.warning(f"Removendo o produto {k} da lista de necessidades.")
                products_needed.remove(k)
            continue

        # Faz a inserção do mercado na rota (se ainda não estiver)
        if best_market not in route_obj:
            # Insere logo antes do depósito, ou seja, no final
            # Posição final é len(route_obj.route) - 0, mas
            # normalmente chamando -1 insere literalmente no final, 
            # pois a classe Route gerencia a posição do depósito depois.
            # Vamos inserir explicitamente antes do depósito:
            insert_pos = len(route_obj.route)
            # Se o depósito estiver no final, inserir na penúltima posição
            if route_obj.route[-1] == depot:
                insert_pos -= 1

            route_obj.add_market(best_market, insert_pos)

        # Adiciona o produto ao mercado
        if best_market not in purchases:
            purchases[best_market] = []
        purchases[best_market].append(best_product)

        # Remove o produto da lista de necessários
        products_needed.remove(best_product)

    return new_solution


def random_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
                    pik: Dict[Tuple[str, str], float], distancias: List[List[float]],
                    node_index: Dict[str, int], depot: str) -> Optional[Dict]:
    """
    Insere mercados aleatoriamente para atender todos os produtos.
    """
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    products_needed = set(K)
    for products in purchases.values():
        products_needed -= set(products)

    while products_needed:
        k = random.choice(list(products_needed))
        mercados_possiveis = Mk.get(k, set())
        mercados_validos = [i for i in mercados_possiveis if (i, k) in pik]
        if not mercados_validos:
            logger.warning(f"Não há mercados que vendem o produto {k}. Removendo-o da lista de necessidades.")
            products_needed.remove(k)
            continue
        market = random.choice(mercados_validos)
        if market not in route_obj:
            position = random.randint(1, len(route_obj.route) - 1)
            route_obj.add_market(market, position)
        if market not in purchases:
            purchases[market] = []
        purchases[market].append(k)
        products_needed.remove(k)

    return new_solution


# def run_alns_recursive(data: Dict, max_iterations: int, no_improve_limit: int,
#                        run_count: int = 1, max_runs: int = 10,
#                        accumulated_results: Optional[List[Dict]] = None) -> List[Dict]:
#     if accumulated_results is None:
#         accumulated_results = []

#     if run_count > max_runs:
#         # Todas as execuções concluídas
#         total_cost = sum(result['cost'] for result in accumulated_results if result['cost'] is not None)
#         total_time = sum(
#             result['execution_time'] for result in accumulated_results if result['execution_time'] is not None)
#         successful_runs = len([result for result in accumulated_results if result['cost'] is not None])
#         average_cost = total_cost / successful_runs if successful_runs > 0 else float('inf')
#         average_time = total_time / successful_runs if successful_runs > 0 else float('inf')

#         logger.info("\n--- Resultados Finais ---")
#         logger.info(f"Média dos custos totais das {max_runs} execuções: {average_cost:.2f}")
#         logger.info(f"Média dos tempos de execução das {max_runs} execuções: {average_time:.2f} segundos")

#         # Agregar os mercados com itens comprados
#         aggregated_purchases: Dict[str, int] = {}
#         for result in accumulated_results:
#             if result['purchases'] is not None:
#                 for market, produtos in result['purchases'].items():
#                     if market not in aggregated_purchases:
#                         aggregated_purchases[market] = 0
#                     aggregated_purchases[market] += len(produtos)

#         # Opcional: Exibir informações agregadas
#         # logger.info("\n--- Mercados com Itens Comprados (Agregado) ---")
#         # for market, count in aggregated_purchases.items():
#         #     logger.info(f"Mercado {market}: {count} itens comprados")

#         return accumulated_results

#     logger.info(f"\n--- Execução {run_count} ---")
#     best_solution, best_cost, execution_time = alns_solve_tpp(data, max_iterations, no_improve_limit)

#     # Adicionar os resultados da execução atual
#     accumulated_results.append({
#         'run': run_count,
#         'cost': best_cost,
#         'execution_time': execution_time,
#         'purchases': best_solution['purchases'] if best_solution else None
#     })

#     # Prosseguir para a próxima execução
#     return run_alns_recursive(data, max_iterations, no_improve_limit, run_count + 1, max_runs, accumulated_results)

def run_alns_recursive(data: Dict,
                       max_iterations: int,
                       no_improve_limit: int,
                       run_count: int = 1,
                       max_runs: int = 10,
                       accumulated_results: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Executa várias rodadas do alns_solve_tpp de forma iterativa (em vez de recursiva),
    acumulando os resultados de cada execução.
    """

    if accumulated_results is None:
        accumulated_results = []

    # Loop de run_count até max_runs, sem recursão.
    for current_run in range(run_count, max_runs + 1):
        logger.info(f"\n--- Execução {current_run} ---")
        best_solution, best_cost, execution_time = alns_solve_tpp(data, max_iterations, no_improve_limit)

        # Adicionar os resultados da execução atual
        accumulated_results.append({
            'run': current_run,
            'cost': best_cost,
            'execution_time': execution_time,
            'purchases': best_solution['purchases'] if best_solution else None
        })

    # Após concluir todas as execuções, computar estatísticas finais
    total_cost = sum(result['cost'] for result in accumulated_results if result['cost'] is not None)
    total_time = sum(result['execution_time'] for result in accumulated_results if result['execution_time'] is not None)
    successful_runs = len([result for result in accumulated_results if result['cost'] is not None])
    average_cost = total_cost / successful_runs if successful_runs > 0 else float('inf')
    average_time = total_time / successful_runs if successful_runs > 0 else float('inf')

    logger.info("\n--- Resultados Finais ---")
    logger.info(f"Média dos custos totais das {max_runs} execuções: {average_cost:.2f}")
    logger.info(f"Média dos tempos de execução das {max_runs} execuções: {average_time:.2f} segundos")

    # Agregar compras em mercados (caso seja útil para estatísticas)
    aggregated_purchases: Dict[str, int] = {}
    for result in accumulated_results:
        if result['purchases'] is not None:
            for market, produtos in result['purchases'].items():
                if market not in aggregated_purchases:
                    aggregated_purchases[market] = 0
                aggregated_purchases[market] += len(produtos)

    # (Opcional) Exibir informações agregadas
    # logger.info("\n--- Mercados com Itens Comprados (Agregado) ---")
    # for market, count in aggregated_purchases.items():
    #     logger.info(f"Mercado {market}: {count} itens comprados")

    return accumulated_results
