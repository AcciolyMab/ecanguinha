import pytest

from algorithms import sefaz_lista as sl


def item(desc, gtin="7896224813082", preco=9.0, ncm=9012100, cnpj="1", lat=-9.66, lon=-35.72, bairro="CENTRO"):
    return {"produto": {"descricao": desc, "gtin": gtin, "ncm": ncm,
                        "venda": {"valorVenda": preco, "dataVenda": "2026-10-08T10:00:00Z"}},
            "estabelecimento": {"cnpj": cnpj, "razaoSocial": f"MERCADO {cnpj}", "nomeFantasia": f"MERCADO {cnpj}",
                                "endereco": {"nomeLogradouro": "RUA A", "numeroImovel": "1", "bairro": bairro,
                                             "latitude": lat, "longitude": lon}}}


def test_interpretar_consulta():
    c = sl.interpretar_consulta("Café 250g")
    assert c["nucleo"] == "CAFE" and c["qualificadores"] == [] and c["quantidade"] == (250.0, "G", 1)
    c = sl.interpretar_consulta("Leite integral 1,5 L")
    assert c["nucleo"] == "LEITE" and c["qualificadores"] == ["INTEGRAL"] and c["quantidade"] == (1500.0, "ML", 1)
    with pytest.raises(ValueError):
        sl.interpretar_consulta("250g")


@pytest.mark.parametrize("desc,esperado", [
    ("CAFE SANTA CLARA 250G", True), ("Cafe Damare Trad 250", True), ("CAFE 0,25KG", True),
    ("CAFE BOA VIAGEM 20X250G", False), ("CAFE 500G", False), ("CAFE KIMIMO", None)])
def test_quantidade_confere(desc, esperado):
    assert sl.quantidade_confere(desc, (250.0, "G", 1)) is esperado


@pytest.mark.parametrize("desc,esperado", [
    ("CAFE SANTA CLARA 250G", True), ("Cafe Santa Clara 250", True), ("CB ASSAI CAFE 250G", False),
    ("IOGURTE SABOR CAFE 250G", False), ("BEB YOBEN 250G CAFE", False),
    ("BEBIDA YOPRO 15G CAFE EXP BOOST 250G", False), ("PCT CAFE PILAO 250G", True)])
def test_nucleo_confere(desc, esperado):
    assert sl.nucleo_confere(desc, sl.interpretar_consulta("Café 250g")) is esperado


def test_qualificador_aceita_abreviacao_e_plural():
    c = sl.interpretar_consulta("Leite integral 1l")
    assert sl.nucleo_confere("LEITE INT 1L", c) and sl.nucleo_confere("LEITES INTEGRAL 1L", c)
    assert not sl.nucleo_confere("LEITE DESNATADO 1L", c)


@pytest.mark.parametrize("valor,esperado", [("7896224813082", "7896224813082"), ("07896224813082", "7896224813082"),
                                            ("78908901", "78908901"), ("0000078908901", "78908901"),
                                            ("0", None), ("SEM GTIN", None), ("", None), (None, None)])
def test_gtin_canonico(valor, esperado):
    assert sl.gtin_canonico(valor) == esperado


def test_selecionar_descarta_sem_gtin_ruido_e_ncm():
    itens = [item("CAFE SANTA CLARA 250G", cnpj=str(n), preco=9 + n / 10) for n in range(5)]
    itens += [item("CAFE SANTA CLARA 250", gtin="07896224813082", cnpj="9")]            # mesmo GTIN com zero à esquerda
    itens += [item("CAFE KIMIMO 250G", gtin="7896224807098", cnpj=str(n)) for n in range(3)]
    itens += [item("CAFE SANTA CLARA 250G", gtin="0", cnpj="x")]                          # sem GTIN
    itens += [item("CAFE SANTA CLARA 250G", gtin="", cnpj="y")]
    itens += [item("BEB YOBEN 250G CAFE", gtin="7891234567895")]                          # outro produto
    itens += [item("CAFE SOLUVEL TRES 250G", gtin="7890000000017", ncm=21011110)]         # NCM diferente
    itens += [item("CAFE PILAO 250G", gtin="7896089011982", cnpj=str(n)) for n in range(4)]   # + grupos para o voto valer
    itens += [item("CAFE MELITTA 250G", gtin="7891021006071", cnpj=str(n)) for n in range(4)]
    itens += [item("CAFE 3 CORACOES 250G", gtin="7896005800027", cnpj=str(n)) for n in range(4)]
    itens += [item("CAFE MARATA 500G", gtin="7898286200122")]                             # quantidade diferente
    aceitos, desc = sl.selecionar_itens(itens, sl.interpretar_consulta("Café 250g"))
    assert {g for g, _ in aceitos} == {"7896224813082", "7896224807098", "7896089011982", "7891021006071", "7896005800027"}
    assert len(dict(aceitos)["7896224813082"]) == 6
    assert desc["sem código de barras (GTIN)"] == 2
    assert desc["não é o produto pedido"] == 1 and desc["quantidade diferente ou não informada"] == 1
    assert desc["classificação fiscal (NCM) diferente"] == 1


