from celery import shared_task, current_task
from algorithms.sefaz_api import obter_produtos, verificar_delay_sefaz
from algorithms.alns_solver import alns_solve_tpp
from ecanguinha.services.combustivel import (
    obter_preco_combustivel_por_gtin,
    update_progresso_cache
)
import logging
import json
from django.core.cache import cache
from celery import shared_task
from django.core.cache import cache
import logging



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
def processar_busca_produtos_task(
    self, 
    gtin_list, 
    raio, 
    latitude, 
    longitude, 
    dias, 
    preco_combustivel, 
    session_key=None
):
    """
    Task Celery para processar a busca de produtos de forma assíncrona.
    Atualiza progresso tanto via `self.update_state` (Celery) quanto via Redis.
    """
    try:
        task_id = self.request.id
        progress_key = f"progresso_{session_key}_{task_id}" if session_key else f"progresso_{task_id}"

        def atualizar_progresso(porcentagem: int, etapa: str):
            self.update_state(state='PROGRESS', meta={'progress': porcentagem, 'step': etapa})
            cache.set(progress_key, porcentagem, timeout=600)
            logger.info(f"📈 {porcentagem}% - {etapa}")

        # Etapa 1 — Consultar SEFAZ
        atualizar_progresso(25, "Consultando a SEFAZ...")
        df = obter_produtos(task_id, gtin_list, int(raio), float(latitude), float(longitude), int(dias), task_id)

        if df.empty:
            atualizar_progresso(100, "Nenhum dado encontrado na SEFAZ.")
            return {'error': 'Nenhum dado foi retornado pela API da SEFAZ.'}

        # Etapa 2 — Preparar dados para o otimizador
        atualizar_progresso(50, "Preparando dados para otimização...")
        avg_lat = df["LAT"].mean()
        avg_lon = df["LONG"].mean()
        # IMPORTAÇÃO TARDIA APLICADA AQUI
        from algorithms.tpplib_data import create_tpplib_data
        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=float(preco_combustivel))

        # Etapa 3 — Executar ALNS
        atualizar_progresso(75, "Calculando a melhor rota...")
        resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

        if not resultado_solver:
            atualizar_progresso(100, "Nenhuma solução encontrada.")
            return {'error': 'Não foi possível encontrar uma solução viável.'}

        # Etapa 4 — Formatar resultado
        atualizar_progresso(100, "Concluido com ")
        subtotal_cesta_basica = sum(
            float(item['preco']) for produtos in resultado_solver.get('purchases', {}).values() for item in produtos
        )

        resultado_final = {
            'resultado': resultado_solver,
            'mercados_comprados': resultado_solver.get('mercados_comprados', []),
            'node_coords': [
                (float(m['latitude']), float(m['longitude'])) 
                for m in resultado_solver.get('mercados_comprados', [])
            ],
            'user_lat': float(avg_lat),
            'user_lon': float(avg_lon),
            'dias': int(dias),
            'raio': int(raio),
            'item_list': gtin_list,
            'media_combustivel': preco_combustivel,
            'subtotal_cesta_basica': subtotal_cesta_basica
        }

        atualizar_progresso(100, "Concluído com sucesso ✅")
        return resultado_final

    except Exception as e:
        logger.exception("❌ Erro na task processar_busca_produtos_task")
        self.update_state(state='FAILURE', meta={
            'exc_type': type(e).__name__,
            'exc_message': str(e)
        })
        if session_key:
            cache.set(f"progresso_{session_key}_{self.request.id}", 100, timeout=600)
        return {'error': 'Ocorreu um erro inesperado durante o processamento.'}

    
