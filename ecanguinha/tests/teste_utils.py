# tests/test_utils.py
import pytest
from unittest.mock import patch
from ecanguinha.services.combustivel import update_progresso_cache


@patch("django.core.cache.cache")
def test_update_progresso_cache(mock_cache):
    mock_cache.get.return_value = 50

    update_progresso_cache("sessao_x", 5, 10)

    # Deve atualizar com 60% (6/10)
    mock_cache.set.assert_called_once_with("sessao_x", 60, timeout=300)