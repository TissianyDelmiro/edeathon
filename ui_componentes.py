"""
Componentes visuais do Sinfonia (fonte grande, alto contraste, cor + ícone + texto).

Identidade visual tirada do logo do Sinfonia (azul-marinho + verde-azulado), com
acabamento inspirado em sites de hospitais: barra superior fina, cabeçalho branco com
a marca, muito espaço em branco, cartões suaves e rodapé institucional.
Pensado para tablet ou TV do setor e para quem tem pouca familiaridade com tecnologia.
"""
from __future__ import annotations

import base64
import html
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

import painel as P
from dados import A_CONFIRMAR, ROTULO

AVISO = "Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy."

NOME_APP = "Sinfonia"
PASTA_IMG = Path(__file__).resolve().parent / "img"
LOGO = PASTA_IMG / "sinfonia-logo.png"
ICONE = PASTA_IMG / "sinfonia-icone.png"

# Cores da identidade visual (tiradas do logo; contraste conferido pela WCAG)
MARINHO = "#19375d"  # cabeçalho, abas, títulos, tabelas (12:1 no branco)
TEAL = "#08756e"  # destaques e a "proposta" nos gráficos (5,6:1 no branco)
TEAL_CLARO = "#e3f2f0"
FUNDO = "#f4f7f9"
TEXTO = "#102a33"  # texto principal (contraste > 13:1 no branco)
TEXTO_2 = "#3d5560"  # texto secundário (contraste > 7:1 no branco)
BORDA = "#dde5ea"

# Cores dos grupos, iguais às da folha do setor. Vermelho x verde se confundem para
# daltônicos (validado: não há tom que resolva sem mudar as cores do setor), então a cor
# NUNCA vai sozinha: sempre com o nome escrito, o emoji da cor e uma hachura por grupo.
CORES_PERFIL = {
    "Longo": "#c62828",
    "Intermediário laranja": "#ef6c00",
    "Intermediário marrom": "#7a3e0e",
    "Rápido": "#2e7d32",
    "Injetável": "#1565c0",
}
# Hachura de cada grupo nos gráficos (segunda forma de identificar, além da cor)
HACHURA_PERFIL = {
    "Longo": "",
    "Intermediário laranja": "/",
    "Intermediário marrom": "x",
    "Rápido": ".",
    "Injetável": "\\",
}
# As mesmas cores e hachuras indexadas pelo nome completo (usado nas legendas)
CORES_ROTULO = {ROTULO[g]: c for g, c in CORES_PERFIL.items()}
HACHURA_ROTULO = {ROTULO[g]: h for g, h in HACHURA_PERFIL.items()}
# Cores dos cenários nos gráficos (mesma ordem fixa da paleta)
# Hoje em cinza (o jeito antigo) e a proposta na cor da marca
COR_HOJE, COR_PROPOSTA = "#5f6f7e", TEAL

# Situação da poltrona: ícone, texto, cor forte (borda) e tinta clara (fundo do selo)
# (cores diferentes das dos grupos para não confundir situação com tipo de tratamento)
SITUACAO_POLTRONA = {
    P.LIVRE: ("✅", "Livre", "#52606b", "#f1f4f6"),
    P.AGUARDANDO: ("⏳", "Aguardando bolsa", "#b27600", "#fff5dc"),
    P.INFUSAO: ("💧", "Em infusão", MARINHO, "#e6edf6"),
    P.ALTA: ("🚪", "Em alta", "#4a3aa7", "#efebff"),
}
ESPERA_LONGA = ("⚠️", "Espera longa", "#c62828", "#fdeaea")
NEUTRO = ("#52606b", "#eef3f6")
OK = ("#0a8a0a", "#e9f7e9")  # tudo certo (verde de status, sempre com ✅ e texto)

ICONE_BOLSA = {
    "Prescrita": "📝", "Em preparo": "🧪", "Pronta": "📦",
    "Em transporte": "🚶", "Instalada": "💧", "Infusão concluída": "✔️",
}