def test_filtrar_outliers():
    assert sl.filtrar_outliers([8, 9, 10, 260]) == [8, 9, 10]
    assert sl.filtrar_outliers([5, 500]) == [5, 500]          # amostra pequena: mantém
    assert sl.filtrar_outliers([0, -1, 9, 10, 11]) == [9, 10, 11]


def test_validacoes():
    with pytest.raises(ValueError):
        sl.validar_parametros(1234567, 3)
    with pytest.raises(ValueError):
        sl.validar_parametros(2704302, 11)
    with pytest.raises(ValueError):
        sl.validar_descricao("ab")
    with pytest.raises(ValueError):
        sl.validar_descricao("x" * 51)
    assert sl.validar_descricao("  café   250g ") == "café 250g"


def sefaz_falsa(chamadas=None):
    """Simula a SEFAZ: só responde a pesquisas por `descricao`."""
    def consultar(produto, municipio, dias):
        assert list(produto) == ["descricao"]
        if chamadas is not None:
            chamadas.append((produto, municipio, dias))
        if produto["descricao"].startswith("Café"):
            return [item("CAFE SC 250G", gtin="7896224813082", cnpj="1", preco=10, lat=-9.66, lon=-35.72),
                    item("CAFE SC 250G", gtin="7896224813082", cnpj="1", preco=8, lat=-9.66, lon=-35.72),    # menor do mercado 1
                    item("CAFE SC 250G", gtin="7896224813082", cnpj="2", preco=9, lat=-9.67, lon=-35.73),
                    item("CAFE SC 250G", gtin="7896224813082", cnpj="3", preco=9.5, lat=-9.60, lon=-35.60, bairro="TABULEIRO"),  # longe
                    item("CAFE SC 250G", gtin="7896224813082", cnpj="4", preco=290, lat=-9.661, lon=-35.721),  # outlier
                    item("CAFE KIMIMO 250G", gtin="7896224807098", cnpj="2", preco=7, lat=-9.67, lon=-35.73),
                    item("CAFE KIMIMO 250G", gtin="7896224807098", cnpj="3", preco=6, lat=-9.60, lon=-35.60, bairro="TABULEIRO"),
                    item("IOGURTE SABOR CAFE 250G", gtin="7891111111116", cnpj="1", preco=1),                # ruído
                    item("CAFE SEM CODIGO 250G", gtin="0", cnpj="1", preco=1)]                              # sem GTIN
        return [item("LEITE INTEGRAL 1L", gtin="7898387120380", cnpj="2", preco=5, lat=-9.67, lon=-35.73)]
    return consultar


def test_montar_dataframe_entrega_todas_as_ofertas_ao_solver():
    chamadas = []
    df, resumo = sl.montar_dataframe(["Café 250g", "Leite integral 1l"], 2704302, 7, (-9.66, -35.72),
                                     consultar=sefaz_falsa(chamadas))
    assert sorted(c[0]["descricao"] for c in chamadas) == ["Café 250g", "Leite integral 1l"]
    assert {c[1:] for c in chamadas} == {(2704302, 7)}
    # nenhum corte por preço ou distância: todos os mercados (inclusive o "longe", cnpj 3) e todas as marcas/preços
    assert set(df["CNPJ"]) == {"1", "2", "3"}
    cafe = df[df["PRODUTO"] == "Café 250g"]
    assert sorted(cafe[cafe["CNPJ"] == "1"]["VALOR"]) == [8, 10]            # as duas ofertas do mesmo mercado seguem
    assert 290 not in set(df["VALOR"])                                      # erro grosseiro de nota (R$ 290) sai
    assert df.groupby("MERCADO")["CNPJ"].nunique().max() == 1
    assert not df["DESCRICAO_ITEM"].str.contains("IOGURTE").any()           # ruído de descrição não entra
    r = {x["descricao"]: x for x in resumo}["Café 250g"]
    assert r["gtins"] == 2 and r["descartados"]["sem código de barras (GTIN)"] == 1


