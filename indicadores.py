"""
Cálculo dos indicadores (KPIs) e das séries por hora usadas nos gráficos.

Funciona para qualquer agenda no formato de COLUNAS_AGENDA (cenário atual ou otimizado).
Definições (em linguagem simples, como aparecem na tela):
- Espera na poltrona (T2): minutos entre o paciente sentar e a bolsa chegar/começar a infusão.
- Horas de poltrona sem tratamento: espera na poltrona + tempo de alta, somadas no dia.
- Horas de quimioterapia: minutos de infusão realizados dentro do turno.
- Pico de pacientes: maior número de pacientes na unidade ao mesmo tempo
  (sentados ou aguardando poltrona na recepção).
- Ocupação da capela: % do tempo dos postos da capela usado com preparo
  (manhã = início do turno até 13h; tarde = 13h até o fim do turno).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dados import Premissas
from simulacao_atual import perdeu_transporte

MEIO_DIA = 13 * 60  # divisão manhã x tarde da capela

# Números observados no hospital (usados para validar a simulação do cenário atual)
REAL = {
    "t2_mediana": 13.0,
    "pct_espera_30": 21.0,
    "pct_espera_60": 9.0,
    "horas_sem_tratamento": 54.0,
    "pico_simultaneos": 49.0,
    "pct_antes_10h": 57.0,
    # Painel de Indicadores do setor: espera média por tipo (Rápido = antigo perfil A,
    # Injetável = antigo Suporte)
    "espera_media_rapido": 43.0,
    "espera_media_injetavel": 47.0,
}


def _sobreposicao(inicios, fins, a: float, b: float) -> float:
    """Soma dos minutos de cada intervalo [início, fim) que caem dentro de [a, b)."""
    ini = np.clip(np.asarray(inicios, dtype=float), a, b)
    fim = np.clip(np.asarray(fins, dtype=float), a, b)
    return float(np.nansum(fim - ini))


def _ocupacao_por_minuto(inicios, fins, t0: int, t1: int) -> np.ndarray:
    """Quantos intervalos estão ativos em cada minuto de [t0, t1)."""
    conta = np.zeros(t1 - t0 + 1)
    for a, b in zip(inicios, fins):
        if pd.isna(a) or pd.isna(b):
            continue
        ia = int(np.clip(np.floor(a) - t0, 0, t1 - t0))
        ib = int(np.clip(np.floor(b) - t0, 0, t1 - t0))
        conta[ia] += 1
        conta[ib] -= 1
    return np.cumsum(conta)[:-1]


def calcular_kpis(ag: pd.DataFrame, prem: Premissas, alta: int) -> dict:
    """Indicadores de uma agenda. `alta` = minutos da alta usados naquele cenário."""
    atend = ag.dropna(subset=["inicio_infusao"])
    t2 = (atend["inicio_infusao"] - atend["senta"]).to_numpy()
    ini, fim = prem.inicio_turno, prem.fim_turno
    cap = prem.capacidade_capela
    t_fim = int(max(fim, np.nanmax(ag["sai"]) if len(atend) else fim)) + 1
    na_unidade = _ocupacao_por_minuto(atend["chegada"], atend["sai"], ini, t_fim)
    por_grupo = pd.Series(t2, index=atend.index).groupby(atend["perfil"]).mean()
    interior = (ag["interior"].astype(bool) if "interior" in ag.columns
                else pd.Series(False, index=ag.index))
    return {
        "pacientes_interior": int(interior.sum()),
        "interior_perdeu_transporte": int(perdeu_transporte(ag).sum()),
        "interior_remarcados": int((interior & ag["remarcado"]).sum()),
        "pacientes_atendidos": len(atend),
        "remarcados": int(ag["remarcado"].sum()),
        "espera_media_rapido": float(por_grupo.get("Rápido", np.nan)),
        "espera_media_injetavel": float(por_grupo.get("Injetável", np.nan)),
        "horas_qt": _sobreposicao(atend["inicio_infusao"], atend["fim_infusao"], ini, fim) / 60,
        "horas_sem_tratamento": (t2.sum() + alta * len(atend)) / 60,
        "t2_mediana": float(np.median(t2)) if len(t2) else 0.0,
        "t2_p90": float(np.percentile(t2, 90)) if len(t2) else 0.0,
        "pct_espera_30": float((t2 > 30).mean() * 100) if len(t2) else 0.0,
        "pct_espera_60": float((t2 > 60).mean() * 100) if len(t2) else 0.0,
        "pico_simultaneos": int(na_unidade.max()) if len(na_unidade) else 0,
        "capela_manha": 100 * _sobreposicao(atend["inicio_preparo"], atend["fim_preparo"],
                                            ini, MEIO_DIA) / (cap * (MEIO_DIA - ini)),
        "capela_tarde": 100 * _sobreposicao(atend["inicio_preparo"], atend["fim_preparo"],
                                            MEIO_DIA, fim) / (cap * (fim - MEIO_DIA)),
        "termina_apos_turno": int((atend["sai"] > fim).sum()),
    }


# (chave, nome na tela, unidade, "maior é melhor?")
INDICADORES = [
    ("remarcados", "Pacientes remarcados por perder o horário limite", "pacientes", False),
    ("pacientes_atendidos", "Pacientes atendidos no dia", "pacientes", True),
    ("horas_qt", "Horas de quimioterapia no turno", "h", True),
    ("horas_sem_tratamento", "Horas de poltrona sem tratamento (espera + alta)", "h", False),
    ("t2_mediana", "Espera na poltrona – metade dos pacientes espera até", "min", False),
    ("t2_p90", "Espera na poltrona – 9 em cada 10 pacientes esperam até", "min", False),
    ("pct_espera_30", "Pacientes que esperam mais de 30 min", "%", False),
    ("pico_simultaneos", "Maior número de pacientes ao mesmo tempo na unidade", "pacientes", False),
    ("capela_manha", "Ocupação da capela de manhã (até 13h)", "%", None),
    ("capela_tarde", "Ocupação da capela à tarde (depois das 13h)", "%", None),
]


def tabela_comparativa(k_atual: dict, k_otim: dict) -> pd.DataFrame:
    """Tabela lado a lado com a variação em % (proposta em relação a hoje)."""
    linhas = []
    for chave, nome, unid, maior_melhor in INDICADORES:
        a, o = k_atual[chave], k_otim[chave]
        var = (o - a) / a * 100 if a else np.nan
        if maior_melhor is not None and not a and o:
            # Partindo de zero não há variação em %: avalia pela diferença
            avaliacao = "✅ Melhora" if maior_melhor else "⚠️ Piora"
        elif maior_melhor is None or np.isnan(var) or abs(var) < 0.5:
            avaliacao = "➖ Equilíbrio" if maior_melhor is None else "➖ Igual"
        elif (var > 0) == maior_melhor:
            avaliacao = "✅ Melhora"
        else:
            avaliacao = "⚠️ Piora"
        linhas.append({"Indicador": nome, "Unidade": unid, "Hoje": a, "Proposta": o,
                       "Variação (%)": var, "Resultado": avaliacao})
    return pd.DataFrame(linhas)


def tabela_calibracao(k_atual: dict, pct_antes_10h: float) -> pd.DataFrame:
    """Compara a simulação do cenário atual com os números observados no hospital."""
    simulado = dict(k_atual, pct_antes_10h=pct_antes_10h)
    nomes = {
        "pct_antes_10h": "Pacientes que chegam antes das 10h (%)",
        "t2_mediana": "Espera na poltrona – metade espera até (min)",
        "pct_espera_30": "Esperam mais de 30 min (%)",
        "pct_espera_60": "Esperam mais de 1 hora (%)",
        "horas_sem_tratamento": "Horas de poltrona sem tratamento por dia",
        "pico_simultaneos": "Maior número de pacientes ao mesmo tempo",
        "espera_media_rapido": "Espera média na poltrona – 🟢 Rápido (min)",
        "espera_media_injetavel": "Espera média na poltrona – 🔵 Injetável (min)",
    }
    return pd.DataFrame([{"Número": nome, "Observado no hospital": REAL[k],
                          "Simulação de hoje": simulado[k]} for k, nome in nomes.items()])


def carga_capela_por_hora(ag: pd.DataFrame, prem: Premissas) -> pd.DataFrame:
    """Ocupação da capela (%) em cada hora do turno."""
    linhas = []
    for h in range(prem.inicio_turno, prem.fim_turno, 60):
        minutos = _sobreposicao(ag["inicio_preparo"], ag["fim_preparo"], h, h + 60)
        linhas.append({"hora": h, "ocupacao": 100 * minutos / (60 * prem.capacidade_capela)})
    return pd.DataFrame(linhas)


def poltronas_por_hora(ag: pd.DataFrame, prem: Premissas) -> pd.DataFrame:
    """Máximo de poltronas ocupadas e de pacientes na unidade em cada hora."""
    t0, t1 = prem.inicio_turno, prem.fim_turno
    sent = _ocupacao_por_minuto(ag["senta"], ag["sai"], t0, t1)
    unid = _ocupacao_por_minuto(ag["chegada"], ag["sai"], t0, t1)
    linhas = []
    for i, h in enumerate(range(t0, t1, 60)):
        fatia = slice(i * 60, i * 60 + 60)
        linhas.append({"hora": h, "poltronas": int(sent[fatia].max()),
                       "na_unidade": int(unid[fatia].max())})
    return pd.DataFrame(linhas)


def ociosidade_por_hora(ag: pd.DataFrame, prem: Premissas) -> pd.DataFrame:
    """Ociosidade média em cada hora do turno.

    - poltronas_ociosas:   poltronas vazias (média da hora);
    - poltronas_sem_tratar: poltronas ocupadas por paciente que NÃO está em infusão
                            (esperando a bolsa ou esperando a alta): desperdício "escondido";
    - capela_ociosa:       % da capacidade da capela parada.
    """
    t0, t1 = prem.inicio_turno, prem.fim_turno
    at = ag.dropna(subset=["inicio_infusao"])
    ocupadas = _ocupacao_por_minuto(at["senta"], at["sai"], t0, t1)
    esperando = _ocupacao_por_minuto(at["senta"], at["inicio_infusao"], t0, t1)
    em_alta = _ocupacao_por_minuto(at["fim_infusao"], at["sai"], t0, t1)
    preparo = _ocupacao_por_minuto(at["inicio_preparo"], at["fim_preparo"], t0, t1)
    linhas = []
    for i, h in enumerate(range(t0, t1, 60)):
        fatia = slice(i * 60, min(i * 60 + 60, t1 - t0))
        linhas.append({
            "hora": h,
            "poltronas_ociosas": float(prem.n_poltronas - ocupadas[fatia].mean()),
            "poltronas_sem_tratar": float((esperando[fatia] + em_alta[fatia]).mean()),
            "capela_ociosa": float(100 * (1 - preparo[fatia].mean() / prem.capacidade_capela)),
        })
    return pd.DataFrame(linhas)
