# algorithms/sefaz_lista.py
"""Busca por lista de descrições e município (API Economiza Alagoas, manual do desenvolvedor v1.0).

Fluxo (a SEFAZ só é consultada depois que o usuário clica em "Buscar Ofertas"):
  1. Para cada descrição da lista: pesquisa por `descricao` no município, descarta itens sem GTIN
     e filtra o ruído (núcleo da descrição, quantidade, NCM dominante).
  2. Por GTIN aceito: remove preços outliers e guarda o menor preço de cada mercado por item.
  3. montar_dataframe() devolve o DataFrame que create_tpplib_data()/ALNS já consomem.
"""
import difflib
import logging
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from geopy.distance import geodesic

from algorithms.municipios_al import MUNICIPIOS_AL

logger = logging.getLogger(__name__)

# Limites aproximados de Alagoas: coordenadas fora deles (ex.: 0,0, cadastro sem geolocalização) são inválidas.
# Coordenada de um mercado a mais que isto do centro típico do seu bairro é tratada como erro de cadastro.
MAX_KM_DO_BAIRRO = 7.0
MIN_MERCADOS_PARA_VALIDAR_BAIRRO = 3   # mediana do bairro só é confiável com amostra mínima
AL_LAT = (-10.55, -8.75)
AL_LON = (-38.30, -35.10)
REGISTROS_POR_PAGINA = 5000  # máximo permitido pela API
MAX_PAGINAS = 20
# Só erros grosseiros de nota fiscal (ex.: R$ 260 num café de R$ 15, R$ 0,01): fora de 1/4 a 4x a mediana do GTIN.
# Não é filtro de "menor preço": preços baixos legítimos (promoções) passam; quem escolhe é o solver.
FAIXA_OUTLIER = (0.25, 4.0)
NCM_MIN_GRUPOS = 5           # o voto de NCM só vale com ao menos 5 GTINs (com menos, o NCM errado de uma nota decide)
NCM_DOMINANCIA = 0.5         # e quando o capítulo (2 primeiros dígitos) dominante tem >= 50% dos itens

# Palavras que podem vir antes do núcleo da descrição sem mudar o produto ("REFRI COCA COLA").
PREFIXOS_OK = {"PCT", "PACOTE", "CB", "KIT", "UN", "UND", "KG", "PC", "REF", "REFR", "REFRI", "REFRIG", "REFRIGERANTE",
               "CARNE", "BOV", "BOVINA", "BOVINO", "BV", "BIFE"}   # cortes: "CARNE BOV PATINHO KG"
# Palavras ignoradas como qualificadores da consulta.
STOPWORDS = {"DE", "DA", "DO", "DAS", "DOS", "E", "COM", "C", "EM", "SEM", "NA", "NO",
             "KG", "G", "GR", "L", "LT", "ML", "UN", "UND"}   # unidades soltas ("Patinho Kg") não são qualificadores
# Termos que indicam outro produto (ração, uso animal) mesmo com o nome do alimento ("ARROZ P ANIMAIS");
# valem só quando a consulta não os contém.
EXCLUSOES = {"ANIMAL", "ANIMAIS", "PET", "RACAO", "CAO", "CAES", "DOG", "CACHORRO", "CACHORROS", "GATO", "GATOS", "PASSAROS",
             "OSSO", "HAMBURGUER", "STROGONOFF", "SUINO", "SUINA"}   # outro produto/corte (ex.: "OSSO DE PATINHO")
