import time
import copy
import random
import math
import logging
from dataclasses import dataclass

@dataclass
class ALNSConfig:
    """
    Parâmetros do ALNS conforme Ropke e Pisinger (2006),
    referenciados na Seção 4.3 da dissertação.
    """
    segment_length: int = 60        # L na dissertação (linha 5 do Algoritmo 4.1)
    reaction_factor: float = 0.4    # η na dissertação (linha 6 do Algoritmo 4.1)
    remove_fraction: float = 0.2    # fração de destruição dos operadores
    penalty_value: float = 10.0     # penalidade por mercado com item único
    max_infeasible: int = 50        # infMax (linha 9 do Algoritmo 4.1)
    # Recompensas σ1, σ2, σ3 conforme Algoritmo 2.1 da dissertação
    sigma1: float = 3.0  # nova melhor solução global
    sigma2: float = 2.0  # melhora solução corrente, não a global
    sigma3: float = 1.0  # aceita por simulated annealing (não melhora)
    # Parâmetros do esquema de resfriamento (Simulated Annealing)
    initial_temperature: float = 1.0   # T_max: temperatura inicial (sistema "quente")
    min_temperature: float = 0.01      # T_min: piso da temperatura (evita divisão por zero)

from typing import Dict, List, Tuple, Optional, Set

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Classe para gerenciar a rota
class Route:
    def __init__(self, depot: str, markets: Optional[Set[str]] = None):
        self.route: List[str] = [depot] + (list(markets) if markets else [])
        self.route_set: Set[str] = set(self.route)

    def add_market(self, market: str, position: Optional[int] = None):
        if market not in self.route_set:
            if position is None or position < 0 or position > len(self.route):
                self.route.append(market)
            else:
                self.route.insert(position, market)
            self.route_set.add(market)

    def remove_market(self, market: str):
        if market in self.route_set:
            self.route.remove(market)
            self.route_set.remove(market)

    def __contains__(self, market: str) -> bool:
        return market in self.route_set

    def get_route(self) -> List[str]:
        return self.route

    def deepcopy(self):
        return copy.deepcopy(self)


def alns_solve_tpp(data: Dict, max_iterations: int, no_improve_limit: int,
                   session_key: Optional[str] = None,
                   task_id: Optional[str] = None,
                   config: Optional[ALNSConfig] = None):

    if config is None:
        config = ALNSConfig()  # usa defaults — nenhuma chamada existente quebra

    # Extrair dados
    K = data['K']           # Conjunto de produtos
    M = data['M']           # Conjunto de mercados
    depot = data['depot']   # Depot (localização do comprador)

    # Monta a lista de nós: o depot seguido dos demais mercados (sem duplicação)
    V = [depot] + [m for m in M if m != depot]

    Mk = data['Mk']         # Mercados que vendem cada produto
    pik_original = data['pik']  # Preços dos produtos nos mercados

    # Obter as duas matrizes:
    distancias_km = data['distancias_km']  # Distâncias em km
    custos_viagem = data['custos_viagem']  # Custos da viagem em R$

    # Verifica se a matriz de custos está corretamente dimensionada
    assert len(custos_viagem) == len(V), "A matriz de custos deve ter uma linha para cada nó em V."
    for idx, row in enumerate(custos_viagem):
        assert len(row) == len(V), f"A linha {idx} na matriz de custos não possui a dimensão correta."

    node_index = {node_id: index for index, node_id in enumerate(V)}
    if depot not in node_index:
        node_index[depot] = len(node_index)

    # Cria uma cópia local de 'pik'
    pik = pik_original.copy()

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
    segment_length = config.segment_length
    reaction_factor = config.reaction_factor

    # Solução inicial
    current_solution = initial_solution(K, M, depot, Mk, pik)
    current_cost = calculate_cost(current_solution, custos_viagem, node_index, pik)
    best_solution = copy.deepcopy(current_solution)
    best_cost = current_cost

    iteration = 0
    no_improve_best = 0
    infeasible_count = 0
    max_infeasible_solutions = config.max_infeasible
    start_time = time.time()

    while iteration < max_iterations and no_improve_best < no_improve_limit and infeasible_count < max_infeasible_solutions:
        iteration += 1

        if session_key and task_id and iteration % 100 == 0:
            from django.core.cache import cache
            progresso_base = 76
            progresso_max = 99
            progresso = progresso_base + int((iteration / max_iterations) * (progresso_max - progresso_base))
            progresso = min(progresso, progresso_max)
            cache_key = f"progresso_{session_key}_{task_id}"
            cache.set(cache_key, progresso, timeout=600)
            logger.info(f"📈 Progresso solver atualizado: {progresso}% (iteração {iteration})")

        # --- Etapa 1: seleção com índice para rastrear qual operador foi usado ---
        destroy_idx = random.choices(range(len(destroy_operators)), weights=weights_destroy)[0]
        repair_idx  = random.choices(range(len(repair_operators)),  weights=weights_repair)[0]

        destroy_operator = destroy_operators[destroy_idx]
        repair_operator  = repair_operators[repair_idx]

        # --- Destruição (usando config em vez de hardcode) ---
        if destroy_operator == worst_removal:
            partial_solution = worst_removal(
                current_solution, custos_viagem, node_index, pik,
                remove_fraction=config.remove_fraction
            )
        else:
            partial_solution = destroy_operator(
                current_solution,
                remove_fraction=config.remove_fraction
            )

        # --- Reparo ---
        new_solution = repair_operator(partial_solution, K, Mk, pik, custos_viagem, node_index, depot)

        # --- Solução inviável ---
        if new_solution is None:
            infeasible_count += 1
            continue
        else:
            infeasible_count = 0

        new_cost = calculate_cost(
            new_solution, custos_viagem, node_index, pik,
            penalty_value=config.penalty_value
        )

        # --- Etapas 2 e 3: critério de aceitação + scores σ1, σ2, σ3 ---
        # Conforme Algoritmo 2.1 da dissertação (Ropke e Pisinger, 2006)
        accepted      = False
        score_awarded = 0

        if new_cost < current_cost:
            # Melhora a solução corrente — aceita imediatamente
            accepted = True
            if new_cost < best_cost:
                score_awarded = config.sigma1   # σ1: melhorou a melhor global
            else:
                score_awarded = config.sigma2   # σ2: melhorou corrente, não a global

        else:
            # Critério Simulated Annealing: pode aceitar solução pior
            # Usa config.initial_temperature e config.min_temperature
            # em vez de literais 1.0 e 0.01 (linha 21 Algoritmo 2.1)
            temperature = max(
                config.min_temperature,
                min(config.initial_temperature,
                    config.initial_temperature - iteration / max_iterations)
            )
            probability = math.exp(-(new_cost - current_cost) / temperature)
            if random.random() < probability:
                accepted      = True
                score_awarded = config.sigma3   # σ3: aceito por SA, linha 21 Alg. 2.1

        # --- Aplicar decisão de aceitação ---
        if accepted:
            current_solution = new_solution
            current_cost     = new_cost

            if new_cost < best_cost:
                best_solution   = copy.deepcopy(new_solution)
                best_cost       = new_cost
                no_improve_best = 0
                logger.info(f"Melhoria encontrada na iteração {iteration}: Custo = {best_cost}")
            else:
                no_improve_best += 1
        else:
            no_improve_best += 1

        # --- Atualizar scores dos operadores usados nesta iteração ---
        scores_destroy[destroy_idx] += score_awarded
        scores_repair[repair_idx]   += score_awarded

        # --- Atualizar pesos ao fim do segmento (linha 36 Algoritmo 4.1) ---
        if iteration % config.segment_length == 0:
            segmento_atual = iteration // config.segment_length

            for i in range(len(weights_destroy)):
                weights_destroy[i] = (
                    (1 - config.reaction_factor) * weights_destroy[i]
                    + config.reaction_factor * scores_destroy[i]
                )
                weights_destroy[i] = max(weights_destroy[i], 0.01)
                scores_destroy[i] = 0

            for i in range(len(weights_repair)):
                weights_repair[i] = (
                    (1 - config.reaction_factor) * weights_repair[i]
                    + config.reaction_factor * scores_repair[i]
                )
                weights_repair[i] = max(weights_repair[i], 0.01)
                scores_repair[i] = 0

            # Log para verificar se a adaptação está funcionando
            logger.info(
                f"[Segmento {segmento_atual}] "
                f"weights_destroy={[round(w, 4) for w in weights_destroy]} "
                f"[random_removal, worst_removal] | "
                f"weights_repair={[round(w, 4) for w in weights_repair]} "
                f"[greedy_insertion, random_insertion]"
            )

    # --- Pós-loop ---
    end_time       = time.time()
    execution_time = end_time - start_time

    if best_solution is None:
        logger.error("Não foi possível encontrar uma solução viável.")
        return None, None, None

    return format_result(best_solution, best_cost, execution_time, distancias_km, custos_viagem, node_index, data)