CSS = f"""
<style>
/* ---------- Base: fonte grande, alto contraste e Open Sans ---------- */
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700;800&display=swap');
.stApp {{ background: {FUNDO}; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp td, .stApp th, .stApp input, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp [data-testid="stMarkdownContainer"] div,
.stApp [data-testid="stCaptionContainer"] {{ font-family: 'Open Sans', system-ui, sans-serif; }}
.stApp p, .stApp li, .stApp label, .stApp td, .stApp th, .stApp input,
.stApp [data-testid="stCaptionContainer"] {{ font-size: 20px !important; }}
.stApp h1, .stApp h1 * {{ font-size: 36px !important; font-weight: 800 !important; }}
.stApp h2, .stApp h2 * {{ font-size: 30px !important; font-weight: 800 !important; }}
.stApp h3, .stApp h3 * {{ font-size: 24px !important; font-weight: 700 !important; color: {MARINHO};
                          letter-spacing: -.2px; }}
.stApp p, .stApp li, .stApp label {{ color: {TEXTO}; }}
.block-container {{ padding-top: 2.2rem !important; max-width: 1400px; }}

/* ---------- Barra superior fina (como nos sites de hospital) ---------- */
.topo {{
  background: {MARINHO}; color: #fff; border-radius: 14px 14px 0 0; padding: 8px 22px;
  display: flex; gap: 22px; flex-wrap: wrap; align-items: center; font-size: 17px; font-weight: 600;
}}
.topo .dir {{ margin-left: auto; background: {TEAL}; border-radius: 999px; padding: 2px 14px; }}

/* ---------- Cabeçalho com a marca ---------- */
.cabecalho {{
  background: #fff; border: 1px solid {BORDA}; border-top: none; border-radius: 0 0 14px 14px;
  padding: 14px 22px; margin-bottom: 12px; display: flex; align-items: center; gap: 18px;
  flex-wrap: wrap; box-shadow: 0 6px 18px rgba(25, 55, 93, .08);
}}
.cabecalho img {{ height: 72px; width: auto; flex-shrink: 0; }}
.cabecalho .titulo {{ font-size: 34px; font-weight: 800; color: {MARINHO}; line-height: 1.05;
                      letter-spacing: -.5px; }}
.cabecalho .sub {{ font-size: 19px; color: {TEAL}; font-weight: 700; margin-top: 2px; }}
.cabecalho .chips {{ margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }}
.cabecalho .chip {{
  background: {FUNDO}; border: 1px solid {BORDA}; color: {TEXTO}; border-radius: 999px;
  padding: 6px 14px; font-size: 17px; font-weight: 700; white-space: nowrap;
}}

/* ---------- Aviso fixo no topo ---------- */
.aviso-fixo {{
  position: sticky; top: 3.2rem; z-index: 999;
  background: #fff8e6; color: #3d2a00; border: 1px solid #e2b54a; border-left: 8px solid #b27600;
  border-radius: 12px; padding: 10px 16px; font-size: 19px; font-weight: 700; margin-bottom: 16px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, .06);
}}

/* ---------- Abas ---------- */
.stTabs [role="tablist"] {{ gap: 8px; border-bottom: none !important; flex-wrap: wrap; }}
.stTabs [role="tab"] {{
  background: #fff; border: 1px solid {BORDA} !important; border-radius: 12px;
  padding: 10px 16px !important; height: auto !important; box-shadow: 0 1px 3px rgba(25, 55, 93, .06);
}}
.stTabs [role="tab"]:hover {{ border-color: {TEAL} !important; }}
.stTabs [role="tab"] p {{ font-size: 20px !important; font-weight: 700 !important; color: {MARINHO}; }}
.stTabs [role="tab"][aria-selected="true"] {{ background: {MARINHO}; border-color: {MARINHO} !important;
                                              box-shadow: inset 0 -5px 0 {TEAL}; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---------- Rodapé institucional ---------- */
.rodape {{
  margin-top: 28px; background: {MARINHO}; color: #dfe7f1; border-radius: 14px;
  padding: 18px 24px; display: flex; gap: 24px; flex-wrap: wrap; align-items: center;
  font-size: 17px; line-height: 1.5;
}}
.rodape b {{ color: #fff; }}
.rodape .marca {{ font-size: 22px; font-weight: 800; color: #fff; }}
.rodape .col {{ flex: 1 1 260px; }}

/* ---------- Blocos brancos (st.container com chave "bloco_...") ---------- */
[class*="st-key-bloco"], [data-testid="stForm"] {{
  background: #fff; border: 1px solid {BORDA}; border-radius: 16px;
  padding: 20px 24px 24px; box-shadow: 0 4px 14px rgba(25, 55, 93, .06);
}}

/* ---------- Botões grandes ---------- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopover"] button {{
  min-height: 56px; padding: 10px 22px; border-width: 2px; border-radius: 12px;
}}
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p,
[data-testid="stPopover"] button p {{ font-size: 20px !important; font-weight: 700; }}
[data-testid="stPopover"] button {{ border-color: {BORDA}; background: {TEAL_CLARO}; }}
[data-testid="stPopover"] button p {{ color: {MARINHO} !important; }}
.stApp [data-testid*="primary"] p, .stApp [kind*="primary"] p {{ color: #ffffff !important; }}

/* ---------- Cartões de resumo (números grandes) ---------- */
.resumo {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px; margin-bottom: 14px; }}
.kpi {{
  background: #fff; border: 1px solid {BORDA}; border-left: 10px solid var(--cor);
  border-radius: 14px; padding: 12px 14px; display: flex; align-items: center; gap: 12px;
  box-shadow: 0 2px 6px rgba(16, 42, 51, .07);
}}
.kpi .icone {{
  width: 52px; height: 52px; border-radius: 50%; background: var(--tinta);
  border: 2px solid var(--cor); display: flex; align-items: center; justify-content: center;
  font-size: 26px; flex-shrink: 0;
}}
.kpi .valor {{ font-size: 40px; font-weight: 800; color: {TEXTO}; line-height: 1; }}
.kpi > div {{ min-width: 0; }}
.kpi .rotulo {{ font-size: 19px; font-weight: 700; color: {TEXTO_2}; margin-top: 4px; }}
/* Variante empilhada (ícone em cima) para linhas com muitos cartões */
.resumo.empilhado .kpi {{ flex-direction: column; align-items: flex-start; gap: 8px; }}

/* ---------- Mapa das poltronas ---------- */
.grade {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }}
.poltrona {{
  background: #fff; border: 1px solid {BORDA}; border-left: 10px solid var(--cor);
  border-radius: 12px; padding: 10px 12px; color: {TEXTO}; line-height: 1.35;
  box-shadow: 0 1px 4px rgba(16, 42, 51, .10);
}}
.poltrona.critico {{ border: 3px solid var(--cor); border-left-width: 10px; }}
.poltrona .num {{ font-size: 18px; font-weight: 800; color: {TEXTO_2}; letter-spacing: .3px; }}
.poltrona .selo {{
  display: inline-block; background: var(--tinta); border: 2px solid var(--cor);
  border-radius: 999px; padding: 2px 12px; margin: 6px 0; font-size: 18px; font-weight: 800;
  white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}}
.poltrona .det {{ font-size: 18px; }}
.grupo {{ display: inline-flex; align-items: flex-start; gap: 6px; font-size: 17px; font-weight: 700;
          border: 1px solid {BORDA}; border-radius: 10px; padding: 2px 10px; margin: 2px 0;
          background: #fff; line-height: 1.25; }}
.grupo .bola {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; margin-top: 3px;
                border: 1px solid rgba(0, 0, 0, .25); }}
.grupo .obs {{ display: block; font-size: 15px; font-weight: 600; color: {TEXTO_2}; }}

/* ---------- Alertas ---------- */
.alerta {{
  background: var(--tinta); border: 2px solid var(--cor); border-left: 10px solid var(--cor);
  border-radius: 12px; padding: 12px 16px; margin: 8px 0; font-size: 20px; font-weight: 600; color: {TEXTO};
}}

/* ---------- Destaque de remarcações ---------- */
.rem {{ display: flex; align-items: stretch; gap: 14px; flex-wrap: wrap; }}
.rem-lado {{ flex: 1 1 240px; background: var(--tinta); border: 3px solid var(--cor);
            border-radius: 14px; padding: 14px 18px; color: {TEXTO}; }}
.rem-titulo {{ font-size: 20px; font-weight: 800; color: {TEXTO_2}; text-transform: uppercase; }}
.rem-num {{ font-size: 56px; font-weight: 900; line-height: 1.1; }}
.rem-texto {{ font-size: 20px; font-weight: 600; }}
.rem-seta {{ align-self: center; font-size: 40px; color: {TEAL}; }}
.rem-nota {{ margin-top: 12px; font-size: 19px; color: {TEXTO}; }}

/* ---------- Dashboard "O que melhorou" ---------- */
.impacto {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }}
.imp {{ background: #fff; border: 1px solid {BORDA}; border-top: 6px solid var(--cor);
        border-radius: 16px; padding: 16px 18px; box-shadow: 0 4px 14px rgba(25, 55, 93, .06); }}
.imp .ic {{ font-size: 28px; }}
.imp .num {{ font-size: 44px; font-weight: 800; color: {MARINHO}; line-height: 1.1; letter-spacing: -1px; }}
.imp .txt {{ font-size: 19px; font-weight: 700; color: {TEXTO}; }}
.imp .det {{ font-size: 17px; color: {TEXTO_2}; margin-top: 4px; }}
.historias {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
.hist {{ background: #fff; border: 1px solid {BORDA}; border-radius: 16px; padding: 16px 18px;
         box-shadow: 0 4px 14px rgba(25, 55, 93, .06); color: {TEXTO}; }}
.hist .quem {{ display: flex; justify-content: space-between; align-items: center; gap: 8px;
               font-size: 20px; font-weight: 800; color: {MARINHO}; flex-wrap: wrap; }}
.hist .antes-depois {{ display: flex; align-items: stretch; gap: 10px; margin: 12px 0 8px; }}
.hist .caixa {{ flex: 1 1 0; min-width: 0; border-radius: 12px; padding: 8px 12px; }}
.hist .caixa.hoje {{ background: #f1f3f5; border: 1px solid #cfd6dc; }}
.hist .caixa.prop {{ background: {TEAL_CLARO}; border: 1px solid #9fd0c9; }}
.hist .rot {{ font-size: 16px; font-weight: 700; color: {TEXTO_2}; text-transform: uppercase; }}
.hist .val {{ font-size: 28px; font-weight: 800; white-space: nowrap; }}
.hist .val.palavra {{ font-size: 21px; white-space: normal; }}
.hist .seta {{ font-size: 28px; color: {TEAL}; align-self: center; }}
.hist .ganho {{ display: inline-block; background: {TEAL}; color: #fff; border-radius: 999px;
                padding: 4px 14px; font-size: 19px; font-weight: 800; }}
.hist .ganho.neutro {{ background: #5f6f7e; }}
.hist .frase {{ font-size: 18px; margin-top: 8px; }}

/* ---------- Notificações no canto (st.toast) ---------- */
[data-testid="stToast"] {{ min-width: 380px; border-left: 8px solid {TEAL};
                           box-shadow: 0 8px 24px rgba(25, 55, 93, .25); }}
[data-testid="stToast"] p {{ font-size: 19px !important; font-weight: 600; color: {TEXTO}; }}

/* ---------- Quadro de alertas flutuante (canto inferior direito) ---------- */
.flutuante {{ position: fixed; right: 22px; bottom: 22px; z-index: 1000; width: 400px;
              max-width: calc(100vw - 44px); background: #fff; border: 1px solid {BORDA};
              border-left: 8px solid {TEAL}; border-radius: 16px;
              box-shadow: 0 10px 30px rgba(25, 55, 93, .28); }}
.flutuante summary {{ cursor: pointer; list-style: none; padding: 12px 16px; font-size: 20px;
                      font-weight: 800; color: {MARINHO}; }}
.flutuante summary::-webkit-details-marker {{ display: none; }}
.flutuante summary::after {{ content: "▲"; float: right; font-size: 16px; color: {TEXTO_2}; }}
.flutuante[open] summary::after {{ content: "▼"; }}
.fl-corpo {{ max-height: 32vh; overflow-y: auto; padding: 0 12px 12px; }}
.fl-item {{ font-size: 17px; font-weight: 600; color: {TEXTO}; padding: 6px 10px; margin-top: 6px;
            border-radius: 10px; background: #f5f8fa; border-left: 5px solid #b27600; }}
.fl-item[data-tipo="remarcado"], .fl-item[data-tipo="espera"] {{ border-left-color: #c62828; }}
.fl-item[data-tipo="alta"] {{ border-left-color: #4a3aa7; }}
.fl-item.novo {{ animation: fl-entrar .7s ease-out; background: #fff8e6; }}
.fl-selo {{ background: {TEAL}; color: #fff; border-radius: 999px; padding: 1px 8px;
            font-size: 14px; font-weight: 800; }}
.fl-badge {{ background: #c62828; color: #fff; border-radius: 999px; padding: 2px 10px;
             font-size: 15px; margin-left: 6px; animation: fl-pulsar 1.4s ease-in-out 3; }}
.fl-mais, .fl-vazio {{ font-size: 17px; color: {TEXTO_2}; padding: 8px 4px 0; }}
@keyframes fl-entrar {{ from {{ transform: translateX(60px); opacity: 0; }}
                        to {{ transform: translateX(0); opacity: 1; }} }}
@keyframes fl-pulsar {{ 50% {{ transform: scale(1.15); }} }}
@media (prefers-reduced-motion: reduce) {{ .fl-item.novo, .fl-badge {{ animation: none; }} }}

/* ---------- Kanban do fluxo ---------- */
.kb-topo {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 12px; }}
.kb-medidor {{ background: {TEAL_CLARO}; border: 1px solid #9fd0c9; border-radius: 999px;
               padding: 6px 16px; font-size: 18px; font-weight: 800; color: {MARINHO}; }}
.kb-medidor.cheio {{ background: #fdeaea; border-color: #c62828; color: #7f1d1d; }}
.kanban {{ display: grid; grid-template-columns: repeat(6, minmax(165px, 1fr));
           gap: 12px; overflow-x: auto; padding-bottom: 8px; }}
.kb-col {{ background: #eef3f6; border: 1px solid {BORDA}; border-radius: 14px; padding: 8px;
           min-width: 0;
           min-height: 160px; }}
.kb-cab {{ font-size: 19px; font-weight: 800; color: {MARINHO}; display: flex;
           justify-content: space-between; align-items: center; gap: 6px; }}
.kb-qtd {{ background: {MARINHO}; color: #fff; border-radius: 999px; padding: 1px 10px;
           font-size: 16px; }}
.kb-sub {{ font-size: 15px; color: {TEXTO_2}; margin-bottom: 8px; min-height: 20px; }}
.kb-card {{ background: #fff; border: 1px solid {BORDA}; border-left: 6px solid var(--cor);
            border-radius: 10px; padding: 8px 10px; margin-bottom: 8px; color: {TEXTO};
            box-shadow: 0 1px 3px rgba(25, 55, 93, .08); line-height: 1.35; }}
.kb-card .kb-id {{ display: flex; justify-content: space-between; gap: 6px; font-size: 18px;
                   font-weight: 800; color: {MARINHO}; }}
.kb-card .kb-det {{ font-size: 16px; color: {TEXTO}; margin-top: 2px; }}
.kb-card .kb-risco {{ font-size: 15px; font-weight: 700; margin-top: 4px; }}
.kb-int {{ display: inline-block; background: #efe7d8; border: 1px solid #b08850;
           color: #5a3d12; border-radius: 999px; padding: 0 8px; margin: 2px 0;
           font-size: 14px; font-weight: 800; max-width: 100%; }}
.kb-card .grupo {{ max-width: 100%; box-sizing: border-box; font-size: 16px; }}
.kb-mais {{ font-size: 15px; color: {TEXTO_2}; text-align: center; padding: 4px; }}
.kb-fora {{ margin-top: 10px; font-size: 17px; color: {TEXTO}; }}
.kb-fora b {{ color: #7f1d1d; }}

/* ---------- Tabelas ---------- */
.tabela-grande {{ width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid {BORDA};
                 border-radius: 12px; overflow: hidden; }}
.tabela-grande th {{ background: {MARINHO}; color: #fff !important; text-align: left; padding: 12px; }}
.tabela-grande td {{ padding: 11px 12px; border-bottom: 1px solid #e3eaee; color: {TEXTO}; background: #fff; }}
.tabela-grande tr:nth-child(even) td {{ background: #f5f8fa; }}
.tabela-grande tr:last-child td {{ border-bottom: none; }}
</style>
"""