def test_montar_dataframe_sem_resultado_devolve_vazio():
    df, resumo = sl.montar_dataframe(["Café 250g"], 2704302, 7, (-9.66, -35.72), consultar=lambda *a: [])
    assert df.empty and resumo[0]["gtins"] == 0


def test_nomes_unicos_para_filiais():
    df = sl.pd.DataFrame([{"CNPJ": "1", "NOME": "REDE", "BAIRRO": "CENTRO"}, {"CNPJ": "2", "NOME": "REDE", "BAIRRO": "CENTRO"}])
    assert sl._nomes_unicos(df)["MERCADO"].tolist() == ["REDE - CENTRO", "REDE - CENTRO (2)"]


def test_grafo_viario_cobre_pontos_e_reaproveita_cache():
    origem = (-9.66, -35.72)
    df = sl.pd.DataFrame({"LAT": [-9.66, -9.55], "LONG": [-35.72, -35.60]})
    centro, raio = sl.grafo_viario(df, origem)
    assert 4.0 <= raio <= 20.0 and raio % 2 == 0
    assert all(sl.geodesic(centro, p).km <= raio for p in [(-9.66, -35.72), (-9.55, -35.60)])
    # busca parecida (mercados ligeiramente diferentes) cai no mesmo centro e raio -> mesmo mapa em cache
    df2 = sl.pd.DataFrame({"LAT": [-9.66, -9.552], "LONG": [-35.72, -35.601]})
    assert sl.grafo_viario(df2, origem) == (centro, raio)


def test_sem_mapa_viario_estima_distancias_em_linha_reta(monkeypatch):
    from algorithms import tpplib_data as tp
    monkeypatch.setattr(tp, "_mapa_local_cobre", lambda pontos: None)             # sem mapa local
    monkeypatch.setattr(tp, "_grafo_com_fallback", lambda centro, raio_m: None)   # nenhum Overpass responde
    df = sl.pd.DataFrame([
        {"PRODUTO": "Café", "VALOR": 10.0, "MERCADO": "A", "ENDERECO": "R1", "LAT": -9.66, "LONG": -35.72},
        {"PRODUTO": "Café", "VALOR": 9.0, "MERCADO": "B", "ENDERECO": "R2", "LAT": -9.64, "LONG": -35.70}])
    data = tp.create_tpplib_data(df, -9.65, -35.71, media_preco=6.0, raio_busca=4.0)
    assert data["distancias_aproximadas"] is True
    d = data["distancias_km"]
    assert d[0][0] == 0 and d[0][1] > 0 and d[0][1] == d[1][0]
    assert abs(data["custos_viagem"][0][1] - d[0][1] * 6.0 / 9.5) < 1e-9


def test_overpass_pula_servidor_que_acabou_de_falhar(monkeypatch):
    from algorithms import tpplib_data as tp
    tentativas = []

    def falso(centro, dist, network_type):
        tentativas.append(tp.ox.settings.overpass_url)
        raise ConnectionError("fora do ar")

    monkeypatch.setattr(tp.ox, "graph_from_point", falso)
    monkeypatch.setattr(tp, "_overpass_falhas", {})
    assert tp._grafo_com_fallback((0, 0), 1000) is None
    assert len(tentativas) == len(tp.OVERPASS_URLS)
    assert tp._grafo_com_fallback((0, 0), 1000) is None      # todos em pausa: nem tenta de novo
    assert len(tentativas) == len(tp.OVERPASS_URLS)


def test_custo_deslocamento_sem_penalidades():
    from algorithms.custos import custo_deslocamento
    assert custo_deslocamento(31.23, 6.69) == 21.99          # 31,23 km x (6,69 / 9,5)
    assert custo_deslocamento(0, 6.69) == 0 and custo_deslocamento(None, None) == 0


