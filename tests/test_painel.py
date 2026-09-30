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


def _com_limite(ag, paciente, limite, remarcado=False, chegada=None):
    ag = ag.copy()
    i = ag.index[ag["paciente"] == paciente][0]
    ag.loc[i, "limite_min"] = limite
    ag.loc[i, "remarcado"] = remarcado
    if chegada is not None:
        ag.loc[i, "chegada"] = chegada
    return ag


def test_alerta_perto_do_horario_limite(ag):
    # PAC-002 chega às 8h50; limite às 9h00
    ag2 = _com_limite(ag, "PAC-002", 9 * 60)
    tipos = lambda t: [a["tipo"] for a in P.alertas(ag2, t)]
    assert "limite" in tipos(8 * 60 + 40)  # faltam 20 min e ainda não chegou
    assert "limite" not in tipos(8 * 60 + 20)  # faltam 40 min: ainda não é alerta
    assert "limite" not in tipos(8 * 60 + 55)  # já chegou à triagem (8h50)
    texto = next(a["texto"] for a in P.alertas(ag2, 8 * 60 + 40) if a["tipo"] == "limite")
    assert "PAC-002" in texto and "09h00" in texto and "faltam 20 min" in texto


def test_alerta_remarcado_depois_do_limite(ag):
    # PAC-002 chegaria às 9h10 com limite às 9h00: remarcado
    ag2 = _com_limite(ag, "PAC-002", 9 * 60, remarcado=True, chegada=9 * 60 + 10)
    antes = [a["tipo"] for a in P.alertas(ag2, 8 * 60 + 55)]
    depois = [a["tipo"] for a in P.alertas(ag2, 9 * 60 + 5)]
    assert "limite" in antes and "remarcado" not in antes
    assert "remarcado" in depois and "limite" not in depois


def test_ordem_dos_alertas(ag):
    ag2 = _com_limite(ag, "PAC-002", 9 * 60)
    tipos = [a["tipo"] for a in P.alertas(ag2, 8 * 60 + 40)]
    assert tipos == sorted(tipos, key=P.ORDEM_ALERTAS.get)