def aplicar_estilo():
    """Injeta o CSS do visual institucional e de acessibilidade."""
    st.markdown(CSS, unsafe_allow_html=True)


@lru_cache(maxsize=4)
def imagem_base64(caminho: Path) -> str:
    """Imagem embutida no HTML (o Streamlit não serve arquivos locais direto no markdown)."""
    return base64.b64encode(caminho.read_bytes()).decode()


def cabecalho(subtitulo: str, chips: list[str], data_do_dia: date | None = None):
    """Barra superior fina + cabeçalho branco com a marca Sinfonia + aviso fixo."""
    dia = (data_do_dia or date.today()).strftime("%d/%m/%Y")
    # No cabeçalho vai só o símbolo: o nome "Sinfonia" já aparece escrito ao lado
    logo = (f'<img src="data:image/png;base64,{imagem_base64(ICONE)}" alt="Símbolo do {NOME_APP}">'
            if ICONE.exists() else "")
    st.markdown(
        f'<div class="topo" role="banner"><span>🗓️ {dia}</span>'
        f'<span>Unidade de Quimioterapia</span>'
        f'<span class="dir">Protótipo · Ideathon CBEB 2026</span></div>'
        f'<div class="cabecalho">{logo}'
        f'<div><div class="titulo">{NOME_APP}</div>'
        f'<div class="sub">{html.escape(subtitulo)}</div></div>'
        f'<div class="chips">{"".join(f"<span class=chip>{html.escape(c)}</span>" for c in chips)}'
        f'</div></div>'
        f'<div class="aviso-fixo" role="alert">⚠️ {AVISO}</div>',
        unsafe_allow_html=True)


