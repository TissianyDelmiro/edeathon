"""Testes da Fase 0: alertas novos viram notificação no canto, uma única vez."""
from datetime import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

import painel as P
from dados import Premissas, gerar_dia
from simulacao_atual import simular_atual
from ui_componentes import MAX_NOTIFICACOES, NOTIFICACAO

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_todo_alerta_tem_id_unico_e_notificacao_definida():
    prem = Premissas()
    hoje = simular_atual(gerar_dia(prem), prem)
    for t in range(prem.inicio_turno, prem.fim_turno, 30):
        lista = P.alertas(hoje, t)
        ids = [a["id"] for a in lista]
        assert len(ids) == len(set(ids))
        assert all(a["tipo"] in NOTIFICACAO for a in lista)


def _app_no_cenario_de_hoje(hora):
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    next(r for r in at.radio if r.label == "Qual agenda mostrar?").set_value(
        "Como é hoje (simulação)")
    at.slider[0].set_value(hora).run()
    assert not at.exception, at.exception
    return at


def test_alerta_novo_vira_notificacao_uma_unica_vez():
    at = _app_no_cenario_de_hoje(time(12, 30))
    lista_vistos = at.session_state["alertas_vistos"]
    vistos = set().union(*lista_vistos.values())
    assert vistos, "às 12h30 do cenário de hoje há alertas (ex.: remarcados)"
    primeira = [t.value for t in at.toast]
    assert primeira, "os alertas novos devem aparecer como notificação"
    # No máximo 3 notificações de alerta + 1 aviso de "+ N alertas"
    assert len(primeira) <= MAX_NOTIFICACOES + 1
    # Nada mudou: rodar de novo não repete as notificações
    at.run()
    assert not at.exception
    assert [t.value for t in at.toast] == []


def test_central_de_alertas_guarda_todos():
    at = _app_no_cenario_de_hoje(time(12, 30))
    titulos = " ".join(h.value for h in at.subheader)
    assert "Central de alertas" in titulos
    assert any(e.label.startswith("Ver os ") for e in at.expander)


def test_texto_curto_cabe_na_notificacao():
    prem = Premissas()
    hoje = simular_atual(gerar_dia(prem), prem)
    for t in range(prem.inicio_turno, prem.fim_turno, 15):
        for a in P.alertas(hoje, t):
            assert len(a["curto"]) <= 60, a["curto"]
            assert not a["curto"].startswith(("+", "-", "*")), a["curto"]
