"""Testes da Fase 3: modelo CP-SAT da agenda otimizada."""
import numpy as np
import pytest

from dados import Premissas, gerar_dia
from otimizador import SLOT, otimizar


def _max_simultaneo(inicios, fins):
    ev = sorted([(t, 1) for t in inicios] + [(t, -1) for t in fins], key=lambda e: (e[0], e[1]))
    atual = pico = 0
    for _, d in ev:
        atual += d
        pico = max(pico, atual)
    return pico


@pytest.fixture(scope="module")
def resultado():
    prem = Premissas()
    return prem, gerar_dia(prem), otimizar(gerar_dia(prem), prem)


def test_status_e_tempo(resultado):
    _, _, r = resultado
    assert r["ok"]
    assert r["tempo_s"] <= 25
    assert r["status_texto"]


def test_todos_no_turno(resultado):
    prem, _, r = resultado
    ag = r["agenda"]
    assert r["remarcados"] == []
    assert (ag["senta"] >= prem.inicio_turno).all()
    assert (ag["inicio_preparo"] >= prem.inicio_turno).all()
    assert (ag["sai"] <= prem.fim_turno).all()


def test_slots_de_10_min(resultado):
    prem, _, r = resultado
    assert ((r["agenda"]["inicio_infusao"] - prem.inicio_turno) % SLOT == 0).all()


def test_bolsa_pronta_antes_da_infusao(resultado):
    _, _, r = resultado
    ag = r["agenda"]
    assert (ag["bolsa_chega"] <= ag["inicio_infusao"]).all()
    assert (ag["senta"] <= ag["inicio_infusao"]).all()


def test_capacidades(resultado):
    prem, _, r = resultado
    ag = r["agenda"]
    assert _max_simultaneo(ag["inicio_preparo"], ag["fim_preparo"]) <= prem.capacidade_capela
    assert _max_simultaneo(ag["senta"], ag["sai"]) <= prem.n_poltronas
    # Nenhuma poltrona ou posto da capela com dois pacientes ao mesmo tempo
    for rec, ini, fim in [("poltrona", "senta", "sai"),
                          ("posto_capela", "inicio_preparo", "fim_preparo")]:
        for _, g in ag.sort_values(ini).groupby(rec):
            assert (g[ini].to_numpy()[1:] >= g[fim].to_numpy()[:-1]).all()


def test_duracoes_nao_alteradas(resultado):
    _, dia, r = resultado
    ag = r["agenda"].set_index("paciente")
    d = dia.set_index("paciente")
    assert np.allclose(ag["fim_infusao"] - ag["inicio_infusao"], d.loc[ag.index, "infusao_min"])
    assert np.allclose(ag["fim_preparo"] - ag["inicio_preparo"], d.loc[ag.index, "preparo_min"])


def test_capela_suavizada(resultado):
    prem, _, r = resultado
    ag = r["agenda"]
    por_hora = ag.groupby((ag["inicio_preparo"] - prem.inicio_turno) // 60)["preparo_min"].sum()
    media = ag["preparo_min"].sum() / 11
    assert por_hora.max() <= 1.2 * media


def test_paciente_que_nao_cabe_fica_fora():
    prem = Premissas(n_pacientes=10)
    prem.perfis["Longo"]["infusao"] = 700  # maior que o turno de 11h
    r = otimizar(gerar_dia(prem), prem, limite_s=10)
    assert r["ok"]
    longos = gerar_dia(prem).query("perfil == 'Longo'")["paciente"].tolist()
    assert sorted(r["remarcados"]) == sorted(longos)


def test_zero_remarcacoes_com_folga_antes_do_limite(resultado):
    prem, _, r = resultado
    ag = r["agenda"]
    assert not ag["remarcado"].any()
    # Todos chegam à triagem pelo menos `folga_limite` min antes do horário limite
    assert (ag["chegada"] <= ag["limite_min"] - prem.folga_limite).all()


def test_proposta_atende_quem_hoje_seria_remarcado(resultado):
    prem, dia, r = resultado
    from simulacao_atual import simular_atual
    hoje = simular_atual(dia, prem)
    remarcados_hoje = set(hoje.loc[hoje["remarcado"], "paciente"])
    assert remarcados_hoje  # o dia padrão tem remarcações hoje
    atendidos = set(r["agenda"].dropna(subset=["inicio_infusao"])["paciente"])
    assert remarcados_hoje <= atendidos


def test_sexta_feira_e_folga_editavel():
    prem = Premissas(sexta_feira=True, folga_limite=45)
    r = otimizar(gerar_dia(prem), prem)
    ag = r["agenda"]
    assert r["ok"] and r["remarcados"] == []
    assert (ag["chegada"] <= ag["limite_min"] - 45).all()
