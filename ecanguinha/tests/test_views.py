from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.messages import get_messages

class ListarProdutosViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("listar_produtos")
        session = self.client.session
        session.save()

    def test_item_list_vazio(self):
        response = self.client.post(self.url, {
            "latitude": "-9.65",
            "longitude": "-35.74",
            "precoCombustivel": "5.45",
            "raio": "2",
            "dias": "3",
            "item_list": ""
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Nenhum produto selecionado.", messages)

    def test_lat_long_invalidos_usa_maceio(self):
        response = self.client.post(self.url, {
            "latitude": "0.0",
            "longitude": "0.0",
            "precoCombustivel": "5.45",
            "raio": "2",
            "dias": "3",
            "item_list": "7891234567890,7890987654321"
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("lista.html", [t.name for t in response.templates])
        context = response.context.get("resultado")
        self.assertIn("total_cost", context)

    def test_preco_combustivel_vazio(self):
        response = self.client.post(self.url, {
            "latitude": "-9.665",
            "longitude": "-35.735",
            "precoCombustivel": "",
            "raio": "2",
            "dias": "3",
            "item_list": "7891234567890,7890987654321"
        })

        self.assertEqual(response.status_code, 200)
        context = response.context.get("resultado")
        self.assertIn("total_cost", context)

    def test_item_list_completo(self):
        response = self.client.post(self.url, {
            "latitude": "-9.665",
            "longitude": "-35.735",
            "precoCombustivel": "5.20",
            "raio": "2",
            "dias": "3",
            "item_list": "7891234567890,7890987654321"
        })

        self.assertEqual(response.status_code, 200)
        context = response.context.get("resultado")
        self.assertIsInstance(context, dict)
        self.assertIn("total_cost", context)