def rodape():
    """Rodapé institucional: avisos do protótipo e da LGPD."""
    st.markdown(
        f'<div class="rodape" role="contentinfo">'
        f'<div class="col"><div class="marca">{NOME_APP}</div>'
        f'Fluxo da quimioterapia em harmonia: a bolsa pronta quando o paciente senta.</div>'
        f'<div class="col"><b>Protótipo com dados sintéticos.</b> Pacientes fictícios '
        f'(PAC-001, PAC-002...). Não substitui decisão clínica nem o sistema Tasy.</div>'
        f'<div class="col"><b>Privacidade (LGPD):</b> nenhum dado real ou sensível de paciente é '
        f'usado ou armazenado. Tempos de preparo e infusão são informados pelo hospital.</div>'
        f'</div>',
        unsafe_allow_html=True)


def bloco(nome: str):
    """Bloco branco com sombra (use com `with ui.bloco("nome"):`)."""
    return st.container(key=f"bloco_{nome}")


def ajuda(texto: str):
    """Botão 'O que é isso?' com uma explicação simples."""
    with st.popover("❓ O que é isso?"):
        st.markdown(texto)


def titulo_bloco(titulo: str, texto_ajuda: str):
    """Título de bloco com o botão de ajuda ao lado."""
    c1, c2 = st.columns([2, 1], vertical_alignment="center")
    c1.subheader(titulo)
    with c2:
        ajuda(texto_ajuda)


