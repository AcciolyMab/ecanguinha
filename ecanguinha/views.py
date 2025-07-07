import json
import logging
import re
import threading
import math
import uuid
import requests
from typing import List, Dict
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import render, redirect

from celery.result import AsyncResult
from django.contrib import messages  # Importe o messages framework
from algorithms.alns_solver import alns_solve_tpp
# Importações dos módulos personalizados
from algorithms.sefaz_api import obter_produtos, obter_combustiveis
from algorithms.tpplib_data import create_tpplib_data
from geopy.distance import geodesic  # Importação correta
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ThreadTimeoutError
from multiprocessing import Process, Queue
from ecanguinha.services.combustivel import calcular_media_combustivel
from algorithms.sefaz_api import calcular_dias_validos_dinamicamente
from ecanguinha.tasks import processar_busca_produtos_task
from random import randint
from algorithms.sefaz_api import verificar_delay_sefaz # Importe a função
from ecanguinha.tasks import buscar_ofertas_task
from ecanguinha.services.combustivel import (
    calcular_media_combustivel,
    obter_produtos
)

# Configuração de log para facilitar o debug
logger = logging.getLogger(__name__)

# View para a página inicial
from django.http import HttpResponse
from django.contrib import messages
import pandas as pd
import numpy as np


def home(request):
    if request.method == "GET":
        contexto = {
            'Seja bem vindo!'  # Substitua pelo valor desejado ou obtenha dinamicamente
        }
        return render(request, 'localizacao.html', contexto)
    else:
        nome = request.POST.get('nome', '')
        return HttpResponse(nome)


# Função para obter latitude e longitude
@require_GET
def get_lat_long(request):
    endereco = request.GET.get("endereco")

    if not endereco:
        return JsonResponse({"error": "Endereço não fornecido"}, status=400)

    # Verifica se já existe cache para o endereço
    cache_key = f"geocode_{endereco}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return JsonResponse(cached_data)

    try:
        # Chamada para a API Nominatim
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": endereco, "format": "json", "limit": 1},
            headers={"User-Agent": "Mozilla/5.0 (compatible; CanguinhaBot/1.0; +https://www.canguinhaal.com.br)"},
            timeout=5  # Tempo limite de resposta
        )

        response.raise_for_status()  # Levanta erro se a resposta for inválida
        data = response.json()

        if data:
            resultado = data[0]
            cache.set(cache_key, resultado, timeout=3600)  # Cache por 1 hora
            return JsonResponse(resultado)
        else:
            return JsonResponse({"error": "Endereço não encontrado"}, status=404)

    except requests.Timeout:
        logger.error("Timeout ao acessar a API Nominatim para o endereço: %s", endereco)
        return JsonResponse({"error": "Tempo limite excedido ao obter localização"}, status=504)

    except requests.RequestException as e:
        logger.error("Erro na requisição para a API Nominatim: %s", str(e))
        return JsonResponse({"error": "Erro ao obter localização", "details": str(e)}, status=500)


def localizacao(request):
    if not request.session.session_key:
        request.session.save()
    return render(request, 'localizacao.html')


def about(request):
    return render(request, 'about.html')


def contact(request):
    return render(request, 'contact.html')


def avaliar(request):
    return render(request, 'avaliar.html')


def submit_feedback(request):
    if request.method == 'POST':
        nome = request.POST.get('name')
        email = request.POST.get('email')
        facilidade = request.POST.get('ease-of-use')
        melhoria = request.POST.get('improvement')
        recomendacao = request.POST.get('recommend')

        # Você pode salvar o feedback em um banco de dados aqui

        # Renderiza a página de agradecimento
        return render(request, 'agradecimento.html')

    return redirect('avaliar')


def agradecimento(request):
    return render(request, 'agradecimento.html')

def progresso_status(request):
    session_key = request.session.session_key
    if not session_key:
        logger.warning("⚠️ Sessão inválida ou inexistente na requisição.")
        return JsonResponse({"porcentagem": 0})

    progress_id = request.GET.get("progress_id")  # Corrigido aqui
    if not progress_id:
        logger.warning("⚠️ progress_id ausente na requisição.")
        return JsonResponse({"porcentagem": 0})

    cache_key = f"progresso_{session_key}_{progress_id}"
    progresso = cache.get(cache_key, 0)

    logger.warning(f"📥 Requisição progresso_status | session_key={session_key}")
    logger.warning(f"🔍 Lendo da chave: {cache_key}, Progresso: {progresso}")

    return JsonResponse({"porcentagem": progresso})