def format_result(solution: Dict, best_cost: float, execution_time: float,
                  distancias_km: List[List[float]], custos_viagem: List[List[float]],
                  node_index: Dict[str, int], data: Dict) -> Dict:
    route = solution['route_obj'].get_route()
    purchases = solution['purchases']
    total_distance = 0.0

    # Cálculo da distância total percorrida (em km) usando a matriz distancias_km
    for i in range(len(route) - 1):
        origem = route[i]
        destino = route[i + 1]
        total_distance += distancias_km[node_index[origem]][node_index[destino]]
    total_distance += distancias_km[node_index[route[-1]]][node_index[route[0]]]

    # Preparar as compras detalhadas (incluindo informações dos mercados)
    compras_detalhadas = {}
    mercados_comprados = []

    for market, products in purchases.items():
        market_info = data['mercados'][market]
        market_name = market_info['nome']
        market_address = market_info['endereco']
        latitude = market_info['latitude']
        longitude = market_info['longitude']

        compras_detalhadas[market_name] = []
        for k in products:
            nome_produto = data['produtos'][k]
            preco_produto = data['pik'][(market, k)]
            compras_detalhadas[market_name].append({
                'produto': nome_produto,
                'preco': preco_produto
            })

        mercados_comprados.append({
            'nome': market_name,
            'endereco': market_address,
            'latitude': latitude,
            'longitude': longitude
        })

    resultado = {
        'route': [data['depot']] + [m for m in route if m != data['depot']] + [data['depot']],
        'purchases': compras_detalhadas,
        'total_cost': round(best_cost, 2),          # Custo total em R$
        'total_distance': round(total_distance, 2),  # Distância total em km
        'execution_time': round(execution_time, 2),
        'mercados_comprados': mercados_comprados
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
    purchases: Dict[str, List[str]] = {}
    markets_to_visit: Set[str] = set()

    for k in K:
        mercados_possiveis = Mk.get(k, set())
        mercados_validos = [i for i in mercados_possiveis if (i, k) in pik]
        if not mercados_validos:
            logger.warning(f"Produto {k} não tem mercados disponíveis na solução inicial.")
            continue
        i = random.choice(mercados_validos)
        if i not in purchases:
            purchases[i] = []
        purchases[i].append(k)
        markets_to_visit.add(i)

    route_obj = Route(depot, markets_to_visit)
    solution = {'route_obj': route_obj, 'purchases': purchases}
    return solution


def calculate_cost(solution, custos_viagem, node_index, pik,
                   penalty_value: float = 10.0) -> float:
    """
    Calcula o custo total da solução: custo de viagem + custo de compra + penalidade.
    O parâmetro penalty_value é controlado pelo ALNSConfig (config.penalty_value).
    """
    if solution is None:
        return float('inf')

    route = solution['route_obj'].get_route()
    purchases = solution['purchases']

    # Custo de viagem
    total_distance_cost = 0.0
    for i in range(len(route) - 1):
        origem = route[i]
        destino = route[i + 1]
        total_distance_cost += custos_viagem[node_index[origem]][node_index[destino]]

    # Retorno ao depósito sem duplicação
    if route[-1] != route[0]:
        total_distance_cost += custos_viagem[node_index[route[-1]]][node_index[route[0]]]

    # Custo de compra
    total_purchase_cost = 0.0
    for market, products in purchases.items():
        for k in products:
            if (market, k) in pik:
                total_purchase_cost += pik[(market, k)]
            else:
                logger.error(f"Erro: Produto {k} não está disponível no mercado {market}.")
                return float('inf')

    # Penalidade — usa o parâmetro recebido, NÃO sobrescreve
    for market, products in purchases.items():
        if len(products) == 1:
            total_purchase_cost += penalty_value  # ← vem do config.penalty_value

    total_cost = total_distance_cost + total_purchase_cost
    return round(total_cost, 2)


def random_removal(solution, remove_fraction: float = 0.2) -> Dict:
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    num_to_remove = max(1, int(len(route_obj.get_route()) * remove_fraction))
    if len(route_obj.get_route()) <= num_to_remove + 1:
        return new_solution

    # Evita remover o depósito
    mercados_disponiveis = list(route_obj.route_set - {route_obj.route[0]})
    markets_to_remove = random.sample(mercados_disponiveis, min(num_to_remove, len(mercados_disponiveis)))

    for market in markets_to_remove:
        route_obj.remove_market(market)
        del purchases[market]

    return new_solution


def worst_removal(solution, custos_viagem, node_index, pik,
                  remove_fraction: float = 0.2) -> Dict:
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']
    route = route_obj.get_route()

    num_to_remove = max(1, int(len(route) * remove_fraction))
    if len(route) <= num_to_remove + 1:
        return new_solution

    market_impact = {}
    for i in range(1, len(route)):
        market = route[i]
        if market == route[0]:
            continue
        purchase_cost = sum(pik[(market, k)] for k in purchases[market]) if market in purchases else 0

        if i < len(route) - 1:
            successor = route[i + 1]
        else:
            successor = route[0]
        predecessor = route[i - 1]
        # Cálculo do impacto usando a matriz de custos
        dist_with_market = (custos_viagem[node_index[predecessor]][node_index[market]] +
                            custos_viagem[node_index[market]][node_index[successor]])
        dist_without_market = custos_viagem[node_index[predecessor]][node_index[successor]]
        distance_impact = dist_with_market - dist_without_market

        total_impact = distance_impact + purchase_cost
        market_impact[market] = total_impact

    sorted_by_impact = sorted(market_impact.items(), key=lambda x: x[1], reverse=True)
    markets_to_remove = [m for (m, _) in sorted_by_impact[:num_to_remove]]

    for market in markets_to_remove:
        if market in route_obj:
            route_obj.remove_market(market)
        if market in purchases:
            del purchases[market]

    return new_solution


def greedy_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
                     pik: Dict[Tuple[str, str], float], custos_viagem: List[List[float]],
                     node_index: Dict[str, int], depot: str) -> Optional[Dict]:
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    products_needed = set(K)
    for prods in purchases.values():
        products_needed -= set(prods)

    while products_needed:
        best_market = None
        best_product = None
        best_cost = float('inf')
        for k in products_needed:
            possible_markets = Mk.get(k, set())
            for market in possible_markets:
                if (market, k) not in pik:
                    continue
                product_cost = pik[(market, k)]
                if market in route_obj:
                    insertion_cost = 0
                else:
                    last_node = route_obj.route[-1]
                    if last_node == depot and len(route_obj.route) > 1:
                        last_node = route_obj.route[-2]
                    insertion_cost = (custos_viagem[node_index[last_node]][node_index[market]]
                                      + custos_viagem[node_index[market]][node_index[depot]]
                                      - custos_viagem[node_index[last_node]][node_index[depot]])
                total_cost = product_cost + insertion_cost
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_market = market
                    best_product = k

        if best_market is None:
            logger.warning("Não foi possível encontrar um mercado para um dos produtos necessários.")
            products_to_remove = [k for k in products_needed if not Mk.get(k, set())]
            for k in products_to_remove:
                logger.warning(f"Removendo o produto {k} da lista de necessidades.")
                products_needed.remove(k)
            continue

        if best_market not in route_obj:
            insert_pos = len(route_obj.route)
            if route_obj.route[-1] == depot:
                insert_pos -= 1
            route_obj.add_market(best_market, insert_pos)

        if best_market not in purchases:
            purchases[best_market] = []
        purchases[best_market].append(best_product)
        products_needed.remove(best_product)

    return new_solution


