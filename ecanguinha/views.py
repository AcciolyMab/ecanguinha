import requests
import pandas as pd
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
import logging
import json

# Configuração de log para facilitar o debug
logger = logging.getLogger(__name__)


# View para a página inicial
def home(request):
    if request.method == "GET":
        return render(request, 'home.html')
    else:
        nome = request.POST['nome']
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
            headers={'User-Agent': 'canguinhaApp/1.0 (your-email@example.com)'}
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


# View para listar produtos
def consultarproduto(gtin, raio, my_lat, my_lon, dias):
    url = 'http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa'

    # Certifique-se de que latitude e longitude são float
    data = {
        "produto": {"gtin": gtin},
        "estabelecimento": {
            "geolocalizacao": {
                "latitude": float(my_lat),
                "longitude": float(my_lon),
                "raio": int(raio)
            }
        },
        "dias": int(dias),
        "pagina": 1,
        "registrosPorPagina": 50
    }

    headers = {
        "Content-Type": "application/json",
        "AppToken": "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d"
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Erro na API para GTIN {gtin}: {response.status_code} - {response.text}")
        return None


# View para listar produtos
def listar_produtos(request):
    if request.method == 'POST' or 'page' in request.GET:
        latitude = request.POST.get('latitude') or request.GET.get('latitude')
        longitude = request.POST.get('longitude') or request.GET.get('longitude')
        dias = request.POST.get('dias') or request.GET.get('dias')
        raio = request.POST.get('raio') or request.GET.get('raio')
        item_list = request.POST.get('item_list') or request.GET.get('item_list')

        # Verificação de item_list
        if not item_list:
            logger.error("item_list está vazio ou não foi enviado.")
            return render(request, 'lista.html', {'error': "Nenhum produto selecionado."})

        try:
            # Decodificar item_list se for uma string JSON
            if isinstance(item_list, str):
                item_list = json.loads(item_list)
        except json.JSONDecodeError as e:
            logger.error("Erro ao decodificar item_list: %s", e)
            return render(request, 'lista.html', {'error': "Erro ao processar a lista de produtos."})

        response_list = []
        for item in item_list:
            try:
                response = consultarproduto(item, raio, latitude, longitude, dias)
                if response and 'conteudo' in response:
                    response_list.extend(response['conteudo'])
            except Exception as e:
                logger.error(f"Erro ao consultar o produto {item}: {e}")

        if response_list:
            data_list = [
                {
                    'CODIGO_BARRAS': str(produto['gtin']),
                    'NCM': str(produto['ncm']),
                    'PRODUTO': produto['descricao'],
                    'VALOR': produto['venda']['valorVenda'],
                    'CNPJ': str(estabelecimento['cnpj']),
                    'MERCADO': estabelecimento['razaoSocial'],
                    'ENDERECO': f"{endereco['nomeLogradouro']}, {endereco['numeroImovel']} - {endereco['bairro']}",
                    'LAT': endereco['latitude'],
                    'LONG': endereco['longitude']
                }
                for item in response_list
                for produto, estabelecimento, endereco in
                [(item['produto'], item['estabelecimento'], item['estabelecimento']['endereco'])]
            ]

            df = pd.DataFrame(data_list)

            # Função para categorizar o produto
            def categorizar_produto(codigo_barras):
                # Definindo o dicionário de categorias dentro da função
                categorias = {
                    'FEIJAO': ['7896006744115', '7893500007715', '7898383101000', '7898907040969', '7898902735167'],
                    'ARROZ': ['7896006716112', '7893500024996', '7896012300213', '7898018160082', '7896084700027'],
                    'MACARRAO': ['7896213005184', '7896532701576', '7896022200879', '7896005030530', '7896016411021'],
                    'FARINHA MANDIOCA': ['7898994092216', '7898902735099', '7898272919211', '7898272919068',
                                         '7898277160021'],
                    'CAFE 250G': ['7896005800027', '7896224808101', '7896224803069', '7898286200060', '7896005213018'],
                    'BOLACHA': ['7896213006266', '7896005030356', '7898657832173', '7896003738636', '7891962014982'],
                    'FLOCAO MILHO': ['7896481130106', '7891091010718', '7898366932973', '7898932426042',
                                     '7898366930023'],
                    'MARGARINA': ['7894904271733', '7893000979932', '7894904929108', '7891152506815', '7891515901066'],
                    'MANTEIGA': ['7898912485496', '7896596000059', '7896010400885', '7898939253399', '7898043230798'],
                    'LEITE PO': ['7898215152330', '7896051130079', '7898949565017', '7896259410133', '7898403780918'],
                    'LEITE UHT': ['7896259412861', '7898118390860', '7898403782394', '7898387120380', '7896085393488'],
                    'OLEO DE SOJA': ['7891107101621', '7892300001428', '7898247780075', '7896036090244',
                                     '7892300030060'],
                    'ACUCAR CRISTAL': ['7896065200072', '7896215300591', '7896065200065', '7897261800011',
                                       '7897154430103'],
                    'OVOS': ['7897146402019', '7897146405010', '7897146402033', '7898903159085', '7896414410121'],
                    'SARDINHA 125G': ['7891167021013', '7891167023017', '7891167023024', '7896009301063',
                                      '7891167021075']
                }

                # Verificar a categoria do código de barras
                for categoria, codigos in categorias.items():
                    if codigo_barras in codigos:
                        return categoria
                return 'Desconhecido'

            df['CATEGORIA'] = df['CODIGO_BARRAS'].apply(categorizar_produto)
            df = df[['CATEGORIA', 'VALOR', 'MERCADO', 'ENDERECO', 'LAT', 'LONG']].rename(
                columns={'CATEGORIA': 'PRODUTO'})
            data = df.to_dict(orient='records')

            paginator = Paginator(data, 10)
            page_number = request.GET.get('page')
            page_obj = paginator.get_page(page_number)

            return render(request, 'lista.html', {
                'page_obj': page_obj,
                'latitude': latitude,
                'longitude': longitude,
                'dias': dias,
                'raio': raio,
                'item_list': json.dumps(item_list)
            })
        else:
            logger.warning("Nenhum dado foi retornado pela API.")
            return render(request, 'lista.html', {'error': "Nenhum dado foi retornado pela API."})

    return render(request, 'localizacao.html')
