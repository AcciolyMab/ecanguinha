"""Geocodificação de endereços de mercados via Nominatim (OpenStreetMap), respeitando o limite de uso.

A política do Nominatim pede no máximo 1 requisição por segundo; aqui usamos INTERVALO_S = 2 s entre consultas,
de forma global (Redis): vale mesmo com vários workers Celery. O resultado é guardado em cache por endereço
(CACHE_DIAS), então cada mercado é geocodificado uma vez só.
"""
import hashlib
import logging
import time

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Mozilla/5.0 (compatible; CanguinhaBot/1.0; +https://www.canguinhaal.com.br)"
INTERVALO_S = 2.0
CACHE_DIAS = 30
CACHE_NAO_ENCONTRADO_DIAS = 1


def _cache():
    from django.core.cache import cache      # importação tardia: o módulo carrega sem Django configurado
    return cache


def _aguardar_vez():
    """Garante >= INTERVALO_S entre consultas: a chave expira em INTERVALO_S e `add` é atômico no Redis."""
    while not _cache().add("nominatim:vez", 1, timeout=int(INTERVALO_S)):
        time.sleep(0.25)


def _buscar(consulta):
    """(lat, lon) da primeira resposta do Nominatim, ou None. Erros de rede devolvem None sem cache."""
    _aguardar_vez()
    try:
        r = requests.get(NOMINATIM_URL, params={"q": consulta, "format": "json", "limit": 1, "countrycodes": "br"},
                         headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Nominatim falhou para '{consulta}': {e}")
        raise
    return (float(dados[0]["lat"]), float(dados[0]["lon"])) if dados else None


def geocodificar_endereco(logradouro, numero, bairro, municipio):
    """(lat, lon) do endereço de um mercado, ou None. Usa cache e o intervalo de 2 s entre consultas."""
    numero = str(numero or "").strip()
    numero = numero if numero.isdigit() and numero != "0" else ""
    consultas = [", ".join(p for p in (logradouro, numero, bairro, municipio, "Alagoas", "Brasil") if p),
                 ", ".join(p for p in (logradouro, bairro, municipio, "Alagoas", "Brasil") if p)]
    consultas = list(dict.fromkeys(consultas))
    chave = "geocode:mercado:" + hashlib.md5("|".join(consultas).encode()).hexdigest()
    guardado = _cache().get(chave)
    if guardado is not None:
        return tuple(guardado) if guardado else None
    try:
        for consulta in consultas:
            ponto = _buscar(consulta)
            if ponto:
                _cache().set(chave, list(ponto), timeout=CACHE_DIAS * 86400)
                return ponto
    except (requests.RequestException, ValueError):
        return None                       # falha de rede: não guarda "não encontrado"
    _cache().set(chave, [], timeout=CACHE_NAO_ENCONTRADO_DIAS * 86400)
    return None
