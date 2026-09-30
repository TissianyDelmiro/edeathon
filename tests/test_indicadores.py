"""Testes da Fase 4: indicadores conferidos com um caso pequeno feito à mão."""
import pandas as pd
import numpy as np
import pytest

from dados import Premissas
from indicadores import (calcular_kpis, carga_capela_por_hora, poltronas_por_hora,
                         tabela_comparativa)
from simulacao_atual import COLUNAS_AGENDA


@pytest.fixture
def caso():
    """3 pacientes, capela com 1 posto, turno 7h–18h.

    PAC-001: senta 7h00, bolsa 7h20 -> espera 20; infusão 7h20–8h20; sai 8h35
    PAC-002: senta 7h30, bolsa 8h10 -> espera 40; infusão 8h10–9h10; sai 9h25
    PAC-003: senta 13h00, bolsa 13h00 -> espera 0; infusão 13h00–18h30 (30 min fora do turno)
    """
    prem = Premissas(capacidade_capela=1, n_poltronas=2)
    linhas = [
        # paciente, chegada, senta, ini_prep, fim_prep, ini_inf, fim_inf, sai
        ("PAC-001", 420, 420, 420, 440, 440, 500, 515),
        ("PAC-002", 450, 450, 470, 490, 490, 550, 565),
        ("PAC-003", 780, 780, 760, 780, 780, 1110, 1125),
    ]
    ag = pd.DataFrame(linhas, columns=["paciente", "chegada", "senta", "inicio_preparo",
                                       "fim_preparo", "inicio_infusao", "fim_infusao", "sai"])
    ag["perfil"] = "Rápido"
    ag["protocolo"] = "Gemzar"
    ag["limite_min"] = 17 * 60 + 30
    ag["remarcado"] = False
    ag["preparo_min"] = 20
    ag["infusao_min"] = ag["fim_infusao"] - ag["inicio_infusao"]
    ag["liberacao"] = ag["inicio_preparo"]
    ag["bolsa_chega"] = ag["inicio_infusao"]
    ag["poltrona"] = [1, 2, 1]
    ag["posto_capela"] = 1
    return prem, ag[COLUNAS_AGENDA]


def test_kpis_caso_manual(caso):
    prem, ag = caso
    k = calcular_kpis(ag, prem, alta=15)
    assert k["pacientes_atendidos"] == 3
    assert k["t2_mediana"] == 20
    assert k["pct_espera_30"] == pytest.approx(100 / 3)
    # Quimio no turno: 60 + 60 + 300 (só até 18h) = 420 min = 7 h
    assert k["horas_qt"] == pytest.approx(7.0)
    # Sem tratamento: esperas 20+40+0 + altas 3x15 = 105 min
    assert k["horas_sem_tratamento"] == pytest.approx(105 / 60)
    assert k["pico_simultaneos"] == 2
    # Capela: 3 preparos de 20 min, todos antes das 13h (o último é 12h40–13h00)
    assert k["capela_manha"] == pytest.approx(100 * 60 / 360)
    assert k["capela_tarde"] == pytest.approx(0.0)
    assert k["termina_apos_turno"] == 1


def test_series_por_hora(caso):
    prem, ag = caso
    capela = carga_capela_por_hora(ag, prem).set_index("hora")["ocupacao"]
    assert capela[420] == pytest.approx(100 * 30 / 60)  # 7h: 7h00–7h20 e 7h50–8h00
    assert capela[480] == pytest.approx(100 * 10 / 60)  # 8h: 8h00–8h10
    assert len(capela) == 11
    polt = poltronas_por_hora(ag, prem).set_index("hora")
    assert polt.loc[420, "poltronas"] == 2
    assert polt.loc[600, "poltronas"] == 0


def test_tabela_comparativa():
    base = dict(remarcados=2, pacientes_atendidos=88, horas_qt=100, horas_sem_tratamento=50,
                t2_mediana=10, t2_p90=60, pct_espera_30=20, pico_simultaneos=40,
                capela_manha=90, capela_tarde=30)
    melhor = dict(base, remarcados=0, pacientes_atendidos=90, horas_qt=110,
                  horas_sem_tratamento=25)
    t = tabela_comparativa(base, melhor).set_index("Indicador")
    rem = t.loc["Pacientes remarcados por perder o horário limite"]
    assert rem["Variação (%)"] == pytest.approx(-100)
    assert rem["Resultado"].startswith("✅")
    assert t.loc["Pacientes atendidos no dia", "Resultado"].startswith("✅")
    qt = t.loc["Horas de quimioterapia no turno"]
    assert qt["Variação (%)"] == pytest.approx(10)
    assert qt["Resultado"].startswith("✅")
    sem = t.loc["Horas de poltrona sem tratamento (espera + alta)"]
    assert sem["Variação (%)"] == pytest.approx(-50)
    assert sem["Resultado"].startswith("✅")
    # Partindo de zero remarcações, qualquer remarcação na proposta é piora
    pior = tabela_comparativa(dict(base, remarcados=0), dict(base, remarcados=1))
    assert pior.set_index("Indicador").loc[rem.name, "Resultado"].startswith("⚠️")


def test_contagem_de_remarcados(caso):
    prem, ag = caso
    ag = ag.copy()
    # PAC-003 chegou às 13h00 com limite às 12h00: remarcado, sem capela nem poltrona
    ag.loc[2, "limite_min"] = 12 * 60
    ag.loc[2, "remarcado"] = True
    ag.loc[2, ["senta", "inicio_preparo", "fim_preparo", "inicio_infusao",
               "fim_infusao", "sai"]] = np.nan
    k = calcular_kpis(ag, prem, prem.alta_atual)
    assert k["remarcados"] == 1
    assert k["pacientes_atendidos"] == 2