def cartao_resumo(icone: str, texto: str, valor, cor: str, tinta: str) -> str:
    """Cartão com número grande: ícone + número + texto (nunca só cor)."""
    return (f'<div class="kpi" style="--cor:{cor};--tinta:{tinta}">'
            f'<div class="icone" aria-hidden="true">{icone}</div>'
            f'<div><div class="valor">{valor}</div>'
            f'<div class="rotulo">{html.escape(texto)}</div></div></div>')


def resumo(cartoes: list[str], empilhado: bool = False):
    classe = "resumo empilhado" if empilhado else "resumo"
    st.markdown(f'<div class="{classe}">{"".join(cartoes)}</div>', unsafe_allow_html=True)


def selo_grupo(grupo: str) -> str:
    """Selo pequeno com a bolinha da cor e o nome do grupo escrito."""
    obs = '<span class="obs">a confirmar</span>' if grupo in A_CONFIRMAR else ""
    return (f'<span class="grupo"><span class="bola" style="background:{CORES_PERFIL[grupo]}" '
            f'aria-hidden="true"></span><span>{html.escape(grupo)}{obs}</span></span>')


def grade_poltronas(estado: pd.DataFrame, hhmm):
    """Mapa das poltronas: cada cartão tem cor + ícone + texto e a previsão de liberação."""
    cartoes = []
    for _, r in estado.iterrows():
        icone, texto, cor, tinta = SITUACAO_POLTRONA[r["situacao"]]
        classe = "poltrona"
        detalhes = []
        if r["situacao"] == P.AGUARDANDO and r["espera_min"] > P.LIMITE_ESPERA:
            icone, _, cor, tinta = ESPERA_LONGA
            classe += " critico"
            detalhes.append(f"<b>⚠️ Esperando há {int(r['espera_min'])} min</b>")
        elif r["situacao"] == P.AGUARDANDO:
            detalhes.append(f"Esperando há {int(r['espera_min'])} min")
        if pd.notna(r["paciente"]):
            detalhes.insert(0, f"<b>{r['paciente']}</b><br>{selo_grupo(r['perfil'])}")
            detalhes.append(f"Libera às <b>{hhmm(r['libera_em'])}</b>")
        elif pd.notna(r["proximo"]):
            detalhes.append(f"Próximo: <b>{r['proximo']}</b> às {hhmm(r['proximo_em'])}")
        else:
            detalhes.append("Sem mais pacientes hoje")
        cartoes.append(
            f'<div class="{classe}" style="--cor:{cor};--tinta:{tinta}" '
            f'aria-label="Poltrona {r["poltrona"]}: {texto}">'
            f'<div class="num">POLTRONA {int(r["poltrona"]):02d}</div>'
            f'<div class="selo">{icone} {texto}</div>'
            f'<div class="det">{"<br>".join(detalhes)}</div></div>')
    st.markdown(f'<div class="grade">{"".join(cartoes)}</div>', unsafe_allow_html=True)