# Sinônimos: o nome na nota fiscal costuma ser outro ("bolacha" é "BISCOITO" na nota).
SINONIMOS = {"BOLACHA": "BISCOITO", "BOLACHAS": "BISCOITO", "BISCOITOS": "BISCOITO"}
# Palavras de supermercado usadas para corrigir erros de digitação ("mateiga" -> "manteiga"). Só palavras fora
# deste vocabulário são comparadas, e só trocadas por uma muito parecida (difflib, corte 0,85).
VOCABULARIO = {
    "ARROZ", "FEIJAO", "ACUCAR", "CAFE", "LEITE", "MANTEIGA", "MARGARINA", "BISCOITO", "FARINHA", "MANDIOCA", "TRIGO",
    "MILHO", "FLOCAO", "MACARRAO", "OLEO", "SOJA", "SAL", "OVOS", "CARNE", "FRANGO", "PATINHO", "MOIDA", "COXAO",
    "LINGUICA", "SALSICHA", "PRESUNTO", "MORTADELA", "QUEIJO", "MUSSARELA", "REQUEIJAO", "IOGURTE", "CREME", "CREAM",
    "CRACKER", "RECHEADO", "INTEGRAL", "DESNATADO", "PARBOILIZADO", "TRADICIONAL", "REFRIGERANTE", "SUCO", "AGUA",
    "CERVEJA", "SARDINHA", "ATUM", "MOLHO", "TOMATE", "EXTRATO", "ACHOCOLATADO", "CEREAL", "FARINHA", "FERMENTO",
    "VINAGRE", "SABAO", "DETERGENTE", "SABONETE", "SHAMPOO", "DESODORANTE", "PAPEL", "HIGIENICO", "BANANA", "CEBOLA",
    "ALHO", "BATATA", "PAO", "BOLO", "CHOCOLATE", "GELATINA", "TEMPERO", "COLORAU", "FUBA", "CRISTAL", "REFINADO",
    "PRETO", "CARIOCA", "BRANCO", "SOLUVEL", "TORRADO",
}


def corrigir_consulta(texto):
    """Aplica sinônimos e corrige palavras com erro de digitação; mantém números, tamanhos e palavras conhecidas."""
    saida = []
    for palavra in str(texto).split():
        puro = _sem_acento(palavra)
        if not puro.isalpha() or len(puro) < 4:
            saida.append(palavra)
            continue
        if puro in SINONIMOS:
            saida.append(SINONIMOS[puro].lower())
        elif puro in VOCABULARIO:
            saida.append(palavra)
        else:
            perto = difflib.get_close_matches(puro, VOCABULARIO, n=1, cutoff=0.85)
            saida.append(perto[0].lower() if perto else palavra)
    corrigida = " ".join(saida)
    return re.sub(r"\bcreme\s+cracker\b", "cream cracker", corrigida, flags=re.I)   # "crem" empata entre creme/cream


# Abreviações comuns nas notas fiscais (abreviação -> forma completa).
ABREVIACOES = {"STA": "SANTA", "TRAD": "TRADICIONAL", "TRADIC": "TRADICIONAL", "VAC": "VACUO",
               "ALM": "ALMOFADA", "EXT": "EXTRA", "INT": "INTEGRAL", "DESN": "DESNATADO", "SEMI": "SEMIDESNATADO"}

_UNIDADES = {"KG": ("G", 1000.0), "G": ("G", 1.0), "GR": ("G", 1.0), "GRS": ("G", 1.0), "MG": ("G", 0.001),
             "L": ("ML", 1000.0), "LT": ("ML", 1000.0), "LTS": ("ML", 1000.0), "LITRO": ("ML", 1000.0),
             "LITROS": ("ML", 1000.0), "ML": ("ML", 1.0), "UN": ("UN", 1.0), "UND": ("UN", 1.0)}
_UNIDADES_RE = "|".join(sorted(_UNIDADES, key=len, reverse=True))
_RE_QTD = re.compile(rf"(?<![A-Z0-9])(?:(\d+)\s*X\s*)?(\d+(?:[.,]\d+)?)\s*({_UNIDADES_RE})(?![A-Z])")


class SefazErro(Exception):
    """Erro devolvido pela API (campo `message`) ou falha de comunicação."""


# ---------------------------------------------------------------- texto
def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").upper()


def tokenizar(texto):
    return re.sub(r"[^A-Z0-9]+", " ", _sem_acento(texto)).split()


def _raiz(token):
    return token[:-1] if len(token) > 3 and token.endswith("S") else token


