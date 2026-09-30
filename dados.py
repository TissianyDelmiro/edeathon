"""
Premissas do protótipo, tabela de protocolos e gerador do dia sintético.

REGRAS DO EVENTO:
- Nenhum dado real de paciente: todos os pacientes são fictícios (PAC-001, PAC-002...).
- Nenhuma decisão clínica: as durações de preparo e de infusão de cada grupo são
  PARÂMETROS DE ENTRADA informados pelo hospital. O sistema só as lê, nunca as calcula
  nem as altera.

A tabela data/horarios_limite.csv vem da folha fixada na unidade de QT (dado do setor,
não de paciente): para cada protocolo, o horário limite para o paciente estar na triagem
com o farmacêutico e a cor que classifica o tempo de infusão.

Todos os horários são guardados em minutos desde a meia-noite (ex.: 7h00 = 420).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ARQUIVO_PROTOCOLOS = Path(__file__).resolve().parent / "data" / "horarios_limite.csv"

# Grupos de tratamento, definidos pela cor da folha do setor (ordem fixa em tabelas e gráficos)
PERFIS = ["Longo", "Intermediário laranja", "Intermediário marrom", "Rápido", "Injetável"]
GRUPO_DA_COR = {
    "vermelho": "Longo",
    "laranja": "Intermediário laranja",
    "marrom": "Intermediário marrom",
    "verde": "Rápido",
    "azul": "Injetável",
}
# Laranja e marrom ainda não confirmados como o mesmo nível pelo setor
A_CONFIRMAR = {"Intermediário laranja", "Intermediário marrom"}
# Nome com a cor escrita junto (nunca só a cor)
ROTULO = {
    "Longo": "🔴 Longo (vermelho)",
    "Intermediário laranja": "🟠 Intermediário laranja (a confirmar)",
    "Intermediário marrom": "🟤 Intermediário marrom (a confirmar)",
    "Rápido": "🟢 Rápido (verde)",
    "Injetável": "🔵 Injetável (azul)",
}

MINUTOS_SEXTA = 60  # às sextas, todos os horários limite têm 1h a menos


def perfis_padrao() -> dict:
    """Valores padrão por grupo. TODOS são 'suposição a validar' com o hospital.

    preparo  = minutos de manipulação da bolsa na capela
    infusao  = minutos de infusão (Longo=240, Intermediário=120, Rápido=51, Injetável=15)
    mix      = fração dos pacientes do dia neste grupo
    """
    return {
        "Longo": {"preparo": 15, "infusao": 240, "mix": 0.15},
        "Intermediário laranja": {"preparo": 12, "infusao": 120, "mix": 0.15},
        "Intermediário marrom": {"preparo": 12, "infusao": 120, "mix": 0.15},
        "Rápido": {"preparo": 9, "infusao": 51, "mix": 0.35},
        "Injetável": {"preparo": 6, "infusao": 15, "mix": 0.20},
    }


def _hhmm_para_min(texto: str) -> int:
    h, m = texto.strip().split(":")
    return int(h) * 60 + int(m)


@lru_cache(maxsize=1)
def carregar_protocolos() -> pd.DataFrame:
    """Lê a tabela de horários limite do setor e acrescenta o grupo e o limite em minutos."""
    if not ARQUIVO_PROTOCOLOS.exists():
        raise FileNotFoundError(f"Tabela de horários limite não encontrada: {ARQUIVO_PROTOCOLOS}")
    tab = pd.read_csv(ARQUIVO_PROTOCOLOS, encoding="utf-8")
    cores_invalidas = set(tab["cor"]) - set(GRUPO_DA_COR)
    if cores_invalidas:
        raise ValueError(f"Cor desconhecida na tabela de horários limite: {cores_invalidas}")
    tab["grupo"] = tab["cor"].map(GRUPO_DA_COR)
    tab["limite_min"] = tab["horario_limite"].map(_hhmm_para_min)
    return tab


@dataclass
class Premissas:
    """Conjunto único de premissas do protótipo (todas editáveis na aba Premissas)."""

    # Turno da unidade
    inicio_turno: int = 7 * 60
    fim_turno: int = 18 * 60
    # Capacidades
    n_poltronas: int = 40
    capacidade_capela: int = 3  # bolsas manipuladas ao mesmo tempo
    # Demanda do dia
    n_pacientes: int = 90
    perfis: dict = field(default_factory=perfis_padrao)
    frac_antes_10h: float = 0.57  # fração de pacientes que chega antes das 10h hoje
    # Horário limite (folha do setor)
    sexta_feira: bool = False  # às sextas, todos os limites ficam 1h mais cedo
    folga_limite: int = 30  # proposta: chegar à triagem pelo menos X min antes do limite
    # Tempos de processo (minutos)
    alta_atual: int = 15  # do fim da infusão até liberar a poltrona no Tasy (hoje)
    alta_antecipada: int = 5  # idem, com a alta preparada antes do fim da infusão
    transporte: int = 5  # da capela até a poltrona
    acomodacao: int = 10  # no cenário otimizado: paciente senta 10 min antes da bolsa chegar
    # Calibração do cenário atual (ajustada para reproduzir os números observados)
    frac_pre_liberada: float = 0.60  # prescrições liberadas antes da chegada do paciente
    atraso_liberacao_mediana: float = 4.0  # min entre chegada e liberação (demais pacientes)
    atraso_liberacao_dispersao: float = 0.6  # espalhamento (log-normal) desse atraso
    # Semente do gerador aleatório (mesma semente = mesmo dia)
    semente: int = 125  # escolhida por gerar um dia típico (próximo dos números observados)

    def copia(self) -> "Premissas":
        return copy.deepcopy(self)


def _contagem_por_perfil(n: int, perfis: dict) -> dict:
    """Divide n pacientes entre os perfis respeitando o mix (método do maior resto)."""
    soma = sum(p["mix"] for p in perfis.values()) or 1.0
    cotas = {nome: n * p["mix"] / soma for nome, p in perfis.items()}
    contagem = {nome: int(np.floor(c)) for nome, c in cotas.items()}
    faltam = n - sum(contagem.values())
    for nome in sorted(cotas, key=lambda k: cotas[k] - contagem[k], reverse=True)[:faltam]:
        contagem[nome] += 1
    return contagem


def gerar_dia(prem: Premissas) -> pd.DataFrame:
    """Gera o dia sintético: um paciente fictício por linha.

    Colunas:
      paciente, perfil, preparo_min, infusao_min, chegada_min (horário de chegada HOJE),
      e sorteios usados na calibração do cenário atual (u_pre, u_antecedencia, z_atraso).
    Os sorteios ficam guardados para que mudar a calibração não mude o dia.
    """
    rng = np.random.default_rng(prem.semente)
    n = prem.n_pacientes
    if n <= 0:
        raise ValueError("O número de pacientes precisa ser maior que zero.")

    # 1) Grupo de cada paciente, respeitando o mix; dentro do grupo, um protocolo da
    #    tabela do setor sorteado com a mesma chance para todos (suposição)
    contagem = _contagem_por_perfil(n, prem.perfis)
    perfis = [nome for nome in PERFIS if nome in contagem for _ in range(contagem[nome])]
    tab = carregar_protocolos()
    protocolos, limites = [], []
    for grupo in perfis:
        opcoes = tab[tab["grupo"] == grupo]
        if opcoes.empty:
            raise ValueError(f"Nenhum protocolo do grupo '{grupo}' na tabela de horários limite.")
        linha = opcoes.iloc[rng.integers(len(opcoes))]
        protocolos.append(linha["protocolo"])
        limites.append(linha["limite_min"] - (MINUTOS_SEXTA if prem.sexta_feira else 0))

    # 2) Quem chega antes das 10h (57% hoje). Pacientes do perfil longo chegam de manhã,
    #    como na prática, para caber a infusão no turno.
    n_manha = int(round(prem.frac_antes_10h * n))
    idx = np.arange(n)
    longos = [i for i in idx if perfis[i] == "Longo"]
    outros = [i for i in idx if perfis[i] != "Longo"]
    rng.shuffle(outros)
    ordem = longos + outros
    manha = set(ordem[:n_manha])

    dez_h = 10 * 60
    chegadas = np.empty(n)
    for i in idx:
        if i in manha:
            # Manhã: concentração logo na abertura (pico por volta das 8h)
            chegadas[i] = rng.triangular(prem.inicio_turno, prem.inicio_turno + 60, dez_h)
        else:
            # Depois das 10h: chegadas decrescendo até o limite para caber a infusão
            dur = prem.perfis[perfis[i]]["infusao"] + prem.perfis[perfis[i]]["preparo"]
            limite = max(dez_h + 10, min(14 * 60 + 30, prem.fim_turno - dur - 60))
            chegadas[i] = rng.triangular(dez_h, dez_h, limite)
    chegadas = np.floor(chegadas)

    df = pd.DataFrame({
        "perfil": perfis,  # grupo de tratamento (cor da folha do setor)
        "protocolo": protocolos,
        "limite_min": limites,  # horário limite para chegar à triagem com o farmacêutico
        "chegada_min": chegadas.astype(int),
        "u_pre": rng.random(n),
        "u_antecedencia": rng.random(n),
        "z_atraso": rng.standard_normal(n),
    })
    # Durações vêm diretamente das premissas do hospital (sem nenhum cálculo clínico)
    df["preparo_min"] = df["perfil"].map(lambda p: int(prem.perfis[p]["preparo"]))
    df["infusao_min"] = df["perfil"].map(lambda p: int(prem.perfis[p]["infusao"]))

    # 3) IDs fictícios em ordem de chegada
    df = df.sort_values(["chegada_min", "perfil"], kind="stable").reset_index(drop=True)
    df.insert(0, "paciente", [f"PAC-{i + 1:03d}" for i in range(n)])
    return df[["paciente", "perfil", "protocolo", "limite_min", "preparo_min", "infusao_min",
               "chegada_min", "u_pre", "u_antecedencia", "z_atraso"]]


def hhmm(minutos) -> str:
    """Converte minutos desde a meia-noite em texto 'HHhMM' (ex.: 545 -> '09h05')."""
    if minutos is None or pd.isna(minutos):
        return "—"
    m = int(round(minutos))
    return f"{m // 60:02d}h{m % 60:02d}"