def test_mapa_local_so_e_usado_quando_cobre_todos_os_pontos(tmp_path, monkeypatch):
    import networkx as nx
    from algorithms import tpplib_data as tp
    G = nx.MultiDiGraph(crs="EPSG:4326")
    G.add_node(1, x=-35.74, y=-9.66)
    G.add_node(2, x=-35.70, y=-9.62)
    G.add_edge(1, 2, length=5000.0)
    arquivo = tmp_path / "mapa.graphml"
    tp.ox.save_graphml(G, arquivo)
    monkeypatch.setattr(tp, "ARQUIVO_MAPA", arquivo)
    monkeypatch.setattr(tp, "_mapa_local", None)
    monkeypatch.setattr(tp, "_mapa_local_tentado", False)
    assert tp._mapa_local_cobre([(-9.65, -35.72), (-9.63, -35.71)]) is not None   # dentro do mapa
    assert tp._mapa_local_cobre([(-9.65, -35.72), (-9.40, -35.72)]) is None       # um ponto fora: cai no Overpass


def test_sem_arquivo_de_mapa_usa_o_fluxo_antigo(tmp_path, monkeypatch):
    from algorithms import tpplib_data as tp
    monkeypatch.setattr(tp, "ARQUIVO_MAPA", tmp_path / "nao_existe.graphml")
    monkeypatch.setattr(tp, "_mapa_local", None)
    monkeypatch.setattr(tp, "_mapa_local_tentado", False)
    assert tp._mapa_local_cobre([(-9.65, -35.72)]) is None


def test_voto_de_ncm_nao_decide_com_poucos_grupos():
    # carne moída: cada nota traz um NCM diferente (e errado); com 4 GTINs nenhum deve ser descartado por NCM
    itens = [item("CARNE MOIDA DE SEGUNDA 1KG", gtin="2001984002385", ncm=16010000, cnpj="1"),
             item("CARNE MOIDA CONGELADA 1KG", gtin="7898951859012", ncm=2062990, cnpj="2"),
             item("CARNE MOIDA CONGELADA PUMBA 1KG", gtin="637850035113", ncm=2023000, cnpj="3"),
             item("CARNE MOIDA BOV 1KG", gtin="7899566301583", ncm=11081200, cnpj="4")]
    aceitos, desc = sl.selecionar_itens(itens, sl.interpretar_consulta("Carne Moida 1kg"))
    assert len(aceitos) == 4 and "classificação fiscal (NCM) diferente" not in desc


def test_capitulo_ncm_aceita_inteiro_sem_zero_a_esquerda():
    assert sl._capitulo_ncm(2062990) == "02" and sl._capitulo_ncm("09012100") == "09" and sl._capitulo_ncm(None) == "00"


def test_escolhas_do_solver_mostra_o_produto_exato():
    df = sl.pd.DataFrame([
        {"MERCADO": "A - CENTRO", "PRODUTO": "Café 250g", "VALOR": 12.38, "DESCRICAO_ITEM": "CAFE SANTA CLARA 250G", "CODIGO_BARRAS": "7896224813082"},
        {"MERCADO": "A - CENTRO", "PRODUTO": "Café 250g", "VALOR": 9.99, "DESCRICAO_ITEM": "CAFE KIMIMO 250G", "CODIGO_BARRAS": "7896224807098"},
        {"MERCADO": "A - CENTRO", "PRODUTO": "Arroz 5kg", "VALOR": 17.98, "DESCRICAO_ITEM": "ARROZ CAMIL 5KG", "CODIGO_BARRAS": "7896006716112"}])
    compras = {"A - CENTRO": [{"produto": "Café 250g", "preco": 9.99}, {"produto": "Arroz 5kg", "preco": 17.98}]}
    out = sl.escolhas_do_solver(compras, df)
    assert out["A - CENTRO"][0]["item"] == "CAFE KIMIMO 250G"            # o produto cujo preço o solver usou
    assert out["A - CENTRO"][1]["gtin"] == "7896006716112"


@pytest.mark.parametrize("lat,lon,esperado", [(-9.66, -35.72, True), (0.0, 0.0, False), (None, -35.7, False),
                                              ("x", "y", False), (-23.5, -46.6, False)])
def test_coordenada_valida(lat, lon, esperado):
    assert sl.coordenada_valida(lat, lon) is esperado


