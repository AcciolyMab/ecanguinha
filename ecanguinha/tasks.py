from celery import shared_task, current_task
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
    from algorithms.alns_solver import ALNSConfig, alns_solve_tpp
    from algorithms.sefaz_api import obter_produtos
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
        # resultado_solver =resultado_solver = alns_solve_tpp(
        #     tpplib_data,
        #     max_iterations=10000,
        #     no_improve_limit=100,
        #     session_key=session_key,
        #     task_id=task_id
        # )
        resultado_solver = alns_solve_tpp(
            tpplib_data,
            max_iterations=10000,
            no_improve_limit=100,        # ← permite explorar mais antes de desistir
            session_key=session_key,
            task_id=task_id,
            config=ALNSConfig(
                segment_length=60,       # L — conforme dissertação
                reaction_factor=0.4,     # η — conforme dissertação
                remove_fraction=0.2,     # fração de destruição
                penalty_value=10.0,      # penalidade mercado com 1 item
                max_infeasible=50,       # máximo de soluções inviáveis consecutivas
                sigma1=3.0,              # recompensa: melhorou global
                sigma2=2.0,              # recompensa: melhorou corrente
                sigma3=1.0               # recompensa: aceito por SA
            )
        )


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
    from algorithms.sefaz_api import obter_produtos, verificar_delay_sefaz
    from algorithms.alns_solver import alns_solve_tpp
    from algorithms.tpplib_data import create_tpplib_data
    import time
    from django.core.cache import cache

    task_id = self.request.id
    dias_usuario = int(dias)

    # ✅ CORREÇÃO 1: Usa a chave de progresso SIMPLIFICADA que a view espera.
    progress_key = f"progress:{task_id}"

    def update_progress(percentage, step):
        self.update_state(state='PROGRESS', meta={'progress': int(percentage), 'step': step})
        cache.set(progress_key, int(percentage), timeout=600)
        logger.info(f"Task {task_id}: {int(percentage)}% - {step}")

    try:
        # --- ETAPA 1: LÓGICA DE DELAY E BUSCA OTIMIZADA ---
        update_progress(5, "Olá Canguinha vou verificar a sua lista de compras...")
        dias_delay = verificar_delay_sefaz(latitude, longitude)

        if dias_delay > 10:
            raise Exception("A API da SEFAZ parece estar com dados muito desatualizados.")

        # ✅ CORREÇÃO 2: Lógica final para o período de busca.
        # Usa o maior valor entre a seleção do usuário e o delay + 1 dia de margem.
        dias_reais = max(dias_usuario, dias_delay + 1)
        # Garante que não exceda o limite máximo de 10 dias.
        dias_para_consulta = min(dias_reais, 10)
        
        logger.info(f"Período de busca definido para {dias_para_consulta} dias. (Usuário: {dias_usuario}d, Delay API: {dias_delay}d)")

        # --- ETAPA 2: EXECUÇÃO DA BUSCA ---
        update_progress(15, f"Buscando mercados da região...")

        update_progress(25, f"Buscando ofertas nos últimos {dias_para_consulta} dias...")
        
        # A função obter_produtos deve ser ajustada para também usar a chave 'progress:{task_id}'
        # internamente, se ela atualizar o progresso.
        df = obter_produtos(session_key, gtin_list, int(raio), float(latitude), float(longitude), dias_para_consulta, task_id)

        # --- ETAPA 3: FINALIZAÇÃO ---
        if df.empty:
            update_progress(100, "Nenhum produto encontrado.")
            return {
                'error': 'Não encontramos ofertas para os produtos selecionados.',
                'sugestao': 'Tente aumentar o raio de busca ou o período. A base de dados da SEFAZ pode não ter registros para sua área.'
            }
        
        # ... (O resto do código para o solver permanece exatamente igual) ...
        avg_lat = df["LAT"].mean()
        avg_lon = df["LONG"].mean()
        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=preco_combustivel)
        resultado_solver = alns_solve_tpp(
            tpplib_data, max_iterations=10000, no_improve_limit=100,
            session_key=session_key, task_id=task_id
        )

        if not resultado_solver:
            update_progress(100, "Nenhuma solução viável encontrada.")
            return {
                'error': 'Encontramos as ofertas, mas não foi possível criar uma rota otimizada.',
                'sugestao': 'Isso pode acontecer se os produtos estiverem em locais muito distantes.'
            }

        resultado_solver.update({
            "media_combustivel": preco_combustivel,
            "user_lat": float(latitude),
            "user_lon": float(longitude)
        })

        update_progress(100, "Busca finalizada! Oxe! toma ai tua rota! 🚗")
        return resultado_solver

    except Exception as e:
        logger.exception(f"Erro crítico na tarefa 'buscar_ofertas_task': {e}")
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        return {
            'error': 'Ocorreu um erro inesperado no servidor.',
            'sugestao': 'Nossa equipe já foi notificada. Por favor, tente novamente mais tarde.'
        }

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
    from ecanguinha.services.combustivel import (
    update_progresso_cache
)
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
    from ecanguinha.services.combustivel import (
    obter_preco_combustivel_por_gtin
)
    preco, detalhes = obter_preco_combustivel_por_gtin(
        gtin=gtin,
        tipo_combustivel=tipo_combustivel,
        raio=raio,
        lat=latitude,
        lon=longitude,
        dias=dias
    )
    return preco, detalhes
