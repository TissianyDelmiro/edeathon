"""Testes dos imprevistos: o dia realizado recalculado a partir do plano."""
import numpy as np
import pandas as pd
import pytest

import ocorrencias as O
from dados import Premissas, gerar_dia
from otimizador import otimizar
from simulacao_atual import COLUNAS_AGENDA

ALTA = 5


@pytest.fixture
def plano():
    # Poltrona 1: PAC-001 senta 8h00, infusão 8h10–9h10, sai 9h15
    #             PAC-002 senta 9h20, infusão 9h30–10h00, sai 10h05
    # Poltrona 2: PAC-003 senta 8h00, infusão 8h10–8h25, sai 8h30 (limite 8h20)
    linhas = [
        ("PAC-001", 1, 480, 480, 490, 550, 555, 11 * 60),
        ("PAC-002", 1, 560, 560, 570, 600, 605, 12 * 60),
        ("PAC-003", 2, 480, 480, 490, 505, 510, 8 * 60 + 20),
    ]
    ag = pd.DataFrame(linhas, columns=["paciente", "poltrona", "chegada", "senta",
                                       "inicio_infusao", "fim_infusao", "sai", "limite_min"])
    ag["perfil"], ag["protocolo"], ag["remarcado"] = "Rápido", "Gemzar", False
    ag["infusao_min"] = ag["fim_infusao"] - ag["inicio_infusao"]
    ag["preparo_min"] = 9
    ag["bolsa_chega"] = ag["inicio_infusao"]
    ag["fim_preparo"] = ag["bolsa_chega"] - 5
    ag["inicio_preparo"] = ag["fim_preparo"] - 9
    ag["liberacao"] = ag["inicio_preparo"]
    ag["posto_capela"] = 1
    return ag[COLUNAS_AGENDA]


def _linha(ag, pac):
    return ag.set_index("paciente").loc[pac]


def test_sem_imprevisto_fica_igual_ao_plano(plano):
    real = O.aplicar(plano, [], ALTA)
    for col in ["senta", "inicio_infusao", "fim_infusao", "sai"]:
        assert (real[col].to_numpy() == plano[col].to_numpy()).all()
    assert O.planejado_x_realizado(plano, real).empty


def test_atraso_com_efeito_em_cascata(plano):
    # PAC-001 chega 8h40 (40 min atrasado): tudo dele anda 40 min e PAC-002 espera
    real = O.aplicar(plano, [{"paciente": "PAC-001", "tipo": "atraso", "valor": 520}], ALTA)
    p1, p2 = _linha(real, "PAC-001"), _linha(real, "PAC-002")
    assert p1["senta"] == 520 and p1["inicio_infusao"] == 530 and p1["sai"] == 595
    # PAC-002 chegou 9h20, mas a poltrona só libera 9h55: espera na recepção
    assert p2["chegada"] == 560 and p2["senta"] == 595
    assert p2["inicio_infusao"] == 605 and p2["sai"] == 640
    # Duração da infusão nunca muda
    assert p1["fim_infusao"] - p1["inicio_infusao"] == 60
    comp = O.planejado_x_realizado(plano, real).set_index("paciente")
    assert set(comp.index) == {"PAC-001", "PAC-002"}
    assert comp.loc["PAC-002", "imprevisto"] == "↪️ efeito em cascata"


def test_atraso_depois_do_horario_limite_vira_remarcado(plano):
    real = O.aplicar(plano, [{"paciente": "PAC-003", "tipo": "atraso", "valor": 8 * 60 + 30}],
                     ALTA)
    p3 = _linha(real, "PAC-003")
    assert p3["remarcado"] and np.isnan(p3["senta"]) and np.isnan(p3["inicio_preparo"])


def test_falta_libera_a_poltrona(plano):
    real = O.aplicar(plano, [{"paciente": "PAC-001", "tipo": "falta"}], ALTA)
    p1, p2 = _linha(real, "PAC-001"), _linha(real, "PAC-002")
    assert p1["faltou"] and np.isnan(p1["sai"]) and np.isnan(p1["inicio_preparo"])
    assert p2["senta"] == 560  # PAC-002 segue no horário


def test_bolsa_atrasada(plano):
    real = O.aplicar(plano, [{"paciente": "PAC-002", "tipo": "bolsa", "valor": 25}], ALTA)
    p2 = _linha(real, "PAC-002")
    assert p2["bolsa_chega"] == 595 and p2["inicio_infusao"] == 595
    assert p2["senta"] == 560  # sentou no horário e esperou a bolsa
    assert p2["fim_infusao"] == 625 and p2["sai"] == 630


def test_termino_real_da_infusao(plano):
    # Enfermagem registra término às 9h30 (em vez de 9h10): PAC-002 espera
    real = O.aplicar(plano, [{"paciente": "PAC-001", "tipo": "termino", "valor": 570}], ALTA)
    assert _linha(real, "PAC-001")["sai"] == 575
    assert _linha(real, "PAC-002")["senta"] == 575


def test_validacao_em_portugues(plano):
    assert O.validar({"paciente": "PAC-999", "tipo": "falta"}, plano)
    assert O.validar({"paciente": "PAC-001", "tipo": "atraso", "valor": 400}, plano)
    assert O.validar({"paciente": "PAC-001", "tipo": "bolsa", "valor": 0}, plano)
    assert O.validar({"paciente": "PAC-001", "tipo": "termino", "valor": 480}, plano)
    assert O.validar({"paciente": "PAC-001", "tipo": "atraso", "valor": 520}, plano) is None


def test_no_dia_otimizado_sem_imprevisto_nada_muda():
    prem = Premissas(n_pacientes=20)
    plano = otimizar(gerar_dia(prem), prem, limite_s=5)["agenda"]
    real = O.aplicar(plano, [], prem.alta_antecipada)
    assert O.planejado_x_realizado(plano, real).empty
