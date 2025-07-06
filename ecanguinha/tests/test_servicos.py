# tests/test_servicos.py
import pytest
import pandas as pd
from unittest.mock import patch
from ecanguinha.services.combustivel import obter_preco_combustivel_por_gtin


@patch("django.core.cache.cache")
def test_obter_preco_combustivel_cache_hit(mock_cache):
    mock_cache.get.return_value = {"VALOR": 5.1, "CNPJ": "111", "MERCADO": "Teste"}

    preco, detalhes = obter_preco_combustivel_por_gtin("7890000000000", 1, -9.6, -35.7, 3)

    assert preco == 5.1
    assert detalhes["MERCADO"] == "Teste"
    mock_cache.set.assert_not_called()


@patch("django.core.cache.cache")
@patch("ecanguinha.services.combustivel.consultar_combustivel")
def test_obter_preco_combustivel_cache_miss(mock_consulta, mock_cache):
    mock_cache.get.return_value = None
    mock_df = pd.DataFrame([{"VALOR": 5.1, "GTIN": "7890000000000"}])
    mock_consulta.return_value = mock_df

    preco, detalhes = obter_preco_combustivel_por_gtin("7890000000000", 1, -9.6, -35.7, 3)

    assert preco == 5.1
    assert "GTIN" in detalhes
    mock_cache.set.assert_called_once()