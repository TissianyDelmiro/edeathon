"""
Estado da unidade em uma "hora atual" (usado no Painel do dia).

A partir da agenda (otimizada ou simulada), calcula para o instante t:
- situação de cada poltrona e a previsão de liberação;
- fila da capela ordenada pela próxima poltrona a liberar (sistema puxado);
- situação de cada bolsa;
- alertas para a equipe.
"""
from __future__ import annotations

import pandas as pd

from dados import ROTULO, hhmm

# Situações da poltrona (a interface associa cor + ícone + texto a cada uma)
LIVRE, AGUARDANDO, INFUSAO, ALTA = "livre", "aguardando", "infusao", "alta"

# Situações da bolsa, na ordem do processo
BOLSA_ETAPAS = ["Prescrita", "Em preparo", "Pronta", "Em transporte", "Instalada",
                "Infusão concluída"]

LIMITE_ESPERA = 30  # min: alerta de espera longa
AVISO_ALTA = 15  # min antes do fim da infusão: preparar a alta
AVISO_LIMITE = 30  # min antes do horário limite: paciente ainda não chegou à triagem

# Ordem dos alertas na tela (mais urgente primeiro)
AVISO_TRANSPORTE = 120  # min antes do retorno: avisar se a poltrona não libera a tempo

# Ordem dos alertas na tela (mais urgente primeiro)
ORDEM_ALERTAS = {"espera": 0, "transporte": 1, "limite": 2, "remarcado": 3, "alta": 4}


def estado_poltronas(ag: pd.DataFrame, t: float, n_poltronas: int) -> pd.DataFrame:
    """Uma linha por poltrona com a situação no instante t."""
    atend = ag.dropna(subset=["senta"])
    linhas = []
    for p in range(1, n_poltronas + 1):
        da_poltrona = atend[atend["poltrona"] == p].sort_values("senta")
        agora = da_poltrona[(da_poltrona["senta"] <= t) & (t < da_poltrona["sai"])]
        proximo = da_poltrona[da_poltrona["senta"] > t].head(1)
        linha = {"poltrona": p, "situacao": LIVRE, "paciente": None, "perfil": None,
                 "libera_em": None, "espera_min": 0.0, "minutos_para_fim": None,
                 "proximo": None, "proximo_em": None}
        if len(proximo):
            linha["proximo"] = proximo.iloc[0]["paciente"]
            linha["proximo_em"] = proximo.iloc[0]["senta"]
        if len(agora):
            r = agora.iloc[0]
            linha.update(paciente=r["paciente"], perfil=r["perfil"], libera_em=r["sai"])
            if t < r["inicio_infusao"]:
                linha["situacao"] = AGUARDANDO
                linha["espera_min"] = t - r["senta"]
            elif t < r["fim_infusao"]:
                linha["situacao"] = INFUSAO
                linha["minutos_para_fim"] = r["fim_infusao"] - t
            else:
                linha["situacao"] = ALTA
        linhas.append(linha)
    return pd.DataFrame(linhas)


def situacao_bolsa(r: pd.Series, t: float) -> str:
    """Situação da bolsa de um paciente no instante t."""
    if t < r["inicio_preparo"]:
        return "Prescrita"
    if t < r["fim_preparo"]:
        return "Em preparo"
    # A bolsa sai da farmácia a tempo de chegar na hora da infusão
    transporte = r["bolsa_chega"] - r["fim_preparo"]
    saida = max(r["fim_preparo"], r["inicio_infusao"] - transporte)
    if t < saida:
        return "Pronta"
    if t < r["inicio_infusao"]:
        return "Em transporte"
    if t < r["fim_infusao"]:
        return "Instalada"
    return "Infusão concluída"


def status_bolsas(ag: pd.DataFrame, t: float) -> pd.DataFrame:
    """Situação de todas as bolsas do dia no instante t."""
    atend = ag.dropna(subset=["inicio_preparo"]).copy()
    atend["situacao"] = [situacao_bolsa(r, t) for _, r in atend.iterrows()]
    return atend


