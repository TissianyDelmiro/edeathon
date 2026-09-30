"""Testes da Fase 1: premissas e gerador do dia sintético."""
from dados import PERFIS, Premissas, gerar_dia, hhmm


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
    prem.perfis["Médio"]["infusao"] = 133  # valor informado pelo hospital
    df = gerar_dia(prem)
    assert (df.loc[df["perfil"] == "Médio", "infusao_min"] == 133).all()


def test_mesma_semente_mesmo_dia():
    a, b = gerar_dia(Premissas()), gerar_dia(Premissas())
    assert a.equals(b)
    c = gerar_dia(Premissas(semente=7))
    assert not a.equals(c)


def test_hhmm():
    assert hhmm(545) == "09h05"
    assert hhmm(None) == "—"