@shared_task(bind=True)
def buscar_ofertas_task(self, gtin_list, raio, latitude, longitude, dias, preco_combustivel, session_key=None):
    """
    Esta tarefa executa todo o processo de busca e otimização de rota,
    verificando o delay da API da SEFAZ antes de começar.
    """
    try:
        task_id = self.request.id
        progress_key = f"progresso_{session_key}_{task_id}" if session_key else f"progresso_{task_id}"

        def update_progress(percentage, step):
            self.update_state(state='PROGRESS', meta={'progress': percentage, 'step': step})
            cache.set(progress_key, percentage, timeout=600)
            logger.info(f"Task {task_id}: {percentage}% - {step}")

        # --- ETAPA 0: VERIFICAR O DELAY DA API ---
        update_progress(5, "Verificando status da API da SEFAZ...")
        dias_delay = verificar_delay_sefaz(latitude, longitude)

        if dias_delay > 10:
            logger.error(f"API da SEFAZ com delay de {dias_delay} dias. Abortando a tarefa.")
            raise Exception("A API da SEFAZ parece estar com problemas ou muito desatualizada. Tente novamente mais tarde.")

        dias_usuario = int(dias)
        dias_reais = min(max(dias_usuario, dias_delay), 10)

        logger.info(f"Dias selecionado pelo usuário: {dias_usuario}. Delay da API: {dias_delay}. Dias reais para busca: {dias_reais}.")

        # --- ETAPA 1: OBTER PRODUTOS DA SEFAZ ---
        update_progress(15, "Consultando a SEFAZ...")
        df = obter_produtos(task_id, gtin_list, int(raio), float(latitude), float(longitude), dias_reais, task_id)

        if df.empty:
            update_progress(100, "Nenhum dado retornado pela API da SEFAZ.")
            return {'error': 'Nenhum produto encontrado para os itens selecionados no período e raio definidos. Tente aumentar o raio.'}

        # # --- ETAPA 2: CONSULTAR COMBUSTÍVEL POR GTIN ---
        # update_progress(50, "Consultando preços de combustível...")
        # gtins_combustivel = cache.get(f"{session_key}_gtins", []) or []

        # precos_combustivel = []
        # for posicao, gtin in enumerate(gtins_combustivel):
        #     preco, _ = task_consultar_combustivel(
        #         gtin=gtin,
        #         tipo_combustivel=int(preco_combustivel),
        #         raio=float(raio),
        #         latitude=float(latitude),
        #         longitude=float(longitude),
        #         dias=dias_reais,
        #         posicao=posicao,
        #         session_key=session_key
        #     )
        #     if preco > 0:
        #         precos_combustivel.append(preco)

        # media_combustivel = round(sum(precos_combustivel) / len(precos_combustivel), 2) if precos_combustivel else 0.0
        # logger.info(f"📊 Preço médio do combustível calculado: R$ {media_combustivel:.2f}")

        # --- ETAPA 3: PREPARAR DADOS E RODAR SOLVER ---

        # IMPORTAÇÃO TARDIA APLICADA AQUI
        from algorithms.tpplib_data import create_tpplib_data
        update_progress(70, "Preparando dados para o otimizador...")
        avg_lat = df["LAT"].mean()
        avg_lon = df["LONG"].mean()
        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=preco_combustivel)

        update_progress(85, "Calculando a melhor rota...")
        resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

        if not resultado_solver:
            update_progress(100, "Nenhuma solução viável encontrada.")
            return {'error': 'Não foi possível encontrar uma solução viável.'}

        resultado_solver["media_combustivel"] = preco_combustivel
        resultado_solver["user_lat"] = float(latitude)
        resultado_solver["user_lon"] = float(longitude)

        update_progress(100, "Busca finalizada!")
        return resultado_solver

    except Exception as e:
        logger.exception(f"Erro na tarefa Celery 'buscar_ofertas_task': {e}")
        if session_key:
            cache.set(f"progresso_{session_key}_{self.request.id}", 100, timeout=600)
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
    preco, detalhes = consultar_combustivel_sync(
        gtin=gtin,
        tipo_combustivel=tipo_combustivel,
        raio=raio,
        latitude=latitude,
        longitude=longitude,
        dias=dias
    )

    if session_key:
        update_progresso_cache(session_key, posicao, total=len(cache.get(session_key + "_gtins", [])))

    return preco, detalhes

def consultar_combustivel_sync(gtin, tipo_combustivel, raio, latitude, longitude, dias):
    """
    Consulta o preço do combustível por GTIN, de forma síncrona.
    """
    preco, detalhes = obter_preco_combustivel_por_gtin(
        gtin=gtin,
        tipo_combustivel=tipo_combustivel,
        raio=raio,
        lat=latitude,
        lon=longitude,
        dias=dias
    )
    return preco, detalhes
