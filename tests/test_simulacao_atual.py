"""Testes da Fase 2: simulação do cenário atual (fila por ordem de chegada)."""
import numpy as np
import pytest

from dados import Premissas, gerar_dia
from simulacao_atual import simular_atual


@pytest.fixture(scope="module")
def cenario():
    prem = Premissas()
    return prem, simular_atual(gerar_dia(prem), prem)


def _max_simultaneo(inicios, fins):
    ev = sorted([(t, 1) for t in inicios] + [(t, -1) for t in fins], key=lambda e: (e[0], e[1]))
    atual = pico = 0
    for _, d in ev:
        atual += d
        pico = max(pico, atual)
    return pico


def test_sequencia_de_tempos_coerente(cenario):
    _, ag = cenario
    assert (ag["senta"] >= ag["chegada"]).all()
    assert (ag["inicio_preparo"] >= ag["liberacao"]).all()
    assert (ag["bolsa_chega"] >= ag["fim_preparo"]).all()
    # Ninguém começa a infusão antes de a bolsa chegar nem antes de sentar
    assert (ag["inicio_infusao"] >= ag["bolsa_chega"]).all()
    assert (ag["inicio_infusao"] >= ag["senta"]).all()
    assert (ag["sai"] > ag["fim_infusao"]).all()


def test_capacidades_respeitadas(cenario):
    prem, ag = cenario
    assert _max_simultaneo(ag["inicio_preparo"], ag["fim_preparo"]) <= prem.capacidade_capela
    assert _max_simultaneo(ag["senta"], ag["sai"]) <= prem.n_poltronas
    # A mesma poltrona nunca tem dois pacientes ao mesmo tempo
    for _, g in ag.sort_values("senta").groupby("poltrona"):
        assert (g["senta"].to_numpy()[1:] >= g["sai"].to_numpy()[:-1]).all()


def test_capela_por_ordem_de_liberacao(cenario):
    _, ag = cenario
    ordem = ag.sort_values("liberacao", kind="stable")["inicio_preparo"].to_numpy()
    # FIFO: quem foi liberado antes nunca começa a ser preparado depois de quem veio depois
    assert (np.diff(ordem) >= 0).all()


def test_calibracao_proxima_dos_numeros_reais():
    """Média de 5 dias sintéticos próxima do observado no hospital."""
    esperas, pct30, pct60, horas = [], [], [], []
    for semente in range(5):
        prem = Premissas(semente=semente)
        ag = simular_atual(gerar_dia(prem), prem)
        t2 = (ag["inicio_infusao"] - ag["senta"]).to_numpy()
        esperas.append(np.median(t2))
        pct30.append((t2 > 30).mean())
        pct60.append((t2 > 60).mean())
        horas.append((t2.sum() + prem.alta_atual * len(ag)) / 60)
    assert 9 <= np.mean(esperas) <= 17  # real: 13 min
    assert 0.15 <= np.mean(pct30) <= 0.30  # real: 21%
    assert 0.05 <= np.mean(pct60) <= 0.14  # real: 9%
    assert 45 <= np.mean(horas) <= 63  # real: ~54 h
