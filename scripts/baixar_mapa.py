"""Baixa UMA vez o mapa viário (ruas para carro) de Maceió e região metropolitana.

O app carrega o arquivo gerado (data/mapas/maceio_metro.graphml) em vez de baixar o mapa do
Overpass a cada busca (o que levava de segundos a minutos e falhava com frequência).

Uso (dentro do container, onde as dependências estão instaladas):
    docker compose exec web python scripts/baixar_mapa.py
    docker compose exec web python scripts/baixar_mapa.py --lugares "Maceió, Alagoas, Brasil" "Satuba, Alagoas, Brasil"

É retomável: cada lugar baixado fica em data/mapas/partes/ e não é baixado de novo.
"""
import argparse
import re
import sys
import time
import unicodedata
from pathlib import Path

import networkx as nx
import osmnx as ox

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from algorithms.tpplib_data import ARQUIVO_MAPA, OVERPASS_URLS  # noqa: E402

LUGARES_PADRAO = [
    "Maceió, Alagoas, Brasil", "Rio Largo, Alagoas, Brasil", "Satuba, Alagoas, Brasil",
    "Marechal Deodoro, Alagoas, Brasil", "Coqueiro Seco, Alagoas, Brasil",
    "Santa Luzia do Norte, Alagoas, Brasil", "Pilar, Alagoas, Brasil", "Barra de São Miguel, Alagoas, Brasil",
]


def slug(texto):
    t = unicodedata.normalize("NFD", texto.split(",")[0]).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def baixar_lugar(lugar, tentativas=6):
    """Tenta os servidores Overpass em rodízio até conseguir."""
    for n in range(tentativas):
        url = OVERPASS_URLS[n % len(OVERPASS_URLS)]
        ox.settings.overpass_url = url
        ox.settings.requests_timeout = 300
        inicio = time.time()
        try:
            G = ox.graph_from_place(lugar, network_type="drive")
            print(f"  ok via {url} em {time.time() - inicio:.0f}s: {len(G)} nós")
            return G
        except Exception as e:  # noqa: BLE001
            print(f"  falha via {url} após {time.time() - inicio:.0f}s: {type(e).__name__}: {str(e)[:100]}")
            time.sleep(5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lugares", nargs="+", default=LUGARES_PADRAO)
    a = ap.parse_args()

    partes = ARQUIVO_MAPA.parent / "partes"
    partes.mkdir(parents=True, exist_ok=True)
    grafos, faltou = [], []
    for lugar in a.lugares:
        arq = partes / f"{slug(lugar)}.graphml"
        print(f"{lugar}:")
        if arq.exists():
            print("  já baixado")
            grafos.append(ox.load_graphml(arq))
            continue
        G = baixar_lugar(lugar)
        if G is None:
            faltou.append(lugar)
            continue
        ox.save_graphml(G, arq)
        grafos.append(G)

    if not grafos:
        sys.exit("Nenhum lugar foi baixado. Tente de novo mais tarde (o Overpass público é instável).")
    G = nx.compose_all(grafos)
    ox.save_graphml(G, ARQUIVO_MAPA)
    print(f"\nMapa salvo em {ARQUIVO_MAPA}: {len(G)} nós, {G.number_of_edges()} trechos, "
          f"{ARQUIVO_MAPA.stat().st_size / 1e6:.1f} MB")
    if faltou:
        print("ATENÇÃO: não foram baixados (rode de novo para completar):", "; ".join(faltou))


if __name__ == "__main__":
    main()