def test_mercado_sem_geolocalizacao_nao_entra_mesmo_sendo_o_mais_barato():
    def falso(produto, municipio, dias):
        return [item("CAFE X 250G", gtin="7896224813082", cnpj="ok1", preco=12, lat=-9.66, lon=-35.72),
                item("CAFE X 250G", gtin="7896224813082", cnpj="ok2", preco=13, lat=-9.67, lon=-35.73),
                item("CAFE X 250G", gtin="7896224813082", cnpj="ok3", preco=11, lat=-9.65, lon=-35.71),
                item("CAFE X 250G", gtin="7896224813082", cnpj="sem-geo", preco=10, lat=0.0, lon=0.0)]

    df, _ = sl.montar_dataframe(["Café 250g"], 2704302, 7, (-9.66, -35.72), consultar=falso)
    assert set(df["CNPJ"]) == {"ok1", "ok2", "ok3"}


def test_exclui_produto_de_uso_animal_quando_a_consulta_nao_pede():
    c = sl.interpretar_consulta("Arroz 5kg")
    assert not sl.nucleo_confere("ARROZ P ANIMAIS AMI 5KG", c)
    assert not sl.nucleo_confere("ARROZ RACAO PET 5KG", c)
    assert not sl.nucleo_confere("ARROZ;P CAO MATILHA 5KG", c)
    assert sl.nucleo_confere("ARROZ CAMIL TIPO 1 5KG", c)
    assert sl.nucleo_confere("RACAO PET 5KG", sl.interpretar_consulta("Racao pet 5kg"))   # a consulta pede ração


def test_modelo_do_solver_usa_a_melhor_oferta_do_mercado_para_cada_item(monkeypatch):
    from algorithms import tpplib_data as tp
    df = sl.pd.DataFrame([
        {"PRODUTO": "Café", "VALOR": 12.0, "MERCADO": "A", "ENDERECO": "R1", "LAT": -9.66, "LONG": -35.72},
        {"PRODUTO": "Café", "VALOR": 9.0, "MERCADO": "A", "ENDERECO": "R1", "LAT": -9.66, "LONG": -35.72},   # outra marca, mesmo mercado
        {"PRODUTO": "Café", "VALOR": 10.0, "MERCADO": "B", "ENDERECO": "R2", "LAT": -9.64, "LONG": -35.70}])
    monkeypatch.setattr(tp, "_mapa_local_cobre", lambda pontos: None)
    monkeypatch.setattr(tp, "_grafo_com_fallback", lambda centro, raio_m: None)
    data = tp.create_tpplib_data(df, -9.65, -35.71, media_preco=6.0, raio_busca=4.0)
    precos = sorted(data["pik"].values())
    assert precos == [9.0, 10.0]


def test_penalidade_big_m_supera_qualquer_economia_possivel():
    from algorithms.alns_solver import penalidade_da_instancia
    # produtos 1 e 2: maiores preços 10 e 6 (soma 16); idas e voltas ao depósito (índice 0): 2, 4 e 6 -> maior 6
    pik = {(1, 1): 10.0, (2, 1): 4.0, (1, 2): 6.0, (3, 2): 5.0}
    custos = [[0, 1, 2, 3], [1, 0, 9, 9], [2, 9, 0, 9], [3, 9, 9, 0]]
    assert penalidade_da_instancia(pik, custos, 0, 1.0) == 22.0        # 16 + 6
    assert penalidade_da_instancia(pik, custos, 0, 2.0) == 44.0        # fator multiplica
    inf = float("inf")
    assert penalidade_da_instancia(pik, [[0, inf], [inf, 0]], 0, 1.0) == 16.0   # sem trechos viáveis: só os preços


def test_descarta_mercado_com_coordenada_fora_do_seu_bairro():
    # Benedito Bentes fica ~20 km ao norte do Centro; a Lamenha tem bairro "BENEDITO BENTES" mas coordenadas do Centro
    linhas = []
    for n in range(4):
        linhas.append({"CNPJ": f"bb{n}", "NOME": f"MERCADO BB {n}", "BAIRRO": "BENEDITO BENTES", "LAT": -9.55 - n * 0.002, "LONG": -35.73})
    linhas.append({"CNPJ": "lamenha", "NOME": "LAMENHA", "BAIRRO": "BENEDITO BENTES", "LAT": -9.669, "LONG": -35.737})
    for n in range(3):
        linhas.append({"CNPJ": f"c{n}", "NOME": f"CENTRO {n}", "BAIRRO": "Centro", "LAT": -9.667 + n * 0.001, "LONG": -35.735})
    linhas.append({"CNPJ": "solo", "NOME": "SOZINHO", "BAIRRO": "Bairro Raro", "LAT": -9.40, "LONG": -35.60})   # amostra pequena: não valida
    df = sl.pd.DataFrame(linhas)
    ok, descartados = sl.descartar_localizacao_inconsistente(df)
    assert [d[0] for d in descartados] == ["LAMENHA"] and descartados[0][2] > 10
    assert set(ok["CNPJ"]) == {"bb0", "bb1", "bb2", "bb3", "c0", "c1", "c2", "solo"}