def lista_poltronas(estado: pd.DataFrame, hhmm):
    """Mapa das poltronas em lista: uma linha por poltrona, a próxima a liberar primeiro.

    Poltronas livres vêm por último, ordenadas pelo próximo paciente.
    """
    linhas = []
    for _, r in estado.iterrows():
        icone, texto = SITUACAO_POLTRONA[r["situacao"]][:2]
        detalhe = ""
        if r["situacao"] == P.AGUARDANDO:
            espera = int(r["espera_min"])
            if espera > P.LIMITE_ESPERA:
                icone, texto = ESPERA_LONGA[0], "Aguardando bolsa (espera longa)"
            detalhe = f"esperando há {espera} min"
        elif r["situacao"] == P.INFUSAO and pd.notna(r["minutos_para_fim"]):
            detalhe = f"faltam {int(round(r['minutos_para_fim']))} min de infusão"
        if pd.notna(r["paciente"]):
            paciente, grupo = r["paciente"], ROTULO[r["perfil"]]
            libera, ordem = hhmm(r["libera_em"]), (0, r["libera_em"])
        else:
            paciente, grupo = "—", "—"
            libera = "livre agora"
            if pd.notna(r["proximo"]):
                detalhe = f"próximo: {r['proximo']} às {hhmm(r['proximo_em'])}"
                ordem = (1, r["proximo_em"])
            else:
                detalhe, ordem = "sem mais pacientes hoje", (2, 0)
        linhas.append({"_ordem": ordem, "Poltrona": f"{int(r['poltrona']):02d}",
                       "Situação": f"{icone} {texto}", "Paciente": paciente,
                       "Tipo de tratamento": grupo, "Detalhe": detalhe, "Libera às": libera})
    linhas.sort(key=lambda linha: linha["_ordem"])
    tabela(pd.DataFrame(linhas).drop(columns="_ordem"))


# Notificação no canto: (ícone, tempo na tela). Todas ficam ~10 s; remarcado fica até fechar.
NOTIFICACAO = {
    "remarcado": ("❌", "infinite"),
    "espera": ("⚠️", "long"),
    "limite": ("⚠️", "long"),
    "alta": ("🔔", "long"),
}
MAX_NOTIFICACOES = 3  # por vez, para não poluir a tela
ICONE_ALERTA = {"remarcado": "❌", "espera": "⚠️", "limite": "⚠️", "alta": "🔔"}


def notificar_novos(alertas: list[dict], contexto: str) -> set[str]:
    """Notificação no canto para os alertas que COMEÇARAM agora.

    Compara com os alertas da tela anterior: um alerta que continua ativo não se repete,
    mas se ele acabar e voltar (ou se a hora voltar), a notificação aparece de novo.
    Devolve os ids dos alertas novos (para destacar no quadro flutuante).
    """
    anteriores = st.session_state.setdefault("alertas_ativos", {})
    antes = anteriores.get(contexto, set())
    novos = [a for a in alertas if a["id"] not in antes]
    for a in novos[:MAX_NOTIFICACOES]:
        icone, duracao = NOTIFICACAO[a["tipo"]]
        # Texto curto: a notificação corta mensagens longas (o completo fica na central)
        st.toast(a["curto"], icon=icone, duration=duracao)
    if len(novos) > MAX_NOTIFICACOES:
        resto = len(novos) - MAX_NOTIFICACOES
        # (não começa com "+", que o markdown transformaria em item de lista)
        st.toast(f"Mais {resto} alerta{'s' if resto > 1 else ''} no quadro de alertas",
                 icon="🔔", duration="long")
    anteriores[contexto] = {a["id"] for a in alertas}
    return {a["id"] for a in novos}