def random_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
                     pik: Dict[Tuple[str, str], float], custos_viagem: List[List[float]],
                     node_index: Dict[str, int], depot: str) -> Optional[Dict]:
    new_solution = copy.deepcopy(solution)
    route_obj: Route = new_solution['route_obj']
    purchases = new_solution['purchases']

    products_needed = set(K)
    for prods in purchases.values():
        products_needed -= set(prods)

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


def acceptance_criterion(current_cost: float, new_cost: float,
                         iteration: int, max_iterations: int,
                         config: Optional[ALNSConfig] = None) -> bool:
    """
    Critério de aceitação inspirado em Simulated Annealing.
    Conforme Algoritmo 2.1 da dissertação (Ropke e Pisinger, 2006).

    ATENÇÃO: esta função NÃO é mais chamada diretamente no loop principal
    do ALNS. A lógica de aceitação foi incorporada ao while em alns_solve_tpp
    para permitir a atribuição correta dos scores σ1, σ2 e σ3.

    Mantida aqui apenas como referência ou para uso em testes isolados.
    """
    if config is None:
        config = ALNSConfig()
    if new_cost < current_cost:
        return True
    temperature = max(
        config.min_temperature,
        min(config.initial_temperature,
            config.initial_temperature - iteration / max_iterations)
    )
    probability = math.exp(-(new_cost - current_cost) / temperature)
    return random.random() < probability


