Canguinha


## Buscas (página inicial, duas abas)

- **Busca por lista (padrão):** o usuário escolhe o município de Alagoas, informa CEP/endereço (ponto de partida) e monta uma lista de descrições ("Café 250g"). Para cada item o app consulta a SEFAZ por `descricao` + município, descarta itens sem GTIN, filtra ruído (núcleo da descrição, quantidade, NCM dominante) e agrupa por GTIN; o usuário escolhe as marcas. A busca final usa os GTINs escolhidos, remove preços outliers, limita a 30 mercados mais próximos e roda o otimizador de rota. Código: `algorithms/sefaz_lista.py`, `buscar_lista_task` em `ecanguinha/tasks.py`, rotas `api/lista/*`.
- **Busca por CEP (produtos selecionados):** a busca original por raio e cesta básica fixa.

Regras da API (manual v1.0): um só critério de produto (`gtin` ou `descricao`) e de estabelecimento (`municipio`, `geolocalizacao` ou `individual`), `dias` de 1 a 10, `registrosPorPagina` de 50 a 5000, `codigoIBGE` numérico. Testes: `python -m pytest ecanguinha/tests/test_sefaz_lista.py`.

## Mapa viário local (rotas rápidas)

As distâncias entre mercados usam o mapa de ruas do OpenStreetMap. Para não baixá-lo do Overpass a cada busca (lento e instável), gere-o **uma vez**:

```bash
docker compose exec web python scripts/baixar_mapa.py
```

Gera `data/mapas/maceio_metro.graphml` (Maceió, Rio Largo, Satuba, Marechal Deodoro, Coqueiro Seco, Santa Luzia do Norte, Pilar, Barra de São Miguel; ~28 MB, fora do git) e é retomável. Se o arquivo existir e cobrir todos os pontos da busca, ele é usado (carrega em ~2 s por processo); caso contrário o app baixa o mapa do Overpass (servidores em `OVERPASS_URLS`) e, se nenhum responder, estima as distâncias em linha reta. Em deploy, gere o arquivo no servidor ou copie-o junto com o código; o caminho pode ser trocado por `MAPA_VIARIO_PATH`.
