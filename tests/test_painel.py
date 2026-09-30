"""Testes do estado do Painel do dia."""
import pandas as pd
import pytest

import painel as P
from simulacao_atual import COLUNAS_AGENDA


@pytest.fixture
def ag():
    # PAC-001: poltrona 1, senta 7h00, bolsa: preparo 6h50–7h00, transporte 5, infusão 7h40–8h40, sai 8h45
    # PAC-002: poltrona 1, senta 8h50 (depois do PAC-001), infusão 9h00–9h15, sai 9h20
    linhas = [
        ("PAC-001", 420, 420, 410, 410, 420, 425, 460, 520, 525, 1),
        ("PAC-002", 530, 530, 510, 520, 530, 535, 540, 555, 560, 1),
    ]
    df = pd.DataFrame(linhas, columns=["paciente", "chegada", "senta", "liberacao",
                                       "inicio_preparo", "fim_preparo", "bolsa_chega",
                                       "inicio_infusao", "fim_infusao", "sai", "poltrona"])
    df["perfil"] = "Rápido"
    df["protocolo"] = "Gemzar"
    df["limite_min"] = 17 * 60 + 30
    df["remarcado"] = False
    df["preparo_min"] = df["fim_preparo"] - df["inicio_preparo"]
    df["infusao_min"] = df["fim_infusao"] - df["inicio_infusao"]
    df["posto_capela"] = 1
    return df[COLUNAS_AGENDA]


def test_situacao_das_poltronas(ag):
    def sit(t):
        return P.estado_poltronas(ag, t, 2).set_index("poltrona").loc[1, "situacao"]
    assert sit(415) == P.LIVRE
    assert sit(430) == P.AGUARDANDO
    assert sit(500) == P.INFUSAO
    assert sit(522) == P.ALTA
    assert P.estado_poltronas(ag, 500, 2).set_index("poltrona").loc[1, "libera_em"] == 525
    assert P.estado_poltronas(ag, 500, 2).set_index("poltrona").loc[2, "situacao"] == P.LIVRE


def test_situacao_das_bolsas(ag):
    r = ag.iloc[0]
    assert P.situacao_bolsa(r, 405) == "Prescrita"
    assert P.situacao_bolsa(r, 415) == "Em preparo"
    assert P.situacao_bolsa(r, 430) == "Pronta"  # paciente sentado, bolsa aguardando
    assert P.situacao_bolsa(r, 457) == "Em transporte"
    assert P.situacao_bolsa(r, 470) == "Instalada"
    assert P.situacao_bolsa(r, 530) == "Infusão concluída"


def test_alertas(ag):
    tipos = {a["tipo"] for a in P.alertas(ag, 455)}  # espera de 35 min
    assert tipos == {"espera"}
    alerta = P.alertas(ag, 510)  # faltam 10 min
    assert alerta[0]["tipo"] == "alta" and "10 min" in alerta[0]["texto"]
    assert P.alertas(ag, 480) == []


def test_fila_capela_sistema_puxado(ag):
    fila = P.fila_capela(ag, 505)
    assert fila["Paciente"].tolist() == ["PAC-002"]
    assert fila.iloc[0]["Poltrona libera"] == "08h45"
