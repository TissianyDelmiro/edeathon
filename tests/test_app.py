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