def test_sem_mercados_inconsistentes_nao_altera_nada():
    df = sl.pd.DataFrame([{"CNPJ": str(n), "NOME": f"M{n}", "BAIRRO": "FAROL", "LAT": -9.65, "LONG": -35.73} for n in range(4)])
    ok, descartados = sl.descartar_localizacao_inconsistente(df)
    assert descartados == [] and len(ok) == 4


def _df_lamenha():
    linhas = [{"CNPJ": f"bb{n}", "NOME": f"MERCADO BB {n}", "BAIRRO": "BENEDITO BENTES", "ENDERECO": "R", "NUMERO": "1",
               "MUNICIPIO": "MACEIO", "LAT": -9.55 - n * 0.002, "LONG": -35.73, "VALOR": 5.0} for n in range(4)]
    linhas.append({"CNPJ": "lamenha", "NOME": "LAMENHA", "BAIRRO": "BENEDITO BENTES", "ENDERECO": "AV ARTHUR VALENTE JUCA",
                   "NUMERO": "269", "MUNICIPIO": "MACEIO", "LAT": -9.669, "LONG": -35.737, "VALOR": 4.0})
    return sl.pd.DataFrame(linhas)


def test_localizacao_inconsistente_e_corrigida_pelo_endereco():
    chamadas = []

    def geocodificar(logradouro, numero, bairro, municipio):
        chamadas.append((logradouro, numero, bairro, municipio))
        return (-9.5565, -35.7301)                      # de fato em Benedito Bentes

    df, corrigidos, descartados = sl.corrigir_ou_descartar_localizacao(_df_lamenha(), geocodificar)
    assert chamadas == [("AV ARTHUR VALENTE JUCA", "269", "BENEDITO BENTES", "MACEIO")]
    assert [c[0] for c in corrigidos] == ["LAMENHA"] and descartados == []
    lam = df[df["CNPJ"] == "lamenha"].iloc[0]
    assert (lam["LAT"], lam["LONG"]) == (-9.5565, -35.7301)               # coordenada corrigida entra na busca


@pytest.mark.parametrize("resultado", [None, (-9.669, -35.737), (0.0, 0.0), (-23.5, -46.6)])
def test_localizacao_que_nao_se_corrige_e_descartada(resultado):
    df, corrigidos, descartados = sl.corrigir_ou_descartar_localizacao(_df_lamenha(), lambda *a: resultado)
    assert corrigidos == [] and [d[0] for d in descartados] == ["LAMENHA"]
    assert "lamenha" not in set(df["CNPJ"])


def test_todos_os_mercados_inconsistentes_sao_geocodificados_sem_limite():
    linhas = [{"CNPJ": f"bb{n}", "NOME": f"BB{n}", "BAIRRO": "BENEDITO BENTES", "ENDERECO": "R", "NUMERO": "1",
               "MUNICIPIO": "M", "LAT": -9.55, "LONG": -35.73, "VALOR": 5.0} for n in range(40)]
    linhas += [{"CNPJ": f"x{n}", "NOME": f"X{n}", "BAIRRO": "BENEDITO BENTES", "ENDERECO": "R", "NUMERO": "1",
                "MUNICIPIO": "M", "LAT": -9.67, "LONG": -35.73, "VALOR": 5.0} for n in range(30)]    # 30 inconsistentes
    chamadas = []
    sl.corrigir_ou_descartar_localizacao(sl.pd.DataFrame(linhas), lambda *a: chamadas.append(a))
    assert len(chamadas) == 30                         # nenhum teto: todos são geocodificados


