"""
Ganhos para o paciente: compara, paciente a paciente, o dia de HOJE (simulado) com a
PROPOSTA (agenda otimizada).

Tempo na unidade = da chegada até a poltrona ser liberada, dividido em:
- recepção:        chegada até sentar (hoje, quando a sala está lotada);
- espera poltrona: sentado aguardando a bolsa (inclui a acomodação planejada na proposta);
- infusão:         igual nos dois cenários (a duração é do hospital e nunca muda);
- alta:            fim da infusão até liberar a poltrona.

Pacientes do interior: o tempo conta desde a chegada do transporte da prefeitura (é
quando eles chegam à unidade), nos dois cenários, para a comparação ser justa.

Todos os pacientes são fictícios; os números são estimativas do modelo.
Na proposta o paciente chega no horário marcado: parte do ganho é tempo que ele passa
em casa em vez de esperar na unidade.
"""
from __future__ import annotations

import pandas as pd

ETAPAS = {  # nome na tela: (início, fim)
    "Recepção (sem poltrona)": ("chegada", "senta"),
    "Espera na poltrona": ("senta", "inicio_infusao"),
    "Infusão": ("inicio_infusao", "fim_infusao"),
    "Alta": ("fim_infusao", "sai"),
}


def jornada(atual: pd.DataFrame, otim: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por paciente com o tempo na unidade hoje e na proposta."""
    base = atual[["paciente", "perfil", "protocolo", "remarcado"]].rename(
        columns={"remarcado": "remarcado_hoje"})
    for nome, ag in (("hoje", atual), ("proposta", otim)):
        a = ag.set_index("paciente")
        inicio = a["chegada"]
        if "chegada_transporte" in a.columns:
            inicio = a["chegada_transporte"].where(a["interior"].astype(bool), a["chegada"])
        base[f"tempo_{nome}"] = base["paciente"].map(a["sai"] - inicio)
        base[f"espera_{nome}"] = base["paciente"].map(a["inicio_infusao"] - a["senta"])
        base[f"chegada_{nome}"] = base["paciente"].map(a["chegada"])
        base[f"inicio_infusao_{nome}"] = base["paciente"].map(a["inicio_infusao"])
    base["remarcado_proposta"] = base["tempo_proposta"].isna()
    base["ganho"] = base["tempo_hoje"] - base["tempo_proposta"]
    return base


def resumo(j: pd.DataFrame, meta_espera: int) -> dict:
    """Números de impacto para o topo do dashboard."""
    ambos = j.dropna(subset=["tempo_hoje", "tempo_proposta"])
    acima_hoje = int((j["espera_hoje"] > meta_espera).sum())
    acima_prop = int((j["espera_proposta"] > meta_espera).sum())
    return {
        "horas_economizadas": float(ambos["ganho"].clip(lower=0).sum() / 60),
        "horas_economizadas_liquidas": float(ambos["ganho"].sum() / 60),
        "pacientes_com_ganho": int((ambos["ganho"] > 0).sum()),
        "pacientes_comparados": len(ambos),
        "maior_ganho_min": float(ambos["ganho"].max()) if len(ambos) else 0.0,
        "remarcados_evitados": int((j["remarcado_hoje"] & ~j["remarcado_proposta"]).sum()),
        "acima_meta_hoje": acima_hoje,
        "acima_meta_proposta": acima_prop,
        "tempo_medio_hoje": float(ambos["tempo_hoje"].mean()) if len(ambos) else 0.0,
        "tempo_medio_proposta": float(ambos["tempo_proposta"].mean()) if len(ambos) else 0.0,
    }


def maiores_ganhos(j: pd.DataFrame, n: int = 6) -> pd.DataFrame:
    """Pacientes com o maior ganho de tempo (para os cartões de história)."""
    return j.dropna(subset=["ganho"]).sort_values("ganho", ascending=False).head(n)


def por_grupo(j: pd.DataFrame, ordem: list[str]) -> pd.DataFrame:
    """Tempo médio na unidade por tipo de tratamento, hoje x proposta."""
    ambos = j.dropna(subset=["tempo_hoje", "tempo_proposta"])
    g = ambos.groupby("perfil")[["tempo_hoje", "tempo_proposta"]].mean()
    return g.reindex([p for p in ordem if p in g.index]).reset_index()


def composicao(ag: pd.DataFrame) -> dict:
    """Horas somadas de cada etapa no dia (só pacientes atendidos)."""
    at = ag.dropna(subset=["inicio_infusao"])
    return {nome: float((at[fim] - at[ini]).clip(lower=0).sum() / 60)
            for nome, (ini, fim) in ETAPAS.items()}


def dentro_da_meta(ag: pd.DataFrame, meta_espera: int) -> float:
    """% dos pacientes atendidos com espera na poltrona dentro da meta."""
    at = ag.dropna(subset=["inicio_infusao"])
    if at.empty:
        return 0.0
    return float(((at["inicio_infusao"] - at["senta"]) <= meta_espera).mean() * 100)


def formatar_duracao(minutos: float) -> str:
    """125 -> '2h05'; 45 -> '45 min'."""
    if minutos is None or pd.isna(minutos):
        return "—"
    m = int(round(minutos))
    sinal = "-" if m < 0 else ""
    m = abs(m)
    return f"{sinal}{m // 60}h{m % 60:02d}" if m >= 60 else f"{sinal}{m} min"