def run_alns_recursive(data: Dict, max_iterations: int, no_improve_limit: int,
                       run_count: int = 1, max_runs: int = 10,
                       accumulated_results: Optional[List[Dict]] = None) -> List[Dict]:
    if accumulated_results is None:
        accumulated_results = []

    for current_run in range(run_count, max_runs + 1):
        logger.info(f"\n--- Execução {current_run} ---")
        best_solution, best_cost, execution_time = alns_solve_tpp(data, max_iterations, no_improve_limit)
        accumulated_results.append({
            'run': current_run,
            'cost': best_cost,
            'execution_time': execution_time,
            'purchases': best_solution['purchases'] if best_solution else None
        })

    total_cost = sum(result['cost'] for result in accumulated_results if result['cost'] is not None)
    total_time = sum(result['execution_time'] for result in accumulated_results if result['execution_time'] is not None)
    successful_runs = len([result for result in accumulated_results if result['cost'] is not None])
    average_cost = total_cost / successful_runs if successful_runs > 0 else float('inf')
    average_time = total_time / successful_runs if successful_runs > 0 else float('inf')

    logger.info("\n--- Resultados Finais ---")
    logger.info(f"Média dos custos totais das {max_runs} execuções: {average_cost:.2f}")
    logger.info(f"Média dos tempos de execução das {max_runs} execuções: {average_time:.2f} segundos")

    aggregated_purchases: Dict[str, int] = {}
    for result in accumulated_results:
        if result['purchases'] is not None:
            for market, produtos in result['purchases'].items():
                if market not in aggregated_purchases:
                    aggregated_purchases[market] = 0
                aggregated_purchases[market] += len(produtos)

    return accumulated_results
# import time
# import copy
# import random
# import math
# import logging
# from dataclasses import dataclass

# @dataclass
# class ALNSConfig:
#     """
#     Parâmetros do ALNS conforme Ropke e Pisinger (2006),
#     referenciados na Seção 4.3 da dissertação.
#     """
#     segment_length: int = 60        # L na dissertação (linha 5 do Algoritmo 4.1)
#     reaction_factor: float = 0.4    # η na dissertação (linha 6 do Algoritmo 4.1)
#     remove_fraction: float = 0.2    # fração de destruição dos operadores
#     penalty_value: float = 10.0     # penalidade por mercado com item único
#     max_infeasible: int = 50        # infMax (linha 9 do Algoritmo 4.1)
#     # Recompensas σ1, σ2, σ3 conforme Algoritmo 2.1 da dissertação
#     sigma1: float = 3.0  # nova melhor solução global
#     sigma2: float = 2.0  # melhora solução corrente, não a global
#     sigma3: float = 1.0  # aceita por simulated annealing (não melhora)
# from typing import Dict, List, Tuple, Optional, Set

# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# # Classe para gerenciar a rota
# class Route:
#     def __init__(self, depot: str, markets: Optional[Set[str]] = None):
#         self.route: List[str] = [depot] + (list(markets) if markets else [])
#         self.route_set: Set[str] = set(self.route)

#     def add_market(self, market: str, position: Optional[int] = None):
#         if market not in self.route_set:
#             if position is None or position < 0 or position > len(self.route):
#                 self.route.append(market)
#             else:
#                 self.route.insert(position, market)
#             self.route_set.add(market)

#     def remove_market(self, market: str):
#         if market in self.route_set:
#             self.route.remove(market)
#             self.route_set.remove(market)

#     def __contains__(self, market: str) -> bool:
#         return market in self.route_set

#     def get_route(self) -> List[str]:
#         return self.route

#     def deepcopy(self):
#         return copy.deepcopy(self)


# #def alns_solve_tpp(data: Dict, max_iterations: int, no_improve_limit: int,
# #                   session_key: Optional[str] = None,
# #                   task_id: Optional[str] = None):
# def alns_solve_tpp(data: Dict, max_iterations: int, no_improve_limit: int,
#                    session_key: Optional[str] = None,
#                    task_id: Optional[str] = None,
#                    config: Optional[ALNSConfig] = None):  # <-- único acréscimo

#     if config is None:
#         config = ALNSConfig()  # usa defaults — nenhuma chamada existente quebra

#     # Extrair dados
#     K = data['K']           # Conjunto de produtos
#     M = data['M']           # Conjunto de mercados
#     depot = data['depot']   # Depot (localização do comprador)

#     # Monta a lista de nós: o depot seguido dos demais mercados (sem duplicação)
#     V = [depot] + [m for m in M if m != depot]

#     Mk = data['Mk']         # Mercados que vendem cada produto
#     pik_original = data['pik']  # Preços dos produtos nos mercados

#     # Obter as duas matrizes:
#     distancias_km = data['distancias_km']  # Distâncias em km
#     custos_viagem = data['custos_viagem']  # Custos da viagem em R$

#     # Verifica se a matriz de custos está corretamente dimensionada
#     assert len(custos_viagem) == len(V), "A matriz de custos deve ter uma linha para cada nó em V."
#     for idx, row in enumerate(custos_viagem):
#         assert len(row) == len(V), f"A linha {idx} na matriz de custos não possui a dimensão correta."

#     node_index = {node_id: index for index, node_id in enumerate(V)}
#     if depot not in node_index:
#         node_index[depot] = len(node_index)

#     # Cria uma cópia local de 'pik'
#     pik = pik_original.copy()

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
#     #segment_length = 60
#     #reaction_factor = 0.4
#     segment_length = config.segment_length
#     reaction_factor = config.reaction_factor

#     # Solução inicial
#     current_solution = initial_solution(K, M, depot, Mk, pik)
#     current_cost = calculate_cost(current_solution, custos_viagem, node_index, pik)
#     best_solution = copy.deepcopy(current_solution)
#     best_cost = current_cost

#     iteration = 0
#     no_improve_best = 0
#     infeasible_count = 0
#     #max_infeasible_solutions = 50
#     max_infeasible_solutions = config.max_infeasible
#     start_time = time.time()

#     while iteration < max_iterations and no_improve_best < no_improve_limit and infeasible_count < max_infeasible_solutions:
#         iteration += 1