def listar_produtos(request):
    if request.method != 'POST':
        messages.error(request, "Método inválido. Apenas POST permitido.")
        return redirect('localizacao')

    if not request.session.session_key:
        request.session.save()

    latitude = request.POST.get('latitude', -9.6658)
    longitude = request.POST.get('longitude', -35.7350)
    dias = request.POST.get('dias', 0)
    raio = request.POST.get('raio', 0)
    preco_combustivel = request.POST.get('precoCombustivel', 0.0)
    item_list = request.POST.get('item_list')

    try:
        latitude = float(latitude)
        longitude = float(longitude)
        preco_combustivel = float(preco_combustivel)
        dias_slider = int(dias) # Renomeado para clareza
        raio = int(raio)
    except ValueError as e:
        messages.error(request, f"Erro de conversão de dados: {e}")
        return render(request, 'lista.html', {
            'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
            'mercados_comprados': [],
            'media_combustivel': preco_combustivel,
            'user_lat': latitude,
            'user_lon': longitude,
            'dias': dias,
            'raio': raio,
            'item_list': []
        })

    if not item_list:
        messages.error(request, "Nenhum produto selecionado.")
        # (código original mantido)
        return render(request, 'lista.html', {
            'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
            'mercados_comprados': [],
            'media_combustivel': preco_combustivel,
            'user_lat': latitude,
            'user_lon': longitude,
            'dias': dias,
            'raio': raio,
            'item_list': []
        })

    try:
        item_list = json.loads(item_list) if isinstance(item_list, str) else item_list
        gtin_list = [int(gtin) for gtin in item_list]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        # (código original mantido)
        logger.error("Erro ao processar item_list: %s", e)
        messages.error(request, "Erro ao processar a lista de produtos.")
        return render(request, 'lista.html', {
            'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
            'mercados_comprados': [],
            'media_combustivel': preco_combustivel,
            'user_lat': latitude,
            'user_lon': longitude,
            'dias': dias,
            'raio': raio,
            'item_list': []
        })
        
    # --- INÍCIO DA NOVA LÓGICA INSERIDA ---
    try:
        logger.info("Verificando status e atraso da API SEFAZ para produtos...")
        dias_reais_sefaz = calcular_dias_validos_dinamicamente(
            gtin_exemplo=gtin_list[0],
            tipo_combustivel=2,
            raio=raio,
            lat=latitude,
            lon=longitude,
            max_dias=10
        )

        if dias_reais_sefaz > 10:
            messages.error(request, "A API da SEFAZ parece estar fora do ar ou com dados muito desatualizados. Tente novamente mais tarde.")
            return redirect('localizacao')

        # Decide qual valor de dias usar, conforme a regra de negócio
        dias_para_consulta = max(dias_slider, dias_reais_sefaz)
        logger.info(f"Slider: {dias_slider}d. Atraso SEFAZ: {dias_reais_sefaz}d. Usando: {dias_para_consulta}d para a consulta.")

    except IndexError:
        messages.error(request, "A lista de produtos está vazia.")
        return redirect('localizacao')
    # --- FIM DA NOVA LÓGICA ---

    progress_id = request.POST.get('progress_id') or str(uuid.uuid4())
    session_key = request.session.session_key
    cache_key = f"progresso_{session_key}_{progress_id}"
    cache.set(cache_key, 0, timeout=600)

    logger.warning(f"🔁 Progresso iniciado para sessão {session_key}")

    try:
        # A chamada agora usa a variável 'dias_para_consulta'
        df = obter_produtos(session_key, gtin_list, raio, latitude, longitude, dias_para_consulta, progress_id)

        if df.empty:
            messages.warning(request, "Nenhum dado foi retornado pela API para os produtos e localização selecionados.")
            return render(request, 'lista.html', {
                'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
                'mercados_comprados': [],
                'media_combustivel': preco_combustivel,
                'user_lat': latitude,
                'user_lon': longitude,
                'dias': dias_para_consulta, # Usando a variável correta
                'raio': raio,
                'item_list': gtin_list
            })

        avg_lat = df["LAT"].mean() if "LAT" in df.columns else latitude
        avg_lon = df["LONG"].mean() if "LONG" in df.columns else longitude

        tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=preco_combustivel)
        resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

        if not resultado_solver:
            # (código original mantido)
            messages.error(request, "Não foi possível encontrar uma solução viável.")
            return render(request, 'lista.html', {
                'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
                'mercados_comprados': [],
                'media_combustivel': preco_combustivel,
                'user_lat': avg_lat,
                'user_lon': avg_lon,
                'dias': dias_para_consulta, # Usando a variável correta
                'raio': raio,
                'item_list': gtin_list
            })
        
        route = [idx for idx in resultado_solver.get('route', []) if 1 <= idx <= len(resultado_solver.get('mercados_comprados', []))]
        purchases = resultado_solver.get('purchases', {})
        total_cost = resultado_solver.get('total_cost', 0.0)
        total_distance = resultado_solver.get('total_distance', 0.0)
        execution_time = resultado_solver.get('execution_time', 0.0)
        mercados_raw = resultado_solver.get('mercados_comprados', [])

        node_coords = {
            str(idx): [
                float(m.get('latitude', avg_lat)), 
                float(m.get('longitude', avg_lon))
            ]
            for idx, m in enumerate(mercados_raw, start=1)
            if m.get('latitude') and m.get('longitude')
        }

        # Fallback caso não haja coordenadas
        if not node_coords:
            node_coords = {0: [avg_lat, avg_lon]}  # Usando as coordenadas médias como fallback


        processed_purchases = {key.replace('Produtos comprados no ', ''): value for key, value in purchases.items()}

        subtotal_cesta_basica = sum(
            float(item['preco']) for produtos in purchases.values() for item in produtos
        )

        mercados_enriquecidos = []
        # O for original tinha um erro de variável, corrigido para 'm'
        for m in mercados_raw:
            mercado = {
                'nome': m.get('nome', 'Desconhecido'),
                'endereco': m.get('endereco', 'N/A'),
                'latitude': float(m.get('latitude', avg_lat)),
                'longitude': float(m.get('longitude', avg_lon)),
                'avaliacao': m.get('avaliacao'),
                'distancia': m.get('distancia'),
                'tipo': m.get('tipo', 'Mercado')
            }
            mercados_enriquecidos.append(mercado)

        context = {
            'resultado': {
                'rota': route,
                'purchases': processed_purchases,
                'total_cost': float(total_cost),
                'total_distance': float(total_distance),
                'execution_time': float(execution_time)
            },
            'mercados_comprados': mercados_enriquecidos,
            'node_coords': [(float(m['latitude']), float(m['longitude'])) for m in mercados_enriquecidos],
            'user_lat': avg_lat,
            'user_lon': avg_lon,
            'dias': dias_para_consulta, # Usando a variável correta
            'raio': raio,
            'item_list': gtin_list,
            'media_combustivel': preco_combustivel,
            'subtotal_cesta_basica': subtotal_cesta_basica
        }

        logger.warning(f"🧭 Coordenadas médias: lat={avg_lat}, lon={avg_lon}")
        #print(context)
        return render(request, 'lista.html', context)

    except Exception as e:
        logger.exception("Erro ao processar a solicitação:")
        # (código original mantido)
        return render(request, 'lista.html', {
            'resultado': {'rota': [], 'purchases': {}, 'total_cost': 0.0, 'total_distance': 0.0, 'execution_time': 0.0},
            'mercados_comprados': [],
            'media_combustivel': preco_combustivel,
            'user_lat': latitude,
            'user_lon': longitude,
            'dias': dias,
            'raio': raio,
            'item_list': gtin_list if 'gtin_list' in locals() else []
        })