def fila_capela(ag: pd.DataFrame, t: float) -> pd.DataFrame:
    """Bolsas ainda não prontas, ordenadas pela próxima poltrona a liberar.

    Para cada bolsa pendente, vê quando a poltrona reservada ao paciente fica livre
    (saída do paciente anterior). A capela prepara primeiro a bolsa da poltrona que
    libera antes: é o sistema puxado.
    """
    atend = ag.dropna(subset=["inicio_preparo"])
    pend = atend[atend["fim_preparo"] > t].copy()
    if pend.empty:
        return pd.DataFrame(columns=["Ordem", "Paciente", "Tipo de tratamento", "Poltrona",
                                     "Poltrona libera", "Situação da bolsa"])

    def libera(r):
        anteriores = atend[(atend["poltrona"] == r["poltrona"]) & (atend["sai"] <= r["senta"])]
        fim_anterior = anteriores["sai"].max() if len(anteriores) else None
        return fim_anterior if fim_anterior is not None and fim_anterior > t else t

    pend["libera"] = pend.apply(libera, axis=1)
    pend = pend.sort_values(["libera", "inicio_infusao"])
    return pd.DataFrame({
        "Ordem": range(1, len(pend) + 1),
        "Paciente": pend["paciente"],
        "Tipo de tratamento": pend["perfil"].map(ROTULO),
        "Poltrona": pend["poltrona"].astype("Int64"),
        "Poltrona libera": ["já está livre" if lib <= t else hhmm(lib) for lib in pend["libera"]],
        "Situação da bolsa": [situacao_bolsa(r, t) for _, r in pend.iterrows()],
    })


def alertas(ag: pd.DataFrame, t: float, folga_transporte: int = 30) -> list[dict]:
    """Alertas do instante t: espera acima de 30 min, transporte do interior em risco,
    perto do horário limite, remarcado por perder o horário limite e preparar alta."""
    lista = []
    # Interior: a poltrona só libera depois do retorno do transporte (menos a folga)
    if "interior" in ag.columns:
        no_dia = ag[ag["interior"].astype(bool) & ag["sai"].notna()]
        for _, r in no_dia.iterrows():
            retorno, sai = r["retorno_min"], r["sai"]
            if not (r["chegada"] <= t < sai) or sai <= retorno - folga_transporte:
                continue
            pol = "" if pd.isna(r["poltrona"]) else f" (poltrona {int(r['poltrona'])})"
            if t >= retorno:
                lista.append({
                    "tipo": "transporte", "poltrona": 0, "id": f"transporte:{r['paciente']}",
                    "curto": f"{r['paciente']} perdeu o transporte das {hhmm(retorno)}",
                    "texto": f"{r['paciente']}{pol} perdeu o transporte das {hhmm(retorno)}: "
                             f"a poltrona só libera às {hhmm(sai)}. Acionar o serviço social "
                             "para a volta ao interior."})
            elif retorno - t <= AVISO_TRANSPORTE:
                lista.append({
                    "tipo": "transporte", "poltrona": 0, "id": f"transporte:{r['paciente']}",
                    "curto": f"{r['paciente']}: transporte às {hhmm(retorno)}, sai às {hhmm(sai)}",
                    "texto": f"{r['paciente']}{pol} é do interior: o transporte volta às "
                             f"{hhmm(retorno)} e a poltrona só libera às {hhmm(sai)}. "
                             "Priorizar a bolsa e a alta deste paciente."})
    # Horário limite: o paciente precisa chegar à triagem com o farmacêutico até o limite
    for _, r in ag.iterrows():
        faltam = r["limite_min"] - t
        if r["chegada"] > t and 0 < faltam < AVISO_LIMITE:
            lista.append({"tipo": "limite", "poltrona": 0, "id": f"limite:{r['paciente']}",
                          "curto": f"{r['paciente']}: limite às {hhmm(r['limite_min'])} e ainda "
                                   "não chegou",
                          "texto": f"Perto do horário limite: {r['paciente']} ({r['protocolo']}) "
                                   f"ainda não chegou à triagem. Limite às "
                                   f"{hhmm(r['limite_min'])} (faltam {int(round(faltam))} min)"})
        elif r["remarcado"] and t >= r["limite_min"]:
            lista.append({"tipo": "remarcado", "poltrona": 0,
                          "id": f"remarcado:{r['paciente']}",
                          "curto": f"{r['paciente']} perdeu o horário limite: remarcado",
                          "texto": f"{r['paciente']} ({r['protocolo']}) perdeu o horário limite "
                                   f"das {hhmm(r['limite_min'])}: remarcado para outro dia"})
    atend = ag.dropna(subset=["senta"])
    for _, r in atend.iterrows():
        if r["senta"] <= t < r["inicio_infusao"] and t - r["senta"] > LIMITE_ESPERA:
            lista.append({"tipo": "espera", "poltrona": int(r["poltrona"]),
                          "id": f"espera:{r['paciente']}",
                          "curto": f"{r['paciente']} (poltrona {int(r['poltrona'])}): esperando "
                                   f"a bolsa há {int(t - r['senta'])} min",
                          "texto": f"{r['paciente']} (poltrona {int(r['poltrona'])}) está "
                                   f"aguardando a bolsa há {int(t - r['senta'])} min"})
        faltam = r["fim_infusao"] - t
        if r["inicio_infusao"] <= t and 0 < faltam <= AVISO_ALTA:
            lista.append({"tipo": "alta", "poltrona": int(r["poltrona"]),
                          "id": f"alta:{r['paciente']}",
                          "curto": f"{r['paciente']} (poltrona {int(r['poltrona'])}): preparar "
                                   f"a alta, faltam {int(round(faltam))} min",
                          "texto": f"{'Falta' if round(faltam) == 1 else 'Faltam'} {int(round(faltam))} "
                                   f"min para acabar a infusão de "
                                   f"{r['paciente']} (poltrona {int(r['poltrona'])}): "
                                   "preparar a alta"})
    return sorted(lista, key=lambda a: (ORDEM_ALERTAS[a["tipo"]], a["poltrona"]))


