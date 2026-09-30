"""Testes da Fase 5: o app abre e cada aba roda sem erro."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _botao(at, rotulo):
    """Botão pelo texto (a ordem dos botões na página muda quando a tela muda)."""
    return next(b for b in at.button if b.label == rotulo)


def _rodar():
    # Erro de sintaxe no app.py não aparece em at.exception: confere a compilação antes
    compile(Path(APP).read_text(encoding="utf-8"), APP, "exec")
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    assert at.tabs, "o app não desenhou nenhuma aba"
    return at


def test_app_abre_com_aviso_e_abas():
    at = _rodar()
    textos = " ".join(m.value for m in at.markdown)
    assert "Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy." in textos
    assert [t.label for t in at.tabs] == ["🏥 Painel do dia", "📊 Hoje x Proposta",
                                         "💚 O que melhorou", "📅 Agenda do dia",
                                         "⚙️ Premissas"]
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
    _botao(at, "▶️ Gerar dia sintético e calcular agenda").click().run()
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
    _botao(at, "▶️ Gerar dia sintético e calcular agenda").click().run()
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


def test_marca_sinfonia_e_rodape():
    at = _rodar()
    textos = " ".join(m.value for m in at.markdown)
    assert "Sinfonia" in textos
    assert "data:image/png;base64," in textos  # símbolo embutido no cabeçalho
    assert "Privacidade (LGPD)" in textos  # rodapé institucional


def test_registrar_e_desfazer_imprevisto():
    at = _rodar()
    # Paciente: fica o primeiro da agenda (padrão)
    tipo = next(s for s in at.selectbox if s.label == "O que aconteceu?")
    tipo.set_value("falta")
    next(b for b in at.button if b.label == "✅ Registrar").click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["ocorrencias"]) == 1
    textos = " ".join(m.value for m in at.markdown)
    assert "🚫 Faltou" in textos and "imprevistos registrados" in textos
    next(b for b in at.button if b.label == "↩️ Desfazer o último").click().run()
    assert not at.exception
    assert at.session_state["ocorrencias"] == []


def test_imprevisto_invalido_mostra_erro_em_portugues():
    at = _rodar()
    tipo = next(s for s in at.selectbox if s.label == "O que aconteceu?")
    tipo.set_value("atraso").run()
    hora = next(t for t in at.time_input if t.label == "Hora real de chegada à triagem")
    from datetime import time as _t
    hora.set_value(_t(6, 0))  # antes do horário marcado: inválido
    next(b for b in at.button if b.label == "✅ Registrar").click().run()
    assert not at.exception
    assert any("precisa ser depois do horário marcado" in e.value for e in at.error)
    assert at.session_state["ocorrencias"] == []


def test_mapa_das_poltronas_em_lista():
    at = _rodar()
    modo = next(r for r in at.radio if r.label == "Ver como")
    modo.set_value("📋 Lista").run()
    assert not at.exception, at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "Libera às" in textos and "tabela-grande" in textos
