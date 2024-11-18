# ecanguinha/views.py

import requests

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
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages


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

        # Verificação se os parâmetros obrigatórios foram recebidos
        if not item_list:
            messages.error(request, "Nenhum produto selecionado.")
            return render(request, 'lista.html', {'resultado': None})

        try:
            # Processamento da lista de produtos
            item_list = json.loads(item_list) if isinstance(item_list, str) else item_list
            gtin_list = [int(gtin) for gtin in item_list]
        except Exception as e:
            logger.error("Erro ao processar item_list: %s", e)
            messages.error(request, "Erro ao processar a lista de produtos.")
            return render(request, 'lista.html', {'resultado': None})

        try:
            # Chamada síncrona para obter os produtos
            df = obter_produtos(request, gtin_list, int(raio), float(latitude), float(longitude), int(dias))

            if df.empty:
                messages.warning(request, "Nenhum dado foi retornado pela API.")
                return render(request, 'lista.html', {'resultado': None})

            # Calcular latitude e longitude médias
            avg_lat = df["LAT"].mean() if "LAT" in df.columns else float(latitude)
            avg_lon = df["LONG"].mean() if "LONG" in df.columns else float(longitude)

            # Gerar dados para o solver
            tpplib_data = create_tpplib_data(df, avg_lat, avg_lon)

            # Parâmetros do solver
            max_iterations = 10000
            no_improve_limit = 100

            # Resolver o problema
            resultado_solver = alns_solve_tpp(tpplib_data, max_iterations, no_improve_limit)

            if not resultado_solver:
                messages.error(request, "Não foi possível encontrar uma solução viável.")
                return render(request, 'lista.html', {'resultado': None})

            # Processamento dos resultados
            rota = [idx for idx in resultado_solver.get('route', []) if 1 <= idx <= len(resultado_solver.get('mercados_comprados', []))]
            purchases = resultado_solver.get('purchases', {})
            total_cost = resultado_solver.get('total_cost', 0.0)
            total_distance = resultado_solver.get('total_distance', 0.0)
            execution_time = resultado_solver.get('execution_time', 0.0)
            mercados_comprados = resultado_solver.get('mercados_comprados', [])

            # Coordenadas dos mercados
            node_coords = {
                str(idx): [float(mercado.get('latitude')), float(mercado.get('longitude'))]
                for idx, mercado in enumerate(mercados_comprados, start=1)
                if mercado.get('latitude') and mercado.get('longitude')
            }

            # Ajustar nomes dos produtos
            processed_purchases = {key.replace('Produtos comprados no ', ''): value for key, value in purchases.items()}

            # Contexto para renderização
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

            return render(request, 'lista.html', context)

        except Exception as e:
            logger.error("Erro ao processar a solicitação: %s", e)
            messages.error(request, "Erro ao processar a solicitação.")
            return render(request, 'lista.html', {'resultado': None})

    # Redirecionar para a página de localização se não for POST
    return redirect('localizacao')