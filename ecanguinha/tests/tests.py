from django.test import TestCase
import pytest
import json
from django.urls import reverse
from django.test import RequestFactory
from unittest.mock import patch, MagicMock

from ecanguinha.views import listar_produtos


@pytest.mark.django_db
@patch('ecanguinha.views.obter_produtos')
@patch('ecanguinha.views.alns_solve_tpp')
@patch('ecanguinha.views.calcular_dias_validos_dinamicamente', return_value=2)
def test_listar_produtos_ok(mock_dias, mock_solver, mock_obter):
    factory = RequestFactory()
    gtins = [7891234567890, 7899876543210]

    # Simula retorno de produtos
    df_mock = MagicMock()
    df_mock.empty = False
    df_mock.columns = ['LAT', 'LONG']
    df_mock.__getitem__.side_effect = lambda key: [ -9.66, -9.66 ] if key == "LAT" else [ -35.73, -35.73 ]
    mock_obter.return_value = df_mock

    mock_solver.return_value = {
        'route': [1, 2],
        'purchases': {
            'Produtos comprados no Mercado 1': [
                {'produto': 'Feijão', 'preco': 5.49},
                {'produto': 'Arroz', 'preco': 4.90}
            ]
        },
        'total_cost': 15.20,
        'total_distance': 3.5,
        'execution_time': 2.0,
        'mercados_comprados': [
            {'nome': 'Mercado 1', 'endereco': 'Rua A', 'latitude': -9.6600, 'longitude': -35.7300,
             'valor_total': 10.39, 'tipo': 'Supermercado', 'avaliacao': 4.3}
        ]
    }

    post_data = {
        'latitude': '-9.6658',
        'longitude': '-35.7350',
        'dias': '2',
        'raio': '1',
        'precoCombustivel': '5.29',
        'item_list': json.dumps(gtins),
        'progress_id': '12345'
    }

    request = factory.post(reverse('listar_produtos'), post_data)
    request.session = {}  # mocka sessão
    request.session.session_key = 'testsession'

    response = listar_produtos(request)

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Lista de mercados" in content
    assert "Mercado 1" in content
    assert "Feijão" in content
    assert "R$ 5,49" in content or "R$ 5.49" in content


from django.test import TestCase, Client
from django.urls import reverse

class ListarProdutosViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_listar_produtos_post_sem_dados(self):
        response = self.client.post(reverse('listar_produtos'), {
            "latitude": "-9.6658",
            "longitude": "-35.7350",
            "item_list": "7891234567890,7890987654321",
            "raio": "2",
            "dias": "3",
            "precoCombustivel": "5.00"
        })
        self.assertEqual(response.status_code, 200)
