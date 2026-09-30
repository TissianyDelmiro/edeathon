"""Testes da Fase 5: o app abre e cada aba roda sem erro."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _rodar():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_abre_com_aviso_e_abas():
    at = _rodar()
    textos = " ".join(m.value for m in at.markdown)
    assert "Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy." in textos
    assert [t.label for t in at.tabs] == ["🏥 Painel do dia", "📊 Hoje x Proposta",
                                         "📅 Agenda do dia", "⚙️ Premissas"]
    assert not at.error


def test_mudar_hora_e_cenario():
    at = _rodar()
    at.radio[0].set_value("Como é hoje (simulação)").run()
    assert not at.exception
    from datetime import time
    at.slider[0].set_value(time(11, 0)).run()
    assert not at.exception


def test_erro_de_mix_em_portugues():
    at = _rodar()
    at.number_input[0].set_value(50)  # total de pacientes
    at.button[0].click().run()  # botão do formulário
    assert not at.exception


def test_destaque_de_remarcacoes_na_comparacao():
    at = _rodar()
    textos = " ".join(m.value for m in at.markdown)
    assert "Pacientes remarcados por perder o horário limite" in textos
    assert "pacientes remarcados" in textos  # cartão de destaque (hoje: 2)
    assert "0 paciente" in textos or "✅ 0" in textos  # proposta: zero


def test_premissas_sexta_feira_e_folga():
    at = _rodar()
    at.checkbox[0].check()
    folga = next(n for n in at.number_input if n.label.startswith("Folga antes do horário limite"))
    folga.set_value(45)
    at.button[0].click().run()  # botão do formulário
    assert not at.exception
    prem = at.session_state["premissas"]
    assert prem.sexta_feira and prem.folga_limite == 45


def test_premissas_de_versao_antiga_na_sessao():
    """Depois de um deploy, a sessão pode trazer premissas com campos antigos."""
    import dataclasses

    @dataclasses.dataclass
    class PremissasAntigas:
        n_pacientes: int = 90
        frac_pre_liberada: float = 0.6  # campo que não existe mais

    at = AppTest.from_file(APP, default_timeout=90)
    at.session_state["premissas"] = PremissasAntigas()
    at.run()
    assert not at.exception, at.exception
    assert not at.error
    assert hasattr(at.session_state["premissas"], "folga_limite")