#         if session_key and task_id and iteration % 100 == 0:
#             from django.core.cache import cache
#             progresso_base = 76
#             progresso_max = 99
#             progresso = progresso_base + int((iteration / max_iterations) * (progresso_max - progresso_base))
#             progresso = min(progresso, progresso_max)
#             cache_key = f"progresso_{session_key}_{task_id}"
#             cache.set(cache_key, progresso, timeout=600)
#             logger.info(f"📈 Progresso solver atualizado: {progresso}% (iteração {iteration})")

#         # --- Etapa 1: seleção com índice para rastrear qual operador foi usado ---
#         destroy_idx = random.choices(range(len(destroy_operators)), weights=weights_destroy)[0]
#         repair_idx  = random.choices(range(len(repair_operators)),  weights=weights_repair)[0]

#         destroy_operator = destroy_operators[destroy_idx]
#         repair_operator  = repair_operators[repair_idx]

#         # --- Destruição (usando config em vez de hardcode) ---
#         if destroy_operator == worst_removal:
#             partial_solution = worst_removal(
#                 current_solution, custos_viagem, node_index, pik,
#                 remove_fraction=config.remove_fraction
#             )
#         else:
#             partial_solution = destroy_operator(
#                 current_solution,
#                 remove_fraction=config.remove_fraction
#             )

#         # --- Reparo ---
#         new_solution = repair_operator(partial_solution, K, Mk, pik, custos_viagem, node_index, depot)

#         # --- Solução inviável ---
#         if new_solution is None:
#             infeasible_count += 1
#             continue
#         else:
#             infeasible_count = 0

#         new_cost = calculate_cost(
#             new_solution, custos_viagem, node_index, pik,
#             penalty_value=config.penalty_value
#         )

#         # --- Etapas 2 e 3: critério de aceitação + scores σ1, σ2, σ3 ---
#         # Conforme Algoritmo 2.1 da dissertação (Ropke e Pisinger, 2006)
#         accepted     = False
#         score_awarded = 0

#         if new_cost < current_cost:
#             # Melhora a solução corrente — aceita imediatamente
#             accepted = True
#             if new_cost < best_cost:
#                 score_awarded = config.sigma1   # σ1: melhorou a melhor global
#             else:
#                 score_awarded = config.sigma2   # σ2: melhorou corrente, não a global

#         else:
#             # Critério Simulated Annealing: pode aceitar solução pior
#             temperature = max(0.01, min(1.0, 1.0 - iteration / max_iterations))
#             probability = math.exp(-(new_cost - current_cost) / temperature)
#             if random.random() < probability:
#                 accepted     = True
#                 score_awarded = config.sigma3   # σ3: aceito por SA, linha 21 Alg. 2.1

#         # --- Aplicar decisão de aceitação ---
#         if accepted:
#             current_solution = new_solution
#             current_cost     = new_cost

#             if new_cost < best_cost:
#                 best_solution  = copy.deepcopy(new_solution)
#                 best_cost      = new_cost
#                 no_improve_best = 0
#                 logger.info(f"Melhoria encontrada na iteração {iteration}: Custo = {best_cost}")
#             else:
#                 no_improve_best += 1
#         else:
#             no_improve_best += 1

#         # --- Atualizar scores dos operadores usados nesta iteração ---
#         scores_destroy[destroy_idx] += score_awarded
#         scores_repair[repair_idx]   += score_awarded

#         # # --- Atualizar pesos ao fim do segmento (linha 36 Algoritmo 4.1) ---
#         # if iteration % config.segment_length == 0:
#         #     for i in range(len(weights_destroy)):
#         #         weights_destroy[i] = (
#         #             (1 - config.reaction_factor) * weights_destroy[i]
#         #             + config.reaction_factor * scores_destroy[i]
#         #         )
#         #         weights_destroy[i] = max(weights_destroy[i], 0.01)  # evita peso zero
#         #         scores_destroy[i]  = 0

#         #     for i in range(len(weights_repair)):
#         #         weights_repair[i] = (
#         #             (1 - config.reaction_factor) * weights_repair[i]
#         #             + config.reaction_factor * scores_repair[i]
#         #         )
#         #         weights_repair[i] = max(weights_repair[i], 0.01)
#         #         scores_repair[i]  = 0
#         # --- Atualizar pesos ao fim do segmento (linha 36 Algoritmo 4.1) ---
#         if iteration % config.segment_length == 0:
#             segmento_atual = iteration // config.segment_length

#             for i in range(len(weights_destroy)):
#                 weights_destroy[i] = (
#                     (1 - config.reaction_factor) * weights_destroy[i]
#                     + config.reaction_factor * scores_destroy[i]
#                 )
#                 weights_destroy[i] = max(weights_destroy[i], 0.01)
#                 scores_destroy[i] = 0

#             for i in range(len(weights_repair)):
#                 weights_repair[i] = (
#                     (1 - config.reaction_factor) * weights_repair[i]
#                     + config.reaction_factor * scores_repair[i]
#                 )
#                 weights_repair[i] = max(weights_repair[i], 0.01)
#                 scores_repair[i] = 0

#             # Log para verificar se a adaptação está funcionando
#             logger.info(
#                 f"[Segmento {segmento_atual}] "
#                 f"weights_destroy={[round(w, 4) for w in weights_destroy]} "
#                 f"[random_removal, worst_removal] | "
#                 f"weights_repair={[round(w, 4) for w in weights_repair]} "
#                 f"[greedy_insertion, random_insertion]"
#             )
#     # --- Pós-loop (sem alteração) ---
#     end_time       = time.time()
#     execution_time = end_time - start_time

#     if best_solution is None:
#         logger.error("Não foi possível encontrar uma solução viável.")
#         return None, None, None

#     return format_result(best_solution, best_cost, execution_time, distancias_km, custos_viagem, node_index, data)