def extrair_quantidades(texto):
    """Quantidades na descrição: lista de (valor na unidade base, unidade base, embalagens)."""
    achadas = []
    for pack, valor, unidade in _RE_QTD.findall(_sem_acento(texto)):
        base, fator = _UNIDADES[unidade]
        achadas.append((round(float(valor.replace(",", ".")) * fator, 3), base, int(pack) if pack else 1))
    return achadas


def quantidade_confere(descricao, quantidade):
    """True/False se a descrição declara a quantidade pedida; None se não declara nenhuma."""
    if quantidade is None:
        return True
    valor, base, _ = quantidade
    achadas = extrair_quantidades(descricao)
    if achadas:
        return any(b == base and abs(v - valor) <= valor * 0.01 and p == 1 for v, b, p in achadas)
    # sem unidade ("CAFE SANTA CLARA 250"): aceita o número solto quando é igual ao pedido
    numero = str(int(valor)) if float(valor).is_integer() else None
    if numero and re.search(rf"(?<![\dA-Z.,]){numero}(?![\dA-Z.,])", _sem_acento(descricao)):
        return True
    return None


def interpretar_consulta(texto):
    """'Café 250g' -> núcleo 'CAFE', qualificadores [], quantidade (250.0, 'G', 1)."""
    achadas = extrair_quantidades(texto)
    sem_qtd = _RE_QTD.sub(" ", _sem_acento(texto))
    tokens = [t for t in tokenizar(sem_qtd) if not t.isdigit() and t not in STOPWORDS]
    if not tokens:
        raise ValueError("Informe o nome do produto, por exemplo: Café 250g.")
    return {"nucleo": tokens[0], "qualificadores": tokens[1:], "quantidade": achadas[0] if achadas else None,
            "excluir": EXCLUSOES - {_raiz(t) for t in tokens} - set(tokens)}


def _token_confere(token_consulta, tokens_item):
    alvo = _raiz(ABREVIACOES.get(token_consulta, token_consulta))
    for t in tokens_item:
        t = _raiz(ABREVIACOES.get(t, t))
        if t == alvo or (len(t) >= 3 and alvo.startswith(t)):
            return True
    return False


def nucleo_confere(descricao, consulta):
    """O substantivo principal é o pedido (descarta 'Iogurte sabor café', 'Bebida ... café')."""
    tokens = tokenizar(descricao)
    nucleo = _raiz(consulta["nucleo"])

    def eh_nucleo(t):                       # palavra inteira ou abreviação por prefixo ("BISC", "ARR" para BISCOITO, ARROZ)
        t = _raiz(ABREVIACOES.get(t, t))
        return t == nucleo or (len(t) >= 3 and nucleo.startswith(t))

    posicao = next((i for i, t in enumerate(tokens) if eh_nucleo(t)), None)
    if posicao is None or any(t not in PREFIXOS_OK and t not in STOPWORDS for t in tokens[:posicao]):
        return False
    if consulta.get("excluir", EXCLUSOES) & set(tokens):
        return False
    return all(_token_confere(q, tokens) for q in consulta["qualificadores"])


# ---------------------------------------------------------------- GTIN
def gtin_canonico(valor):
    """GTIN válido (8/12/13/14 dígitos, não zerado) na forma canônica, ou None."""
    g = str(valor or "").strip()
    if not g.isdigit():
        return None
    sig = g.lstrip("0")
    if not sig:
        return None
    for tam in (8, 12, 13, 14):
        if len(sig) <= tam:
            return sig.zfill(tam)
    return None


def _capitulo_ncm(ncm):
    """Capítulo do NCM (2 primeiros dígitos do código de 8; o inteiro vindo da API perde o zero à esquerda)."""
    return str(ncm or "").strip().zfill(8)[:2]


def vendido_por_peso(produto):
    """Itens vendidos por peso (carne, frios, hortifrúti) raramente têm GTIN; a unidade da nota é KG/KG0001/KG9."""
    return str(produto.get("unidadeMedida") or "").strip().upper().startswith("KG")


def _chave_gtin(valor):
    g = gtin_canonico(valor)
    return g.lstrip("0") if g else None


