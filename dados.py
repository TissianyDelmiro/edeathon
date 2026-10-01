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
FIM_CHEGADAS_TARDE = 15 * 60 + 30  # últimas chegadas do dia hoje (suposição)


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


def calibracao_padrao() -> dict:
    """Liberação das prescrições no cenário atual, por grupo (resultado da calibração).

    Grupos planejados (longo e intermediários) quase sempre têm a prescrição liberada antes
    da chegada; nos curtos (rápido e injetável) a liberação costuma ocorrer depois, o que faz
    esses pacientes esperarem mais na poltrona (como no Painel de Indicadores do setor).
    """
    curtos = {"Rápido", "Injetável"}
    return {g: ({"pre": 0.20, "atraso": 10.0} if g in curtos else {"pre": 0.90, "atraso": 2.0})
            for g in PERFIS}


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
    # Meta de espera na poltrona (min): usada nos indicadores e gráficos de meta
    meta_espera: int = 30
    # Pacientes do interior (transporte da prefeitura). Todos "suposição a validar".
    frac_interior: float = 0.40  # fração dos pacientes do dia que vem do interior
    transporte_chega_de: int = 6 * 60 + 30  # o transporte chega a Fortaleza entre...
    transporte_chega_ate: int = 7 * 60 + 30  # ...6h30 e 7h30
    transporte_volta_de: int = 15 * 60  # e volta para o interior entre...
    transporte_volta_ate: int = 16 * 60 + 30  # ...15h00 e 16h30
    folga_transporte: int = 30  # proposta: liberar a poltrona X min antes do retorno
    # Tempos de processo (minutos)
    alta_atual: int = 15  # do fim da infusão até liberar a poltrona no Tasy (hoje)
    alta_antecipada: int = 5  # idem, com a alta preparada antes do fim da infusão
    transporte: int = 5  # da capela até a poltrona
    acomodacao: int = 10  # no cenário otimizado: paciente senta 10 min antes da bolsa chegar
    # Calibração do cenário atual (ajustada para reproduzir os números observados), por grupo:
    #   pre    = fração das prescrições liberadas antes da chegada do paciente
    #   atraso = mediana, em min, entre a chegada e a liberação (demais pacientes)
    calibracao: dict = field(default_factory=calibracao_padrao)
    atraso_liberacao_dispersao: float = 1.0  # espalhamento (log-normal) do atraso
    # Semente do gerador aleatório (mesma semente = mesmo dia)
    semente: int = 56  # escolhida por gerar um dia típico (próximo dos números observados)

    def copia(self) -> "Premissas":
        return copy.deepcopy(self)


def _contagem_por_perfil(n: int, perfis: dict) -> dict:
    """Divide n pacientes entre os perfis respeitando o mix (método do maior resto)."""
    soma = sum(p["mix"] for p in perfis.values()) or 1.0
    # Ordem fixa dos grupos: o desempate não pode depender da ordem do dicionário
    # (o app salva as premissas em JSON, que reordena as chaves)
    ordem = [p for p in PERFIS if p in perfis] + [p for p in perfis if p not in PERFIS]
    cotas = {nome: n * perfis[nome]["mix"] / soma for nome in ordem}
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
      Interior: interior (sim/não), chegada_transporte (quando o transporte chega a
      Fortaleza) e retorno_min (quando o transporte volta). Vazios para quem é da capital.
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

    # 2) Quem chega antes das 10h (57% hoje), sorteado entre todos os grupos. O horário
    #    de chegada de hoje não olha o horário limite: quem chega depois dele é remarcado.
    n_manha = int(round(prem.frac_antes_10h * n))
    idx = np.arange(n)
    ordem = rng.permutation(n)
    manha = set(ordem[:n_manha].tolist())

    dez_h = 10 * 60
    chegadas = np.empty(n)
    for i in idx:
        if i in manha:
            # Manhã: concentração logo na abertura (pico por volta das 8h)
            chegadas[i] = rng.triangular(prem.inicio_turno, prem.inicio_turno + 60, dez_h)
        else:
            # Depois das 10h: chegadas decrescendo até o fim da janela da tarde, iguais para
            # todos os grupos (hoje o horário de chegada não considera o horário limite)
            fim_janela = max(dez_h + 10, min(FIM_CHEGADAS_TARDE, prem.fim_turno - 60))
            chegadas[i] = rng.triangular(dez_h, dez_h, fim_janela)
    chegadas = np.floor(chegadas)

    # 2b) Pacientes do interior. Gerador separado: o dia calibrado não muda.
    #     Eles chegam cedo no transporte da prefeitura, mas HOJE são atendidos na vez
    #     deles (a hora de chegada à triagem é a mesma de qualquer paciente): ficam
    #     esperando desde a chegada do transporte e podem perder o retorno.
    rng_int = np.random.default_rng([prem.semente, 7])
    n_int = int(round(min(max(prem.frac_interior, 0.0), 1.0) * n))
    interior = np.isin(idx, rng_int.permutation(n)[:n_int])
    passo = 15  # horários do transporte em múltiplos de 15 min
    chega_v = rng_int.integers(prem.transporte_chega_de // passo,
                               prem.transporte_chega_ate // passo + 1, n) * passo
    volta_v = rng_int.integers(prem.transporte_volta_de // passo,
                               prem.transporte_volta_ate // passo + 1, n) * passo
    chegada_transporte = np.where(interior, np.minimum(chega_v, chegadas), np.nan)
    retorno = np.where(interior, volta_v, np.nan)

    df = pd.DataFrame({
        "perfil": perfis,  # grupo de tratamento (cor da folha do setor)
        "protocolo": protocolos,
        "limite_min": limites,  # horário limite para chegar à triagem com o farmacêutico
        "chegada_min": chegadas.astype(int),
        "interior": interior,
        "chegada_transporte": chegada_transporte,
        "retorno_min": retorno,
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
               "chegada_min", "interior", "chegada_transporte", "retorno_min",
               "u_pre", "u_antecedencia", "z_atraso"]]


def hhmm(minutos) -> str:
    """Converte minutos desde a meia-noite em texto 'HHhMM' (ex.: 545 -> '09h05')."""
    if minutos is None or pd.isna(minutos):
        return "—"
    m = int(round(minutos))
    return f"{m // 60:02d}h{m % 60:02d}"
