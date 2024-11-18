# ecanguinha/views.py

import requests
import pandas as pd
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
import logging
import json

# Importações dos módulos personalizados
from algorithms.sefaz_api import obter_produtos
from algorithms.tpplib_data import create_tpplib_data
from algorithms.alns_solver import alns_solve_tpp

# Configuração de log para facilitar o debug
logger = logging.getLogger(__name__)

# View para a página inicial
from django.shortcuts import render
from django.http import HttpResponse


def home(request):
    if request.method == "GET":
        contexto = {
            'name': 'Seja bem vindo!'  # Substitua pelo valor desejado ou obtenha dinamicamente
        }
        return render(request, 'home.html', contexto)
    else:
        nome = request.POST.get('nome', '')
        return HttpResponse(nome)


# Função para obter latitude e longitude
@require_GET
def get_lat_long(request):
    endereco = request.GET.get('endereco')
    if not endereco:
        return JsonResponse({'error': 'Endereço não fornecido'}, status=400)

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': endereco, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'canguinhaApp/1.0 (seu-email@exemplo.com)'}
        )
        response.raise_for_status()
        data = response.json()

        if data:
            return JsonResponse(data[0])
        else:
            return JsonResponse({'error': 'Endereço não encontrado'}, status=404)

    except requests.RequestException as e:
        logger.error("Erro na requisição para a API Nominatim: %s", e)
        return JsonResponse({'error': 'Erro ao obter localização', 'details': str(e)}, status=500)


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


# View para listar produtos e processar a rota
def listar_produtos(request):
    if request.method == 'POST':
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        dias = request.POST.get('dias')
        raio = request.POST.get('raio')
        item_list = request.POST.get('item_list')

        # Verificação se item_list foi fornecido
        if not item_list:
            logger.error("item_list está vazio ou não foi enviado.")
            return render(request, 'lista.html', {
                'error': "Nenhum produto selecionado.",
                'resultado': None,
                'mercados_comprados': []
            })

        try:
            # Processar item_list para garantir que é uma lista de inteiros
            if isinstance(item_list, str):
                item_list = json.loads(item_list)
            gtin_list = [int(gtin) for gtin in item_list]
        except Exception as e:
            logger.error("Erro ao processar item_list: %s", e)
            return render(request, 'lista.html', {
                'error': "Erro ao processar a lista de produtos.",
                'resultado': None,
                'mercados_comprados': []
            })

        try:
            # Chamar a função para obter produtos
            df = obter_produtos(gtin_list, int(raio), float(latitude), float(longitude), int(dias))

            if df.empty:
                logger.warning("Nenhum dado foi retornado pela API.")
                return render(request, 'lista.html', {
                    'error': "Nenhum dado foi retornado pela API.",
                    'resultado': None,
                    'mercados_comprados': []
                })

            # Calcular a média das coordenadas dinamicamente
            if "LAT" in df.columns and "LONG" in df.columns:
                avg_lat = df["LAT"].mean()
                avg_lon = df["LONG"].mean()
            else:
                logger.error("Dados de localização não estão presentes no DataFrame.")
                avg_lat = float(latitude) if latitude else 0.0
                avg_lon = float(longitude) if longitude else 0.0

            logger.debug(f"Coordenadas médias calculadas: Latitude={avg_lat}, Longitude={avg_lon}")

            # Gerar dados para o solver
            tpplib_data = create_tpplib_data(df, avg_lat, avg_lon)

            logger.debug(f"Dados preparados para o solver: {tpplib_data}")

            # Executar o solver
            max_iterations = 10000
            no_improve_limit = 100
            resultado_solver = alns_solve_tpp(tpplib_data, max_iterations, no_improve_limit)

            logger.debug(f"Resultado formatado do solver: {resultado_solver}")

            if resultado_solver is None:
                logger.error("Não foi possível encontrar uma solução viável.")
                return render(request, 'lista.html', {
                    'error': "Não foi possível encontrar uma solução viável.",
                    'resultado': None,
                    'mercados_comprados': [],
                    'latitude': float(latitude),
                    'longitude': float(longitude),
                    'dias': int(dias),
                    'raio': int(raio),
                    'item_list': gtin_list
                })

            # Preparar o contexto para o template
            rota = resultado_solver.get('route', [])
            purchases = resultado_solver.get('purchases', {})
            total_cost = resultado_solver.get('total_cost', 0.0)
            total_distance = resultado_solver.get('total_distance', 0.0)
            execution_time = resultado_solver.get('execution_time', 0.0)
            mercados_comprados = resultado_solver.get('mercados_comprados', [])

            # Validar e corrigir o routeOrder
            max_index = len(mercados_comprados)
            rota = [idx for idx in rota if 1 <= idx <= max_index]

            if len(rota) != len(resultado_solver.get('route', [])):
                logger.warning("O routeOrder foi corrigido para evitar índices inválidos.")

            resultado_solver['route'] = rota

            # Preencher node_coords com as coordenadas dos mercados comprados
            node_coords = {}
            for idx, mercado in enumerate(mercados_comprados, start=1):
                lat = mercado.get('latitude')
                lon = mercado.get('longitude')
                if lat and lon:
                    node_coords[str(idx)] = [float(lat), float(lon)]

            # Processar as chaves de purchases
            processed_purchases = {}
            prefix = 'Produtos comprados no '
            for key, value in purchases.items():
                mercado_nome = key[len(prefix):] if key.startswith(prefix) else key
                processed_purchases[mercado_nome] = value

            context = {
                'resultado': {
                    'rota': rota,
                    'purchases': processed_purchases,
                    'total_cost': total_cost,
                    'total_distance': total_distance,
                    'execution_time': execution_time
                },
                'mercados_comprados': mercados_comprados,
                'node_coords': node_coords,
                'latitude': avg_lat,
                'longitude': avg_lon,
                'dias': int(dias),
                'raio': int(raio),
                'item_list': gtin_list
            }

            logger.debug(f"Contexto passado para lista.html: {context}")
            return render(request, 'lista.html', context)

        except Exception as e:
            logger.error("Erro ao processar a solicitação: %s", e)
            return render(request, 'lista.html', {
                'error': "Erro ao processar a solicitação.",
                'resultado': None,
                'mercados_comprados': [],
                'node_coords': {},
                'latitude': float(latitude) if latitude else 0.0,
                'longitude': float(longitude) if longitude else 0.0,
                'dias': int(dias) if dias else 1,
                'raio': int(raio) if raio else 2,
                'item_list': gtin_list
            })

    # Se não for POST, redireciona para a página de localização
    return render(request, 'localizacao.html')