# ---------------------------------------------------------------- seleção
def selecionar_itens(itens, consulta):
    """Agrupa por GTIN (itens vendidos por peso sem GTIN entram um a um) e devolve ([(gtin|None, itens)], descartados)."""
    grupos, por_peso, sem_gtin = defaultdict(list), [], 0
    for it in itens:
        chave = _chave_gtin(it["produto"].get("gtin"))
        if chave:
            grupos[chave].append(it)
        elif vendido_por_peso(it["produto"]):
            por_peso.append([it])                 # sem GTIN, mas vendido por peso (KG): cada oferta é um item
        else:
            sem_gtin += 1

    avaliados, motivos = [], Counter()
    for lista, peso in [(l, False) for l in grupos.values()] + [(l, True) for l in por_peso]:
        descs = [i["produto"].get("descricao", "") for i in lista]
        passam = [d for d in descs if nucleo_confere(d, consulta)]
        if len(passam) * 2 < len(descs):
            motivos["não é o produto pedido"] += 1
            continue
        votos = Counter(quantidade_confere(d, consulta["quantidade"]) for d in passam)
        # a quantidade só se confere em itens embalados; por peso o preço já é por KG
        if not peso and consulta["quantidade"] is not None and not (votos[True] and votos[True] >= votos[False]):
            motivos["quantidade diferente ou não informada"] += 1
            continue
        ncm = Counter(_capitulo_ncm(i["produto"].get("ncm")) for i in lista if i["produto"].get("ncm")).most_common(1)
        avaliados.append({"itens": lista, "ncm": ncm[0][0] if ncm else ""})

    # NCM como voto: o capítulo dominante entre os aprovados vence (o NCM declarado erra com frequência).
    # Só vale com amostra suficiente e domínio claro; com poucos GTINs o NCM de uma nota errada decidiria.
    dominante = Counter()
    for a in avaliados:
        dominante[a["ncm"]] += len(a["itens"])
    esperado = ""
    if len(avaliados) >= NCM_MIN_GRUPOS and dominante:
        capitulo, n = dominante.most_common(1)[0]
        if n >= NCM_DOMINANCIA * sum(dominante.values()):
            esperado = capitulo
    aceitos = []
    for a in avaliados:
        if esperado and a["ncm"] and a["ncm"] != esperado:
            motivos["classificação fiscal (NCM) diferente"] += 1
            continue
        aceitos.append((gtin_canonico(a["itens"][0]["produto"].get("gtin")), a["itens"]))   # None = vendido por peso
    motivos["sem código de barras (GTIN)"] = sem_gtin
    return aceitos, {k: v for k, v in motivos.items() if v}


def filtrar_outliers(precos):
    """Descarta erros grosseiros de preço: fora de FAIXA_OUTLIER x mediana (com ao menos 3 amostras)."""
    precos = [p for p in precos if p and p > 0]
    if len(precos) < 3:
        return precos
    m = statistics.median(precos)
    return [p for p in precos if FAIXA_OUTLIER[0] * m <= p <= FAIXA_OUTLIER[1] * m]


# ---------------------------------------------------------------- API
def validar_parametros(municipio_ibge, dias):
    if int(municipio_ibge) not in MUNICIPIOS_AL:
        raise ValueError("Município de Alagoas inválido.")
    if not 1 <= int(dias) <= 10:
        raise ValueError("O período da pesquisa deve ficar entre 1 e 10 dias.")


def validar_descricao(descricao):
    texto = " ".join(str(descricao or "").split())
    if not 3 <= len(texto) <= 50:
        raise ValueError("A descrição do produto deve ter de 3 a 50 caracteres.")
    return texto


