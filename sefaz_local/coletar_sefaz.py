"""Coleta preços REAIS na API Economiza Alagoas e grava em data/economizaal_coletado.json.

O server.py carrega esse arquivo junto com o JSON base. Rode numa rede que alcance a SEFAZ:
    python coletar_sefaz.py [--dias 10] [--raio 15] [--gtins arquivo.txt]

GTINs: os do catálogo do app (algorithms/sefaz_api.py) + os mais frequentes do JSON base.
Pontos: centros de bairros de Maceió e de cidades de Alagoas (PONTOS abaixo).
Retoma de onde parou (mescla por CNPJ+GTIN, mantendo a venda mais recente) e aborta após
várias falhas seguidas (ex.: API fora do ar / 403).
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

AQUI = Path(__file__).parent
DATA = AQUI / "data"
SAIDA = DATA / "economizaal_coletado.json"
URL = os.environ.get("SEFAZ_COLETA_URL",
                     "http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public/produto/pesquisa")
TOKEN = os.environ.get("SEFAZ_API_KEY", "ad909a7a6f0d6a130941ae2a9706eec58c0bb65d")

PONTOS = {  # nome: (lat, lon)
    "Maceió - Ponta Verde": (-9.6616, -35.7090), "Maceió - Jatiúca": (-9.6540, -35.7171),
    "Maceió - Centro": (-9.6669, -35.7369), "Maceió - Farol": (-9.6560, -35.7350),
    "Maceió - Jacintinho": (-9.6360, -35.7200), "Maceió - Benedito Bentes": (-9.5560, -35.7240),
    "Maceió - Cidade Universitária": (-9.5560, -35.7740), "Maceió - Serraria": (-9.5950, -35.7250),
    "Maceió - Tabuleiro": (-9.5530, -35.7530), "Maceió - Jaraguá": (-9.6597, -35.7261),
    "Maceió - Pajuçara": (-9.6690, -35.7201), "Maceió - Ouro Preto": (-9.6136, -35.7314),
    "Maceió - Cruz das Almas": (-9.6370, -35.7050), "Maceió - Gruta de Lourdes": (-9.6230, -35.7440),
    "Maceió - Clima Bom": (-9.5700, -35.7850), "Maceió - Santa Lúcia": (-9.6140, -35.7600),
    "Satuba": (-9.5650, -35.8230), "Rio Largo": (-9.4780, -35.8530), "Marechal Deodoro": (-9.7100, -35.8960),
    "Coqueiro Seco": (-9.6380, -35.7940), "Pilar": (-9.6040, -35.9560), "Barra de São Miguel": (-9.8420, -35.9000),
    "São Miguel dos Campos": (-9.7800, -36.0970), "Arapiraca": (-9.7520, -36.6610), "Palmeira dos Índios": (-9.4050, -36.6320),
    "Penedo": (-10.2890, -36.5810), "Delmiro Gouveia": (-9.3850, -37.9990), "União dos Palmares": (-9.1590, -36.0220),
    "Maragogi": (-9.0120, -35.2240), "Porto Calvo": (-9.0510, -35.3990), "Santana do Ipanema": (-9.3690, -37.2450),
    "São Luís do Quitunde": (-9.3170, -35.5600), "Passo de Camaragibe": (-9.2410, -35.4850),
    "Atalaia": (-9.5120, -36.0100), "Coruripe": (-10.1260, -36.1740), "Viçosa": (-9.3700, -36.2440),
}


def gtins_do_app():
    src = (AQUI.parent / "algorithms" / "sefaz_api.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r"\b(78\d{11})\b", src)))


def gtins_do_json(n=40):
    base = json.loads((DATA / "economizaal.json").read_text(encoding="utf-8"))
    c = Counter(r["codGetin"].lstrip("0") for r in base if r["codGetin"].isdigit() and len(r["codGetin"]) >= 13)
    return [g for g, _ in c.most_common(n)]


def converter(item, gtin):
    p, e = item.get("produto", {}), item.get("estabelecimento", {})
    end, venda = e.get("endereco", {}), p.get("venda", {})
    preco = venda.get("valorVenda")
    return {
        "codGetin": str(gtin), "codNcm": p.get("ncm"), "dscProduto": p.get("descricao", ""),
        "valMinimoVendido": preco, "valMaximoVendido": preco,
        "dthEmissaoUltimaVenda": venda.get("dataVenda", ""),
        "valUnitarioUltimaVenda": preco, "valUltimaVenda": preco,
        "numCNPJ": e.get("cnpj"), "nomRazaoSocial": e.get("razaoSocial"),
        "nomFantasia": e.get("nomeFantasia") or e.get("razaoSocial"), "numTelefone": e.get("telefone"),
        "nomLogradouro": end.get("nomeLogradouro", ""), "numImovel": end.get("numeroImovel", ""),
        "nomBairro": end.get("bairro", ""), "numCep": end.get("cep"), "nomMunicipio": end.get("municipio", ""),
        "numLatitude": end.get("latitude"), "numLongitude": end.get("longitude"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=10)
    ap.add_argument("--raio", type=int, default=15)
    ap.add_argument("--gtins", help="arquivo com um GTIN por linha (substitui a lista padrão)")
    ap.add_argument("--pausa", type=float, default=0.5)
    ap.add_argument("--max-falhas", type=int, default=5)
    a = ap.parse_args()

    gtins = ([l.strip() for l in open(a.gtins) if l.strip()] if a.gtins
             else sorted(set(gtins_do_app()) | set(gtins_do_json())))
    acumulado = {}
    if SAIDA.exists():
        for r in json.loads(SAIDA.read_text(encoding="utf-8")):
            acumulado[(r["numCNPJ"], r["codGetin"].lstrip("0"))] = r

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "AppToken": TOKEN})
    falhas = novos = 0
    total = len(gtins) * len(PONTOS)
    for i, (gtin, (nome, (lat, lon))) in enumerate(((g, p) for g in gtins for p in PONTOS.items()), 1):
        body = {"produto": {"gtin": gtin},
                "estabelecimento": {"geolocalizacao": {"latitude": lat, "longitude": lon, "raio": a.raio}},
                "dias": a.dias, "pagina": 1, "registrosPorPagina": 3000}
        try:
            r = s.post(URL, json=body, timeout=60)
            r.raise_for_status()
            conteudo = r.json().get("conteudo") or []
            falhas = 0
        except (requests.RequestException, ValueError) as ex:
            falhas += 1
            print(f"[{i}/{total}] {gtin} @ {nome}: falha ({ex})", file=sys.stderr)
            if falhas >= a.max_falhas:
                print(f"{falhas} falhas seguidas: API indisponível. Abortando (progresso salvo).", file=sys.stderr)
                break
            time.sleep(2)
            continue
        for item in conteudo:
            reg = converter(item, gtin)
            if not reg["numCNPJ"] or reg["numLatitude"] is None:
                continue
            k = (reg["numCNPJ"], gtin.lstrip("0"))
            if k not in acumulado:
                novos += 1
            if k not in acumulado or reg["dthEmissaoUltimaVenda"] > acumulado[k]["dthEmissaoUltimaVenda"]:
                acumulado[k] = reg
        if i % 25 == 0:
            SAIDA.write_text(json.dumps(list(acumulado.values()), ensure_ascii=False), encoding="utf-8")
            print(f"[{i}/{total}] {len(acumulado)} registros ({novos} novos)", flush=True)
        time.sleep(a.pausa)

    SAIDA.write_text(json.dumps(list(acumulado.values()), ensure_ascii=False), encoding="utf-8")
    mercados = len({r["numCNPJ"] for r in acumulado.values()})
    print(f"Concluído: {len(acumulado)} registros, {mercados} mercados em {SAIDA.name}")


if __name__ == "__main__":
    main()
