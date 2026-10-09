"""Gera data/economizaal_sintetico.json: mercados SINTÉTICOS (fictícios) em bairros pouco cobertos.

Cada mercado sintético nasce ~100-300 m de um mercado real do mesmo bairro (para cair perto
de um nó viário) e recebe um subconjunto das vendas de mercados reais, com preço variado em
+-10%. Todos têm "sintetico": true e CNPJ iniciado em 99. Reprodutível (seed fixa).

Uso: python gerar_sintetico.py
"""
import json
import math
import random
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"
MIN_MERCADOS_POR_BAIRRO = 8   # bairros com menos que isso recebem sintéticos
NOVOS_POR_BAIRRO = 3
ITENS_POR_MERCADO = 40

rnd = random.Random(2023)
reais = json.loads((DATA / "economizaal.json").read_text(encoding="utf-8"))

por_bairro = defaultdict(dict)                 # (município, bairro) -> {cnpj: registro}
vendas = defaultdict(list)                      # cnpj -> registros
for r in reais:
    por_bairro[(r["nomMunicipio"], r["nomBairro"])].setdefault(r["numCNPJ"], r)
    vendas[r["numCNPJ"]].append(r)
com_gtin = [c for c, v in vendas.items() if any(x["codGetin"] != "SEM GTIN" for x in v)]

saida, seq = [], 0
for (mun, bairro), mercados in sorted(por_bairro.items()):
    if len(mercados) >= MIN_MERCADOS_POR_BAIRRO:
        continue
    ancora = rnd.choice(list(mercados.values()))
    for _ in range(NOVOS_POR_BAIRRO):
        seq += 1
        dist, ang = rnd.uniform(100, 300) / 111000, rnd.uniform(0, 2 * math.pi)
        lat = round(ancora["numLatitude"] + dist * math.sin(ang), 6)
        lon = round(ancora["numLongitude"] + dist * math.cos(ang) / math.cos(math.radians(lat)), 6)
        cnpj = f"99{seq:06d}000199"
        nome = f"SUPERMERCADO SINTETICO {bairro} {seq}"
        origem = vendas[rnd.choice(com_gtin)]
        for v in rnd.sample(origem, min(ITENS_POR_MERCADO, len(origem))):
            preco = round(v["valUnitarioUltimaVenda"] * rnd.uniform(0.9, 1.1), 2)
            saida.append({**v, "valMinimoVendido": preco, "valMaximoVendido": preco,
                          "valUnitarioUltimaVenda": preco, "valUltimaVenda": preco,
                          "numCNPJ": cnpj, "nomRazaoSocial": nome, "nomFantasia": nome,
                          "nomLogradouro": ancora["nomLogradouro"], "numImovel": str(rnd.randint(1, 900)),
                          "nomBairro": bairro, "nomMunicipio": mun, "numCep": ancora["numCep"],
                          "numLatitude": lat, "numLongitude": lon, "sintetico": True})

(DATA / "economizaal_sintetico.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
print(f"{seq} mercados sintéticos, {len(saida)} registros, {len(por_bairro)} bairros analisados")