def validar_quantidade(valor, maximo=99):
    """Quantidade de um item da lista (1 a 99). Só multiplica na totalização; o solver usa o preço unitário."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ValueError("A quantidade deve ser um número inteiro.")
    if not 1 <= n <= maximo:
        raise ValueError(f"A quantidade deve ficar entre 1 e {maximo}.")
    return n


def consultar_paginado(produto, municipio_ibge, dias):
    """POST produto/pesquisa em todas as páginas. `produto` é {'descricao': ...} ou {'gtin': ...}."""
    import requests
    from algorithms.sefaz_api import SEFAZ_SESSION, SEFAZ_BASE_URL

    itens, pagina = [], 1
    while True:
        corpo = {"produto": produto, "estabelecimento": {"municipio": {"codigoIBGE": int(municipio_ibge)}},
                 "dias": int(dias), "pagina": pagina, "registrosPorPagina": REGISTROS_POR_PAGINA}
        try:
            r = SEFAZ_SESSION.post(f"{SEFAZ_BASE_URL}/produto/pesquisa", json=corpo, timeout=120)
        except requests.RequestException as e:
            raise SefazErro(f"Falha ao consultar a SEFAZ: {e}") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("message")
            except ValueError:
                msg = None
            raise SefazErro(msg or f"A SEFAZ respondeu HTTP {r.status_code}.")
        dados = r.json()
        itens += dados.get("conteudo") or []
        if dados.get("ultimaPagina") in (True, "true") or pagina >= int(dados.get("totalPaginas") or 1) or pagina >= MAX_PAGINAS:
            return itens
        pagina += 1


def consultar_cacheado(produto, municipio_ibge, dias):
    """consultar_paginado com cache de 10 min (a SEFAZ leva ~25 s por descrição)."""
    from django.core.cache import cache
    chave = f"lista:sefaz:{int(municipio_ibge)}:{int(dias)}:{sorted(produto.items())}"
    itens = cache.get(chave)
    if itens is None:
        itens = consultar_paginado(produto, municipio_ibge, dias)
        cache.set(chave, itens, timeout=600)
    return itens


# ---------------------------------------------------------------- preços finais
def coordenada_valida(lat, lon):
    """True se (lat, lon) é um ponto utilizável em Alagoas; a SEFAZ devolve 0,0 para mercados sem geolocalização."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return AL_LAT[0] <= lat <= AL_LAT[1] and AL_LON[0] <= lon <= AL_LON[1]


def _linhas_do_gtin(rotulo, gtin, itens):
    chave = _chave_gtin(gtin) if gtin else None      # gtin None: pool de itens vendidos por peso
    validos = [i for i in itens if (chave is None or _chave_gtin(i["produto"].get("gtin")) == chave)
               and i["produto"].get("venda", {}).get("valorVenda")
               and coordenada_valida(i["estabelecimento"].get("endereco", {}).get("latitude"),
                                     i["estabelecimento"].get("endereco", {}).get("longitude"))]
    aceitos = set(filtrar_outliers([float(i["produto"]["venda"]["valorVenda"]) for i in validos]))
    linhas = []
    for i in validos:
        preco, e = float(i["produto"]["venda"]["valorVenda"]), i["estabelecimento"]
        if preco not in aceitos:
            continue
        end = e.get("endereco", {})
        linhas.append({"PRODUTO": rotulo, "VALOR": preco, "CNPJ": e.get("cnpj"),
                       "NOME": e.get("nomeFantasia") or e.get("razaoSocial") or "Mercado",
                       "ENDERECO": end.get("nomeLogradouro", ""), "NUMERO": end.get("numeroImovel", ""),
                       "BAIRRO": end.get("bairro", ""), "MUNICIPIO": end.get("municipio", ""),
                       "LAT": float(end["latitude"]), "LONG": float(end["longitude"]),
                       "CODIGO_BARRAS": gtin or "", "DESCRICAO_ITEM": i["produto"].get("descricao", ""),
                       "DATA_VENDA": i["produto"]["venda"].get("dataVenda")})
    return linhas


def linhas_da_descricao(descricao, itens, consulta=None):
    """Linhas de preço dos itens aceitos para uma descrição (GTINs + itens vendidos por peso), com resumo."""
    aceitos, descartados = selecionar_itens(itens, interpretar_consulta(consulta or descricao))
    linhas, pool_peso = [], []
    for gtin, itens_grupo in aceitos:
        if gtin:
            linhas += _linhas_do_gtin(descricao, gtin, itens_grupo)
        else:
            pool_peso += itens_grupo              # outliers de preço por KG avaliados no conjunto
    por_peso = len(pool_peso)
    if pool_peso:
        linhas += _linhas_do_gtin(descricao, None, pool_peso)
    return linhas, {"descricao": descricao, "total_itens": len(itens), "gtins": len(aceitos) - por_peso,
                    "itens_por_peso": por_peso, "mercados": len({l["CNPJ"] for l in linhas}),
                    "descartados": descartados}


