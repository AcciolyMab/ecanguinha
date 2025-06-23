import json
import logging
import re

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

# Configuração de log para facilitar o debug
logger = logging.getLogger(__name__)

# View para a página inicial
from django.http import HttpResponse
from django.contrib import messages
import pandas as pd


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

def obter_rota(request):
    """
    View para retornar a rota detalhada gerada pelo OSMnx.
    """
    try:
        # Aqui, você deve garantir que `mercados_df` tenha os dados necessários.
        data = create_tpplib_data(mercados_df, buyer_lat, buyer_lon, media_preco=5.5, raio_busca=5.0)
        return JsonResponse({'rota': data['rota_osmnx']})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def listar_produtos(request):
    if request.method == 'POST':
        try:
            print("🔎 Dados recebidos no POST:", request.POST)

            # 🔹 Captura Latitude e Longitude e remove espaços
            latitude_str = request.POST.get("hiddenLatitude", "").strip()
            longitude_str = request.POST.get("hiddenLongitude", "").strip()

            #print(f"📌 Coordenadas recebidas: Latitude={latitude_str}, Longitude={longitude_str}")  

            # 🔹 Garante que latitude e longitude estão no formato correto
            try:
                # Substitui vírgula por ponto caso venha com formato errado
                # latitude_str = latitude_str.replace(',', '.')
                # longitude_str = longitude_str.replace(',', '.')

                latitude = float(latitude_str)
                longitude = float(longitude_str)

                #print(f"SEM TRATAR recebidas: Latitude={latitude_str}, Longitude={longitude_str}")  


                #Validação de coordenadas.
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                  print("Coordenadas fora do Range")
                  return JsonResponse({"error": "Coordenadas fora do range"}, status=400)

            except ValueError:
                print("Erro: Latitude ou Longitude não são números válidos.")
                return JsonResponse({"error": "Latitude ou Longitude inválidas"}, status=400)

            except TypeError:
              print("Erro de tipo, verifique se a latitude e longitude foram recebidas corretamente")
              return JsonResponse({"error": "Erro de tipo"}, status=400)


            #logger.debug(f"📍 Coordenadas processadas: Latitude {latitude}, Longitude {longitude}")

            # Captura demais parâmetros
            dias = int(request.POST.get('dias', '1').strip())
            raio = int(request.POST.get('raio', '3').strip())
            preco_combustivel = float(request.POST.get('precoCombustivel', '0').strip())

            # Processamento da lista de produtos
            item_list = request.POST.get('item_list', '[]').strip()
            if not item_list or item_list == "[]":
                messages.error(request, "Nenhum produto selecionado.")
                return render(request, 'lista.html', {'resultado': None})

            try:
                gtin_list = json.loads(item_list)
                gtin_list = [int(gtin) for gtin in gtin_list if str(gtin).isdigit()]
            except json.JSONDecodeError:
                raise ValueError("Erro ao decodificar item_list")

            #logger.debug(f"🛒 Lista de produtos GTIN: {gtin_list}")

            # 🔥 🔹 Obtém os produtos com base nos parâmetros
            df = obter_produtos(request, gtin_list, raio, latitude, longitude, dias)
            if df.empty:
                messages.warning(request, "Nenhum dado foi retornado pela API.")
                return render(request, 'lista.html', {'resultado': None})

            # 🔥 🔹 Processa os dados do solver
            tpplib_data = create_tpplib_data(df, latitude, longitude, media_preco=preco_combustivel)
            resultado_solver = alns_solve_tpp(tpplib_data, 60000, 100)

            if not resultado_solver:
                messages.error(request, "Não foi possível encontrar uma solução viável.")
                return render(request, 'lista.html', {'resultado': None})

            mercados_comprados = resultado_solver.get('mercados_comprados', [])
            purchases = resultado_solver.get('purchases', {})
            total_cost = resultado_solver.get('total_cost', 0.0)
            total_distance = resultado_solver.get('total_distance', 0.0)
            execution_time = resultado_solver.get('execution_time', 0.0)

            rota = [
                idx for idx in resultado_solver.get('route', [])
                if 1 <= idx <= len(mercados_comprados)
            ]

            node_coords = {
                str(idx): [float(mercado.get('latitude')), float(mercado.get('longitude'))]
                for idx, mercado in enumerate(mercados_comprados, start=1)
                if mercado.get('latitude') and mercado.get('longitude')
            }

            processed_purchases = {
                key.replace('Produtos comprados no ', ''): value for key, value in purchases.items()
            }

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
                'user_latitude': latitude,  # Corrigido: Envia latitude correta para o template
                'user_longitude': longitude,
                'dias': dias,
                'raio': raio,
                'item_list': gtin_list
            }

            print(f"Contexto enviado para lista.html: user_lat={latitude}, user_lon={longitude}")  
            #logger.debug(f"Contexto enviado para lista.html: {context}")
            return render(request, 'lista.html', context)

        except ValueError as ve:
            #logger.error(f" Erro nos dados de entrada: {ve}")
            messages.error(request, str(ve))
        except Exception as e:
            #logger.exception(" Erro inesperado ao processar a solicitação")
            messages.error(request, "Erro interno ao processar a solicitação. Tente novamente.")

    return redirect('localizacao')


def calcular_distancia(lat1, lon1, lat2, lon2):
    """
    Calcula a distância entre dois pontos geográficos (latitude, longitude) usando a fórmula de Haversine.
    """
    return geodesic((lat1, lon1), (lat2, lon2)).km


def processar_combustivel(request):
    """
    View para processar a busca de combustíveis, calcular a média de preços e retornar o posto mais próximo.
    """
    descricao = request.POST.get('descricao')
    latitude = request.POST.get('latitude')
    longitude = request.POST.get('longitude')
    dias = request.POST.get('dias')
    raio = request.POST.get('raio')

    if not descricao:
        return JsonResponse({"error": "A descrição do combustível é obrigatória"}, status=400)

    if latitude == "0.0" or longitude == "0.0":
        return JsonResponse({"error": "Latitude e Longitude são obrigatórios"}, status=400)

    # Obter os estabelecimentos mais próximos via API SEFAZ
    data = consultar_combustivel(descricao, int(raio), float(latitude), float(longitude), int(dias))

    # Verifica se a resposta da API é válida
    if not data or "conteudo" not in data:
        return JsonResponse({"error": "Nenhum dado encontrado para o combustível especificado."}, status=404)

    # Converter a resposta para DataFrame do Pandas
    df = pd.DataFrame(data["conteudo"])

    # Se não houver dados, retorna erro
    if df.empty:
        return JsonResponse({"error": "Nenhum dado encontrado para o combustível especificado."}, status=404)

    # Extrair preços dos combustíveis corretamente
    df["VALOR"] = df["produto"].apply(lambda x: x["venda"]["valorVenda"])

    # Selecionar os 3 menores valores de venda e calcular a média
    media_preco = df.nsmallest(3, "VALOR")["VALOR"].mean()

    # Adicionar a distância calculada para cada estabelecimento
    df["DISTANCIA_KM"] = df["estabelecimento"].apply(
        lambda x: calcular_distancia(
            float(latitude), 
            float(longitude), 
            x["endereco"]["latitude"], 
            x["endereco"]["longitude"]))

    # Selecionar o posto mais próximo
    estabelecimento_mais_proximo = df.loc[df["DISTANCIA_KM"].idxmin()]["estabelecimento"]

    # Montar resposta JSON
    resposta = {
        "descricao": descricao,
        "media_preco": round(media_preco, 2),
        "posto_mais_proximo": estabelecimento_mais_proximo
    }

    return JsonResponse(resposta, safe=False)