def calcular_distancia(lat1, lon1, lat2, lon2):
    """
    Calcula a distância entre dois pontos geográficos (latitude, longitude) usando a fórmula de Haversine.
    """
    R = 6371  # Raio da Terra em quilômetros
    
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    
    a = math.sin(dLat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return round(distance, 2)  # Retorna a distância arredondada para 2 casas decimais


def consultar_worker_thread(tipo_combustivel, raio, lat, lon, dias, result_container):
    try:
        result_container["result"] = obter_combustiveis(tipo_combustivel, raio, lat, lon, dias)
    except Exception as e:
        result_container["result"] = {"error": str(e)}

def safe_consultar_combustivel(tipo_combustivel, raio, lat, lon, dias, timeout=120):
    result = {}
    t = threading.Thread(target=consultar_worker_thread, args=(tipo_combustivel, raio, lat, lon, dias, result))
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.critical("⏱️ Thread da SEFAZ excedeu timeout total e foi encerrada.")
        return {"error": "Tempo limite atingido para a consulta à SEFAZ."}
    return result.get("result", {"error": "Falha na consulta à SEFAZ."})
#----------------------------------------------------------------------------------------------------------------------#
@csrf_exempt
def processar_combustivel(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        logger.debug(f"🔧 Payload para combustível recebido: {data}")

        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        raio = int(data.get("raio"))
        dias_usuario = int(data.get("dias"))
        tipo_combustivel = int(data.get("tipoCombustivel"))

       # --- Lógica de Delay ---
        logger.info("Verificando delay da API da SEFAZ...")
        dias_delay = verificar_delay_sefaz(latitude, longitude, raio)

        if dias_delay > 10:
            # ... (código mantido igual)
            return JsonResponse({"erro": "API da SEFAZ muito desatualizada."}, status=424)

        # AJUSTE PARA MAIOR ROBUSTEZ: Adiciona +1 dia de margem de segurança
        dias_ajustados_com_margem = dias_delay + 1

        # Usa o maior valor entre a seleção do usuário e o delay com margem
        dias_reais = min(max(dias_usuario, dias_ajustados_com_margem), 10)
        
        logger.info(f"Dias do usuário: {dias_usuario}, Delay da API: {dias_delay}. Período de busca ajustado para: {dias_reais} dias.")
        # --- Fim da Lógica de Delay ---

        # O resto da função continua igual, usando 'dias_reais'
        df = obter_combustiveis(tipo_combustivel, raio, latitude, longitude, dias_reais)

        if df.empty:
            logger.warning("⚠️ Nenhum dado de combustível retornado pela API com o período ajustado.")
            return JsonResponse({"erro": "Não foram encontrados preços de combustível para esta região e período."}, status=404)

        # Remove registros com valor 0 ou nulo
        df = df[df["VALOR"].apply(lambda x: isinstance(x, (int, float)) and x > 0)]

        if df.empty:
            logger.warning("⚠️ Todos os preços de combustível retornados estavam zerados ou inválidos")
            return JsonResponse({"erro": "Preços de combustível indisponíveis ou inválidos na região."}, status=404)

        media = calcular_media_combustivel(df)

        return JsonResponse({
            "media_preco": round(media, 2),
            "tipo_combustivel": tipo_combustivel
        })
    
    except json.JSONDecodeError:
        logger.error("❌ JSON inválido recebido")
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    except Exception as e:
        logger.exception(f"❌ Erro interno ao processar combustível: {e}")
        return JsonResponse({"erro": f"Erro interno: {str(e)}"}, status=500)


@csrf_exempt
def iniciar_busca_produtos(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método GET não permitido'}, status=405)

    try:
        # Extrai dados do formulário
        latitude = float(request.POST.get('latitude', '-9.6658'))
        longitude = float(request.POST.get('longitude', '-35.7350'))
        dias = int(request.POST.get('dias', '1'))
        raio = int(request.POST.get('raio', '1'))
        preco_combustivel = float(request.POST.get('precoCombustivel', '0.0'))

        item_list_json = request.POST.get('item_list')
        if not item_list_json:
            return JsonResponse({'error': 'Nenhum produto selecionado.'}, status=400)

        try:
            item_list = json.loads(item_list_json)
            gtin_list = [int(gtin) for gtin in item_list]
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.exception("Erro ao interpretar item_list.")
            return JsonResponse({'error': f'Erro ao processar a lista de produtos: {e}'}, status=400)

        # Garante session_key válida
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key

        # Inicia a task Celery com todos os argumentos
        task = buscar_ofertas_task.delay(
            gtin_list, raio, latitude, longitude, dias, preco_combustivel, session_key=session_key
        )

        progress_id = task.id
        cache.set(f"progresso_{session_key}_{progress_id}", 0, timeout=600)

        logger.info(f"🚀 Task Celery iniciada | session_key={session_key} | progress_id={progress_id}")

        return JsonResponse({
            'task_id': task.id,
            'progress_id': progress_id,
            'status': 'PROCESSING',
            'message': 'Busca iniciada com sucesso.'
        })

    except Exception as e:
        logger.exception("❌ Erro interno ao iniciar a busca de produtos.")
        return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)

def get_task_status(request):
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'task_id não fornecido'}, status=400)
        
    task_result = AsyncResult(task_id)
    
    response_data = {
        'task_id': task_id,
        'status': task_result.state,
        'result': None, # Será preenchido se a tarefa terminou
        'progress': 0,
        'step': ''
    }

    if task_result.state == 'SUCCESS':
        # --- MUDANÇA PRINCIPAL ---
        # Se a tarefa terminou, incluímos o resultado dela na resposta.
        response_data['result'] = task_result.result 
    
    elif task_result.state == 'PROGRESS':
        response_data['progress'] = task_result.info.get('progress', 0)
        response_data['step'] = task_result.info.get('step', '')
        
    elif task_result.state == 'FAILURE':
        # Guardamos a informação do erro para o frontend.
        response_data['result'] = {'error': 'A tarefa falhou inesperadamente.'}

    return JsonResponse(response_data)

