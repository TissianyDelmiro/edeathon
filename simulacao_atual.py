"""
Simulação de eventos discretos do CENÁRIO ATUAL da unidade de quimioterapia.

Como funciona hoje (modelo simplificado):
1. O paciente chega e senta na primeira poltrona livre. Se todas estiverem ocupadas,
   espera na recepção (fila por ordem de chegada).
2. A prescrição é liberada para a farmácia: parte já vem liberada antes da chegada;
   o restante é liberado alguns minutos depois que o paciente chega.
3. A capela é uma fila única, por ordem de liberação, sem prioridade, com
   capacidade de N bolsas manipuladas ao mesmo tempo.
4. A bolsa pronta é levada até a poltrona (transporte) e a infusão começa.
5. Terminada a infusão, a poltrona só é liberada depois da alta no Tasy (15 min hoje).

As duas filas (capela e poltronas) são servidores múltiplos atendidos por ordem de
chegada. Como a capela não depende das poltronas, cada fila é resolvida em ordem
cronológica de eventos com uma fila de prioridade (heap) dos servidores livres.
"""
from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

from dados import Premissas

# Colunas da agenda (comuns ao cenário atual e ao otimizado)
COLUNAS_AGENDA = [
    "paciente", "perfil", "preparo_min", "infusao_min",
    "chegada", "senta", "liberacao", "inicio_preparo", "fim_preparo", "bolsa_chega",
    "inicio_infusao", "fim_infusao", "sai", "poltrona", "posto_capela",
]


def _servidores_fifo(liberacoes: np.ndarray, duracoes: np.ndarray, n_servidores: int,
                     abertura: float) -> tuple[np.ndarray, np.ndarray]:
    """Fila FIFO com vários servidores. Devolve (início do atendimento, servidor usado)."""
    livres = [(abertura, s) for s in range(n_servidores)]  # (hora em que fica livre, id)
    heapq.heapify(livres)
    inicio = np.empty(len(liberacoes))
    servidor = np.empty(len(liberacoes), dtype=int)
    for i in np.argsort(liberacoes, kind="stable"):
        livre_em, s = heapq.heappop(livres)
        inicio[i] = max(liberacoes[i], livre_em)
        servidor[i] = s
        heapq.heappush(livres, (inicio[i] + duracoes[i], s))
    return inicio, servidor


def horario_liberacao(dia: pd.DataFrame, prem: Premissas) -> np.ndarray:
    """Horário em que cada prescrição chega à farmácia (calibração do cenário atual)."""
    pre = dia["u_pre"].to_numpy() < prem.frac_pre_liberada
    # Pré-liberadas: entre 20 e 60 min antes da chegada (nunca antes da abertura)
    antes = dia["chegada_min"] - (20 + 40 * dia["u_antecedencia"])
    antes = np.maximum(antes, prem.inicio_turno)
    # Demais: atraso log-normal depois da chegada
    atraso = prem.atraso_liberacao_mediana * np.exp(
        prem.atraso_liberacao_dispersao * dia["z_atraso"])
    depois = dia["chegada_min"] + atraso
    return np.where(pre, antes, depois)


def simular_atual(dia: pd.DataFrame, prem: Premissas) -> pd.DataFrame:
    """Simula o dia no modo atual e devolve a agenda realizada (um paciente por linha)."""
    ag = dia[["paciente", "perfil", "preparo_min", "infusao_min"]].copy()
    ag["chegada"] = dia["chegada_min"].astype(float)
    ag["liberacao"] = horario_liberacao(dia, prem)

    # Capela: fila única por ordem de liberação
    ini_prep, posto = _servidores_fifo(ag["liberacao"].to_numpy(), ag["preparo_min"].to_numpy(),
                                       prem.capacidade_capela, prem.inicio_turno)
    ag["inicio_preparo"] = ini_prep
    ag["fim_preparo"] = ini_prep + ag["preparo_min"]
    ag["bolsa_chega"] = ag["fim_preparo"] + prem.transporte
    ag["posto_capela"] = posto + 1

    # Poltronas: o paciente senta ao chegar (ou espera na recepção se estiver lotado)
    livres = [(float(prem.inicio_turno), p) for p in range(prem.n_poltronas)]
    heapq.heapify(livres)
    senta, poltrona, sai = (np.empty(len(ag)) for _ in range(3))
    for i in np.argsort(ag["chegada"].to_numpy(), kind="stable"):
        livre_em, p = heapq.heappop(livres)
        senta[i] = max(ag["chegada"].iat[i], livre_em)
        inicio_inf = max(senta[i], ag["bolsa_chega"].iat[i])
        sai[i] = inicio_inf + ag["infusao_min"].iat[i] + prem.alta_atual
        poltrona[i] = p + 1
        heapq.heappush(livres, (sai[i], p))

    ag["senta"] = senta
    ag["inicio_infusao"] = np.maximum(senta, ag["bolsa_chega"])
    ag["fim_infusao"] = ag["inicio_infusao"] + ag["infusao_min"]
    ag["sai"] = sai
    ag["poltrona"] = poltrona.astype(int)
    return ag[COLUNAS_AGENDA]
