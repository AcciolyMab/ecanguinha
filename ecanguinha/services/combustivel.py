import pandas as pd
import logging

logger = logging.getLogger(__name__)

def calcular_media_combustivel(df: pd.DataFrame) -> float:
    """
    Calcula a média aritmética da coluna 'VALOR' de um DataFrame de combustíveis.
    
    Parâmetros:
        df (pd.DataFrame): DataFrame contendo os dados de estabelecimentos e preços.
    
    Retorno:
        float: Média aritmética dos valores encontrados. Retorna 0.0 se DataFrame estiver vazio ou sem a coluna.
    """
    if df.empty:
        logger.warning("⚠️ DataFrame vazio ao calcular média do combustível.")
        return 0.0

    if 'VALOR' not in df.columns:
        logger.error("❌ Coluna 'VALOR' ausente no DataFrame.")
        return 0.0

    try:
        media = df['VALOR'].mean()
        media_float = float(round(media, 2))
        logger.info(f"✅ Média calculada: {media_float}")
        return media_float
    except Exception as e:
        logger.exception(f"Erro ao calcular média do combustível: {e}")
        return 0.0
