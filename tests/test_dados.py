"""Testes da Fase 1: premissas e gerador do dia sintético."""
from dados import (A_CONFIRMAR, GRUPO_DA_COR, MINUTOS_SEXTA, PERFIS, Premissas,
                   carregar_protocolos, gerar_dia, hhmm)


def test_quantidade_e_ids_ficticios():
    df = gerar_dia(Premissas())
    assert len(df) == 90
    assert df["paciente"].is_unique
    assert df["paciente"].str.fullmatch(r"PAC-\d{3}").all()
    assert df.iloc[0]["paciente"] == "PAC-001"


def test_mix_por_perfil():
    prem = Premissas()
    contagem = gerar_dia(prem)["perfil"].value_counts()
    for perfil in PERFIS:
        esperado = prem.n_pacientes * prem.perfis[perfil]["mix"]
        assert abs(contagem[perfil] - esperado) <= 1


def test_57_por_cento_antes_das_10h():
    df = gerar_dia(Premissas())
    frac = (df["chegada_min"] < 600).mean()
    assert abs(frac - 0.57) <= 0.01


def test_chegadas_dentro_do_turno():
    prem = Premissas()
    df = gerar_dia(prem)
    assert (df["chegada_min"] >= prem.inicio_turno).all()
    # Toda infusão cabe no turno se começasse logo na chegada
    fim = df["chegada_min"] + df["preparo_min"] + df["infusao_min"]
    assert (fim <= prem.fim_turno).all()


def test_duracoes_vem_das_premissas_sem_alteracao():
    prem = Premissas()
    prem.perfis["Intermediário marrom"]["infusao"] = 133  # valor informado pelo hospital
    df = gerar_dia(prem)
    assert (df.loc[df["perfil"] == "Intermediário marrom", "infusao_min"] == 133).all()


def test_mesma_semente_mesmo_dia():
    a, b = gerar_dia(Premissas()), gerar_dia(Premissas())
    assert a.equals(b)
    c = gerar_dia(Premissas(semente=7))
    assert not a.equals(c)


def test_hhmm():
    assert hhmm(545) == "09h05"
    assert hhmm(None) == "—"


def test_tabela_de_protocolos_do_setor():
    tab = carregar_protocolos()
    assert len(tab) == 34
    assert tab["protocolo"].is_unique
    assert set(tab["cor"]) == set(GRUPO_DA_COR)
    # Exemplos conferidos com a folha do setor
    lim = tab.set_index("protocolo")
    assert lim.loc["TIP Alternativo", "limite_min"] == 11 * 60
    assert lim.loc["Herceptin + Perjeta (1ª vez)", "limite_min"] == 14 * 60 + 30
    assert lim.loc["Faslodex/Eligard/Filgrastin", "grupo"] == "Injetável"
    assert lim.loc["Irinotecano", "grupo"] == "Intermediário marrom"
    assert lim.loc["CAPOX ou XELOX", "grupo"] == "Intermediário laranja"
    assert (tab.loc[tab["cor"] == "vermelho", "grupo"] == "Longo").all()
    assert A_CONFIRMAR == {"Intermediário laranja", "Intermediário marrom"}


def test_paciente_recebe_protocolo_do_proprio_grupo():
    df = gerar_dia(Premissas())
    tab = carregar_protocolos().set_index("protocolo")
    assert (tab.loc[df["protocolo"], "grupo"].to_numpy() == df["perfil"].to_numpy()).all()
    assert (tab.loc[df["protocolo"], "limite_min"].to_numpy() == df["limite_min"].to_numpy()).all()


def test_sexta_feira_uma_hora_a_menos():
    normal = gerar_dia(Premissas())
    sexta = gerar_dia(Premissas(sexta_feira=True))
    assert (normal["protocolo"] == sexta["protocolo"]).all()
    assert ((normal["limite_min"] - sexta["limite_min"]) == MINUTOS_SEXTA).all()