def test_nominatim_respeita_intervalo_de_2s_entre_consultas(monkeypatch):
    from algorithms import geocodificacao as g
    respostas = iter([False, False, True])            # chave de "vez" ainda ocupada duas vezes

    class CacheFalso:
        def add(self, chave, valor, timeout):
            assert chave == "nominatim:vez" and timeout == 2          # janela de 2 s
            return next(respostas)

    esperas = []
    monkeypatch.setattr(g, "_cache", lambda: CacheFalso())
    monkeypatch.setattr(g.time, "sleep", esperas.append)
    g._aguardar_vez()
    assert len(esperas) == 2                          # esperou enquanto outra consulta estava dentro da janela


def test_geocodificar_endereco_usa_cache_e_tenta_sem_numero(monkeypatch):
    from algorithms import geocodificacao as g
    guardado, consultas = {}, []

    class CacheFalso:
        def get(self, k): return guardado.get(k)
        def set(self, k, v, timeout): guardado[k] = v

    def buscar(consulta):
        consultas.append(consulta)
        return (-9.55, -35.73) if "269" not in consulta else None      # só a consulta sem número acha

    monkeypatch.setattr(g, "_cache", lambda: CacheFalso())
    monkeypatch.setattr(g, "_buscar", buscar)
    assert g.geocodificar_endereco("AV ARTHUR VALENTE JUCA", "269", "BENEDITO BENTES", "MACEIO") == (-9.55, -35.73)
    assert len(consultas) == 2 and "269" in consultas[0] and "269" not in consultas[1]
    assert g.geocodificar_endereco("AV ARTHUR VALENTE JUCA", "269", "BENEDITO BENTES", "MACEIO") == (-9.55, -35.73)
    assert len(consultas) == 2                          # 2ª chamada veio do cache, sem nova consulta


def test_multistart_prefere_sem_violacao_e_depois_o_menor_custo_real(monkeypatch):
    from algorithms import alns_solver as al
    # cada execução: (compras por mercado, distância km). Combustível R$ 9,50/l e 9,5 km/l -> R$ 1,00 por km
    execucoes = iter([
        ({"A": [{"preco": 5}, {"preco": 5}]}, 1.0),                                               # 2 itens (<3): viola, real 11
        ({"A": [{"preco": 5}] * 3, "B": [{"preco": 5}] * 3}, 4.0),                                # sem violação, real 34
        ({"A": [{"preco": 5}] * 3, "B": [{"preco": 4}] * 3}, 4.0),                                # sem violação, real 31 (melhor)
        ({"A": [{"preco": 1}]}, 0.5),                                                             # viola muito, mais barata
    ])

    def falso(data, max_iterations, no_improve_limit, session_key=None, task_id=None, config=None):
        compras, km = next(execucoes)
        return {"purchases": compras, "total_distance": km, "total_cost": 999}

    monkeypatch.setattr(al, "alns_solve_tpp", falso)
    r = al.alns_solve_tpp_multistart({"media_preco_combustivel": 9.5}, 100, 10, reinicios=4)
    assert r["purchases"] == {"A": [{"preco": 5}] * 3, "B": [{"preco": 4}] * 3}


def test_multistart_ignora_execucoes_sem_solucao(monkeypatch):
    from algorithms import alns_solver as al
    monkeypatch.setattr(al, "alns_solve_tpp", lambda *a, **k: (None, None, None))
    assert al.alns_solve_tpp_multistart({"media_preco_combustivel": 6.0}, 100, 10, reinicios=3) is None


def peso(desc, preco=50.0, ncm=2013000, cnpj="1", unidade="KG", lat=-9.66, lon=-35.72):
    it = item(desc, gtin="0", preco=preco, ncm=ncm, cnpj=cnpj, lat=lat, lon=lon)
    it["produto"]["unidadeMedida"] = unidade
    return it


def test_item_sem_gtin_vendido_por_peso_entra_e_embalado_sem_gtin_nao():
    consulta = sl.interpretar_consulta("Patinho Kg")
    itens = [peso("CARNE PATINHO KG", cnpj="a"), peso("CARNE BOV PATINHO KG", cnpj="b", unidade="KG0001"),
             peso("BV PATINHO KG", cnpj="c", unidade="KG9"), peso("PATINHO", cnpj="d"), peso("PATINHO BOVINO", cnpj="e"),
             peso("CARNE PATINHO", cnpj="f", unidade="UN")]                       # sem GTIN e não é por peso
    aceitos, desc = sl.selecionar_itens(itens, consulta)
    assert len(aceitos) == 5 and all(g is None for g, _ in aceitos)
    assert desc["sem código de barras (GTIN)"] == 1


