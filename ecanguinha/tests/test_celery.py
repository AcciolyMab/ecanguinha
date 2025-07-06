# ecanguinha/tests/test_celery.py
from django.test import TestCase, override_settings
from ecanguinha.tasks import processar_busca_produtos_task

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CeleryTaskTest(TestCase):
    def test_processar_busca_produtos_task_mockado(self):
        resultado = processar_busca_produtos_task.apply(args=[
            [7891234567890, 7890987654321], 1, -9.6658, -35.7350, 3, 5.0
        ]).get()
        self.assertIn("resultado", resultado)
        self.assertIn("purchases", resultado["resultado"])

if __name__ == "__main__":
    import unittest
    unittest.main()