def montar_dataframe(descricoes, municipio_ibge, dias, origem, consultar=consultar_paginado, progresso=None,
                     geocodificar=None):
    """descricoes: ['Café 250g', ...] -> (DataFrame para o otimizador, resumo por descrição).

    O DataFrame é o espaço de decisão do solver: TODAS as ofertas (mercado x produto aceito de cada item da
    lista) com coordenadas válidas. Nenhum corte por preço ou distância: quem decide o que comprar e onde é o solver.
    """
    validar_parametros(municipio_ibge, dias)
    descricoes = [validar_descricao(d) for d in descricoes]

    def buscar(descricao):
        usada = corrigir_consulta(descricao)            # sinônimos e erros de digitação ("bolacha crem" -> "biscoito cream")
        linhas, resumo_item = linhas_da_descricao(descricao, consultar({"descricao": usada}, municipio_ibge, dias), usada)
        resumo_item["consulta_usada"] = usada
        return linhas, resumo_item

    linhas, resumo = [], []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, (l, r) in enumerate(ex.map(buscar, descricoes), 1):
            linhas += l
            resumo.append(r)
            if progresso:
                progresso(n, len(descricoes))
    if not linhas:
        return pd.DataFrame(), resumo
    df, corrigidos, descartados = corrigir_ou_descartar_localizacao(pd.DataFrame(linhas), geocodificar)
    for r in resumo:
        r["localizacao_corrigida"] = len(corrigidos)
        r["localizacao_descartada"] = len(descartados)
    if df.empty:
        return df, resumo
    return _nomes_unicos(df).reset_index(drop=True), resumo


def escolhas_do_solver(compras, df):
    """Associa cada compra do solver à oferta exata (descrição da nota e GTIN) de que veio o preço.

    compras: {'nome do mercado': [{'produto': 'Café 250g', 'preco': 12.38}, ...]} (saída do solver).
    Devolve as mesmas compras com 'item' e 'gtin' preenchidos.
    """
    for mercado, itens in compras.items():
        do_mercado = df[df["MERCADO"] == mercado]
        for compra in itens:
            ofertas = do_mercado[(do_mercado["PRODUTO"] == compra["produto"])
                                 & ((do_mercado["VALOR"] - float(compra["preco"])).abs() < 1e-6)]
            if not ofertas.empty:
                compra["item"] = ofertas.iloc[0]["DESCRICAO_ITEM"]
                compra["gtin"] = ofertas.iloc[0]["CODIGO_BARRAS"]
    return compras


def _localizacoes_inconsistentes(df, max_km, min_mercados):
    """Mercados cuja coordenada está a mais de max_km da mediana do seu bairro (bairros com >= min_mercados)."""
    mercados = df.drop_duplicates("CNPJ")[["CNPJ", "NOME", "BAIRRO", "LAT", "LONG"]].copy()
    mercados["_bairro"] = mercados["BAIRRO"].map(lambda b: " ".join(tokenizar(b)))
    achados = []
    for bairro, grupo in mercados.groupby("_bairro"):
        if not bairro or len(grupo) < min_mercados:
            continue
        centro = (grupo["LAT"].median(), grupo["LONG"].median())
        for r in grupo.itertuples():
            km = geodesic(centro, (r.LAT, r.LONG)).km
            if km > max_km:
                achados.append({"cnpj": r.CNPJ, "nome": r.NOME, "bairro": r.BAIRRO, "km": round(km, 1), "centro": centro})
    return achados


