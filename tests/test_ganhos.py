"""Testes da aba "O que melhorou": ganhos por paciente, meta de espera e ociosidade."""
import numpy as np
import pandas as pd
import pytest

import ganhos as G
from dados import Premissas
from indicadores import ociosidade_por_hora
from simulacao_atual import COLUNAS_AGENDA


def _agenda(linhas, remarcado=()):
    """linhas: paciente, perfil, chegada, senta, ini_inf, fim_inf, sai."""
    ag = pd.DataFrame(linhas, columns=["paciente", "perfil", "chegada", "senta",
                                       "inicio_infusao", "fim_infusao", "sai"])
    ag["protocolo"] = "Gemzar"
    ag["limite_min"] = 17 * 60
    ag["remarcado"] = ag["paciente"].isin(remarcado)
    ag.loc[ag["remarcado"], ["senta", "inicio_infusao", "fim_infusao", "sai"]] = np.nan
    ag["preparo_min"] = 10
    ag["infusao_min"] = ag["fim_infusao"] - ag["inicio_infusao"]
    ag["inicio_preparo"] = ag["inicio_infusao"] - 15
    ag["fim_preparo"] = ag["inicio_infusao"] - 5
    ag["liberacao"] = ag["inicio_preparo"]
    ag["bolsa_chega"] = ag["inicio_infusao"]
    ag["poltrona"] = [1, 2, 3]
    ag["posto_capela"] = 1
    return ag[COLUNAS_AGENDA]


@pytest.fixture
def cenarios():
    # Hoje: PAC-001 fica 5h (4h esperando); PAC-002 sem espera; PAC-003 remarcado
    hoje = _agenda([
        ("PAC-001", "Rápido", 420, 420, 660, 711, 720),
        ("PAC-002", "Rápido", 480, 480, 480, 531, 546),
        ("PAC-003", "Longo", 780, 0, 0, 0, 0),
    ], remarcado=("PAC-003",))
    # Proposta: PAC-001 1h06 (10 min de acomodação); PAC-002 também 1h06; PAC-003 atendido
    prop = _agenda([
        ("PAC-001", "Rápido", 600, 600, 610, 661, 666),
        ("PAC-002", "Rápido", 470, 470, 480, 531, 536),
        ("PAC-003", "Longo", 500, 500, 510, 750, 755),
    ])
    return hoje, prop


def test_jornada_e_ganho(cenarios):
    j = G.jornada(*cenarios).set_index("paciente")
    assert j.loc["PAC-001", "tempo_hoje"] == 300
    assert j.loc["PAC-001", "tempo_proposta"] == 66
    assert j.loc["PAC-001", "ganho"] == 234
    assert j.loc["PAC-002", "ganho"] == 0  # hoje 66, proposta 66
    assert j.loc["PAC-003", "remarcado_hoje"] and not j.loc["PAC-003", "remarcado_proposta"]
    assert np.isnan(j.loc["PAC-003", "ganho"])


def test_resumo(cenarios):
    r = G.resumo(G.jornada(*cenarios), meta_espera=30)
    assert r["horas_economizadas"] == pytest.approx(234 / 60)
    assert r["pacientes_com_ganho"] == 1 and r["pacientes_comparados"] == 2
    assert r["remarcados_evitados"] == 1
    assert r["acima_meta_hoje"] == 1  # PAC-001 esperou 240 min
    assert r["acima_meta_proposta"] == 0


def test_infusao_igual_nos_dois_cenarios(cenarios):
    """A duração da infusão é do hospital: não pode mudar entre os cenários."""
    hoje, prop = cenarios
    j = G.jornada(hoje, prop).dropna(subset=["ganho"])
    inf_h = hoje.set_index("paciente")["infusao_min"]
    inf_p = prop.set_index("paciente")["infusao_min"]
    assert (inf_h[j["paciente"]].to_numpy() == inf_p[j["paciente"]].to_numpy()).all()


def test_composicao_e_meta(cenarios):
    hoje, prop = cenarios
    c = G.composicao(hoje)
    assert c["Espera na poltrona"] == pytest.approx(240 / 60)
    assert c["Alta"] == pytest.approx((9 + 15) / 60)
    assert G.dentro_da_meta(hoje, 30) == pytest.approx(50)
    assert G.dentro_da_meta(prop, 30) == pytest.approx(100)


def test_formatar_duracao():
    assert G.formatar_duracao(125) == "2h05"
    assert G.formatar_duracao(45) == "45 min"
    assert G.formatar_duracao(-70) == "-1h10"
    assert G.formatar_duracao(np.nan) == "—"


def test_ociosidade(cenarios):
    hoje, _ = cenarios
    prem = Premissas(n_poltronas=3, capacidade_capela=1)
    oc = ociosidade_por_hora(hoje, prem).set_index("hora")
    # 7h: só PAC-001 sentado (esperando a bolsa): 2 livres, 1 ocupada sem tratar
    assert oc.loc[420, "poltronas_ociosas"] == pytest.approx(2)
    assert oc.loc[420, "poltronas_sem_tratar"] == pytest.approx(1)
    # Capela: PAC-002 prepara 7h45–7h55 (10 dos 60 min da hora das 7h)
    assert oc.loc[420, "capela_ociosa"] == pytest.approx(100 * 50 / 60)
    # 8h: PAC-001 (esperando) e PAC-002 (8h00–9h06) ocupam poltrona a hora toda
    assert oc.loc[480, "poltronas_ociosas"] == pytest.approx(1)
    # Sem tratar: PAC-001 esperando (60 min) + PAC-002 em alta 8h51–9h00 (9 min)
    assert oc.loc[480, "poltronas_sem_tratar"] == pytest.approx(1 + 9 / 60)