def sum_precos(produtos):
    return sum(item['preco'] for item in produtos if 'preco' in item)

def mostrar_resultado(request, task_id):
    task_result = AsyncResult(task_id)

    if task_result.state == 'SUCCESS':
        context_raw = task_result.result

        if isinstance(context_raw, dict) and 'error' in context_raw:
            messages.error(request, context_raw['error'])
            return redirect('localizacao')

        mercados_raw = context_raw.get('mercados_comprados', [])
        avg_lat = context_raw.get('user_lat', -9.6658)
        avg_lon = context_raw.get('user_lon', -35.7350)

        mercados_enriquecidos = []
        for m in mercados_raw:
            mercado = {
                'nome': m.get('nome', 'Desconhecido'),
                'endereco': m.get('endereco', 'N/A'),
                'latitude': float(m.get('latitude', avg_lat)),
                'longitude': float(m.get('longitude', avg_lon)),
                'valor_total': float(m.get('valor_total', 0.0)),
                'tipo': m.get('tipo', 'Mercado'),
                'avaliacao': m.get('avaliacao', None),
                'distancia': m.get('distancia', None),
            }
            mercados_enriquecidos.append(mercado)

        context = context_raw.copy()
        context['mercados_comprados'] = mercados_enriquecidos

        # ✅ Calcula subtotal da cesta básica
        total = 0.0
        purchases = context.get('purchases', {})
        for produtos in purchases.values():
            total += sum_precos(produtos)
        context['subtotal_cesta_basica'] = total

        # ✅ Garante que media_combustivel esteja presente
        context.setdefault('media_combustivel', 0.0)

        # ✅ Reorganiza dados no formato esperado pela template
        context['resultado'] = {
            'route': context.get('route', []),
            'purchases': context.get('purchases', {}),
            'total_cost': context.get('total_cost', 0.0),
            'total_distance': context.get('total_distance', 0.0),
            'execution_time': context.get('execution_time', 0.0),
        }

        # ✅ Adiciona coordenadas dos nós
        context['node_coords'] = [
            (float(m['latitude']), float(m['longitude']))
            for m in mercados_enriquecidos
            if m.get('latitude') is not None and m.get('longitude') is not None
        ]

        # ✅ Adiciona user_lat e user_lon ao contexto (para uso no template)
        context['user_lat'] = avg_lat
        context['user_lon'] = avg_lon
        logger.warning(f"🧭 Coordenadas médias: lat={avg_lat}, lon={avg_lon}")
        #print(context)

        return render(request, 'lista.html', context)

    elif task_result.state == 'FAILURE':
        messages.error(request, "Ocorreu um erro inesperado ao processar sua solicitação. Por favor, tente novamente.")
        return redirect('localizacao')

    else:
        messages.info(request, "Sua busca ainda está em processamento. Aguarde um momento e a página de resultados aparecerá.")
        return redirect('localizacao')
