"""Garante que nenhuma chave de API (ex.: AppToken da SEFAZ) fique escrita no código."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTAS = ["algorithms", "ecanguinha", "canguinaProject", "scripts"]
# literal de 40 hexadecimais entre aspas (formato do token da SEFAZ)
TOKEN_FIXO = re.compile(r"""["'][0-9a-f]{40}["']""")


def test_nenhum_token_fixo_no_codigo():
    achados = []
    for pasta in PASTAS:
        for arq in (RAIZ / pasta).rglob("*.py"):
            if "tests" in arq.parts:
                continue
            for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
                if TOKEN_FIXO.search(linha):
                    achados.append(f"{arq.relative_to(RAIZ)}:{n}")
    assert not achados, f"token/chave fixa no código (use variável de ambiente): {achados}"


def test_sefaz_api_le_a_chave_do_ambiente():
    fonte = (RAIZ / "algorithms" / "sefaz_api.py").read_text(encoding="utf-8")
    assert 'os.environ.get("SEFAZ_API_KEY"' in fonte
    assert '"AppToken": SEFAZ_API_KEY' in fonte
