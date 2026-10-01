"""Testes da Fase 1: pacientes do interior (dados sintéticos e cenário de hoje)."""
import numpy as np
import pandas as pd
import pytest

import indicadores as I
from dados import Premissas, gerar_dia
from simulacao_atual import perdeu_transporte, simular_atual


def test_fracao_e_horarios_do_transporte():
    prem = Premissas()
    dia = gerar_dia(prem)
    intr = dia[dia["interior"]]
    assert len(intr) == round(prem.frac_interior * prem.n_pacientes)
    # Horários do transporte dentro das faixas e em múltiplos de 15 min
    assert intr["retorno_min"].between(prem.transporte_volta_de, prem.transporte_volta_ate).all()
    assert (intr["retorno_min"] % 15 == 0).all()
    assert (intr["chegada_transporte"] <= intr["chegada_min"]).all()
    assert (intr["chegada_transporte"] <= prem.transporte_chega_ate).all()
    # Quem é da capital não tem horário de transporte
    capital = dia[~dia["interior"]]
    assert capital["retorno_min"].isna().all() and capital["chegada_transporte"].isna().all()


def test_interior_nao_muda_o_dia_calibrado():
    """Os sorteios do interior usam outro gerador: o resto do dia fica idêntico."""
    com = gerar_dia(Premissas())
    sem = gerar_dia(Premissas(frac_interior=0.0))
    colunas = ["paciente", "perfil", "protocolo", "limite_min", "chegada_min",
               "u_pre", "u_antecedencia", "z_atraso"]
    assert com[colunas].equals(sem[colunas])
    assert not sem["interior"].any()


def test_perdeu_transporte_conta_certo():
    ag = pd.DataFrame({
        "paciente": ["PAC-001", "PAC-002", "PAC-003", "PAC-004"],
        "interior": [True, True, False, True],
        "retorno_min": [900.0, 900.0, np.nan, 900.0],
        "sai": [890.0, 910.0, 1000.0, np.nan],  # PAC-004 remarcado (sem saída)
    })
    assert perdeu_transporte(ag).tolist() == [False, True, False, False]


def test_kpis_do_interior_no_dia_padrao():
    prem = Premissas()
    hoje = simular_atual(gerar_dia(prem), prem)
    k = I.calcular_kpis(hoje, prem, prem.alta_atual)
    assert k["pacientes_interior"] == 36
    assert k["interior_perdeu_transporte"] == int(perdeu_transporte(hoje).sum())
    assert k["interior_perdeu_transporte"] >= 1  # hoje há quem perca o transporte
    assert k["interior_remarcados"] == int((hoje["interior"] & hoje["remarcado"]).sum())


@pytest.mark.parametrize("frac", [0.0, 1.0])
def test_extremos_da_fracao(frac):
    dia = gerar_dia(Premissas(frac_interior=frac))
    assert dia["interior"].mean() == frac


# ---------------------------------------------------------------------------
# Fase 2: otimizador com o transporte do interior
# ---------------------------------------------------------------------------
from ganhos import jornada  # noqa: E402
from otimizador import otimizar  # noqa: E402


@pytest.fixture(scope="module", params=[False, True], ids=["dia normal", "sexta-feira"])
def proposta(request):
    prem = Premissas(sexta_feira=request.param)
    dia = gerar_dia(prem)
    return prem, dia, otimizar(dia, prem)


def test_ninguem_do_interior_perde_o_transporte(proposta):
    prem, _, r = proposta
    ag = r["agenda"]
    intr = ag[ag["interior"].astype(bool)]
    assert r["ok"] and not ag["remarcado"].any()
    assert not perdeu_transporte(ag).any()
    # Folga mínima antes do retorno do transporte
    assert (intr["sai"] <= intr["retorno_min"] - prem.folga_transporte).all()


def test_interior_chega_com_o_transporte(proposta):
    _, _, r = proposta
    intr = r["agenda"][r["agenda"]["interior"].astype(bool)]
    assert (intr["chegada"] == intr["chegada_transporte"]).all()
    assert (intr["senta"] >= intr["chegada_transporte"]).all()


def test_prioridade_do_interior_nao_prejudica_a_capital(proposta):
    prem, dia, r = proposta
    hoje = simular_atual(dia, prem)
    j = jornada(hoje, r["agenda"]).dropna(subset=["tempo_hoje", "tempo_proposta"])
    do_interior = j["paciente"].isin(dia.loc[dia["interior"], "paciente"])
    # Os dois grupos ficam, em média, menos tempo na unidade do que hoje
    assert j.loc[do_interior, "tempo_proposta"].mean() < j.loc[do_interior, "tempo_hoje"].mean()
    assert j.loc[~do_interior, "tempo_proposta"].mean() < j.loc[~do_interior, "tempo_hoje"].mean()


def test_tempo_do_interior_conta_desde_o_transporte():
    prem = Premissas()
    dia = gerar_dia(prem)
    hoje = simular_atual(dia, prem)
    j = jornada(hoje, hoje).set_index("paciente")
    pac = hoje[hoje["interior"] & ~hoje["remarcado"]].iloc[0]
    assert j.loc[pac["paciente"], "tempo_hoje"] == pac["sai"] - pac["chegada_transporte"]
