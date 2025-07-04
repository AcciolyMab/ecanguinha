import json
import logging
import re
import threading
import math
import uuid
import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

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
from random import randint


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


from django.shortcuts import render, redirect


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
    if request.method == 'POST':
        if not request.session.session_key:
            request.session.save()
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        # Valores padrão se localização for inválida
        if not latitude or not longitude or latitude == "0.0" or longitude == "0.0":
            latitude = -9.6658  # Maceió
            longitude = -35.7350

        dias = request.POST.get('dias')
        preco_combustivel = request.POST.get('precoCombustivel')
        raio = request.POST.get('raio')
        item_list = request.POST.get('item_list')

        preco_combustivel = float(preco_combustivel or 0)

        if not item_list:
            messages.error(request, "Nenhum produto selecionado.")
            return render(request, 'lista.html', {
                'resultado': {
                    'rota': [],
                    'purchases': {},
                    'total_cost': 0.0,
                    'total_distance': 0.0,
                    'execution_time': 0.0
                },
                'mercados_comprados': [],
                'media_combustivel': 0,
                'user_lat': float(latitude),
                'user_lon': float(longitude),
                'node_coords': [],
                'dias': int(dias or 0),
                'raio': int(raio or 0),
                'item_list': []
            })

        try:
            item_list = json.loads(item_list) if isinstance(item_list, str) else item_list
            gtin_list = [int(gtin) for gtin in item_list]
        except Exception as e:
            logger.error("Erro ao processar item_list: %s", e)
            messages.error(request, "Erro ao processar a lista de produtos.")
            return render(request, 'lista.html', {
                'resultado': {
                    'rota': [],
                    'purchases': {},
                    'total_cost': 0.0,
                    'total_distance': 0.0,
                    'execution_time': 0.0
                },
                'mercados_comprados': [],
                'media_combustivel': 0,
                'user_lat': float(latitude),
                'user_lon': float(longitude),
                'node_coords': [],
                'dias': int(dias or 0),
                'raio': int(raio or 0),
                'item_list': []
            })

        try:
            progress_id = request.POST.get('progress_id') or str(uuid.uuid4())
            session_key_raw = request.session.session_key
            cache_key = f"progresso_{session_key_raw}_{progress_id}"
            cache.set(cache_key, 0, timeout=600)

            logger.warning(f"🔁 Progresso iniciado manualmente para sessão {session_key_raw}")

            df = obter_produtos(session_key_raw, gtin_list, int(raio), float(latitude), float(longitude), int(dias), progress_id)

            # Se a SEFAZ estiver instável e não retornar nada, tenta dias dinamicamente
            if df.empty:
                logger.warning("⚠️ Nenhum dado encontrado. Recalculando dias dinamicamente...")
                dias = calcular_dias_validos_dinamicamente(
                    gtin_exemplo=gtin_list[0],
                    tipo_combustivel=2,
                    raio=raio,
                    lat=float(latitude),
                    lon=float(longitude),
                    max_dias=10
                )
                df = obter_produtos(session_key_raw, gtin_list, int(raio), float(latitude), float(longitude), dias, progress_id)

            if df.empty:
                messages.warning(request, "Nenhum dado foi retornado pela API.")
                return render(request, 'lista.html', {
                    'resultado': {
                        'rota': [],
                        'purchases': {},
                        'total_cost': 0.0,
                        'total_distance': 0.0,
                        'execution_time': 0.0
                    },
                    'mercados_comprados': [],
                    'media_combustivel': 0,
                    'user_lat': float(latitude),
                    'user_lon': float(longitude),
                    'node_coords': [],
                    'dias': int(dias or 0),
                    'raio': int(raio or 0),
                    'item_list': gtin_list
                })

            avg_lat = df["LAT"].mean() if "LAT" in df.columns else float(latitude)
            avg_lon = df["LONG"].mean() if "LONG" in df.columns else float(longitude)

            tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=float(preco_combustivel or 0))
            resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

            if not resultado_solver:
                messages.error(request, "Não foi possível encontrar uma solução viável.")
                return render(request, 'lista.html', {
                    'resultado': {
                        'rota': [],
                        'purchases': {},
                        'total_cost': 0.0,
                        'total_distance': 0.0,
                        'execution_time': 0.0
                    },
                    'mercados_comprados': [],
                    'media_combustivel': preco_combustivel or 0,
                    'user_lat': float(avg_lat),
                    'user_lon': float(avg_lon),
                    'node_coords': [],
                    'dias': int(dias or 0),
                    'raio': int(raio or 0),
                    'item_list': gtin_list
                })

            rota = [idx for idx in resultado_solver.get('route', []) if 1 <= idx <= len(resultado_solver.get('mercados_comprados', []))]
            purchases = resultado_solver.get('purchases', {})
            total_cost = resultado_solver.get('total_cost', 0.0)
            total_distance = resultado_solver.get('total_distance', 0.0)
            execution_time = resultado_solver.get('execution_time', 0.0)
            mercados_comprados = resultado_solver.get('mercados_comprados', [])
            subtotal_cesta_basica = sum(
                float(item['preco'])
                for produtos in purchases.values()
                for item in produtos
            )


            node_coords = {
                str(idx): [float(mercado.get('latitude')), float(mercado.get('longitude'))]
                for idx, mercado in enumerate(mercados_comprados, start=1)
                if mercado.get('latitude') and mercado.get('longitude')
            }

            processed_purchases = {key.replace('Produtos comprados no ', ''): value for key, value in purchases.items()}

            context = {
                'resultado': {
                    'rota': rota,
                    'purchases': processed_purchases,
                    'total_cost': float(total_cost),
                    'total_distance': float(total_distance),
                    'execution_time': float(execution_time)
                },
                'mercados_comprados': [
                    {
                        'nome': m['nome'],
                        'endereco': m['endereco'],
                        'latitude': float(m['latitude']),
                        'longitude': float(m['longitude']),
                        'valor_total': float(m.get('valor_total', 0.0)),
                        'distancia': calcular_distancia(avg_lat, avg_lon, float(m['latitude']), float(m['longitude'])),
                        'tipo': m.get('tipo', 'Supermercado'),
                        'avaliacao': m.get('avaliacao', 0)
                    }
                    for m in mercados_comprados
                ],
                'node_coords': [
                    (float(m['latitude']), float(m['longitude'])) for m in mercados_comprados
                ],
                'user_lat': float(avg_lat),
                'user_lon': float(avg_lon),
                'dias': int(dias),
                'raio': int(raio),
                'item_list': gtin_list,
                'media_combustivel': preco_combustivel,
                'subtotal_cesta_basica': subtotal_cesta_basica  # ✅ adicionado
            }

            logger.warning(f"🧭 Coordenadas médias: avg_lat={avg_lat}, avg_lon={avg_lon}")
            return render(request, 'lista.html', context)

        except Exception as e:
            logger.error("Erro ao processar a solicitação: %s", e)
            messages.error(request, "Erro ao processar a solicitação.")
            return render(request, 'lista.html', {
                'resultado': {
                    'rota': [],
                    'purchases': {},
                    'total_cost': 0.0,
                    'total_distance': 0.0,
                    'execution_time': 0.0
                },
                'mercados_comprados': [],
                'media_combustivel': preco_combustivel or 0,
                'user_lat': float(latitude),
                'user_lon': float(longitude),
                'node_coords': [],
                'dias': int(dias or 0),
                'raio': int(raio or 0),
                'item_list': gtin_list if 'gtin_list' in locals() else []
            })

    return redirect('localizacao')

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
    return geodesic((lat1, lon1), (lat2, lon2)).km


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
        logger.debug(f"🔧 Payload recebido: {data}")

        tipo_combustivel = int(data.get("tipoCombustivel"))
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        raio = int(data.get("raio"))
        dias = int(data.get("dias"))

        df = obter_combustiveis(tipo_combustivel, raio, latitude, longitude, dias)

        if df.empty:
            logger.warning("⚠️ Nenhum dado retornado. Recalculando dias dinamicamente...")
            dias = calcular_dias_validos_dinamicamente(
                gtin_exemplo=None,  # não é necessário para combustíveis
                tipo_combustivel=tipo_combustivel,
                raio=raio,
                lat=latitude,
                lon=longitude,
                max_dias=10
            )
            df = obter_combustiveis(tipo_combustivel, raio, latitude, longitude, dias)

        # Remove registros com valor 0 ou nulo
        df = df[df["VALOR"].apply(lambda x: isinstance(x, (int, float)) and x > 0)]

        if df.empty:
            logger.warning("⚠️ Todos os preços estavam zerados ou inválidos")
            return JsonResponse({"erro": "Preços indisponíveis ou inválidos"}, status=204)

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
