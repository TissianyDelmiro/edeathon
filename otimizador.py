"""
Modelo de otimização da agenda do dia com Google OR-Tools (CP-SAT).

Ideia: agendar cada paciente para que a bolsa já esteja pronta quando ele sentar
na poltrona (sistema puxado), espalhando o trabalho da capela ao longo do dia.

Variáveis (por paciente):
- slot de início da infusão (múltiplos de 10 min a partir do início do turno);
- início do preparo da bolsa na capela (em minutos);
- espera na poltrona (minutos entre sentar e começar a infusão);
- se o paciente cabe no turno (quando não cabe, fica fora e é penalizado).

Restrições:
- intervalo de preparo na capela: no máximo N bolsas ao mesmo tempo (cumulativa);
- intervalo de poltrona = acomodação + espera + infusão + alta:
  no máximo N poltronas ocupadas ao mesmo tempo (cumulativa);
- o paciente só começa a infusão quando a bolsa chegou (preparo + transporte);
- tudo dentro do turno.

Objetivo (soma ponderada, em ordem de importância):
1. maximizar as horas de quimioterapia realizadas dentro do turno;
2. suavizar a carga da capela (minimizar o maior volume de preparo em uma hora);
3. minimizar a espera total na poltrona;
4. minimizar o tempo em que a bolsa pronta fica parada antes da infusão.

As durações de preparo e infusão são lidas das premissas e NUNCA alteradas.
"""
from __future__ import annotations

import heapq
import time

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

from dados import Premissas
from simulacao_atual import COLUNAS_AGENDA

SLOT = 10  # minutos por slot da agenda

# Pesos do objetivo
PESO_FORA_DO_TURNO = 1000  # por minuto de infusão que não coube no turno
PESO_PICO_CAPELA = 20  # por minuto de preparo na hora mais carregada da capela
PESO_ESPERA = 10  # por minuto de espera do paciente na poltrona
PESO_BOLSA_PARADA = 1  # por minuto de bolsa pronta aguardando

STATUS_PT = {
    cp_model.OPTIMAL: "Solução ótima encontrada",
    cp_model.FEASIBLE: "Boa solução encontrada dentro do tempo limite (pode não ser a ótima)",
    cp_model.INFEASIBLE: "Não existe agenda possível com estas premissas",
    cp_model.MODEL_INVALID: "Erro no modelo (premissas inválidas)",
    cp_model.UNKNOWN: "Nenhuma agenda encontrada dentro do tempo limite",
}


