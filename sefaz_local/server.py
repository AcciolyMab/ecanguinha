"""Servidor local que expõe o JSON exportado da API Economiza Alagoas (SEFAZ-AL).

Fala o mesmo contrato da API real (POST /produto/pesquisa e /combustivel/pesquisa),
então o app só precisa apontar SEFAZ_BASE_URL para cá. Os preços de produtos vêm de
data/economizaal.json (dados reais, vendas de 2023) e, opcionalmente, de
data/economizaal_sintetico.json (mercados SINTÉTICOS gerados por gerar_sintetico.py,
campo "sintetico": true) e de data/economizaal_coletado.json (coletar_sefaz.py, dados reais). Desligue o sintético com SEFAZ_INCLUIR_SINTETICO=0.

Limitações: o parâmetro "dias" é ignorado nos produtos (o JSON é de 2023) e o JSON não
tem combustíveis; /combustivel/pesquisa devolve preços de referência FICTÍCIOS (datados
de agora) apenas para o fluxo do app, que depende deles, funcionar.
"""
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = "/sfz-economiza-alagoas-api/api/public"
DATA = Path(os.environ.get("SEFAZ_DATA_DIR", Path(__file__).parent / "data"))


def _carregar():
    registros = json.loads((DATA / "economizaal.json").read_text(encoding="utf-8"))
    sint = DATA / "economizaal_sintetico.json"
    if sint.exists() and os.environ.get("SEFAZ_INCLUIR_SINTETICO", "1") != "0":
        registros += json.loads(sint.read_text(encoding="utf-8"))
    coletado = DATA / "economizaal_coletado.json"   # gerado por coletar_sefaz.py (dados reais)
    if coletado.exists():
        registros += json.loads(coletado.read_text(encoding="utf-8"))
    return registros


def _norm(gtin):
    g = str(gtin).strip()
    return g.lstrip("0") if g.isdigit() else None


def _indexar(registros):
    """Índice gtin normalizado -> {cnpj: registro mais recente}; e estabelecimentos por CNPJ."""
    por_gtin, estabs = {}, {}
    for r in registros:
        cnpj = r["numCNPJ"]
        estabs.setdefault(cnpj, r)
        g = _norm(r["codGetin"])
        if not g:
            continue
        atual = por_gtin.setdefault(g, {}).get(cnpj)
        if atual is None or r["dthEmissaoUltimaVenda"] > atual["dthEmissaoUltimaVenda"]:
            por_gtin[g][cnpj] = r
    return por_gtin, estabs


REGISTROS = _carregar()
POR_GTIN, ESTABS = _indexar(REGISTROS)


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def _estab(r):
    return {
        "cnpj": r["numCNPJ"],
        "razaoSocial": r["nomRazaoSocial"],
        "nomeFantasia": r.get("nomFantasia") or r["nomRazaoSocial"],
        "endereco": {"nomeLogradouro": r["nomLogradouro"], "numeroImovel": r["numImovel"],
                     "bairro": r["nomBairro"], "municipio": r["nomMunicipio"], "uf": "AL",
                     "latitude": r["numLatitude"], "longitude": r["numLongitude"]},
    }


def _dentro(geo, r):
    return _km(float(geo["latitude"]), float(geo["longitude"]),
               r["numLatitude"], r["numLongitude"]) <= float(geo.get("raio", 5))


def pesquisa_produto(body):
    gtin = str(body.get("produto", {}).get("gtin", ""))
    geo = body["estabelecimento"]["geolocalizacao"]
    itens = []
    for r in POR_GTIN.get(_norm(gtin) or "", {}).values():
        if not _dentro(geo, r):
            continue
        preco = r.get("valUnitarioUltimaVenda") or r.get("valUltimaVenda") or 0.0
        itens.append({
            "produto": {"gtin": gtin, "descricao": r["dscProduto"],
                        "venda": {"valorVenda": preco, "dataVenda": r["dthEmissaoUltimaVenda"]}},
            "estabelecimento": _estab(r),
        })
    return {"conteudo": itens, "totalRegistros": len(itens), "pagina": 1}


def _h(*parts):
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest(), 16)


def pesquisa_combustivel(body):
    """Referência FICTÍCIA: o JSON não traz combustíveis. Usa os estabelecimentos do JSON no raio."""
    tipo = int(body.get("produto", {}).get("tipoCombustivel", 1))
    base = {1: 6.19, 2: 6.39, 3: 4.59}.get(tipo, 6.09)
    agora = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    geo = body["estabelecimento"]["geolocalizacao"]
    itens = []
    for cnpj, r in ESTABS.items():
        if _dentro(geo, r):
            itens.append({
                "produto": {"descricao": f"COMBUSTIVEL REFERENCIA (FICTICIO) TIPO {tipo}",
                            "venda": {"valorVenda": round(base + (_h("c", cnpj, tipo) % 30) / 100.0, 2),
                                      "dataVenda": agora}},
                "estabelecimento": _estab(r),
            })
    return {"conteudo": itens, "totalRegistros": len(itens), "pagina": 1}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            rota = self.path.rstrip("/")
            if rota == BASE + "/produto/pesquisa":
                out, code = pesquisa_produto(body), 200
            elif rota == BASE + "/combustivel/pesquisa":
                out, code = pesquisa_combustivel(body), 200
            else:
                out, code = {"status": 404, "error": "Not Found"}, 404
        except Exception as e:  # noqa: BLE001
            out, code = {"status": 400, "error": f"requisicao invalida: {e}"}, 400
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[sefaz-local]", fmt % args, flush=True)


if __name__ == "__main__":
    print(f"SEFAZ local: {len(REGISTROS)} registros, {len(ESTABS)} mercados, "
          f"{len(POR_GTIN)} GTINs em :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
