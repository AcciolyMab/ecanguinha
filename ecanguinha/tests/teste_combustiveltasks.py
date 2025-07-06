# tests/test_combustivel_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from ecanguinha.tasks import task_consultar_combustivel
from ecanguinha.services.combustivel import obter_preco_combustivel_por_gtin, update_progresso_cache


@patch("ecanguinha.tasks.obter_preco_combustivel_por_gtin")
@patch("ecanguinha.tasks.update_progresso_cache")
@patch("django.core.cache.cache")
def test_task_consultar_combustivel_basico(mock_cache, mock_update, mock_obter):
    mock_obter.return_value = (4.79, {"GTIN": "mockado"})
    mock_cache.get.return_value = ["7890000000000"]

    preco, detalhes = task_consultar_combustivel(gtin="7890000000000", tipo_combustivel=1, raio=1,
                                                 latitude=-9.65, longitude=-35.75, dias=3, posicao=1)

    assert preco == 4.79
    assert detalhes["GTIN"] == "mockado"
    mock_update.assert_called_once()
    mock_obter.assert_called_once()