#     # while iteration < max_iterations and no_improve_best < no_improve_limit and infeasible_count < max_infeasible_solutions:
#     #     iteration += 1
#     #     if session_key and task_id and iteration % 100 == 0:
#     #         from django.core.cache import cache
#     #         progresso_base = 76  # início da fase do solver
#     #         progresso_max = 99   # limite antes do 100 final
#     #         progresso = progresso_base + int((iteration / max_iterations) * (progresso_max - progresso_base))
#     #         progresso = min(progresso, progresso_max)
#     #         cache_key = f"progresso_{session_key}_{task_id}"
#     #         cache.set(cache_key, progresso, timeout=600)
#     #         logger.info(f"📈 Progresso solver atualizado: {progresso}% (iteração {iteration})")


#     #     destroy_operator = random.choices(destroy_operators, weights=weights_destroy)[0]
#     #     repair_operator = random.choices(repair_operators, weights=weights_repair)[0]

#     #     if destroy_operator == worst_removal:
#     #         partial_solution = worst_removal(current_solution, custos_viagem, node_index, pik, remove_fraction=0.2)
#     #     else:
#     #         partial_solution = destroy_operator(current_solution)
#     #     new_solution = repair_operator(partial_solution, K, Mk, pik, custos_viagem, node_index, depot)

#     #     if new_solution is None:
#     #         infeasible_count += 1
#     #         continue
#     #     else:
#     #         infeasible_count = 0

#     #     new_cost = calculate_cost(new_solution, custos_viagem, node_index, pik)

#     #     if acceptance_criterion(current_cost, new_cost, iteration, max_iterations):
#     #         current_solution = new_solution
#     #         current_cost = new_cost
#     #         if new_cost < best_cost:
#     #             best_solution = copy.deepcopy(new_solution)
#     #             best_cost = new_cost
#     #             no_improve_best = 0
#     #             logger.info(f"Melhoria encontrada na iteração {iteration}: Custo = {best_cost}")
#     #         else:
#     #             no_improve_best += 1
#     #     else:
#     #         no_improve_best += 1

#     #     if iteration % segment_length == 0:
#     #         for i in range(len(weights_destroy)):
#     #             weights_destroy[i] = (1 - reaction_factor) * weights_destroy[i] + reaction_factor * scores_destroy[i]
#     #             scores_destroy[i] = 0
#     #         for i in range(len(weights_repair)):
#     #             weights_repair[i] = (1 - reaction_factor) * weights_repair[i] + reaction_factor * scores_repair[i]
#     #             scores_repair[i] = 0

#     # end_time = time.time()
#     # execution_time = end_time - start_time

#     # if best_solution is None:
#     #     logger.error("Não foi possível encontrar uma solução viável.")
#     #     return None, None, None

#     # return format_result(best_solution, best_cost, execution_time, distancias_km, custos_viagem, node_index, data)


# def format_result(solution: Dict, best_cost: float, execution_time: float,
#                   distancias_km: List[List[float]], custos_viagem: List[List[float]],
#                   node_index: Dict[str, int], data: Dict) -> Dict:
#     route = solution['route_obj'].get_route()
#     purchases = solution['purchases']
#     total_distance = 0.0

#     # Cálculo da distância total percorrida (em km) usando a matriz distancias_km
#     for i in range(len(route) - 1):
#         origem = route[i]
#         destino = route[i + 1]
#         total_distance += distancias_km[node_index[origem]][node_index[destino]]
#     total_distance += distancias_km[node_index[route[-1]]][node_index[route[0]]]

#     # Preparar as compras detalhadas (incluindo informações dos mercados)
#     compras_detalhadas = {}
#     mercados_comprados = []

#     for market, products in purchases.items():
#         market_info = data['mercados'][market]
#         market_name = market_info['nome']
#         market_address = market_info['endereco']
#         latitude = market_info['latitude']
#         longitude = market_info['longitude']

#         #compras_detalhadas[f'Produtos comprados no {market_name}'] = []
#         compras_detalhadas[market_name] = [] 
#         for k in products:
#             nome_produto = data['produtos'][k]
#             preco_produto = data['pik'][(market, k)]
#             #compras_detalhadas[f'Produtos comprados no {market_name}'].append({
#             compras_detalhadas[market_name].append({
#                 'produto': nome_produto,
#                 'preco': preco_produto
#             })

#         mercados_comprados.append({
#             'nome': market_name,
#             'endereco': market_address,
#             'latitude': latitude,
#             'longitude': longitude
#         })

#     resultado = {
#         'route': [data['depot']] + [m for m in route if m != data['depot']] + [data['depot']],
#         'purchases': compras_detalhadas,
#         'total_cost': round(best_cost, 2),          # Custo total em R$
#         'total_distance': round(total_distance, 2),  # Distância total em km
#         'execution_time': round(execution_time, 2),
#         'mercados_comprados': mercados_comprados
#     }

#     logger.debug(f"Resultado formatado: {resultado}")
#     return resultado


# def verificar_dados(K: List[str], Mk: Dict[str, Set[str]], pik: Dict[Tuple[str, str], float]) -> bool:
#     problemas = False
#     for k in K:
#         mercados_disponiveis = Mk.get(k, set())
#         if not mercados_disponiveis:
#             logger.warning(f"Aviso: Não há mercados que vendem o produto {k}.")
#             problemas = True
#         else:
#             mercado_valido = False
#             for mercado in mercados_disponiveis:
#                 if (mercado, k) in pik:
#                     mercado_valido = True
#                     break
#             if not mercado_valido:
#                 logger.warning(f"Aviso: Nenhum mercado válido encontrado para o produto {k}.")
#                 problemas = True

#     if problemas:
#         logger.error("Erros encontrados nos dados de entrada. Por favor, corrija antes de prosseguir.")
#         return False
#     else:
#         logger.info("Dados de entrada verificados com sucesso.")
#         return True


# def initial_solution(K: List[str], M: List[str], depot: str, Mk: Dict[str, Set[str]],
#                      pik: Dict[Tuple[str, str], float]) -> Dict:
#     purchases: Dict[str, List[str]] = {}
#     markets_to_visit: Set[str] = set()