def otimizar(dia: pd.DataFrame, prem: Premissas, limite_s: float = 20.0) -> dict:
    """Monta e resolve o modelo. Devolve dicionário com a agenda e o status."""
    t0 = time.time()
    m = cp_model.CpModel()
    ini, fim = prem.inicio_turno, prem.fim_turno
    n_horas = int(np.ceil((fim - ini) / 60))
    alta = prem.alta_antecipada

    presente, inicio_inf, inicio_prep, espera = [], [], [], []
    iv_capela, dem_capela, iv_poltrona = [], [], []
    horas_prep = []  # por paciente: lista de booleanos "preparo começa na hora h"

    for i, r in dia.reset_index(drop=True).iterrows():
        prep, inf = int(r["preparo_min"]), int(r["infusao_min"])
        x = m.new_bool_var(f"presente_{i}")
        # Primeiro slot possível: a bolsa precisa ser preparada e transportada
        k_min = int(np.ceil((prep + prem.transporte) / SLOT))
        # Último slot possível: infusão + alta terminam até o fim do turno
        k_max = (fim - ini - inf - alta) // SLOT
        if k_max < k_min:
            m.add(x == 0)  # não cabe no turno de jeito nenhum
            k_max = k_min
        k = m.new_int_var(k_min, k_max, f"slot_{i}")
        s_inf = m.new_int_var(ini, fim, f"inicio_inf_{i}")
        m.add(s_inf == ini + SLOT * k)

        # Preparo na capela, antes da infusão (com o transporte)
        s_prep = m.new_int_var(ini, fim, f"inicio_prep_{i}")
        m.add(s_prep + prep + prem.transporte <= s_inf).only_enforce_if(x)
        iv_capela.append(m.new_optional_fixed_size_interval_var(s_prep, prep, x, f"capela_{i}"))
        dem_capela.append(1)

        # Poltrona: paciente senta (acomodação + espera) antes da infusão e sai após a alta
        w = m.new_int_var(0, 60, f"espera_{i}")
        senta = m.new_int_var(ini - 120, fim, f"senta_{i}")
        m.add(senta == s_inf - prem.acomodacao - w)
        m.add(senta >= ini).only_enforce_if(x)
        dur_poltrona = m.new_int_var(prem.acomodacao + inf + alta,
                                     prem.acomodacao + 60 + inf + alta, f"dur_poltrona_{i}")
        m.add(dur_poltrona == prem.acomodacao + w + inf + alta)
        sai = m.new_int_var(ini - 120, fim + 400, f"sai_{i}")
        iv_poltrona.append(m.new_optional_interval_var(senta, dur_poltrona, sai, x, f"poltrona_{i}"))

        # Hora do turno em que o preparo começa (para medir a carga da capela por hora)
        hora = m.new_int_var(0, n_horas - 1, f"hora_prep_{i}")
        rel = m.new_int_var(0, fim - ini, f"rel_prep_{i}")
        m.add(rel == s_prep - ini)
        m.add_division_equality(hora, rel, 60)
        bools = []
        for h in range(n_horas):
            b = m.new_bool_var(f"prep_{i}_h{h}")
            m.add(hora == h).only_enforce_if(b)
            m.add(hora != h).only_enforce_if(b.Not())
            bools.append(b)
        horas_prep.append((bools, prep, x))

        presente.append(x); inicio_inf.append(s_inf); inicio_prep.append(s_prep); espera.append(w)

    # Restrições cumulativas: capela e poltronas
    m.add_cumulative(iv_capela, dem_capela, prem.capacidade_capela)
    m.add_cumulative(iv_poltrona, [1] * len(iv_poltrona), prem.n_poltronas)

    # Carga da capela por hora (minutos de preparo iniciados na hora) e seu pico
    pico = m.new_int_var(0, 60 * prem.capacidade_capela * 3, "pico_capela_hora")
    for h in range(n_horas):
        termos = []
        for bools, prep, x in horas_prep:
            y = m.new_bool_var("")
            m.add_multiplication_equality(y, [bools[h], x])
            termos.append(prep * y)
        m.add(sum(termos) <= pico)
    # Restrição redundante que ajuda o solver a provar a otimalidade:
    # o pico nunca é menor que a média de preparo por hora
    m.add(n_horas * pico >= sum(prep * x for _, prep, x in horas_prep))

    # Objetivo
    fora = [int(r["infusao_min"]) * (1 - x) for (_, r), x in zip(dia.iterrows(), presente)]
    parada = []
    for i, (_, r) in enumerate(dia.iterrows()):
        p = m.new_int_var(0, fim - ini, f"bolsa_parada_{i}")
        m.add(p == inicio_inf[i] - inicio_prep[i] - int(r["preparo_min"]) - prem.transporte
              ).only_enforce_if(presente[i])
        m.add(p == 0).only_enforce_if(presente[i].Not())
        parada.append(p)
    m.minimize(PESO_FORA_DO_TURNO * sum(fora) + PESO_PICO_CAPELA * pico
               + PESO_ESPERA * sum(espera) + PESO_BOLSA_PARADA * sum(parada))

    # Resolver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = limite_s
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = prem.semente
    # Para quando a solução estiver a menos de 2% do melhor valor possível
    solver.parameters.relative_gap_limit = 0.02
    status = solver.solve(m)
    resultado = {
        "status": solver.status_name(status),
        "status_texto": STATUS_PT.get(status, "Situação desconhecida"),
        "ok": status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
        "tempo_s": time.time() - t0,
        "agenda": None,
    }
    if resultado["ok"] and solver.objective_value > 0:
        # Distância máxima até a melhor agenda possível (0% = comprovadamente ótima)
        gap = (solver.objective_value - solver.best_objective_bound) / solver.objective_value
        resultado["distancia_otimo"] = max(0.0, gap)
        # (o OR-Tools também chama de "ótima" a solução que atingiu o limite de 2%)
        if gap > 0.001:
            resultado["status_texto"] = (f"Solução muito boa: no máximo {gap:.0%} "
                                         "distante da melhor agenda possível")
    if not resultado["ok"]:
        return resultado

    # Montar a agenda a partir da solução
    ag = dia[["paciente", "perfil", "protocolo", "limite_min", "preparo_min",
              "infusao_min"]].copy().reset_index(drop=True)
    ok = np.array([solver.boolean_value(x) for x in presente])
    s_inf = np.array([solver.value(v) for v in inicio_inf], dtype=float)
    s_prep = np.array([solver.value(v) for v in inicio_prep], dtype=float)
    w = np.array([solver.value(v) for v in espera], dtype=float)
    ag["inicio_infusao"] = s_inf
    ag["senta"] = s_inf - prem.acomodacao - w
    ag["chegada"] = ag["senta"]  # horário de chegada recomendado = hora de sentar
    ag["inicio_preparo"] = s_prep
    ag["liberacao"] = s_prep  # prescrição liberada com antecedência (agendamento prévio)
    ag["fim_preparo"] = s_prep + ag["preparo_min"]
    ag["bolsa_chega"] = ag["fim_preparo"] + prem.transporte
    ag["fim_infusao"] = s_inf + ag["infusao_min"]
    ag["sai"] = ag["fim_infusao"] + alta
    tempos = ["inicio_infusao", "senta", "chegada", "inicio_preparo", "liberacao",
              "fim_preparo", "bolsa_chega", "fim_infusao", "sai"]
    ag.loc[~ok, tempos] = np.nan
    ag["remarcado"] = ~ok  # quem não coube no dia precisaria ser remarcado
    ag["poltrona"] = _atribuir_recursos(ag["senta"], ag["sai"], prem.n_poltronas)
    ag["posto_capela"] = _atribuir_recursos(ag["inicio_preparo"], ag["fim_preparo"],
                                            prem.capacidade_capela)
    ag = ag[COLUNAS_AGENDA].sort_values("inicio_infusao", na_position="last").reset_index(drop=True)
    resultado["agenda"] = ag
    resultado["fora_do_turno"] = ag.loc[ag["inicio_infusao"].isna(), "paciente"].tolist()
    resultado["pico_capela_hora"] = solver.value(pico)
    return resultado


def _atribuir_recursos(inicios: pd.Series, fins: pd.Series, n: int) -> pd.Series:
    """Distribui intervalos entre n recursos numerados (poltronas ou postos da capela).

    Como a restrição cumulativa garante no máximo n intervalos simultâneos, dar a cada
    intervalo (em ordem de início) o recurso livre de menor número sempre funciona.
    """
    resultado = pd.Series(pd.NA, index=inicios.index, dtype="Int64")
    livres = list(range(1, n + 1))
    heapq.heapify(livres)
    ocupados = []  # (fim, recurso)
    for i in inicios.dropna().sort_values(kind="stable").index:
        while ocupados and ocupados[0][0] <= inicios[i]:
            heapq.heappush(livres, heapq.heappop(ocupados)[1])
        rec = heapq.heappop(livres)
        resultado[i] = rec
        heapq.heappush(ocupados, (fins[i], rec))
    return resultado
