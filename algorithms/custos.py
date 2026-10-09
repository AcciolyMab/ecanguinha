"""Custo real de deslocamento (R$), sem as penalidades internas do otimizador."""

CONSUMO_KM_POR_LITRO = 9.5  # consumo médio do veículo usado na otimização


def custo_deslocamento(distancia_km, preco_litro):
    """Distância percorrida (km) x preço do litro ÷ consumo (km/l)."""
    return round(float(distancia_km or 0) * float(preco_litro or 0) / CONSUMO_KM_POR_LITRO, 2)
