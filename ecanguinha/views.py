import json
import logging
import re
import threading
import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from algorithms.alns_solver import alns_solve_tpp
# Importações dos módulos personalizados
from algorithms.sefaz_api import consultar_combustivel, obter_produtos, obter_combustiveis
from algorithms.tpplib_data import create_tpplib_data
from geopy.distance import geodesic  # Importação correta
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ThreadTimeoutError
from multiprocessing import Process, Queue

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
    if not request.session.session_key:
        request.session.save()  # Garante que a sessão exista
    session_key = f"progresso_{request.session.session_key}"
    progresso = cache.get(session_key, 0)
    logger.warning(f"🔍 Sessão: {request.session.session_key}, Progresso: {progresso}")
    return JsonResponse({"porcentagem": progresso})

# def obter_rota(request):
#     """
#     View para retornar a rota detalhada gerada pelo OSMnx.
#     """
#     try:
#         # Aqui, você deve garantir que `mercados_df` tenha os dados necessários.
#         data = create_tpplib_data(mercados_df, buyer_lat, buyer_lon, media_preco=5.5, raio_busca=5.0)
#         return JsonResponse({'rota': data['rota_osmnx']})
    
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)

def listar_produtos(request):
    if request.method == 'POST':
        if not request.session.session_key:
            request.session.save()
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        # Se latitude e longitude forem inválidas, definir valores padrão (Maceió)
        if not latitude or not longitude or latitude == "0.0" or longitude == "0.0":
            latitude = -9.6658  # Maceió
            longitude = -35.7350

        dias = request.POST.get('dias')
        raio = request.POST.get('raio')
        item_list = request.POST.get('item_list')

        if not item_list:
            messages.error(request, "Nenhum produto selecionado.")
            return render(request, 'lista.html', {'resultado': None})

        try:
            item_list = json.loads(item_list) if isinstance(item_list, str) else item_list
            gtin_list = [int(gtin) for gtin in item_list]
        except Exception as e:
            logger.error("Erro ao processar item_list: %s", e)
            messages.error(request, "Erro ao processar a lista de produtos.")
            return render(request, 'lista.html', {'resultado': None})

        try:
            df = obter_produtos(request, gtin_list, int(raio), float(latitude), float(longitude), int(dias))

            if df.empty:
                messages.warning(request, "Nenhum dado foi retornado pela API.")
                return render(request, 'lista.html', {'resultado': None})

            avg_lat = df["LAT"].mean() if "LAT" in df.columns else float(latitude)
            avg_lon = df["LONG"].mean() if "LONG" in df.columns else float(longitude)

            tpplib_data = create_tpplib_data(df, avg_lat, avg_lon, media_preco=float(request.POST.get('precoCombustivel', 0)))

            resultado_solver = alns_solve_tpp(tpplib_data, 10000, 100)

            if not resultado_solver:
                messages.error(request, "Não foi possível encontrar uma solução viável.")
                return render(request, 'lista.html', {'resultado': None})

            rota = [idx for idx in resultado_solver.get('route', []) if 1 <= idx <= len(resultado_solver.get('mercados_comprados', []))]
            purchases = resultado_solver.get('purchases', {})
            total_cost = resultado_solver.get('total_cost', 0.0)
            total_distance = resultado_solver.get('total_distance', 0.0)
            execution_time = resultado_solver.get('execution_time', 0.0)
            mercados_comprados = resultado_solver.get('mercados_comprados', [])

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
                        'valor_total': float(m.get('valor_total', 0.0))
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
                'item_list': gtin_list
            }

            logger.warning(f"🧭 Coordenadas médias: avg_lat={avg_lat}, avg_lon={avg_lon}")

            return render(request, 'lista.html', context)

        except Exception as e:
            logger.error("Erro ao processar a solicitação: %s", e)
            messages.error(request, "Erro ao processar a solicitação.")
            return render(request, 'lista.html', {'resultado': None})

    return redirect('localizacao')


def calcular_distancia(lat1, lon1, lat2, lon2):
    """
    Calcula a distância entre dois pontos geográficos (latitude, longitude) usando a fórmula de Haversine.
    """
    return geodesic((lat1, lon1), (lat2, lon2)).km


def consultar_worker_thread(descricao, raio, lat, lon, dias, result_container):
    from algorithms.sefaz_api import obter_combustiveis  # Import dentro da thread
    try:
        result_container["result"] = obter_combustiveis(descricao, raio, lat, lon, dias)
    except Exception as e:
        result_container["result"] = {"error": str(e)}

def safe_consultar_combustivel(descricao, raio, lat, lon, dias, timeout=120):
    result = {}
    t = threading.Thread(target=consultar_worker_thread, args=(descricao, raio, lat, lon, dias, result))
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.critical("⏱️ Thread da SEFAZ excedeu timeout total e foi encerrada.")
        return {"error": "Tempo limite atingido para a consulta à SEFAZ."}
    return result.get("result", {"error": "Falha na consulta à SEFAZ."})

@csrf_exempt
def processar_combustivel(request):
    """
    View para processar a busca de combustíveis, calcular a média de preços e retornar o posto mais próximo.
    Protegida contra travamentos e falhas graves da API SEFAZ.
    """
    try:
        tipo_combustivel = request.POST.get('descricao')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        dias = request.POST.get('dias')
        raio = request.POST.get('raio')

        # Validação como inteiro (com fallback e tratamento de erro)
        try:
            tipo_combustivel = int(request.POST.get('descricao'))
        except (ValueError, TypeError):
            return JsonResponse({"error": "Tipo de combustível inválido"}, status=400)

        if tipo_combustivel not in [1, 2, 3, 4, 5, 6]:
            return JsonResponse({"error": "Tipo de combustível inválido"}, status=400)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                safe_consultar_combustivel,
                int(tipo_combustivel), int(raio), float(latitude), float(longitude), int(dias), 120
            )

            try:
                data = future.result(timeout=120)
            except ThreadTimeoutError:
                logger.critical("⏱️ Timeout total excedido na consulta à SEFAZ.")
                return JsonResponse({"error": "Tempo excedido ao consultar dados do combustível."}, status=504)

        if data is None or not isinstance(data, pd.DataFrame) or data.empty:
            return JsonResponse({"error": "Nenhum dado encontrado para o combustível especificado."}, status=404)

        df = data.copy()
        media_preco = float(df.nsmallest(3, "VALOR")["VALOR"].mean())

        estabelecimento_mais_proximo = df.loc[df["DISTANCIA_KM"].idxmin()].to_dict()

        # Converter valores para tipos nativos do Python
        estabelecimento_convertido = {
            k: (float(v) if isinstance(v, (np.float32, np.float64)) else str(v))
            for k, v in estabelecimento_mais_proximo.items()
        }

        mapa_nomes = {
            "1": "Gasolina Comum",
            "2": "Gasolina Aditivada",
            "3": "Álcool",
            "4": "Diesel Comum",
            "5": "Diesel Aditivado (S10)",
            "6": "GNV"
        }

        resposta = {
            "descricao": mapa_nomes.get(tipo_combustivel, "Desconhecido"),
            "media_preco": round(media_preco, 2),
            "posto_mais_proximo": estabelecimento_convertido
        }

        return JsonResponse(resposta)

    except SystemExit:
        logger.critical("🚨 SystemExit capturado! Worker encerrando indevidamente.")
        return JsonResponse({"error": "Erro crítico na requisição. Tente novamente."}, status=500)

    except Exception as e:
        logger.exception(f"❌ Erro inesperado em processar_combustivel: {e}")
        return JsonResponse({"error": "Erro interno no servidor."}, status=500)