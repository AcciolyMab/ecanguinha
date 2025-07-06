# ecanguinha/tests/test_cache.py
from django.test import TestCase
from django.core.cache import cache

class RedisCacheTest(TestCase):
    def test_set_get_cache(self):
        cache.set("teste_cache", "valor_teste", timeout=30)
        valor = cache.get("teste_cache")
        self.assertEqual(valor, "valor_teste")