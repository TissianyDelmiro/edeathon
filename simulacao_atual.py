"""
Simulação de eventos discretos do CENÁRIO ATUAL da unidade de quimioterapia.

Como funciona hoje (modelo simplificado):
0. O paciente chega à triagem com o farmacêutico. Se chegar depois do horário limite do
   protocolo (folha do setor), não dá mais para manipular no dia: ele é REMARCADO e não
   ocupa poltrona nem capela.
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
    "paciente", "perfil", "protocolo", "limite_min", "remarcado", "preparo_min", "infusao_min",
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
    calib = dia["perfil"].map(prem.calibracao)
    pre = dia["u_pre"].to_numpy() < calib.map(lambda c: c["pre"]).to_numpy()
    # Pré-liberadas: entre 20 e 60 min antes da chegada (nunca antes da abertura)
    antes = dia["chegada_min"] - (20 + 40 * dia["u_antecedencia"])
    antes = np.maximum(antes, prem.inicio_turno)
    # Demais: atraso log-normal depois da chegada (mediana própria de cada grupo)
    atraso = calib.map(lambda c: c["atraso"]).to_numpy() * np.exp(
        prem.atraso_liberacao_dispersao * dia["z_atraso"])
    depois = dia["chegada_min"] + atraso
    return np.where(pre, antes, depois)


def simular_atual(dia: pd.DataFrame, prem: Premissas) -> pd.DataFrame:
    """Simula o dia no modo atual e devolve a agenda realizada (um paciente por linha).

    Pacientes remarcados ficam na agenda com `remarcado=True` e sem horários de preparo,
    poltrona ou infusão (só a chegada, para o Painel mostrar o que aconteceu).
    """
    ag = dia[["paciente", "perfil", "protocolo", "limite_min", "preparo_min",
              "infusao_min"]].copy()
    ag["chegada"] = dia["chegada_min"].astype(float)
    ag["remarcado"] = ag["chegada"] > ag["limite_min"]
    ag["liberacao"] = horario_liberacao(dia, prem)
    for col in ["inicio_preparo", "fim_preparo", "bolsa_chega", "senta", "inicio_infusao",
                "fim_infusao", "sai"]:
        ag[col] = np.nan
    ag["posto_capela"] = pd.array([pd.NA] * len(ag), dtype="Int64")
    ag["poltrona"] = pd.array([pd.NA] * len(ag), dtype="Int64")
    ag.loc[ag["remarcado"], "liberacao"] = np.nan
    at = ag.index[~ag["remarcado"]]  # só quem foi atendido usa capela e poltrona
    if len(at) == 0:
        return ag[COLUNAS_AGENDA]

    # Capela: fila única por ordem de liberação
    ini_prep, posto = _servidores_fifo(ag.loc[at, "liberacao"].to_numpy(),
                                       ag.loc[at, "preparo_min"].to_numpy(),
                                       prem.capacidade_capela, prem.inicio_turno)
    ag.loc[at, "inicio_preparo"] = ini_prep
    ag.loc[at, "fim_preparo"] = ini_prep + ag.loc[at, "preparo_min"]
    ag.loc[at, "bolsa_chega"] = ag.loc[at, "fim_preparo"] + prem.transporte
    ag.loc[at, "posto_capela"] = posto + 1

    # Poltronas: o paciente senta ao chegar (ou espera na recepção se estiver lotado)
    chegada = ag.loc[at, "chegada"].to_numpy()
    bolsa = ag.loc[at, "bolsa_chega"].to_numpy()
    infusao = ag.loc[at, "infusao_min"].to_numpy()
    livres = [(float(prem.inicio_turno), p) for p in range(prem.n_poltronas)]
    heapq.heapify(livres)
    senta, poltrona, sai = (np.empty(len(at)) for _ in range(3))
    for i in np.argsort(chegada, kind="stable"):
        livre_em, p = heapq.heappop(livres)
        senta[i] = max(chegada[i], livre_em)
        inicio_inf = max(senta[i], bolsa[i])
        sai[i] = inicio_inf + infusao[i] + prem.alta_atual
        poltrona[i] = p + 1
        heapq.heappush(livres, (sai[i], p))

    ag.loc[at, "senta"] = senta
    ag.loc[at, "inicio_infusao"] = np.maximum(senta, bolsa)
    ag.loc[at, "fim_infusao"] = ag.loc[at, "inicio_infusao"] + ag.loc[at, "infusao_min"]
    ag.loc[at, "sai"] = sai
    ag.loc[at, "poltrona"] = poltrona.astype(int)
    return ag[COLUNAS_AGENDA]