def quadro_flutuante(alertas: list[dict], novos: set[str], maximo: int = 4):
    """Quadro de alertas fixo no canto inferior direito (sempre visível no Painel).

    Abre e fecha com um clique; abre sozinho quando chega alerta novo. Os novos entram
    deslizando e ganham o selo "novo".
    """
    if not alertas:
        corpo, resumo_txt = '<div class="fl-vazio">✅ Nenhum alerta agora</div>', "✅ Sem alertas"
    else:
        itens = []
        for a in alertas[:maximo]:
            classe = "fl-item novo" if a["id"] in novos else "fl-item"
            selo = '<span class="fl-selo">novo</span>' if a["id"] in novos else ""
            itens.append(f'<div class="{classe}" data-tipo="{a["tipo"]}">'
                         f'<span aria-hidden="true">{ICONE_ALERTA[a["tipo"]]}</span> '
                         f'{html.escape(a["curto"])} {selo}</div>')
        if len(alertas) > maximo:
            itens.append(f'<div class="fl-mais">e mais {len(alertas) - maximo} na '
                         'Central de alertas, logo abaixo</div>')
        corpo = "".join(itens)
        n_novos = len(novos)
        resumo_txt = (f"🔔 {len(alertas)} alerta{'s' if len(alertas) > 1 else ''} agora"
                      + (f' <span class="fl-badge">{n_novos} novo{"s" if n_novos > 1 else ""}'
                         '</span>' if n_novos else ""))
    aberto = " open" if novos else ""
    st.markdown(f'<details class="flutuante"{aberto} role="region" aria-label="Alertas">'
                f'<summary>{resumo_txt}</summary><div class="fl-corpo">{corpo}</div></details>',
                unsafe_allow_html=True)


# Selo de risco do Kanban: (ícone, texto, cor da borda). Sempre ícone + texto.
RISCO_KANBAN = {
    P.EM_RISCO: ("⛔", "Em risco", "#c62828"),
    P.ATENCAO: ("⚠️", "Atenção", "#b27600"),
    P.NO_PRAZO: ("", "", "#0a8a0a"),  # sem selo = no prazo (borda verde)
    "": ("", "", "#9aa8b3"),
}
# Quantos cartões mostrar por coluna (o resto vira "+ N")
MAX_CARTOES = {"concluido": 4}
MAX_CARTOES_PADRAO = 6


def kanban(colunas: dict[str, list[dict]], ocupacao: dict[str, int], n_poltronas: int,
           capacidade_capela: int):
    """Quadro Kanban: medidores dos limites + uma coluna por etapa do fluxo."""
    def medidor(icone, nome, usado, total):
        cheio = usado >= total
        aviso = " · ⚠️ no limite" if cheio else ""
        return (f'<span class="kb-medidor{" cheio" if cheio else ""}">{icone} {nome}: '
                f'{usado}/{total}{aviso}</span>')

    topo = (medidor("🪑", "Poltronas ocupadas", ocupacao["poltronas"], n_poltronas)
            + medidor("🧪", "Capela preparando", ocupacao["capela"], capacidade_capela))
    cols_html = []
    for chave, titulo, sub in P.COLUNAS_KANBAN:
        cartoes = colunas[chave]
        limite = MAX_CARTOES.get(chave, MAX_CARTOES_PADRAO)
        itens = []
        for c in cartoes[:limite]:
            icone, texto, cor = RISCO_KANBAN[c["risco"]]
            interior = (f'<div><span class="kb-int" title="Paciente do interior">'
                        f'🚐 volta {c["retorno"]}</span></div>' if c["interior"] else "")
            poltrona = f' · poltrona {c["poltrona"]}' if c["poltrona"] and chave in (
                "aguardando", "infusao", "alta") else ""
            risco = ""
            if texto:
                motivo = f': {html.escape(c["motivo"])}' if c["motivo"] else ""
                risco = f'<div class="kb-risco">{icone} {texto}{motivo}</div>'
            itens.append(
                f'<div class="kb-card" style="--cor:{cor}">'
                f'<div class="kb-id">{c["paciente"]}</div>{interior}'
                f'{selo_grupo(c["perfil"])}'
                f'<div class="kb-det">{html.escape(c["detalhe"])}{poltrona}</div>{risco}</div>')
        if len(cartoes) > limite:
            itens.append(f'<div class="kb-mais">+ {len(cartoes) - limite} pacientes</div>')
        cols_html.append(
            f'<div class="kb-col" aria-label="{html.escape(titulo)}">'
            f'<div class="kb-cab"><span>{titulo}</span><span class="kb-qtd">{len(cartoes)}</span>'
            f'</div><div class="kb-sub">{html.escape(sub)}</div>{"".join(itens)}</div>')
    fora = [f"<b>{titulo}:</b> " + ", ".join(c["paciente"] for c in colunas[chave])
            for chave, titulo in P.FORA_DO_DIA if colunas[chave]]
    fora_html = f'<div class="kb-fora">{" &nbsp;·&nbsp; ".join(fora)}</div>' if fora else ""
    st.markdown(f'<div class="kb-topo">{topo}</div><div class="kanban">{"".join(cols_html)}'
                f'</div>{fora_html}', unsafe_allow_html=True)


