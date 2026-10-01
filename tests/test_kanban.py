"""Testes da Fase 3: Kanban do fluxo (colunas, prioridade e selos de risco)."""
import pandas as pd
import pytest

import painel as P
from dados import Premissas, gerar_dia
from simulacao_atual import COLUNAS_AGENDA, simular_atual


@pytest.fixture(scope="module")
def hoje():
    prem = Premissas()
    return prem, simular_atual(gerar_dia(prem), prem)


@pytest.mark.parametrize("t", [7 * 60, 9 * 60 + 30, 11 * 60 + 45, 14 * 60, 17 * 60 + 30])
def test_cada_paciente_em_exatamente_uma_coluna(hoje, t):
    _, ag = hoje
    k = P.kanban(ag, t)
    todos = [c["paciente"] for cartoes in k.values() for c in cartoes]
    assert sorted(todos) == sorted(ag["paciente"])


@pytest.mark.parametrize("t", [8 * 60, 10 * 60, 13 * 60])
def test_colunas_de_poltrona_batem_com_o_mapa(hoje, t):
    prem, ag = hoje
    k = P.kanban(ag, t)
    na_poltrona = len(k["aguardando"]) + len(k["infusao"]) + len(k["alta"])
    estado = P.estado_poltronas(ag, t, prem.n_poltronas)
    assert na_poltrona == int((estado["situacao"] != P.LIVRE).sum())
    assert na_poltrona == P.ocupacao_kanban(ag, t)["poltronas"] <= prem.n_poltronas


def test_remarcado_so_aparece_depois_do_limite(hoje):
    _, ag = hoje
    rem = ag[ag["remarcado"]].iloc[0]
    antes = P.kanban(ag, rem["limite_min"] - 60)
    depois = P.kanban(ag, rem["limite_min"])
    cartao = next(c for c in antes["agendado"] if c["paciente"] == rem["paciente"])
    assert cartao["risco"] == P.EM_RISCO and "horário limite" in cartao["motivo"]
    assert any(c["paciente"] == rem["paciente"] for c in depois["remarcado"])


def _agenda(**extra):
    linha = dict(paciente="PAC-001", perfil="Rápido", protocolo="Gemzar", limite_min=17 * 60,
                 remarcado=False, preparo_min=9, infusao_min=51, chegada=480.0, senta=480.0,
                 liberacao=460.0, inicio_preparo=460.0, fim_preparo=469.0, bolsa_chega=474.0,
                 inicio_infusao=490.0, fim_infusao=541.0, sai=546.0, poltrona=1,
                 posto_capela=1)
    linha.update(extra)
    ag = pd.DataFrame([linha])
    cols = COLUNAS_AGENDA + [c for c in ("interior", "retorno_min", "chegada_transporte")
                             if c in ag.columns]
    return ag[cols]


def test_selos_de_risco_do_interior():
    # Sai 9h06; transporte volta 9h20 (folga de 30 min não cumprida): atenção
    ag = _agenda(interior=True, retorno_min=560.0, chegada_transporte=450.0)
    cartao = P.kanban(ag, 500, folga_transporte=30)["infusao"][0]
    assert cartao["risco"] == P.ATENCAO and "transporte" in cartao["motivo"]
    assert cartao["interior"] and cartao["retorno"] == "09h20"
    # Transporte volta 9h00, antes da saída: em risco
    ag = _agenda(interior=True, retorno_min=540.0, chegada_transporte=450.0)
    assert P.kanban(ag, 500)["infusao"][0]["risco"] == P.EM_RISCO


def test_espera_longa_vai_para_o_topo_da_coluna():
    a = _agenda(paciente="PAC-001", senta=480.0, inicio_infusao=600.0, fim_infusao=651.0,
                sai=656.0)
    b = _agenda(paciente="PAC-002", senta=520.0, inicio_infusao=600.0, fim_infusao=651.0,
                sai=656.0, poltrona=2)
    ag = pd.concat([b, a], ignore_index=True)
    col = P.kanban(ag, 530)["aguardando"]
    assert [c["paciente"] for c in col] == ["PAC-001", "PAC-002"]  # 50 min antes de 10 min
    assert col[0]["risco"] == P.EM_RISCO and col[1]["risco"] == P.NO_PRAZO
