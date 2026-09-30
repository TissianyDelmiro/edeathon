"""
Componentes visuais acessíveis (fonte grande, alto contraste, cor + ícone + texto).

Visual "clínico institucional": faixa de cabeçalho azul-petróleo, fundo cinza-azulado
claro e blocos brancos. Pensado para tablet ou TV do setor e para quem tem pouca
familiaridade com tecnologia.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import painel as P
from dados import A_CONFIRMAR, ROTULO

AVISO = "Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy."

# Cores da identidade visual
PETROLEO = "#0b4f63"  # cabeçalho, abas selecionadas, cabeçalho das tabelas
TEXTO = "#102a33"  # texto principal (contraste > 13:1 no branco)
TEXTO_2 = "#3d5560"  # texto secundário (contraste > 7:1 no branco)
BORDA = "#d5dfe5"

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
COR_HOJE, COR_PROPOSTA = "#2a78d6", "#eb6834"

# Situação da poltrona: ícone, texto, cor forte (borda) e tinta clara (fundo do selo)
# (cores diferentes das dos grupos para não confundir situação com tipo de tratamento)
SITUACAO_POLTRONA = {
    P.LIVRE: ("✅", "Livre", "#52606b", "#f1f4f6"),
    P.AGUARDANDO: ("⏳", "Aguardando bolsa", "#b27600", "#fff5dc"),
    P.INFUSAO: ("💧", "Em infusão", PETROLEO, "#e3f1f5"),
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
/* ---------- Base: fonte grande e alto contraste ---------- */
.stApp {{ background: #eef3f6; }}
.stApp p, .stApp li, .stApp label, .stApp td, .stApp th, .stApp input,
.stApp [data-testid="stCaptionContainer"] {{ font-size: 20px !important; }}
.stApp h1, .stApp h1 * {{ font-size: 36px !important; font-weight: 800 !important; }}
.stApp h2, .stApp h2 * {{ font-size: 30px !important; font-weight: 800 !important; }}
.stApp h3, .stApp h3 * {{ font-size: 25px !important; font-weight: 800 !important; color: {PETROLEO}; }}
.stApp p, .stApp li, .stApp label {{ color: {TEXTO}; }}
.block-container {{ padding-top: 2.2rem !important; max-width: 1400px; }}

/* ---------- Cabeçalho institucional ---------- */
.cabecalho {{
  background: linear-gradient(90deg, {PETROLEO} 0%, #0e6f86 100%);
  color: #fff; border-radius: 16px; padding: 18px 24px; margin-bottom: 12px;
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  box-shadow: 0 4px 12px rgba(11, 79, 99, .25);
}}
.cabecalho .marca {{
  width: 58px; height: 58px; border-radius: 14px; background: #fff; color: {PETROLEO};
  font-size: 38px; font-weight: 900; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}}
.cabecalho .titulo {{ font-size: 30px; font-weight: 800; line-height: 1.15; }}
.cabecalho .sub {{ font-size: 19px; opacity: .95; margin-top: 2px; }}
.cabecalho .selo {{
  margin-left: auto; border: 2px solid #fff; border-radius: 999px; padding: 6px 16px;
  font-size: 18px; font-weight: 700; background: rgba(255, 255, 255, .12);
}}

/* ---------- Aviso fixo no topo ---------- */
.aviso-fixo {{
  position: sticky; top: 3.2rem; z-index: 999;
  background: #fff8e6; color: #3d2a00; border: 2px solid #e2b54a; border-left: 10px solid #b27600;
  border-radius: 12px; padding: 10px 16px; font-size: 20px; font-weight: 700; margin-bottom: 14px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, .08);
}}

/* ---------- Abas em formato de pílula ---------- */
.stTabs [role="tablist"] {{ gap: 10px; border-bottom: none !important; flex-wrap: wrap; }}
.stTabs [role="tab"] {{
  background: #fff; border: 2px solid #b9cbd4 !important; border-radius: 999px;
  padding: 10px 24px !important; height: auto !important;
}}
.stTabs [role="tab"] p {{ font-size: 22px !important; font-weight: 700 !important; color: {PETROLEO}; }}
.stTabs [role="tab"][aria-selected="true"] {{ background: {PETROLEO}; border-color: {PETROLEO} !important; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---------- Blocos brancos (st.container com chave "bloco_...") ---------- */
[class*="st-key-bloco"], [data-testid="stForm"] {{
  background: #fff; border: 1px solid {BORDA}; border-radius: 16px;
  padding: 18px 22px 22px; box-shadow: 0 2px 6px rgba(16, 42, 51, .07);
}}

/* ---------- Botões grandes ---------- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopover"] button {{
  min-height: 56px; padding: 10px 22px; border-width: 2px; border-radius: 12px;
}}
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p,
[data-testid="stPopover"] button p {{ font-size: 20px !important; font-weight: 700; }}
[data-testid="stPopover"] button {{ border-color: #9fb6c1; background: #f5f9fb; }}
[data-testid="stPopover"] button p {{ color: {PETROLEO} !important; }}
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
.grade {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }}
.poltrona {{
  background: #fff; border: 1px solid {BORDA}; border-left: 10px solid var(--cor);
  border-radius: 12px; padding: 10px 12px; color: {TEXTO}; line-height: 1.35;
  box-shadow: 0 1px 4px rgba(16, 42, 51, .10);
}}
.poltrona.critico {{ border: 3px solid var(--cor); border-left-width: 10px; }}
.poltrona .num {{ font-size: 18px; font-weight: 800; color: {TEXTO_2}; letter-spacing: .3px; }}
.poltrona .selo {{
  display: inline-block; background: var(--tinta); border: 2px solid var(--cor);
  border-radius: 999px; padding: 2px 12px; margin: 6px 0; font-size: 19px; font-weight: 800;
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
.rem-seta {{ align-self: center; font-size: 40px; color: {PETROLEO}; }}
.rem-nota {{ margin-top: 12px; font-size: 19px; color: {TEXTO}; }}

/* ---------- Tabelas ---------- */
.tabela-grande {{ width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid {BORDA};
                 border-radius: 12px; overflow: hidden; }}
.tabela-grande th {{ background: {PETROLEO}; color: #fff !important; text-align: left; padding: 12px; }}
.tabela-grande td {{ padding: 11px 12px; border-bottom: 1px solid #e3eaee; color: {TEXTO}; background: #fff; }}
.tabela-grande tr:nth-child(even) td {{ background: #f5f8fa; }}
.tabela-grande tr:last-child td {{ border-bottom: none; }}
</style>
"""


def aplicar_estilo():
    """Injeta o CSS do visual institucional e de acessibilidade."""
    st.markdown(CSS, unsafe_allow_html=True)


def cabecalho(subtitulo: str):
    """Faixa institucional do topo com o aviso fixo logo abaixo."""
    st.markdown(
        f'<div class="cabecalho" role="banner"><div class="marca" aria-hidden="true">✚</div>'
        f'<div><div class="titulo">Unidade de Quimioterapia</div>'
        f'<div class="sub">{html.escape(subtitulo)}</div></div>'
        f'<div class="selo">Protótipo · Ideathon CBEB 2026</div></div>'
        f'<div class="aviso-fixo" role="alert">⚠️ {AVISO}</div>',
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
