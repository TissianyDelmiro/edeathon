"""Teste do recarregamento: módulo antigo na memória é trocado pelo arquivo novo."""
import importlib
import sys

import painel
import recarregar


def test_modulo_antigo_na_memoria_e_recarregado(monkeypatch):
    # Simula o deploy: na memória está uma versão antiga de painel.alertas
    # (sem o parâmetro folga_transporte), como aconteceu no Streamlit Cloud
    def alertas_antigo(ag, t):
        return []

    monkeypatch.setattr(painel, "alertas", alertas_antigo)
    recarregar._versoes.clear()  # processo "novo" para o módulo recarregar
    recarregados = recarregar.atualizar()
    assert "painel" in recarregados
    assert sys.modules["painel"].alertas is not alertas_antigo
    assert "folga_transporte" in sys.modules["painel"].alertas.__code__.co_varnames


def test_sem_mudanca_nao_recarrega():
    recarregar.atualizar()  # registra as versões atuais
    assert recarregar.atualizar() == []


def test_arquivo_alterado_recarrega(monkeypatch):
    recarregar.atualizar()
    monkeypatch.setitem(recarregar._versoes, "dados", "versao-antiga")
    assert "dados" in recarregar.atualizar()
    importlib.import_module("dados")
