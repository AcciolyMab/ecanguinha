from celery import shared_task, current_task
from algorithms.sefaz_api import obter_produtos, verificar_delay_sefaz
from algorithms.tpplib_data import create_tpplib_data
from algorithms.alns_solver import alns_solve_tpp
from ecanguinha.services.combustivel import (
    obter_preco_combustivel_por_gtin,
    update_progresso_cache
)
import logging
import json
from django.core.cache import cache

logger = logging.getLogger(__name__)

def format_result_for_celery(solution, best_cost, execution_time, data):
    """
    Formata o resultado para ser serializável em JSON.
    Esta é uma versão simplificada da sua função de formatação interna do solver.
    """
    if not solution:
        return None

    purchases = solution.get('purchases', {})
    total_distance = solution.get('total_distance', 0.0)
    
    # Simplifica a rota para apenas os IDs, que são serializáveis
    route_ids = [node_id for node_id in solution.get('route', [])]

    processed_purchases = {key.replace('Produtos comprados no ', ''): value for key, value in purchases.items()}

    return {
        'rota': route_ids,
        'purchases': processed_purchases,
        'total_cost': float(best_cost),
        'total_distance': float(total_distance),
        'execution_time': float(execution_time),
        'mercados_comprados': solution.get('mercados_comprados', [])
    }


@shared_task(bind=True)
def processar_busca_produtos_task(self, gtin_list, raio, latitude, longitude, dias, preco_combustivel):
    """
    Tarefa Celery para processar a busca de produtos de forma assíncrona.
    """
    try:
        total_steps = 4 # Definimos 4 passos principais para o progresso
        
        # Passo 1: Obter produtos da SEFAZ
        self.update_state(state='PROGRESS', meta={'progress': 25, 'step': 'Consultando a SEFAZ...'})
        df = obter_produtos(self.request.id, gtin_list, int(raio), float(latitude), float(longitude), int(dias), self.request.id)

        if df.empty:
            logger.warning("Nenhum dado encontrado na SEFAZ. Tarefa será encerrada.")
            # Retorna um resultado indicando que não encontrou nada
            return {'error': 'Nenhum dado foi retornado pela API da SEFAZ.'}
        
        # Passo 2: Preparar dados para o solver
        self.update_state(state='PROGRESS', meta={'progress': 50, 'step': 'Preparando dados para otimização...'})
        avg_lat = df["LAT"].mean()
        avg_lon = df["LONG"].mean()
        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=float(preco_combustivel))

        # Passo 3: Executar o solver ALNS
        self.update_state(state='PROGRESS', meta={'progress': 75, 'step': 'Calculando a melhor rota...'})
        resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)
        
        if not resultado_solver:
            return {'error': 'Não foi possível encontrar uma solução viável.'}
        
        # Passo 4: Formatar e finalizar
        self.update_state(state='PROGRESS', meta={'progress': 95, 'step': 'Finalizando...'})
        
        # Calcula o subtotal da cesta para incluir no resultado final
        subtotal_cesta_basica = sum(
            float(item['preco'])
            for produtos in resultado_solver.get('purchases', {}).values()
            for item in produtos
        )

        # Adiciona os dados que antes eram do contexto da view
        final_result = {
            'resultado': resultado_solver,
            'mercados_comprados': resultado_solver.get('mercados_comprados', []),
            'node_coords': [(float(m['latitude']), float(m['longitude'])) for m in resultado_solver.get('mercados_comprados', [])],
            'user_lat': float(avg_lat),
            'user_lon': float(avg_lon),
            'dias': int(dias),
            'raio': int(raio),
            'item_list': gtin_list,
            'media_combustivel': preco_combustivel,
            'subtotal_cesta_basica': subtotal_cesta_basica
        }

        return final_result

    except Exception as e:
        logger.exception("Erro na tarefa Celery 'processar_busca_produtos_task'")
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        return {'error': 'Ocorreu um erro inesperado durante o processamento.'}
    