def caixa_alerta(tipo: str, texto: str):
    if tipo == "espera":
        icone, cor, tinta = "⚠️", ESPERA_LONGA[2], ESPERA_LONGA[3]
    elif tipo == "limite":
        icone, cor, tinta = "⚠️", "#b27600", "#fff5dc"
    elif tipo == "remarcado":
        icone, cor, tinta = "❌", ESPERA_LONGA[2], ESPERA_LONGA[3]
    elif tipo == "ok":
        icone, cor, tinta = "✅", *OK
    else:
        icone, cor, tinta = "🔔", *SITUACAO_POLTRONA[P.ALTA][2:]
    st.markdown(f'<div class="alerta" style="--cor:{cor};--tinta:{tinta}" role="alert">'
                f'{icone} {html.escape(texto)}</div>', unsafe_allow_html=True)


def destaque_remarcacoes(hoje: int, proposta: int, atend_hoje: int, atend_prop: int,
                         folga: int):
    """Cartão grande: remarcados hoje -> na proposta (número + ícone + texto)."""
    def lado(titulo, n, atend, cor, tinta, icone):
        texto = "paciente remarcado" if n == 1 else "pacientes remarcados"
        return (f'<div class="rem-lado" style="--cor:{cor};--tinta:{tinta}">'
                f'<div class="rem-titulo">{titulo}</div>'
                f'<div class="rem-num">{icone} {n}</div>'
                f'<div class="rem-texto">{texto}<br>{atend} atendidos no dia</div></div>')
    cor_hoje = ESPERA_LONGA[2:] if hoje else OK
    cor_prop = ESPERA_LONGA[2:] if proposta else OK
    st.markdown(
        '<div class="rem">'
        + lado("Hoje", hoje, atend_hoje, *cor_hoje, "❌" if hoje else "✅")
        + '<div class="rem-seta" aria-hidden="true">➜</div>'
        + lado("Proposta", proposta, atend_prop, *cor_prop, "❌" if proposta else "✅")
        + f'</div><div class="rem-nota">Na proposta, todo paciente chega à triagem pelo menos '
          f'<b>{folga} min</b> antes do horário limite do protocolo.</div>',
        unsafe_allow_html=True)


def cartoes_impacto(itens: list[tuple[str, str, str, str, str]]):
    """Números de impacto: (ícone, número, texto, detalhe, cor da borda)."""
    html_itens = "".join(
        f'<div class="imp" style="--cor:{cor}"><div class="ic" aria-hidden="true">{ic}</div>'
        f'<div class="num">{html.escape(num)}</div><div class="txt">{html.escape(txt)}</div>'
        f'<div class="det">{html.escape(det)}</div></div>'
        for ic, num, txt, det, cor in itens)
    st.markdown(f'<div class="impacto">{html_itens}</div>', unsafe_allow_html=True)


def _classe_valor(texto: str) -> str:
    """Números ('2h05') em fonte grande; palavras ('Remarcado') um pouco menores."""
    return "val" if texto[:1].isdigit() else "val palavra"


def cartoes_historia(historias: list[dict]):
    """Histórias de pacientes fictícios: antes (hoje) x depois (proposta).

    Cada item: paciente, grupo, hoje (texto), proposta (texto), selo (texto), frase,
    e neutro=True quando não há ganho a destacar.
    """
    partes = []
    for h in historias:
        classe = "ganho neutro" if h.get("neutro") else "ganho"
        partes.append(
            f'<div class="hist"><div class="quem"><span>{html.escape(h["paciente"])}</span>'
            f'{selo_grupo(h["grupo"])}</div>'
            f'<div class="antes-depois">'
            f'<div class="caixa hoje"><div class="rot">Hoje</div>'
            f'<div class="{_classe_valor(h["hoje"])}">{html.escape(h["hoje"])}</div></div>'
            f'<div class="seta" aria-hidden="true">➜</div>'
            f'<div class="caixa prop"><div class="rot">Com o Sinfonia</div>'
            f'<div class="{_classe_valor(h["proposta"])}">{html.escape(h["proposta"])}</div>'
            f'</div></div>'
            f'<span class="{classe}">{html.escape(h["selo"])}</span>'
            f'<div class="frase">{html.escape(h["frase"])}</div></div>')
    st.markdown(f'<div class="historias">{"".join(partes)}</div>', unsafe_allow_html=True)


def tabela(df: pd.DataFrame):
    """Tabela em HTML com fonte grande e alto contraste."""
    st.markdown(df.to_html(index=False, classes="tabela-grande", border=0, escape=True),
                unsafe_allow_html=True)


def estilo_grafico(fig, titulo: str, altura: int = 420):
    """Padrão dos gráficos: fonte grande, fundo branco, grade discreta."""
    fig.update_layout(
        # O título fica no bloco da página (com o botão de ajuda); aqui só para leitores de tela
        title=None, meta=titulo,
        font=dict(size=18, color=TEXTO),
        template="plotly_white", height=altura,
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=18), title=None),
        margin=dict(l=10, r=10, t=50, b=10),
        hoverlabel=dict(font_size=18),
    )
    fig.update_xaxes(gridcolor="#e3eaee", tickfont=dict(size=16), title_font=dict(size=18))
    fig.update_yaxes(gridcolor="#e3eaee", tickfont=dict(size=16), title_font=dict(size=18))
    return fig
