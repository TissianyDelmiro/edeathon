"""Testes da Fase 2: simulação do cenário atual (filas por ordem de chegada e remarcações)."""
import numpy as np
import pytest

from dados import Premissas, gerar_dia
from simulacao_atual import simular_atual


@pytest.fixture(scope="module")
def cenario():
    prem = Premissas()
    ag = simular_atual(gerar_dia(prem), prem)
    return prem, ag, ag[~ag["remarcado"]]


def _max_simultaneo(inicios, fins):
    ev = sorted([(t, 1) for t in inicios] + [(t, -1) for t in fins], key=lambda e: (e[0], e[1]))
    atual = pico = 0
    for _, d in ev:
        atual += d
        pico = max(pico, atual)
    return pico


def test_sequencia_de_tempos_coerente(cenario):
    _, _, at = cenario
    assert (at["senta"] >= at["chegada"]).all()
    assert (at["inicio_preparo"] >= at["liberacao"]).all()
    assert (at["bolsa_chega"] >= at["fim_preparo"]).all()
    # Ninguém começa a infusão antes de a bolsa chegar nem antes de sentar
    assert (at["inicio_infusao"] >= at["bolsa_chega"]).all()
    assert (at["inicio_infusao"] >= at["senta"]).all()
    assert (at["sai"] > at["fim_infusao"]).all()


def test_capacidades_respeitadas(cenario):
    prem, _, at = cenario
    assert _max_simultaneo(at["inicio_preparo"], at["fim_preparo"]) <= prem.capacidade_capela
    assert _max_simultaneo(at["senta"], at["sai"]) <= prem.n_poltronas
    # A mesma poltrona nunca tem dois pacientes ao mesmo tempo
    for _, g in at.sort_values("senta").groupby("poltrona"):
        assert (g["senta"].to_numpy()[1:] >= g["sai"].to_numpy()[:-1]).all()


def test_capela_por_ordem_de_liberacao(cenario):
    _, _, at = cenario
    ordem = at.sort_values("liberacao", kind="stable")["inicio_preparo"].to_numpy()
    # FIFO: quem foi liberado antes nunca começa a ser preparado depois de quem veio depois
    assert (np.diff(ordem) >= 0).all()


def test_remarcado_nao_ocupa_poltrona_nem_capela(cenario):
    _, ag, _ = cenario
    rem = ag[ag["remarcado"]]
    assert len(rem) >= 1  # o dia padrão tem remarcações
    assert (rem["chegada"] > rem["limite_min"]).all()
    for col in ["inicio_preparo", "senta", "inicio_infusao", "sai"]:
        assert rem[col].isna().all()
    assert rem["poltrona"].isna().all() and rem["posto_capela"].isna().all()
    # Quem chegou até o limite é atendido
    ok = ag[~ag["remarcado"]]
    assert (ok["chegada"] <= ok["limite_min"]).all()


def test_sexta_feira_remarca_mais():
    normal, sexta = Premissas(), Premissas(sexta_feira=True)
    r_normal = simular_atual(gerar_dia(normal), normal)["remarcado"].sum()
    r_sexta = simular_atual(gerar_dia(sexta), sexta)["remarcado"].sum()
    assert r_sexta >= r_normal


def test_calibracao_proxima_dos_numeros_reais():
    """Média de 6 dias sintéticos próxima do observado no hospital.

    A fração acima de 30 min fica acima do real (≈31% x 21%) porque a calibração também
    aproxima as esperas médias do Rápido e do Injetável do Painel de Indicadores.
    """
    esperas, pct30, pct60, horas = [], [], [], []
    for semente in range(6):
        prem = Premissas(semente=semente)
        ag = simular_atual(gerar_dia(prem), prem)
        at = ag[~ag["remarcado"]]
        t2 = (at["inicio_infusao"] - at["senta"]).to_numpy()
        esperas.append(np.median(t2))
        pct30.append((t2 > 30).mean())
        pct60.append((t2 > 60).mean())
        horas.append((t2.sum() + prem.alta_atual * len(at)) / 60)
    assert 9 <= np.mean(esperas) <= 17  # real: 13 min
    assert 0.15 <= np.mean(pct30) <= 0.35  # real: 21%
    assert 0.05 <= np.mean(pct60) <= 0.14  # real: 9%
    assert 45 <= np.mean(horas) <= 63  # real: ~54 h
