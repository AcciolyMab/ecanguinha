import pytest
import pandas as pd
from ecanguinha.services.combustivel import calcular_media_combustivel

@pytest.mark.parametrize("valores, media_esperada", [
    ([5.0, 6.0, 7.0], 6.0),                     # Caso normal
    ([5.5], 5.5),                               # Apenas um valor
    ([], 0.0),                                  # Lista vazia
    (['5.2', 'erro', 4.8], 5.0),                # Mistura de string e float
    (['erro', 'invalido', None], 0.0),          # Todos inválidos
    ([None, 3.0, ''], 3.0),                     # Apenas um válido
    (['10.0', 10.0], 10.0),                     # String numérica + float
    (['nan', 7.0], 7.0),                        # Valor string 'nan' é descartado
])
def test_calcular_media_combustivel(valores, media_esperada):
    df = pd.DataFrame({'VALOR': valores})
    resultado = calcular_media_combustivel(df)
    assert resultado == media_esperada