def na_recepcao(ag: pd.DataFrame, t: float) -> pd.DataFrame:
    """Pacientes que já chegaram mas ainda aguardam poltrona (acontece no cenário de hoje)."""
    return ag[(ag["chegada"] <= t) & (ag["senta"] > t)]


# ---------------------------------------------------------------------------
# Kanban do fluxo: cada paciente é um cartão; cada coluna, uma etapa
# ---------------------------------------------------------------------------
COLUNAS_KANBAN = [
    ("agendado", "📅 Agendado", "ainda não chegou"),
    ("chegou", "🚪 Chegou", "triagem / recepção"),
    ("aguardando", "⏳ Na poltrona", "aguardando a bolsa"),
    ("infusao", "💧 Em infusão", ""),
    ("alta", "🏁 Em alta", "liberando a poltrona"),
    ("concluido", "✅ Concluído", ""),
]
FORA_DO_DIA = [("remarcado", "❌ Remarcado"), ("faltou", "🚫 Faltou")]
# Selos de risco (a interface mostra ícone + texto, nunca só cor)
NO_PRAZO, ATENCAO, EM_RISCO = "no_prazo", "atencao", "em_risco"


def _coluna(r: pd.Series, t: float) -> str:
    if r.get("faltou", False):
        return "faltou"
    if r["remarcado"]:
        # Só vira "remarcado" quando o horário limite passa; antes disso está a caminho
        return "remarcado" if t >= r["limite_min"] else "agendado"
    if t < r["chegada"]:
        return "agendado"
    if t < r["senta"]:
        return "chegou"
    if t < r["inicio_infusao"]:
        return "aguardando"
    if t < r["fim_infusao"]:
        return "infusao"
    if t < r["sai"]:
        return "alta"
    return "concluido"