@shared_task(bind=True)
def buscar_ofertas_task(self, gtin_list, raio, latitude, longitude, dias, preco_combustivel):
    """
    Esta tarefa executa todo o processo de busca e otimização de rota,
    verificando o delay da API da SEFAZ antes de começar.
    """
    try:
        task_id = self.request.id
        
        def update_progress(percentage, step):
            self.update_state(state='PROGRESS', meta={'progress': percentage, 'step': step})
            logger.info(f"Task {task_id}: {percentage}% - {step}")

        # --- ETAPA 0: VERIFICAR O DELAY DA API ---
        update_progress(5, "Verificando status da API da SEFAZ...")
        dias_delay = verificar_delay_sefaz(latitude, longitude)

        if dias_delay > 10:
            logger.error(f"API da SEFAZ com delay de {dias_delay} dias. Abortando a tarefa.")
            # Esta exceção fará a tarefa falhar e a mensagem será enviada ao frontend.
            raise Exception("A API da SEFAZ parece estar com problemas ou muito desatualizada. Tente novamente mais tarde.")

        # --- Determina o número de dias real para a busca ---
        dias_usuario = int(dias)
        dias_reais = max(dias_usuario, dias_delay)
        if dias_reais > 10: # Garante o limite máximo de 10 dias
            dias_reais = 10
        
        logger.info(f"Dias selecionado pelo usuário: {dias_usuario}. Delay da API: {dias_delay}. Dias reais para busca: {dias_reais}.")

        # --- ETAPA 1: OBTER PRODUTOS DA SEFAZ ---
        update_progress(10, "Consultando a SEFAZ...")
        # Usa 'dias_reais' na chamada da API
        df = obter_produtos(task_id, gtin_list, int(raio), float(latitude), float(longitude), dias_reais, task_id)

        if df.empty:
            logger.warning("Nenhum dado retornado pela API da SEFAZ, mesmo com o período de busca ajustado.")
            return {'error': 'Nenhum produto encontrado para os itens selecionados no período e raio definidos. Tente aumentar o raio.'}

        # --- ETAPAS 2 E 3 (sem alterações) ---
        update_progress(70, "Preparando dados para o otimizador...")
        avg_lat = df["LAT"].mean()
        avg_lon = df["LONG"].mean()
        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=float(preco_combustivel))

        update_progress(85, "Calculando a melhor rota...")
        resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

        if not resultado_solver:
            return {'error': 'Não foi possível encontrar uma solução viável.'}
        
        update_progress(100, "Busca finalizada!")
        return resultado_solver

    except Exception as e:
        logger.exception(f"Erro na tarefa Celery 'buscar_ofertas_task': {e}")
        # Propaga a exceção para que o Celery a marque como FALHA
        # e o frontend possa exibir a mensagem de erro.
        raise e

@shared_task(bind=True)
def task_consultar_combustivel(self, gtin, tipo_combustivel, raio, latitude, longitude, dias, posicao, session_key=None):
    """
    Task Celery para consultar o preço do combustível por GTIN.

    Args:
        gtin (str): Código de barras do produto.
        tipo_combustivel (int): Tipo de combustível selecionado.
        raio (float): Raio de busca.
        latitude (float): Latitude do ponto de origem.
        longitude (float): Longitude do ponto de origem.
        dias (int): Quantidade de dias para busca na SEFAZ.
        posicao (int): Posição atual da lista (para cálculo do progresso).
        session_key (str, opcional): Chave da sessão para salvar o progresso no cache.

    Returns:
        tuple: (preco_float, dict_detalhes)
    """
    preco, detalhes = obter_preco_combustivel_por_gtin(
        gtin=gtin,
        tipo_combustivel=tipo_combustivel,
        raio=raio,
        lat=latitude,       # ✅ alterado
        lon=longitude,      # ✅ alterado
        dias=dias
    )

    if session_key:
        update_progresso_cache(session_key, posicao, total=len(cache.get(session_key + "_gtins", [])))

    return preco, detalhes