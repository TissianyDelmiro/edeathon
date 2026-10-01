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
ORDEM_ALERTAS = {"espera": 0, "limite": 1, "remarcado": 2, "alta": 3}


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


def alertas(ag: pd.DataFrame, t: float) -> list[dict]:
    """Alertas do instante t: espera acima de 30 min, perto do horário limite,
    remarcado por perder o horário limite e preparar alta."""
    lista = []
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
