"""
Recarrega os módulos do Sinfonia que mudaram no disco.

Por que existe: no Streamlit Cloud, depois de um `git push`, o servidor às vezes roda o
app.py novo com módulos antigos ainda na memória (ex.: painel.py da versão anterior), e o
app quebra com erros como TypeError ou KeyError. Este módulo é importado ANTES dos outros
no app.py e, se algum arquivo mudou, recarrega todos na ordem das dependências.
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
# Ordem das dependências: quem importa vem depois de quem é importado
MODULOS = ["dados", "simulacao_atual", "otimizador", "indicadores", "ganhos", "ocorrencias",
           "painel", "ui_componentes"]

_versoes: dict[str, str] = {}  # impressão digital de cada arquivo na última checagem


def _impressao(nome: str) -> str:
    return hashlib.sha256((PASTA / f"{nome}.py").read_bytes()).hexdigest()


def atualizar() -> list[str]:
    """Recarrega os módulos se algum arquivo mudou. Devolve os nomes recarregados.

    Na primeira chamada do processo (ou depois que este arquivo é novo), recarrega os que
    já estavam na memória, porque não dá para saber de que versão eles são.
    """
    atuais = {nome: _impressao(nome) for nome in MODULOS}
    primeira_vez = not _versoes
    mudou = primeira_vez or any(_versoes.get(n) != h for n, h in atuais.items())
    recarregados = []
    if mudou:
        for nome in MODULOS:  # todos, na ordem: quem depende de um módulo novo também muda
            if nome in sys.modules:
                importlib.reload(sys.modules[nome])
                recarregados.append(nome)
    _versoes.clear()
    _versoes.update(atuais)
    return recarregados
