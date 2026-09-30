"""
Imprevistos do dia: o que a equipe registra quando a realidade foge da agenda.

Tipos de registro (apenas o que ACONTECEU; o sistema não toma nenhuma decisão clínica):
- "atraso":  hora real em que o paciente chegou à triagem. Se passar do horário limite do
             protocolo, o paciente é remarcado (não dá mais para manipular no dia);
- "falta":   o paciente não veio. A poltrona fica livre e a bolsa sai da fila da capela;
- "bolsa":   a bolsa atrasou X minutos (ex.: devolução, falta de insumo);
- "termino": hora REAL de término da infusão informada pela enfermagem.

Recalcular o dia (sem replanejar): cada paciente continua na poltrona planejada. Se o
paciente anterior daquela poltrona sair mais tarde, o próximo espera na recepção.
Um paciente sem imprevisto e sem efeito cascata fica exatamente como no plano.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TIPOS = {
    "atraso": "⏰ Paciente atrasou",
    "falta": "🚫 Paciente faltou",
    "bolsa": "📦 Bolsa atrasou",
    "termino": "💧 Infusão terminou em outro horário",
}
TEMPOS = ["senta", "inicio_preparo", "fim_preparo", "bolsa_chega", "inicio_infusao",
          "fim_infusao", "sai"]


def validar(ocorrencia: dict, plano: pd.DataFrame) -> str | None:
    """Devolve uma mensagem de erro em português, ou None se o registro é válido."""
    linha = plano[plano["paciente"] == ocorrencia.get("paciente")]
    if linha.empty:
        return "Escolha um paciente da agenda do dia."
    r = linha.iloc[0]
    tipo, valor = ocorrencia.get("tipo"), ocorrencia.get("valor")
    if tipo not in TIPOS:
        return "Escolha o tipo de imprevisto."
    if pd.isna(r["inicio_infusao"]) and tipo != "falta":
        return f"{r['paciente']} não está na agenda de hoje (remarcado)."
    if tipo == "atraso" and (valor is None or valor < r["chegada"]):
        return "A hora real de chegada precisa ser depois do horário marcado."
    if tipo == "bolsa" and (valor is None or valor <= 0):
        return "Informe quantos minutos a bolsa atrasou (maior que zero)."
    if tipo == "termino" and (valor is None or valor <= r["inicio_infusao"]):
        return "A hora real de término precisa ser depois do início da infusão."
    return None


def aplicar(plano: pd.DataFrame, ocorrencias: list[dict], alta: int) -> pd.DataFrame:
    """Agenda REALIZADA: o plano com os imprevistos registrados e o efeito cascata.

    `alta` = minutos da alta usados no cenário (alta antecipada na proposta).
    """
    ag = plano.copy().reset_index(drop=True)
    ag["faltou"] = False
    ag["imprevisto"] = ""
    chegada_nova = ag["chegada"].astype(float).copy()
    atraso_bolsa = pd.Series(0.0, index=ag.index)
    termino_real = pd.Series(np.nan, index=ag.index)

    # O último registro de cada tipo vale (corrigir = registrar de novo)
    for oc in ocorrencias:
        idx = ag.index[ag["paciente"] == oc["paciente"]]
        if len(idx) == 0:
            continue
        i = idx[0]
        ag.at[i, "imprevisto"] = (ag.at[i, "imprevisto"] + " · " if ag.at[i, "imprevisto"]
                                  else "") + TIPOS[oc["tipo"]]
        if oc["tipo"] == "falta":
            ag.at[i, "faltou"] = True
        elif oc["tipo"] == "atraso":
            chegada_nova[i] = float(oc["valor"])
        elif oc["tipo"] == "bolsa":
            atraso_bolsa[i] = float(oc["valor"])
        elif oc["tipo"] == "termino":
            termino_real[i] = float(oc["valor"])

    # Chegou depois do horário limite do protocolo: remarcado para outro dia
    tarde = (chegada_nova > ag["limite_min"]) & ~ag["remarcado"] & ~ag["faltou"]
    ag["chegada"] = chegada_nova
    ag.loc[tarde, "remarcado"] = True
    fora = ag["remarcado"] | ag["faltou"]
    ag.loc[fora, TEMPOS] = np.nan

    # Bolsa atrasada: o preparo acontece mais tarde
    for col in ["inicio_preparo", "fim_preparo", "bolsa_chega"]:
        ag[col] = ag[col] + atraso_bolsa

    # Recalcula cada poltrona na ordem planejada (efeito cascata)
    livre_em: dict[int, float] = {}
    ordem = ag.loc[~fora].sort_values(["senta", "paciente"]).index
    for i in ordem:
        p = int(ag.at[i, "poltrona"])
        senta_plano, inicio_plano = plano.loc[i, "senta"], plano.loc[i, "inicio_infusao"]
        senta = max(ag.at[i, "chegada"], senta_plano, livre_em.get(p, -np.inf))
        inicio = max(inicio_plano + (senta - senta_plano), ag.at[i, "bolsa_chega"])
        fim = termino_real[i] if not np.isnan(termino_real[i]) else inicio + ag.at[i, "infusao_min"]
        fim = max(fim, inicio + 1)  # o registro de término vale, mas sempre depois do início
        ag.at[i, "senta"] = senta
        ag.at[i, "inicio_infusao"] = inicio
        ag.at[i, "fim_infusao"] = fim
        ag.at[i, "sai"] = fim + alta
        livre_em[p] = fim + alta
    return ag


def planejado_x_realizado(plano: pd.DataFrame, real: pd.DataFrame) -> pd.DataFrame:
    """Pacientes cujo dia mudou em relação ao plano (por imprevisto ou por cascata)."""
    p = plano.set_index("paciente")
    r = real.set_index("paciente")
    mudou = (r["imprevisto"] != "") | r["faltou"] | (r["remarcado"] != p["remarcado"]) | (
        (r["sai"] - p["sai"]).abs().fillna(0) > 0.5) | ((r["senta"] - p["senta"]).abs().fillna(0) > 0.5)
    ids = r.index[mudou]
    return pd.DataFrame({
        "paciente": ids,
        "imprevisto": r.loc[ids, "imprevisto"].replace("", "↪️ efeito em cascata").to_numpy(),
        "faltou": r.loc[ids, "faltou"].to_numpy(),
        "remarcado": r.loc[ids, "remarcado"].to_numpy(),
        "poltrona": p.loc[ids, "poltrona"].to_numpy(),
        "senta_plano": p.loc[ids, "senta"].to_numpy(),
        "senta_real": r.loc[ids, "senta"].to_numpy(),
        "sai_plano": p.loc[ids, "sai"].to_numpy(),
        "sai_real": r.loc[ids, "sai"].to_numpy(),
    })