def _risco(r: pd.Series, coluna: str, t: float, folga_transporte: int) -> tuple[str, str]:
    """Selo de risco do cartão e o motivo, em linguagem simples."""
    if coluna in ("concluido", "remarcado", "faltou"):
        return "", ""
    interior = bool(r.get("interior", False)) and not pd.isna(r.get("retorno_min"))
    if interior and r["sai"] > r["retorno_min"]:
        return EM_RISCO, f"vai perder o transporte das {hhmm(r['retorno_min'])}"
    if coluna == "agendado" and r["chegada"] > r["limite_min"]:
        return EM_RISCO, f"vai perder o horário limite ({hhmm(r['limite_min'])})"
    if coluna == "aguardando" and t - r["senta"] > LIMITE_ESPERA:
        return EM_RISCO, f"esperando a bolsa há {int(t - r['senta'])} min"
    if interior and r["sai"] > r["retorno_min"] - folga_transporte:
        return ATENCAO, f"transporte sai às {hhmm(r['retorno_min'])}"
    if coluna == "agendado" and 0 < r["limite_min"] - t < AVISO_LIMITE:
        return ATENCAO, f"limite às {hhmm(r['limite_min'])}"
    if coluna == "aguardando" and t - r["senta"] > LIMITE_ESPERA / 2:
        return ATENCAO, f"esperando a bolsa há {int(t - r['senta'])} min"
    return NO_PRAZO, ""


def _detalhe(r: pd.Series, coluna: str, t: float) -> tuple[str, float]:
    """Texto do cartão e a chave de ordem dentro da coluna (menor = mais urgente)."""
    if coluna == "agendado":
        return f"chega às {hhmm(r['chegada'])}", r["chegada"]
    if coluna == "chegou":
        return f"senta às {hhmm(r['senta'])}", r["senta"]
    if coluna == "aguardando":
        return f"esperando há {int(t - r['senta'])} min", -(t - r["senta"])
    if coluna == "infusao":
        return f"termina às {hhmm(r['fim_infusao'])}", r["fim_infusao"]
    if coluna == "alta":
        return f"libera às {hhmm(r['sai'])}", r["sai"]
    if coluna == "concluido":
        return f"saiu às {hhmm(r['sai'])}", -r["sai"]
    return "", 0.0


def kanban(ag: pd.DataFrame, t: float, folga_transporte: int = 30) -> dict[str, list[dict]]:
    """Cartões de cada coluna do Kanban no instante t, já na ordem de prioridade.

    Dentro da coluna vêm primeiro os cartões em risco, depois os de atenção, e então a
    ordem natural da etapa (quem chega/termina antes, quem espera há mais tempo).
    """
    colunas: dict[str, list[dict]] = {c: [] for c, *_ in COLUNAS_KANBAN}
    colunas.update({c: [] for c, _ in FORA_DO_DIA})
    peso_risco = {EM_RISCO: 0, ATENCAO: 1, NO_PRAZO: 2, "": 2}
    for _, r in ag.iterrows():
        col = _coluna(r, t)
        risco, motivo = _risco(r, col, t, folga_transporte)
        detalhe, ordem = _detalhe(r, col, t)
        interior = bool(r.get("interior", False)) and not pd.isna(r.get("retorno_min"))
        colunas[col].append({
            "paciente": r["paciente"], "perfil": r["perfil"], "protocolo": r["protocolo"],
            "interior": interior,
            "retorno": hhmm(r["retorno_min"]) if interior else "",
            "poltrona": None if pd.isna(r.get("poltrona")) else int(r["poltrona"]),
            "risco": risco, "motivo": motivo, "detalhe": detalhe,
            "_ordem": (peso_risco[risco], ordem),
        })
    for cartoes in colunas.values():
        cartoes.sort(key=lambda c: c["_ordem"])
    return colunas


def ocupacao_kanban(ag: pd.DataFrame, t: float) -> dict[str, int]:
    """Quantos itens estão nos recursos limitados no instante t (limites do Kanban)."""
    at = ag.dropna(subset=["senta"])
    return {
        "poltronas": int(((at["senta"] <= t) & (t < at["sai"])).sum()),
        "capela": int(((at["inicio_preparo"] <= t) & (t < at["fim_preparo"])).sum()),
    }