def corrigir_ou_descartar_localizacao(df, geocodificar=None, max_km=MAX_KM_DO_BAIRRO,
                                      min_mercados=MIN_MERCADOS_PARA_VALIDAR_BAIRRO):
    """Trata mercados cuja coordenada não bate com o bairro declarado no próprio cadastro da SEFAZ.

    Ex.: "Lamenha - Benedito Bentes" cadastrada com coordenadas do Centro (a ~20 km): a rota seria desenhada e
    custeada para o lugar errado. Compara cada mercado com a mediana do seu bairro; se estiver a mais de max_km,
    tenta corrigir geocodificando o endereço (`geocodificar(logradouro, numero, bairro, municipio)` -> (lat, lon)
    ou None). O ponto novo só vale se estiver em Alagoas e dentro de max_km do bairro; senão o mercado é descartado.
    Devolve (df, corrigidos, descartados), listas de (nome, bairro, km).
    """
    if df.empty:
        return df, [], []
    corrigidos, descartados, ruins = [], [], set()
    achados = _localizacoes_inconsistentes(df, max_km, min_mercados)
    for a in achados:
        ponto = None
        if geocodificar:
            r = df[df["CNPJ"] == a["cnpj"]].iloc[0]
            ponto = geocodificar(r["ENDERECO"], r["NUMERO"], r["BAIRRO"], r.get("MUNICIPIO", ""))
        if ponto and coordenada_valida(*ponto) and geodesic(a["centro"], ponto).km <= max_km:
            df.loc[df["CNPJ"] == a["cnpj"], ["LAT", "LONG"]] = ponto
            corrigidos.append((a["nome"], a["bairro"], a["km"]))
        else:
            ruins.add(a["cnpj"])
            descartados.append((a["nome"], a["bairro"], a["km"]))
    if corrigidos:
        logger.warning("Localização corrigida pelo endereço: " + "; ".join(f"{n} [{b}] (estava a {km} km)" for n, b, km in corrigidos))
    if descartados:
        logger.warning("Mercados com localização inconsistente com o bairro (descartados): "
                       + "; ".join(f"{n} [{b}] a {km} km" for n, b, km in descartados))
    return df[~df["CNPJ"].isin(ruins)].reset_index(drop=True), corrigidos, descartados


def descartar_localizacao_inconsistente(df, max_km=MAX_KM_DO_BAIRRO, min_mercados=MIN_MERCADOS_PARA_VALIDAR_BAIRRO):
    """Versão sem geocodificação: só descarta. Devolve (df, [(nome, bairro, km)])."""
    df, _, descartados = corrigir_ou_descartar_localizacao(df, None, max_km, min_mercados)
    return df, descartados


def _nomes_unicos(df):
    """O otimizador identifica mercados pelo nome: filiais de uma rede precisam de nomes distintos."""
    df = df.copy()
    nomes = df.drop_duplicates("CNPJ").set_index("CNPJ")
    rotulos, usados = {}, Counter()
    for cnpj, r in nomes.iterrows():
        base = f"{r['NOME']} - {r['BAIRRO']}".strip(" -")
        usados[base] += 1
        rotulos[cnpj] = base if usados[base] == 1 else f"{base} ({usados[base]})"
    df["MERCADO"] = df["CNPJ"].map(rotulos)
    return df


def grafo_viario(df, origem, grade=0.02, passo_km=2.0, minimo_km=4.0, maximo_km=20.0):
    """Centro e raio (km) do grafo viário (OSMnx) que cobre origem e mercados.

    O OSMnx só reaproveita o mapa já baixado quando centro e raio são idênticos; baixar um mapa novo
    pode levar minutos. Por isso o centro é "encaixado" numa grade (~2 km) e o raio sobe em degraus.
    """
    pontos = list(zip(df["LAT"], df["LONG"])) + [origem]
    media = (sum(p[0] for p in pontos) / len(pontos), sum(p[1] for p in pontos) / len(pontos))
    centro = (round(round(media[0] / grade) * grade, 6), round(round(media[1] / grade) * grade, 6))
    preciso = max(geodesic(centro, p).km for p in pontos) + 1.0
    raio = math.ceil(preciso / passo_km) * passo_km
    return centro, min(maximo_km, max(minimo_km, raio))