#     for k in K:
#         mercados_possiveis = Mk.get(k, set())
#         mercados_validos = [i for i in mercados_possiveis if (i, k) in pik]
#         if not mercados_validos:
#             logger.warning(f"Produto {k} não tem mercados disponíveis na solução inicial.")
#             continue
#         i = random.choice(mercados_validos)
#         if i not in purchases:
#             purchases[i] = []
#         purchases[i].append(k)
#         markets_to_visit.add(i)

#     route_obj = Route(depot, markets_to_visit)
#     solution = {'route_obj': route_obj, 'purchases': purchases}
#     return solution

# # def calculate_cost(solution: Dict, custos_viagem: List[List[float]], node_index: Dict[str, int],
# #                    pik: Dict[Tuple[str, str], float]) -> float:
# #     if solution is None:
# #         return float('inf')

# #     route = solution['route_obj'].get_route()
# #     purchases = solution['purchases']

# #     # Custo de viagem (em R$) utilizando a matriz de custos
# #     total_distance_cost = 0.0
# #     for i in range(len(route) - 1):
# #         origem = route[i]
# #         destino = route[i + 1]
# #         total_distance_cost += custos_viagem[node_index[origem]][node_index[destino]]
# #     total_distance_cost += custos_viagem[node_index[route[-1]]][node_index[route[0]]]

# #     # Custo de compra
# #     total_purchase_cost = 0.0
# #     for market, products in purchases.items():
# #         for k in products:
# #             if (market, k) in pik:
# #                 total_purchase_cost += pik[(market, k)]
# #             else:
# #                 logger.error(f"Erro: Produto {k} não está disponível no mercado {market}.")
# #                 return float('inf')

# #     # Penalidade para mercados com apenas um item (opcional)
# #     penalty_value = 100
# #     for market, products in purchases.items():
# #         if len(products) == 1:
# #             total_purchase_cost += penalty_value

# #     total_cost = total_distance_cost + total_purchase_cost
# #     return total_cost
# #def calculate_cost(solution: Dict, custos_viagem: List[List[float]], node_index: Dict[str, int],
# #                   pik: Dict[Tuple[str, str], float]) -> float:

# def calculate_cost(solution, custos_viagem, node_index, pik,
#                    penalty_value: float = 10.0) -> float:
#     """
#     Calcula o custo total da solução: custo de viagem + custo de compra + penalidade.
#     O parâmetro penalty_value é controlado pelo ALNSConfig (config.penalty_value).
#     """
#     if solution is None:
#         return float('inf')

#     route = solution['route_obj'].get_route()
#     purchases = solution['purchases']

#     # Custo de viagem
#     total_distance_cost = 0.0
#     for i in range(len(route) - 1):
#         origem = route[i]
#         destino = route[i + 1]
#         total_distance_cost += custos_viagem[node_index[origem]][node_index[destino]]

#     # Retorno ao depósito sem duplicação
#     if route[-1] != route[0]:
#         total_distance_cost += custos_viagem[node_index[route[-1]]][node_index[route[0]]]

#     # Custo de compra
#     total_purchase_cost = 0.0
#     for market, products in purchases.items():
#         for k in products:
#             if (market, k) in pik:
#                 total_purchase_cost += pik[(market, k)]
#             else:
#                 logger.error(f"Erro: Produto {k} não está disponível no mercado {market}.")
#                 return float('inf')

#     # Penalidade — usa o parâmetro recebido, NÃO sobrescreve
#     for market, products in purchases.items():
#         if len(products) == 1:
#             total_purchase_cost += penalty_value  # ← vem do config.penalty_value

#     total_cost = total_distance_cost + total_purchase_cost
#     return round(total_cost, 2)



# #def random_removal(solution: Dict, remove_fraction: float = 0.2) -> Dict:
# def random_removal(solution, remove_fraction: float = 0.2) -> Dict:
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']

#     num_to_remove = max(1, int(len(route_obj.get_route()) * remove_fraction))
#     if len(route_obj.get_route()) <= num_to_remove + 1:
#         return new_solution

#     # Evita remover o depósito
#     mercados_disponiveis = list(route_obj.route_set - {route_obj.route[0]})
#     markets_to_remove = random.sample(mercados_disponiveis, min(num_to_remove, len(mercados_disponiveis)))

#     for market in markets_to_remove:
#         route_obj.remove_market(market)
#         del purchases[market]

#     return new_solution


# #def worst_removal(solution: Dict, custos_viagem: List[List[float]],
# #                  node_index: Dict[str, int],
# #                  pik: Dict[Tuple[str, str], float],
# #                  remove_fraction: float = 0.2) -> Dict:
# def worst_removal(solution, custos_viagem, node_index, pik,
#                   remove_fraction: float = 0.2) -> Dict:
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']
#     route = route_obj.get_route()

#     num_to_remove = max(1, int(len(route) * remove_fraction))
#     if len(route) <= num_to_remove + 1:
#         return new_solution

#     market_impact = {}
#     for i in range(1, len(route)):
#         market = route[i]
#         if market == route[0]:
#             continue
#         purchase_cost = sum(pik[(market, k)] for k in purchases[market]) if market in purchases else 0

#         if i < len(route) - 1:
#             successor = route[i + 1]
#         else:
#             successor = route[0]
#         predecessor = route[i - 1]
#         # Cálculo do impacto usando a matriz de custos
#         dist_with_market = (custos_viagem[node_index[predecessor]][node_index[market]] +
#                             custos_viagem[node_index[market]][node_index[successor]])
#         dist_without_market = custos_viagem[node_index[predecessor]][node_index[successor]]
#         distance_impact = dist_with_market - dist_without_market

#         total_impact = distance_impact + purchase_cost
#         market_impact[market] = total_impact

#     sorted_by_impact = sorted(market_impact.items(), key=lambda x: x[1], reverse=True)
#     markets_to_remove = [m for (m, _) in sorted_by_impact[:num_to_remove]]

#     for market in markets_to_remove:
#         if market in route_obj:
#             route_obj.remove_market(market)
#         if market in purchases:
#             del purchases[market]

#     return new_solution


# def greedy_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
#                      pik: Dict[Tuple[str, str], float], custos_viagem: List[List[float]],
#                      node_index: Dict[str, int], depot: str) -> Optional[Dict]:
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']