def test_cortes_e_derivados_do_patinho_nao_se_confundem_com_a_carne():
    consulta = sl.interpretar_consulta("Patinho")
    for ruim in ["OSSO DE PATINHO KG", "OSSO DO PATINHO", "HAMBURGUER PATINHO", "STROGONOFF PATINHO kg",
                 "CS PATINHO SUINO KG", "CARNE DE SOL DE PATINHO"]:
        assert not sl.nucleo_confere(ruim, consulta), ruim
    for bom in ["PATINHO KG", "CARNE PATINHO KG", "CARNE BOV PATINHO KG", "BV PATINHO KG", "BIFE DE PATINHO kg.",
                "PATINHO BOVINO", "CARNE PATINHO BIFE KG"]:
        assert sl.nucleo_confere(bom, consulta), bom


def test_unidade_solta_nao_vira_qualificador():
    assert sl.interpretar_consulta("Patinho Kg")["qualificadores"] == []
    assert sl.interpretar_consulta("Patinho")["nucleo"] == "PATINHO"


def test_por_peso_ncm_errado_e_descartado_pelo_voto():
    itens = [peso("CARNE PATINHO KG", cnpj=str(n)) for n in range(6)]
    itens.append(peso("CARNE PATINHO", cnpj="madeira", ncm=44129900))              # NCM de madeira (erro de nota)
    aceitos, desc = sl.selecionar_itens(itens, sl.interpretar_consulta("Patinho"))
    assert len(aceitos) == 6 and desc["classificação fiscal (NCM) diferente"] == 1


def test_linhas_do_patinho_por_peso_sem_gtin_chegam_ao_solver():
    itens = [peso("CARNE PATINHO KG", cnpj=str(n), preco=45 + n) for n in range(5)]
    itens.append(peso("PATINHO KG", cnpj="outlier", preco=900.0))                      # erro grosseiro de preço
    linhas, resumo = sl.linhas_da_descricao("Patinho", itens)
    assert {l["CNPJ"] for l in linhas} == {"0", "1", "2", "3", "4"} and all(l["CODIGO_BARRAS"] == "" for l in linhas)
    assert resumo["itens_por_peso"] == 6 and resumo["mercados"] == 5


@pytest.mark.parametrize("entrada,esperado", [
    ("mateiga", "manteiga"), ("bicoito bono", "biscoito bono"), ("bolacha crem cracker", "biscoito cream cracker"),
    ("Cafe 250g", "Cafe 250g"), ("coca cola 2l", "coca cola 2l"), ("tio joao 5kg", "tio joao 5kg"),
    ("manteiga galbani 200g", "manteiga galbani 200g"), ("acucar cristal 1kg", "acucar cristal 1kg"), ("Patinho", "Patinho"),
])
def test_corrigir_consulta(entrada, esperado):
    assert sl.corrigir_consulta(entrada) == esperado


def test_nucleo_aceita_abreviacao_por_prefixo():
    c = sl.interpretar_consulta("biscoito bono")
    assert sl.nucleo_confere("BISC BONO MORANGO 90G", c) and sl.nucleo_confere("BONO", c) is False
    assert sl.nucleo_confere("ARR TIO URBANO 5kg", sl.interpretar_consulta("Arroz 5kg"))
    assert not sl.nucleo_confere("CARNE MOIDA 500G", sl.interpretar_consulta("Arroz 5kg"))


@pytest.mark.parametrize("valor,esperado", [(1, 1), ("3", 3), (99, 99), (2.0, 2)])
def test_validar_quantidade_aceita(valor, esperado):
    assert sl.validar_quantidade(valor) == esperado


@pytest.mark.parametrize("valor", [0, -1, 100, "abc", None, ""])
def test_validar_quantidade_rejeita(valor):
    with pytest.raises(ValueError):
        sl.validar_quantidade(valor)


def test_totalizacao_multiplica_preco_pela_quantidade_so_na_exibicao():
    pytest.importorskip("django")
    from ecanguinha.templatetags.custom_filters import multiplicar, sum_precos
    compras = [{"produto": "Café 250g", "preco": 10.0, "quantidade": 3},
               {"produto": "Leite 1l", "preco": 5.0}]                       # sem quantidade (busca antiga): vale 1
    assert sum_precos(compras) == 35.0
    assert multiplicar(10.0, 3) == 30.0 and multiplicar("x", 3) == 0