#     products_needed = set(K)
#     for prods in purchases.values():
#         products_needed -= set(prods)

#     while products_needed:
#         best_market = None
#         best_product = None
#         best_cost = float('inf')
#         for k in products_needed:
#             possible_markets = Mk.get(k, set())
#             for market in possible_markets:
#                 if (market, k) not in pik:
#                     continue
#                 product_cost = pik[(market, k)]
#                 if market in route_obj:
#                     insertion_cost = 0
#                 else:
#                     last_node = route_obj.route[-1]
#                     if last_node == depot and len(route_obj.route) > 1:
#                         last_node = route_obj.route[-2]
#                     insertion_cost = (custos_viagem[node_index[last_node]][node_index[market]]
#                                       + custos_viagem[node_index[market]][node_index[depot]]
#                                       - custos_viagem[node_index[last_node]][node_index[depot]])
#                 total_cost = product_cost + insertion_cost
#                 if total_cost < best_cost:
#                     best_cost = total_cost
#                     best_market = market
#                     best_product = k

#         if best_market is None:
#             logger.warning("Não foi possível encontrar um mercado para um dos produtos necessários.")
#             products_to_remove = [k for k in products_needed if not Mk.get(k, set())]
#             for k in products_to_remove:
#                 logger.warning(f"Removendo o produto {k} da lista de necessidades.")
#                 products_needed.remove(k)
#             continue

#         if best_market not in route_obj:
#             insert_pos = len(route_obj.route)
#             if route_obj.route[-1] == depot:
#                 insert_pos -= 1
#             route_obj.add_market(best_market, insert_pos)

#         if best_market not in purchases:
#             purchases[best_market] = []
#         purchases[best_market].append(best_product)
#         products_needed.remove(best_product)

#     return new_solution


# def random_insertion(solution: Dict, K: List[str], Mk: Dict[str, Set[str]],
#                      pik: Dict[Tuple[str, str], float], custos_viagem: List[List[float]],
#                      node_index: Dict[str, int], depot: str) -> Optional[Dict]:
#     new_solution = copy.deepcopy(solution)
#     route_obj: Route = new_solution['route_obj']
#     purchases = new_solution['purchases']

#     products_needed = set(K)
#     for prods in purchases.values():
#         products_needed -= set(prods)

#     while products_needed:
#         k = random.choice(list(products_needed))
#         mercados_possiveis = Mk.get(k, set())
#         mercados_validos = [i for i in mercados_possiveis if (i, k) in pik]
#         if not mercados_validos:
#             logger.warning(f"Não há mercados que vendem o produto {k}. Removendo-o da lista de necessidades.")
#             products_needed.remove(k)
#             continue
#         market = random.choice(mercados_validos)
#         if market not in route_obj:
#             position = random.randint(1, len(route_obj.route) - 1)
#             route_obj.add_market(market, position)
#         if market not in purchases:
#             purchases[market] = []
#         purchases[market].append(k)
#         products_needed.remove(k)

#     return new_solution

# def acceptance_criterion(current_cost: float, new_cost: float,
#                          iteration: int, max_iterations: int) -> bool:
#     """
#     Critério de aceitação inspirado em Simulated Annealing.
#     Conforme Algoritmo 2.1 da dissertação (Ropke e Pisinger, 2006).

#     ATENÇÃO: esta função NÃO é mais chamada diretamente no loop principal
#     do ALNS. A lógica de aceitação foi incorporada ao while em alns_solve_tpp
#     para permitir a atribuição correta dos scores σ1, σ2 e σ3.

#     Mantida aqui apenas como referência ou para uso em testes isolados.
#     """
#     if new_cost < current_cost:
#         return True
#     temperature = max(0.01, min(1.0, 1.0 - iteration / max_iterations))
#     probability = math.exp(-(new_cost - current_cost) / temperature)
#     return random.random() < probability


# # def acceptance_criterion(current_cost: float, new_cost: float, iteration: int, max_iterations: int) -> bool:
# #     if new_cost < current_cost:
# #         return True
# #     else:
# #         temperature = max(0.01, min(1, 1 - iteration / max_iterations))
# #         probability = math.exp(-(new_cost - current_cost) / temperature)
# #         return random.random() < probability


# def run_alns_recursive(data: Dict, max_iterations: int, no_improve_limit: int,
#                        run_count: int = 1, max_runs: int = 10,
#                        accumulated_results: Optional[List[Dict]] = None) -> List[Dict]:
#     if accumulated_results is None:
#         accumulated_results = []

#     for current_run in range(run_count, max_runs + 1):
#         logger.info(f"\n--- Execução {current_run} ---")
#         best_solution, best_cost, execution_time = alns_solve_tpp(data, max_iterations, no_improve_limit)
#         accumulated_results.append({
#             'run': current_run,
#             'cost': best_cost,
#             'execution_time': execution_time,
#             'purchases': best_solution['purchases'] if best_solution else None
#         })

#     total_cost = sum(result['cost'] for result in accumulated_results if result['cost'] is not None)
#     total_time = sum(result['execution_time'] for result in accumulated_results if result['execution_time'] is not None)
#     successful_runs = len([result for result in accumulated_results if result['cost'] is not None])
#     average_cost = total_cost / successful_runs if successful_runs > 0 else float('inf')
#     average_time = total_time / successful_runs if successful_runs > 0 else float('inf')

#     logger.info("\n--- Resultados Finais ---")
#     logger.info(f"Média dos custos totais das {max_runs} execuções: {average_cost:.2f}")
#     logger.info(f"Média dos tempos de execução das {max_runs} execuções: {average_time:.2f} segundos")

#     aggregated_purchases: Dict[str, int] = {}
#     for result in accumulated_results:
#         if result['purchases'] is not None:
#             for market, produtos in result['purchases'].items():
#                 if market not in aggregated_purchases:
#                     aggregated_purchases[market] = 0
#                 aggregated_purchases[market] += len(produtos)

#     return accumulated_results
