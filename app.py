"""
Sinfonia – Fluxo da quimioterapia (Ideathon CBEB 2026, Desafio 1).

Rodar com:  streamlit run app.py

Abas:
1. Painel do dia            – tela inicial, para tablet ou TV do setor
2. Hoje x Proposta          – cenário atual simulado x agenda otimizada
3. Agenda do dia            – Gantt das poltronas e da capela, tabela e exportação
4. Premissas                – valores de entrada (todos "suposição a validar")
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Antes de importar os módulos do app: recarrega os que mudaram no disco (evita rodar o
# app.py novo com módulos antigos na memória depois de um deploy no Streamlit Cloud)
import recarregar

recarregar.atualizar()

import ganhos as G  # noqa: E402
import indicadores as I
import ocorrencias as O
import painel as P
import ui_componentes as ui
from dados import (A_CONFIRMAR, GRUPO_DA_COR, PERFIS, ROTULO, Premissas, carregar_protocolos,
                   gerar_dia, hhmm)
from otimizador import otimizar
from simulacao_atual import simular_atual

st.set_page_config(page_title="Sinfonia – Fluxo da quimioterapia",
                   page_icon=str(ui.ICONE) if ui.ICONE.exists() else "💧", layout="wide")
ui.aplicar_estilo()

COR_DO_GRUPO = {g: c for c, g in GRUPO_DA_COR.items()}  # ex.: "Longo" -> "vermelho"
DATA_BASE = datetime(2026, 1, 1)  # data fictícia usada só para desenhar os gráficos de horário


# ---------------------------------------------------------------------------
# Cálculo (guardado em cache: só refaz quando as premissas ou o código mudam)
# ---------------------------------------------------------------------------
def versao_do_codigo() -> str:
    """Impressão digital dos módulos de cálculo e da tabela do setor.

    Entra na chave do cache: depois de uma atualização (ex.: novo deploy), o app não
    reaproveita um resultado calculado pela versão antiga do código.
    """
    pasta = Path(__file__).resolve().parent
    arquivos = ["dados.py", "simulacao_atual.py", "otimizador.py", "indicadores.py",
                "data/horarios_limite.csv"]
    h = hashlib.sha256()
    for nome in arquivos:
        h.update((pasta / nome).read_bytes())
    return h.hexdigest()[:12]


@st.cache_data(show_spinner=False, max_entries=10)
def calcular(premissas_json: str, versao: str) -> dict:
    prem = Premissas(**json.loads(premissas_json))
    dia = gerar_dia(prem)
    atual = simular_atual(dia, prem)
    otim = otimizar(dia, prem, limite_s=20)
    k_atual = I.calcular_kpis(atual, prem, prem.alta_atual)
    k_otim = I.calcular_kpis(otim["agenda"], prem, prem.alta_antecipada) if otim["ok"] else None
    return {"dia": dia, "atual": atual, "otim": otim, "k_atual": k_atual, "k_otim": k_otim}


def para_json(prem: Premissas) -> str:
    return json.dumps(dataclasses.asdict(prem), sort_keys=True)


CAMPOS_PREMISSAS = {f.name for f in dataclasses.fields(Premissas)}
salvas = st.session_state.get("premissas")
# Premissas guardadas por uma versão antiga do app (campos diferentes) voltam ao padrão
if salvas is None or set(dataclasses.asdict(salvas)) != CAMPOS_PREMISSAS:
    st.session_state.premissas = Premissas()
prem: Premissas = st.session_state.premissas

try:
    with st.spinner("⏳ Calculando a melhor agenda do dia… isso pode levar até 20 segundos."):
        R = calcular(para_json(prem), versao_do_codigo())
except Exception as erro:  # mensagem clara em vez de erro técnico
    st.error("❌ Não foi possível montar o dia com estas premissas. Confira os valores na aba "
             "**Premissas** (por exemplo: número de pacientes e porcentagens por tipo de "
             "tratamento) e tente de novo.")
    with st.expander("Detalhe técnico (para a equipe de TI)"):
        st.code(repr(erro))
    st.stop()

otim_ok = R["otim"]["ok"]
if not otim_ok:
    st.error(f"❌ A agenda organizada não pôde ser montada: {R['otim']['status_texto']}. "
             "Tente reduzir o número de pacientes ou aumentar poltronas na aba Premissas. "
             "O painel mostra, por enquanto, a simulação de como é hoje.")


def em_datetime(minutos: pd.Series) -> pd.Series:
    return DATA_BASE + pd.to_timedelta(minutos, unit="min")


def eixo_horas(fig):
    fig.update_xaxes(tickformat="%Hh", dtick=3600000, title=None)
    return fig


ui.cabecalho(
    "Fluxo da quimioterapia em harmonia",
    [f"👥 {prem.n_pacientes} pacientes (fictícios)", f"🪑 {prem.n_poltronas} poltronas",
     f"🧪 Capela: {prem.capacidade_capela} postos",
     f"🕖 {hhmm(prem.inicio_turno)}–{hhmm(prem.fim_turno)}"]
    + (["📅 Sexta-feira"] if prem.sexta_feira else []))

aba_painel, aba_comparar, aba_melhorou, aba_agenda, aba_premissas = st.tabs(
    ["🏥 Painel do dia", "📊 Hoje x Proposta", "💚 O que melhorou", "📅 Agenda do dia",
     "⚙️ Premissas"])

# ---------------------------------------------------------------------------
# Aba 1 – Painel do dia
# ---------------------------------------------------------------------------
with aba_painel:
    with ui.bloco("controles"):
        c1, c2 = st.columns([1, 2])
        with c1:
            opcoes = ["Proposta (agenda organizada)", "Como é hoje (simulação)"]
            escolha = st.radio("Qual agenda mostrar?", opcoes if otim_ok else opcoes[1:],
                               horizontal=False)
        with c2:
            # Começa às 9h30 (horário de movimento), dentro dos limites do turno
            inicial = min(max(9 * 60 + 30, prem.inicio_turno), prem.fim_turno)
            hora = st.slider("🕒 Hora atual (arraste para avançar o dia)",
                             min_value=time(prem.inicio_turno // 60, prem.inicio_turno % 60),
                             max_value=time(prem.fim_turno // 60, prem.fim_turno % 60),
                             value=time(inicial // 60, inicial % 60),
                             step=timedelta(minutes=5), format="HH:mm")

    t = hora.hour * 60 + hora.minute

    # Imprevistos registrados valem para o dia atual (zeram quando as premissas mudam)
    chave_dia = para_json(prem) + versao_do_codigo()
    if st.session_state.get("ocorrencias_chave") != chave_dia:
        st.session_state.ocorrencias_chave = chave_dia
        st.session_state.ocorrencias = []
    ocorrencias = st.session_state.ocorrencias
    usa_proposta = escolha.startswith("Proposta")
    if usa_proposta:
        plano = R["otim"]["agenda"]
        ag = O.aplicar(plano, ocorrencias, prem.alta_antecipada)
    else:
        ag = R["atual"]

    with ui.bloco("imprevistos"):
        titulo = "📝 Registrar imprevisto" + (f" ({len(ocorrencias)} registrado"
                                             f"{'s' if len(ocorrencias) != 1 else ''})"
                                             if ocorrencias else "")
        ui.titulo_bloco(titulo, (
            "Quando o dia foge da agenda, registre aqui **o que aconteceu**. O painel, os "
            "alertas e a fila da capela são recalculados na hora.\n\n"
            "- **⏰ Paciente atrasou**: hora real de chegada à triagem. Depois do horário "
            "limite do protocolo, o paciente é remarcado.\n"
            "- **🚫 Paciente faltou**: a poltrona fica livre e a bolsa sai da fila.\n"
            "- **📦 Bolsa atrasou**: minutos de atraso (devolução, falta de insumo...).\n"
            "- **💧 Infusão terminou em outro horário**: hora real informada pela "
            "enfermagem.\n"
            "- **🚐 Transporte mudou o horário de volta**: novo horário avisado pela "
            "prefeitura (só para pacientes do interior).\n\n"
            "Cada paciente continua na poltrona planejada: se o anterior sair mais tarde, o "
            "próximo espera. É só um **registro**: o sistema não toma decisão clínica."))
        if not usa_proposta:
            st.info("ℹ️ Os imprevistos são registrados na **agenda organizada**. Escolha "
                    "\"Proposta (agenda organizada)\" acima para registrar.")
        else:
            with st.expander("Abrir o registro de imprevistos", expanded=bool(ocorrencias)):
                na_agenda = plano.sort_values("chegada")
                opcoes_pac = {
                    r["paciente"]: (f"{r['paciente']}{' 🚐' if r.get('interior', False) else ''}"
                                    f" · {r['protocolo']} · chega "
                                    f"{hhmm(r['chegada'])} · poltrona "
                                    f"{'—' if pd.isna(r['poltrona']) else int(r['poltrona'])}")
                    for _, r in na_agenda.iterrows()}
                c1, c2 = st.columns([3, 2])
                pac = c1.selectbox("Paciente", list(opcoes_pac), format_func=opcoes_pac.get)
                tipo = c2.selectbox("O que aconteceu?", list(O.TIPOS), format_func=O.TIPOS.get)
                linha = plano.set_index("paciente").loc[pac]
                valor = None
                if tipo == "atraso":
                    base = int(linha["chegada"]) + 30
                    h = st.time_input("Hora real de chegada à triagem",
                                      time(min(base, 23 * 60) // 60, min(base, 23 * 60) % 60),
                                      step=300)
                    valor = h.hour * 60 + h.minute
                    st.caption(f"Marcado para {hhmm(linha['chegada'])} · horário limite do "
                               f"protocolo: {hhmm(linha['limite_min'])}")
                elif tipo == "bolsa":
                    valor = st.number_input("Quantos minutos a bolsa atrasou?", 1, 240, 20)
                elif tipo == "transporte":
                    if bool(linha.get("interior", False)):
                        base = int(linha["retorno_min"]) - 60
                        h = st.time_input("Novo horário de volta do transporte",
                                          time(base // 60, base % 60), step=300)
                        valor = h.hour * 60 + h.minute
                        st.caption(f"Horário previsto: {hhmm(linha['retorno_min'])} · a poltrona "
                                   f"libera às {hhmm(linha['sai'])}")
                    else:
                        st.caption("Este paciente não é do interior.")
                elif tipo == "termino" and not pd.isna(linha["fim_infusao"]):
                    base = int(linha["fim_infusao"]) + 20
                    h = st.time_input("Hora real de término (informada pela enfermagem)",
                                      time(min(base, 23 * 60) // 60, min(base, 23 * 60) % 60),
                                      step=300)
                    valor = h.hour * 60 + h.minute
                    st.caption(f"Término previsto: {hhmm(linha['fim_infusao'])}")
                b1, b2, b3 = st.columns(3)
                if b1.button("✅ Registrar", type="primary", width="stretch"):
                    novo = {"paciente": pac, "tipo": tipo, "valor": valor}
                    erro = O.validar(novo, plano)
                    if erro:
                        st.error(f"❌ {erro}")
                    else:
                        ocorrencias.append(novo)
                        st.rerun()
                if b2.button("↩️ Desfazer o último", width="stretch", disabled=not ocorrencias):
                    ocorrencias.pop()
                    st.rerun()
                if b3.button("🗑️ Apagar todos", width="stretch", disabled=not ocorrencias):
                    ocorrencias.clear()
                    st.rerun()

            if ocorrencias:
                comp = O.planejado_x_realizado(plano, ag)
                atrasos = (comp["sai_real"] - comp["sai_plano"]).clip(lower=0)
                ui.resumo([
                    ui.cartao_resumo("📝", "imprevistos registrados", len(ocorrencias),
                                     *ui.NEUTRO),
                    ui.cartao_resumo("👥", "pacientes afetados (com efeito em cascata)",
                                     len(comp), "#b27600", "#fff5dc"),
                    ui.cartao_resumo("⏱️", "minutos de poltrona a mais no dia",
                                     int(atrasos.sum()), *ui.ESPERA_LONGA[2:]),
                ])

                def situacao(r):
                    if r["faltou"]:
                        return "🚫 Faltou"
                    if r["remarcado"]:
                        return "❌ Remarcado (perdeu o horário limite)"
                    d = r["sai_real"] - r["sai_plano"]
                    texto = (f"⏱️ Libera {int(round(d))} min mais tarde" if d > 0.5
                             else "✅ No horário")
                    if r["sai_real"] > prem.fim_turno:
                        texto += f" · ⚠️ passa do fim do turno ({hhmm(prem.fim_turno)})"
                    return texto

                ui.tabela(pd.DataFrame({
                    "Paciente": comp["paciente"],
                    "O que aconteceu": comp["imprevisto"],
                    "Poltrona": comp["poltrona"].astype("Int64"),
                    "Senta (planejado → real)": [f"{hhmm(a)} → {hhmm(b)}" for a, b in
                                                 zip(comp["senta_plano"], comp["senta_real"])],
                    "Libera (planejado → real)": [f"{hhmm(a)} → {hhmm(b)}" for a, b in
                                                  zip(comp["sai_plano"], comp["sai_real"])],
                    "Situação": comp.apply(situacao, axis=1),
                }))

    estado = P.estado_poltronas(ag, t, prem.n_poltronas)
    cont = estado["situacao"].value_counts()
    recepcao = P.na_recepcao(ag, t)
    cartoes = [ui.cartao_resumo(ic, tx, int(cont.get(k, 0)), f, b)
               for k, (ic, tx, f, b) in ui.SITUACAO_POLTRONA.items()]
    if len(recepcao):
        cartoes.append(ui.cartao_resumo("🪑", "Na recepção sem poltrona", len(recepcao),
                                        *ui.ESPERA_LONGA[2:]))
    remarcados_ate_agora = int((ag["remarcado"] & (ag["limite_min"] <= t)).sum())
    if remarcados_ate_agora:
        cartoes.append(ui.cartao_resumo("❌", "Remarcados (perderam o horário limite)",
                                        remarcados_ate_agora, *ui.ESPERA_LONGA[2:]))
    ui.resumo(cartoes)

    # Alertas: os novos surgem no canto da tela; todos ficam guardados na central
    lista = P.alertas(ag, t, prem.folga_transporte)
    novos = ui.notificar_novos(lista, contexto=f"{chave_dia}|{escolha}")
    ui.quadro_flutuante(lista, novos)
    with ui.bloco("alertas"):
        ui.titulo_bloco(f"🔔 Central de alertas ({len(lista)} agora)", (
            "Quando um alerta **começa**, aparece uma notificação no **canto superior "
            "direito** (o de remarcado fica até ser fechado). Os alertas ativos ficam sempre "
            "no **quadro do canto inferior direito**, e aqui estão **todos os alertas do "
            "horário**, com o texto completo.\n\n"
            "- **⚠️ Espera acima de 30 min**: paciente sentado aguardando a bolsa há mais de meia hora.\n"
            "- **🚐 Transporte do interior**: o transporte volta em menos de 2 horas e a "
            "poltrona do paciente não libera a tempo (ou ele já perdeu o transporte).\n"
            "- **⚠️ Perto do horário limite**: faltam menos de 30 min para o horário limite do "
            "protocolo e o paciente ainda não chegou à triagem com o farmacêutico.\n"
            "- **❌ Remarcado**: o paciente perdeu o horário limite. Não dá mais para manipular "
            "a bolsa no dia e ele é remarcado para outro dia.\n"
            "- **🔔 Preparar alta**: faltam 15 minutos ou menos para acabar a infusão. "
            "Adiantar a alta libera a poltrona mais rápido."))
        if not lista:
            ui.caixa_alerta("ok", "Nenhum alerta neste horário.")
        else:
            with st.expander(f"Ver os {len(lista)} alertas"):
                for a in lista:
                    ui.caixa_alerta(a["tipo"], a["texto"])

    # Mapa de poltronas
    with ui.bloco("poltronas"):
        ui.titulo_bloco("🪑 Mapa das poltronas", (
            "Cada cartão é uma poltrona. A cor, o ícone e o texto mostram a situação:\n\n"
            "- ✅ **Livre** – pronta para o próximo paciente\n"
            "- ⏳ **Aguardando bolsa** – paciente sentado esperando a medicação chegar\n"
            "- 💧 **Em infusão** – medicação sendo aplicada\n"
            "- 🚪 **Em alta** – infusão terminou, aguardando a alta no sistema\n"
            "- ⚠️ **Espera longa** – aguardando a bolsa há mais de 30 minutos\n\n"
            "O selo com a bolinha colorida mostra o **tipo de tratamento**, com as cores da "
            "folha do setor: 🔴 Longo, 🟠 Intermediário laranja, 🟤 Intermediário marrom, "
            "🟢 Rápido e 🔵 Injetável. O nome aparece sempre escrito junto.\n\n"
            "**Libera às** é a previsão de quando a poltrona fica livre.\n\n"
            "**Ver como**: *Grade* mostra um cartão por poltrona (bom para TV); *Lista* "
            "mostra uma linha por poltrona, ordenada pela próxima a liberar; *Kanban* mostra "
            "cada paciente como um cartão andando pelas etapas do dia (agendado → chegou → "
            "na poltrona → em infusão → alta → concluído), com os limites de poltronas e da "
            "capela no topo."))
        c_modo, c_filtro = st.columns([3, 2], vertical_alignment="center")
        with c_modo:
            modo = st.radio("Ver como", ["🔲 Grade", "📋 Lista", "🗂️ Kanban"], horizontal=True,
                            key="modo_poltronas")
        with c_filtro:
            filtro_origem_painel = st.selectbox(
                "📍 Filtrar procedência",
                ["Todos os pacientes", "🏙️ Capital", "🚐 Interior (transporte municipal)"],
                key="filtro_origem_painel"
            )

        if filtro_origem_painel.startswith("🏙️"):
            ag_visual = ag[~ag["interior"].astype(bool)]
            estado_visual = estado[estado["paciente"].isin(ag_visual["paciente"]) | estado["paciente"].isna()]
        elif filtro_origem_painel.startswith("🚐"):
            ag_visual = ag[ag["interior"].astype(bool)]
            estado_visual = estado[estado["paciente"].isin(ag_visual["paciente"])]
        else:
            ag_visual = ag
            estado_visual = estado

        if filtro_origem_painel != "Todos os pacientes":
            st.caption(f"Mostrando apenas pacientes de: **{filtro_origem_painel}**")

        if modo == "📋 Lista":
            ui.lista_poltronas(estado_visual, hhmm)
        elif modo == "🗂️ Kanban":
            st.caption("Cada cartão é um paciente; cada coluna, uma etapa. Os mais urgentes "
                       "vêm primeiro: ⛔ **em risco**, ⚠️ **atenção**; cartão sem selo e com "
                       "borda verde está **no prazo**. 🚐 = paciente do interior, com a hora em "
                       "que o transporte volta.")
            ui.kanban(P.kanban(ag_visual, t, prem.folga_transporte), P.ocupacao_kanban(ag, t),
                      prem.n_poltronas, prem.capacidade_capela)
        else:
            ui.grade_poltronas(estado_visual, hhmm)

    # Fila da capela
    st.write("")
    with ui.bloco("fila"):
        ui.titulo_bloco("🧪 Fila da farmácia (capela)", (
            "Ordem em que as bolsas devem ser preparadas.\n\n"
            "A fila segue **a próxima poltrona a ficar livre**: a farmácia prepara primeiro a "
            "bolsa do paciente cuja poltrona vai liberar antes. Assim a bolsa fica pronta na "
            "hora certa, sem o paciente esperar sentado (sistema puxado)."))
        fila = P.fila_capela(ag, t)
        if fila.empty:
            st.markdown("✅ Nenhuma bolsa pendente na farmácia.")
        else:
            fila["Situação da bolsa"] = fila["Situação da bolsa"].map(
                lambda s: f"{ui.ICONE_BOLSA[s]} {s}")
            ui.tabela(fila.head(8))
            if len(fila) > 8:
                with st.expander(f"Ver a fila completa ({len(fila)} bolsas)"):
                    ui.tabela(fila)

    # Situação das bolsas
    st.write("")
    with ui.bloco("bolsas"):
        ui.titulo_bloco("📦 Situação das bolsas do dia", (
            "Em que etapa está cada bolsa de medicação:\n\n"
            "📝 **Prescrita** → 🧪 **Em preparo** (na capela) → 📦 **Pronta** → "
            "🚶 **Em transporte** → 💧 **Instalada** (infusão em andamento) → ✔️ **Infusão concluída**"))
        bolsas = P.status_bolsas(ag, t)
        cont_b = bolsas["situacao"].value_counts()
        ui.resumo([ui.cartao_resumo(ui.ICONE_BOLSA[s], s, int(cont_b.get(s, 0)), *ui.NEUTRO)
                   for s in P.BOLSA_ETAPAS], empilhado=True)
        with st.expander("Ver a situação de cada bolsa"):
            ui.tabela(pd.DataFrame({
                "Paciente": bolsas["paciente"],
                "Tipo de tratamento": bolsas["perfil"].map(ROTULO),
                "Poltrona": bolsas["poltrona"].astype("Int64"),
                "Situação": [f"{ui.ICONE_BOLSA[s]} {s}" for s in bolsas["situacao"]],
                "Início da infusão": bolsas["inicio_infusao"].map(hhmm),
            }))

# ---------------------------------------------------------------------------
# Aba 2 – Hoje x Proposta
# ---------------------------------------------------------------------------
with aba_comparar:
    if not otim_ok:
        st.warning("⚠️ Sem agenda organizada para comparar. Ajuste as premissas.")
    else:
        otim = R["otim"]
        texto_status = (f"🧮 **Cálculo da agenda:** {otim['status_texto']} "
                        f"(levou {otim['tempo_s']:.0f} segundos).")
        if otim["remarcados"]:
            texto_status += (f" ⚠️ {len(otim['remarcados'])} paciente(s) não couberam no dia "
                             f"e precisariam ser remarcados: {', '.join(otim['remarcados'])}.")
        st.info(texto_status)

        ka, ko = R["k_atual"], R["k_otim"]

        # Destaque: remarcações por perder o horário limite
        with ui.bloco("remarcacoes"):
            ui.titulo_bloco("📅 Pacientes remarcados por perder o horário limite", (
                "Pela folha do setor, cada protocolo tem um **horário limite** para o paciente "
                "estar na triagem com o farmacêutico. Depois dele não dá mais para manipular a "
                "bolsa no dia, e o paciente é **remarcado** para outro dia.\n\n"
                "**Hoje**: quem chega depois do limite é remarcado.\n\n"
                f"**Proposta**: a agenda marca a chegada pelo menos {prem.folga_limite} min "
                "antes do limite de cada protocolo, para ninguém ser remarcado por prazo."
                + ("\n\n**Sexta-feira**: todos os limites estão 1h mais cedo."
                   if prem.sexta_feira else "")))
            ui.destaque_remarcacoes(ka["remarcados"], ko["remarcados"],
                                    ka["pacientes_atendidos"], ko["pacientes_atendidos"],
                                    prem.folga_limite)
            rem = R["atual"][R["atual"]["remarcado"]]
            if len(rem):
                with st.expander(f"Ver quem foi remarcado hoje ({len(rem)})"):
                    ui.tabela(pd.DataFrame({
                        "Paciente": rem["paciente"],
                        "Protocolo": rem["protocolo"],
                        "Tipo de tratamento": rem["perfil"].map(ROTULO),
                        "Chegou à triagem": rem["chegada"].map(hhmm),
                        "Horário limite": rem["limite_min"].map(hhmm),
                    }))

        with ui.bloco("resultados"):
            ui.titulo_bloco("📊 Resultados: hoje x proposta", (
                "**Hoje**: simulação do funcionamento atual – a maioria chega cedo, o paciente senta "
                "ao chegar e a farmácia prepara as bolsas por ordem de chegada.\n\n"
                "**Proposta**: agenda calculada pelo computador – cada paciente recebe um horário, "
                "a bolsa é preparada antes para estar pronta quando ele senta, a alta é preparada "
                f"antes do fim da infusão ({prem.alta_antecipada} min em vez de {prem.alta_atual}) "
                "e o trabalho da farmácia é espalhado ao longo do dia.\n\n"
                "**Variação**: quanto a proposta muda em relação a hoje. Para a ocupação da capela, "
                "a diferença é mostrada em pontos percentuais (p.p.)."))

            def var_fmt(r):
                if r["Unidade"] == "%" and r["Resultado"].startswith("➖ Equilíbrio"):
                    return f"{r['Proposta'] - r['Hoje']:+.0f} p.p."
                return "—" if pd.isna(r["Variação (%)"]) else f"{r['Variação (%)']:+.0f}%"

            comp = I.tabela_comparativa(ka, ko)
            casas = {"h": 1, "min": 0, "%": 0, "pacientes": 0}
            ui.tabela(pd.DataFrame({
                "Indicador": comp["Indicador"],
                "Hoje": [f"{v:.{casas[u]}f} {u}" for v, u in zip(comp["Hoje"], comp["Unidade"])],
                "Proposta": [f"{v:.{casas[u]}f} {u}" for v, u in zip(comp["Proposta"], comp["Unidade"])],
                "Variação": comp.apply(var_fmt, axis=1),
                "Resultado": comp["Resultado"],
            }))
            st.caption("Na proposta, a espera na poltrona é o tempo de acomodação planejado "
                       f"({prem.acomodacao} min) antes de a bolsa chegar.")

        # Gráfico: carga da capela por hora
        st.write("")
        with ui.bloco("graf_capela"):
            ui.titulo_bloco("🧪 Ocupação da capela em cada hora", (
                "Quanto da capacidade da capela (bolsas manipuladas ao mesmo tempo) é usado em "
                "cada hora. Hoje a manhã fica sobrecarregada e a tarde fica ociosa; na proposta "
                "o trabalho é distribuído ao longo do dia."))
            cap = pd.concat([
                I.carga_capela_por_hora(R["atual"], prem).assign(Cenário="Hoje"),
                I.carga_capela_por_hora(otim["agenda"], prem).assign(Cenário="Proposta"),
            ])
            cap["Hora"] = cap["hora"].map(lambda m: f"{m // 60}h")
            fig = px.bar(cap, x="Hora", y="ocupacao", color="Cenário", barmode="group",
                         color_discrete_map={"Hoje": ui.COR_HOJE, "Proposta": ui.COR_PROPOSTA},
                         labels={"ocupacao": "Ocupação da capela (%)"},
                         hover_data={"ocupacao": ":.0f"})
            fig.update_traces(marker_line_color="white", marker_line_width=2)
            fig.update_layout(bargap=0.25, bargroupgap=0.05)
            fig.update_yaxes(range=[0, 105], ticksuffix="%")
            st.plotly_chart(ui.estilo_grafico(fig, "Ocupação da capela por hora (%)"),
                            width="stretch")

        # Gráfico: pacientes na unidade por hora
        with ui.bloco("graf_poltronas"):
            ui.titulo_bloco("🪑 Pacientes na unidade em cada hora", (
                "Maior número de pacientes na unidade em cada hora (sentados nas poltronas ou "
                "esperando poltrona na recepção). A linha tracejada é o total de poltronas."))
            pol = pd.concat([
                I.poltronas_por_hora(R["atual"], prem).assign(Cenário="Hoje"),
                I.poltronas_por_hora(otim["agenda"], prem).assign(Cenário="Proposta"),
            ])
            pol["Hora"] = pol["hora"].map(lambda m: f"{m // 60}h")
            fig = px.line(pol, x="Hora", y="na_unidade", color="Cenário", markers=True,
                          color_discrete_map={"Hoje": ui.COR_HOJE, "Proposta": ui.COR_PROPOSTA},
                          labels={"na_unidade": "Pacientes na unidade"})
            fig.update_traces(line_width=3, marker_size=10)
            fig.add_hline(y=prem.n_poltronas, line_dash="dash", line_color="#52514e",
                          annotation_text=f"Total de poltronas ({prem.n_poltronas})",
                          annotation_position="top left", annotation_font_size=18)
            st.plotly_chart(ui.estilo_grafico(fig, "Pacientes na unidade por hora"),
                            width="stretch")

        # Comparação com os números reais
        with ui.bloco("calibracao"):
            ui.titulo_bloco("🔎 A simulação de hoje é parecida com a realidade?", (
                "Para confiar na comparação, a simulação do funcionamento atual foi ajustada para "
                "ficar próxima dos números medidos no hospital. Os números são de **um dia sintético**, "
                "então pequenas diferenças são esperadas.\n\n"
                "O maior número de pacientes ao mesmo tempo fica abaixo do observado (49) porque o "
                f"protótipo usa {prem.n_poltronas} poltronas: confirmar esse número com o hospital."))
            pct10 = 100 * (R["dia"]["chegada_min"] < 600).mean()
            calib = I.tabela_calibracao(ka, pct10)
            calib["Observado no hospital"] = calib["Observado no hospital"].map(lambda v: f"{v:.0f}")
            calib["Simulação de hoje"] = calib["Simulação de hoje"].map(lambda v: f"{v:.0f}")
            ui.tabela(calib)

# ---------------------------------------------------------------------------
# Aba 3 – O que melhorou (ganhos para o paciente, meta de espera e ociosidade)
# ---------------------------------------------------------------------------
with aba_melhorou:
    if not otim_ok:
        st.warning("⚠️ Sem agenda organizada para comparar. Ajuste as premissas.")
    else:
        atual, otim_ag = R["atual"], R["otim"]["agenda"]
        jor = G.jornada(atual, otim_ag)
        res = G.resumo(jor, prem.meta_espera)
        dur = G.formatar_duracao
        st.caption("📌 Estimativas do modelo com **pacientes fictícios**. Na proposta o paciente "
                   "chega no horário marcado: parte do ganho é tempo que ele passa em casa, e "
                   "não esperando na unidade. A duração da infusão **nunca muda**.")

        # 1) Números de impacto
        with ui.bloco("impacto"):
            ui.titulo_bloco("💚 O que o Sinfonia muda no dia", (
                "Resumo do ganho para os pacientes no dia sintético.\n\n"
                "**Horas a menos na unidade**: soma, paciente a paciente, do tempo que cada um "
                "deixa de passar na unidade (da chegada até liberar a poltrona).\n\n"
                "**Remarcações evitadas**: pacientes que hoje perderiam o horário limite e "
                "voltariam outro dia.\n\n"
                f"**Meta de espera**: {prem.meta_espera} min sentado aguardando a bolsa "
                "(editável na aba Premissas)."))
            ui.cartoes_impacto([
                ("⏱️", f"{res['horas_economizadas']:.0f} h",
                 "a menos de pacientes na unidade",
                 f"{res['pacientes_com_ganho']} de {res['pacientes_comparados']} pacientes "
                 "ficam menos tempo", ui.TEAL),
                ("🏠", dur(res["tempo_medio_hoje"]) + " → " + dur(res["tempo_medio_proposta"]),
                 "tempo médio na unidade", "da chegada até liberar a poltrona", ui.MARINHO),
                ("📅", str(res["remarcados_evitados"]), "remarcações evitadas",
                 "pacientes que perderiam o horário limite", ui.OK[0]),
                ("🎯", f"{res['acima_meta_hoje']} → {res['acima_meta_proposta']}",
                 f"pacientes acima da meta de {prem.meta_espera} min",
                 "sentados esperando a bolsa", "#b27600"),
            ])

        # 1b) Pacientes do interior
        if "perdeu_transporte_hoje" in jor.columns and jor["interior"].any():
            with ui.bloco("interior"):
                ui.titulo_bloco("🚐 Pacientes do interior", (
                    "Pacientes que vêm no **transporte da prefeitura**: chegam cedo e precisam "
                    "voltar num horário fixo. O tempo deles na unidade conta **desde a chegada "
                    "do transporte**, nos dois cenários.\n\n"
                    "O Sinfonia dá prioridade a eles sem prejudicar os pacientes da capital: o "
                    "último cartão mostra o tempo médio da capital, para comparar."))
                ji = jor[jor["interior"]].dropna(subset=["tempo_hoje", "tempo_proposta"])
                jc = jor[~jor["interior"]].dropna(subset=["tempo_hoje", "tempo_proposta"])
                rem_int_h = int((jor["interior"] & jor["remarcado_hoje"]).sum())
                rem_int_p = int((jor["interior"] & jor["remarcado_proposta"]).sum())
                ui.cartoes_impacto([
                    ("🚐", f"{int(jor['perdeu_transporte_hoje'].sum())} → "
                           f"{int(jor['perdeu_transporte_proposta'].sum())}",
                     "perdem o transporte de volta",
                     f"de {int(jor['interior'].sum())} pacientes do interior no dia", "#c62828"),
                    ("📅", f"{rem_int_h} → {rem_int_p}", "remarcados (perdem a viagem)",
                     "pacientes do interior", "#b27600"),
                    ("⏱️", dur(ji["tempo_hoje"].mean()) + " → " + dur(ji["tempo_proposta"].mean()),
                     "tempo médio na unidade (interior)", "desde a chegada do transporte",
                     ui.TEAL),
                    ("🏙️", dur(jc["tempo_hoje"].mean()) + " → " + dur(jc["tempo_proposta"].mean()),
                     "tempo médio na unidade (capital)", "para conferir que ninguém é prejudicado",
                     ui.MARINHO),
                ])

        # 2) Histórias de pacientes
        with ui.bloco("historias"):
            ui.titulo_bloco("👤 Histórias de pacientes (fictícios)", (
                "Exemplos reais **do modelo**: os pacientes fictícios com o maior ganho e os "
                "que deixariam de ser remarcados.\n\n"
                "**Hoje**: tempo na unidade na simulação do funcionamento atual.\n\n"
                "**Com o Sinfonia**: tempo na unidade com a agenda organizada."))
            hist = []
            for _, r in jor[jor["remarcado_hoje"] & ~jor["remarcado_proposta"]].iterrows():
                hist.append({
                    "paciente": r["paciente"] + (" 🚐" if r["interior"] else ""),
                    "id": r["paciente"], "grupo": r["perfil"],
                    "hoje": "Remarcado", "proposta": dur(r["tempo_proposta"]),
                    "selo": "✅ Atendido no mesmo dia",
                    "frase": f"{r['protocolo']}: hoje perderia o horário limite e voltaria "
                             f"outro dia. Com o Sinfonia chega às {hhmm(r['chegada_proposta'])} "
                             f"e começa a infusão às {hhmm(r['inicio_infusao_proposta'])}."})
            if "perdeu_transporte_hoje" in jor.columns:
                salvos = jor[jor["perdeu_transporte_hoje"] & ~jor["perdeu_transporte_proposta"]
                             & ~jor["remarcado_proposta"]]
                for _, r in salvos.iterrows():
                    hist.append({
                        "paciente": r["paciente"] + " 🚐", "id": r["paciente"],
                        "grupo": r["perfil"],
                        "hoje": dur(r["tempo_hoje"]), "proposta": dur(r["tempo_proposta"]),
                        "selo": "🚐 Volta no transporte",
                        "frase": f"Do interior: hoje sairia às {hhmm(r['sai_hoje'])} e perderia o "
                                 f"transporte das {hhmm(r['retorno_min'])}. Com o Sinfonia sai "
                                 f"às {hhmm(r['sai_proposta'])}."})
            hist = hist[:4]  # deixa espaço para pelo menos 2 histórias de ganho de tempo
            ja_contados = {h["id"] for h in hist}  # cada paciente aparece uma vez só
            outros = jor[~jor["paciente"].isin(ja_contados)]
            for _, r in G.maiores_ganhos(outros, 6 - len(hist)).iterrows():
                hist.append({
                    "paciente": r["paciente"] + (" 🚐" if r["interior"] else ""),
                    "id": r["paciente"], "grupo": r["perfil"],
                    "hoje": dur(r["tempo_hoje"]), "proposta": dur(r["tempo_proposta"]),
                    "selo": f"⏱️ {dur(r['ganho'])} a menos",
                    "frase": (
                        f"Do interior: chega no transporte às {hhmm(r['chegada_proposta'])}. "
                        f"Hoje só sairia às {hhmm(r['sai_hoje'])}; com o Sinfonia sai às "
                        f"{hhmm(r['sai_proposta'])}." if r["interior"] else
                        f"Esperava {dur(r['espera_hoje'])} sentado pela bolsa; com o Sinfonia "
                        f"espera {dur(r['espera_proposta'])}"
                        + (" (só a acomodação planejada)."
                           if r["espera_proposta"] <= prem.acomodacao + 0.5 else "."))})
            ui.cartoes_historia(hist[:6])
            piores = jor[jor["ganho"] < 0]
            if len(piores):
                motivos = [f"a proposta reserva {prem.acomodacao} min de acomodação antes da "
                           "bolsa (hoje alguns não esperam nada)"]
                if piores["interior"].any():
                    motivos.append("pacientes do interior que hoje são atendidos cedo podem "
                                   "esperar um pouco mais para que todos peguem o transporte")
                st.caption(f"ℹ️ {len(piores)} paciente(s) ficam até "
                           f"{dur(-piores['ganho'].min())} a mais: " + "; ".join(motivos) + ".")

        # 3) Antes e depois por paciente (gráfico de halteres)
        with ui.bloco("halteres"):
            ui.titulo_bloco("↔️ Antes e depois, paciente a paciente", (
                "Cada linha é um paciente fictício. A bolinha **cinza** é o tempo na unidade "
                "hoje e a **verde-azulada** é com o Sinfonia. Quanto maior a linha, maior o "
                "ganho. Mostra os 20 pacientes com mais ganho."))
            top = G.maiores_ganhos(jor, 20).iloc[::-1]
            fig = go.Figure()
            for _, r in top.iterrows():
                fig.add_trace(go.Scatter(x=[r["tempo_proposta"] / 60, r["tempo_hoje"] / 60],
                                         y=[r["paciente"]] * 2, mode="lines",
                                         line=dict(color="#c7d0d8", width=4),
                                         hoverinfo="skip", showlegend=False))
            for nome, col, cor in (("Hoje", "tempo_hoje", ui.COR_HOJE),
                                   ("Com o Sinfonia", "tempo_proposta", ui.COR_PROPOSTA)):
                fig.add_trace(go.Scatter(
                    x=top[col] / 60, y=top["paciente"], mode="markers", name=nome,
                    marker=dict(size=14, color=cor, line=dict(color="white", width=2)),
                    customdata=top[[col, "ganho"]].map(dur).to_numpy(),
                    hovertemplate="%{y}: %{customdata[0]}<br>Ganho: %{customdata[1]}"
                                  "<extra>" + nome + "</extra>"))
            fig.update_xaxes(title="Horas na unidade", ticksuffix=" h", rangemode="tozero")
            fig.update_yaxes(title=None, tickfont=dict(size=16))
            st.plotly_chart(ui.estilo_grafico(fig, "Tempo na unidade por paciente",
                                              altura=620), width="stretch")

        # 4) Ganho por tipo de tratamento  e  5) Para onde foi o tempo
        with ui.bloco("por_grupo"):
            ui.titulo_bloco("🎨 Por tipo de tratamento", (
                "Tempo médio na unidade de cada tipo de tratamento (cores da folha do setor), "
                "hoje x com o Sinfonia."))
            pg_ = G.por_grupo(jor, PERFIS)
            pg_["Tipo"] = pg_["perfil"].map(lambda g: ROTULO[g].split(" (")[0])
            longo = pg_.melt(id_vars="Tipo", value_vars=["tempo_hoje", "tempo_proposta"],
                             var_name="Cenário", value_name="min")
            longo["Cenário"] = longo["Cenário"].map({"tempo_hoje": "Hoje",
                                                     "tempo_proposta": "Com o Sinfonia"})
            longo["horas"] = longo["min"] / 60
            longo["texto"] = longo["min"].map(dur)
            fig = px.bar(longo, y="Tipo", x="horas", color="Cenário", barmode="group",
                         orientation="h", text="texto",
                         color_discrete_map={"Hoje": ui.COR_HOJE, "Com o Sinfonia": ui.COR_PROPOSTA},
                         hover_data={"horas": False, "texto": True})
            fig.update_traces(marker_line_color="white", marker_line_width=2,
                              textposition="outside", cliponaxis=False)
            fig.update_xaxes(title="Horas na unidade (média)", ticksuffix=" h")
            fig.update_yaxes(title=None, autorange="reversed")
            fig.update_layout(margin=dict(r=70))
            st.plotly_chart(ui.estilo_grafico(fig, "Tempo médio por tipo", altura=520),
                            width="stretch")
        with ui.bloco("composicao"):
            ui.titulo_bloco("🧩 Para onde vai o tempo", (
                "Soma das horas de todos os pacientes no dia, dividida em etapas.\n\n"
                "A **infusão** de cada paciente é igual nos dois cenários: o ganho vem da "
                "recepção, da espera pela bolsa e da alta. O total de infusão sobe um pouco "
                "porque os pacientes que hoje seriam remarcados passam a ser atendidos."))
            cores_etapa = {"Recepção (sem poltrona)": "#c62828", "Espera na poltrona": "#b27600",
                           "Infusão": ui.TEAL, "Alta": "#4a3aa7"}
            comp = pd.DataFrame([
                {"Cenário": nome, "Etapa": e, "horas": h}
                for nome, ag_ in (("Hoje", atual), ("Com o Sinfonia", otim_ag))
                for e, h in G.composicao(ag_).items()])
            comp["texto"] = comp["horas"].map(lambda h: f"{h:.0f} h" if h >= 6 else "")
            fig = px.bar(comp, y="Cenário", x="horas", color="Etapa", orientation="h",
                         text="texto", color_discrete_map=cores_etapa,
                         category_orders={"Etapa": list(cores_etapa),
                                          "Cenário": ["Hoje", "Com o Sinfonia"]},
                         hover_data={"texto": False, "horas": ":.1f"})
            fig.update_traces(marker_line_color="white", marker_line_width=2,
                              textfont=dict(color="#ffffff", size=17), textangle=0,
                              insidetextanchor="middle")
            fig.update_xaxes(title="Horas somadas no dia", ticksuffix=" h")
            fig.update_yaxes(title=None)
            st.plotly_chart(ui.estilo_grafico(fig, "Horas por etapa", altura=380),
                            width="stretch")

        # 6) Meta de espera
        with ui.bloco("meta"):
            ui.titulo_bloco(f"🎯 Meta de espera: até {prem.meta_espera} min na poltrona", (
                "Quanto tempo cada paciente fica **sentado esperando a bolsa**. A linha "
                "tracejada é a meta (editável na aba Premissas). Barras à direita da linha "
                "são pacientes fora da meta."))
            dentro_h = G.dentro_da_meta(atual, prem.meta_espera)
            dentro_p = G.dentro_da_meta(otim_ag, prem.meta_espera)
            ui.resumo([
                ui.cartao_resumo("🎯", "dentro da meta hoje", f"{dentro_h:.0f}%", *ui.NEUTRO),
                ui.cartao_resumo("✅", "dentro da meta com o Sinfonia", f"{dentro_p:.0f}%",
                                 *ui.OK),
            ])
            esp = pd.concat([
                pd.DataFrame({"Cenário": "Hoje", "min": jor["espera_hoje"]}),
                pd.DataFrame({"Cenário": "Com o Sinfonia", "min": jor["espera_proposta"]}),
            ]).dropna()
            # Faixas de 10 min até 2h; esperas maiores ficam juntas em "2h ou mais"
            limites = list(range(0, 121, 10))
            nomes_faixa = [f"{a}–{b}" for a, b in zip(limites[:-1], limites[1:])] + ["2h ou mais"]
            esp["Faixa"] = pd.cut(esp["min"].clip(upper=120.5), limites + [10_000],
                                  labels=nomes_faixa, right=False, include_lowest=True)
            cont = (esp.groupby(["Faixa", "Cenário"], observed=False).size()
                    .rename("Pacientes").reset_index())
            cont["texto"] = cont["Pacientes"].map(lambda n: str(n) if n else "")
            fig = px.bar(cont, x="Faixa", y="Pacientes", color="Cenário", barmode="group",
                         text="texto",
                         category_orders={"Faixa": nomes_faixa,
                                          "Cenário": ["Hoje", "Com o Sinfonia"]},
                         color_discrete_map={"Hoje": ui.COR_HOJE,
                                             "Com o Sinfonia": ui.COR_PROPOSTA})
            fig.update_traces(marker_line_color="white", marker_line_width=2,
                              textposition="outside", cliponaxis=False,
                              hovertemplate="%{x} min: %{y} pacientes")
            # Linha da meta entre as faixas (faixas de 10 min começando em 0)
            pos = prem.meta_espera / 10 - 0.5
            fig.add_vline(x=pos, line_dash="dash", line_color=ui.MARINHO, line_width=3,
                          annotation_text=f"Meta: {prem.meta_espera} min",
                          annotation_position="top right", annotation_font_size=18)
            fig.update_xaxes(title="Minutos sentado esperando a bolsa")
            fig.update_yaxes(title="Pacientes")
            st.plotly_chart(ui.estilo_grafico(fig, "Espera na poltrona x meta", altura=420),
                            width="stretch")

        # 7) Ociosidade (resumo simples; o detalhe hora a hora fica escondido)
        with ui.bloco("ociosidade"):
            ui.titulo_bloco("💤 Ociosidade: poltronas e capela", (
                "- **Poltronas ocupadas sem tratar**: o paciente está sentado, mas esperando a "
                "bolsa ou a alta. É desperdício: **quanto menor, melhor**.\n"
                "- **Poltronas livres**: poltronas vazias, prontas para mais pacientes. Com o "
                "Sinfonia cada paciente usa a poltrona por menos tempo, então sobra mais.\n"
                "- **Capela parada**: parte do tempo em que a capela não está preparando "
                "bolsas. Hoje ela fica lotada de manhã e parada à tarde; com o Sinfonia o "
                "trabalho fica igual o dia todo.\n\n"
                "Os números são a **média por hora** do turno."))
            oc_h = I.ociosidade_por_hora(atual, prem)
            oc_p = I.ociosidade_por_hora(otim_ag, prem)
            manha_h, manha_p = oc_h["hora"] < I.MEIO_DIA, oc_p["hora"] < I.MEIO_DIA

            def num(v):
                return f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ",")

            ui.cartoes_impacto([
                ("🪑", f"{num(oc_h['poltronas_sem_tratar'].mean())} → "
                       f"{num(oc_p['poltronas_sem_tratar'].mean())}",
                 "poltronas ocupadas sem tratar",
                 "em média, a cada hora (esperando bolsa ou alta)", "#b27600"),
                ("✅", f"{num(oc_h['poltronas_ociosas'].mean())} → "
                       f"{num(oc_p['poltronas_ociosas'].mean())}",
                 "poltronas livres",
                 "em média, a cada hora: espaço para mais pacientes", ui.TEAL),
                ("🧪", f"{oc_h.loc[manha_h, 'capela_ociosa'].mean():.0f}% / "
                       f"{oc_h.loc[~manha_h, 'capela_ociosa'].mean():.0f}%",
                 "capela parada hoje (manhã / tarde)",
                 f"com o Sinfonia: {oc_p.loc[manha_p, 'capela_ociosa'].mean():.0f}% / "
                 f"{oc_p.loc[~manha_p, 'capela_ociosa'].mean():.0f}% (trabalho equilibrado)",
                 ui.MARINHO),
            ])
            st.caption("Leitura: **hoje → com o Sinfonia**.")

            with st.expander("📈 Ver hora a hora"):
                oc = pd.concat([oc_h.assign(Cenário="Hoje"),
                                oc_p.assign(Cenário="Com o Sinfonia")])
                oc["Hora"] = oc["hora"].map(lambda m: f"{m // 60}h")
                paineis = [("poltronas_sem_tratar", "Poltronas ocupadas sem tratar", ""),
                           ("poltronas_ociosas", "Poltronas livres", ""),
                           ("capela_ociosa", "Capela parada", "%")]
                fig = make_subplots(rows=1, cols=3, subplot_titles=[p[1] for p in paineis],
                                    horizontal_spacing=0.07)
                for i, (col, _, suf) in enumerate(paineis, start=1):
                    for nome, cor in (("Hoje", ui.COR_HOJE),
                                      ("Com o Sinfonia", ui.COR_PROPOSTA)):
                        d = oc[oc["Cenário"] == nome]
                        fig.add_trace(go.Scatter(
                            x=d["Hora"], y=d[col], name=nome, mode="lines+markers",
                            line=dict(color=cor, width=3), marker=dict(size=9),
                            legendgroup=nome, showlegend=(i == 1),
                            hovertemplate="%{x}: %{y:.0f}" + suf + "<extra>" + nome + "</extra>"),
                            row=1, col=i)
                    fig.update_yaxes(rangemode="tozero", ticksuffix=suf, row=1, col=i)
                fig.update_annotations(font_size=19)
                fig.update_xaxes(dtick=2)
                ui.estilo_grafico(fig, "Ociosidade por hora", altura=470)
                fig.update_layout(legend=dict(orientation="h", y=-0.18, x=0, yanchor="top"),
                                  margin=dict(t=50, b=90))
                st.plotly_chart(fig, width="stretch")

        # 8) Tabela completa
        with ui.bloco("tabela_ganhos"):
            ui.titulo_bloco("📋 Todos os pacientes", (
                "Tempo na unidade de cada paciente fictício, hoje e com o Sinfonia. "
                "Use o filtro para ver um tipo de tratamento."))
            filtro = st.selectbox("Tipo de tratamento", ["Todos"] + [ROTULO[p] for p in PERFIS])
            vis = jor if filtro == "Todos" else jor[jor["perfil"].map(ROTULO) == filtro]
            vis = vis.sort_values("ganho", ascending=False, na_position="first")
            tab = pd.DataFrame({
                "Paciente": vis["paciente"],
                "Protocolo": vis["protocolo"],
                "Tipo de tratamento": vis["perfil"].map(ROTULO),
                "Hoje": [("❌ Remarcado" if rem else dur(t))
                         for rem, t in zip(vis["remarcado_hoje"], vis["tempo_hoje"])],
                "Com o Sinfonia": vis["tempo_proposta"].map(dur),
                "Diferença": [("✅ atendido no dia" if rem else
                               (f"⏱️ {dur(g)} a menos" if g > 0 else
                                ("igual" if round(g) == 0 else f"{dur(-g)} a mais")))
                              for rem, g in zip(vis["remarcado_hoje"], vis["ganho"])],
                "Espera pela bolsa (hoje → Sinfonia)": [
                    f"{dur(a)} → {dur(b)}" for a, b in zip(vis["espera_hoje"],
                                                          vis["espera_proposta"])],
            })
            st.download_button("⬇️ Baixar tabela (CSV)",
                               tab.to_csv(index=False, sep=";").encode("utf-8-sig"),
                               file_name="ganhos_por_paciente.csv", mime="text/csv")
            ui.tabela(tab)

# ---------------------------------------------------------------------------
# Aba 4 – Agenda do dia
# ---------------------------------------------------------------------------
with aba_agenda:
    if not otim_ok:
        st.warning("⚠️ Sem agenda organizada. Ajuste as premissas.")
    else:
        ag = R["otim"]["agenda"].dropna(subset=["inicio_infusao"]).copy()
        ordem_rotulos = [ROTULO[p] for p in PERFIS]
        ag["Tipo de tratamento"] = pd.Categorical(ag["perfil"].map(ROTULO), ordem_rotulos)

        tabela_agenda = pd.DataFrame({
            "Paciente": ag["paciente"],
            "Procedência": ag["interior"].map(lambda x: "🚐 Interior" if x else "🏙️ Capital"),
            "Protocolo": ag["protocolo"],
            "Tipo de tratamento": ag["perfil"].map(ROTULO),
            "Horário limite": ag["limite_min"].map(hhmm),
            "Chegada recomendada": ag["chegada"].map(hhmm),
            "Início do preparo": ag["inicio_preparo"].map(hhmm),
            "Início da infusão": ag["inicio_infusao"].map(hhmm),
            "Fim da infusão": ag["fim_infusao"].map(hhmm),
            "Poltrona": ag["poltrona"].astype("Int64"),
        })
        with ui.bloco("exportar"):
            c1, c2, c3 = st.columns([3, 3, 2], vertical_alignment="center")
            c1.markdown("Horários recomendados para cada paciente fictício. "
                        "As durações vêm das premissas informadas pelo hospital.")
            with c2:
                filtro_origem_agenda = st.selectbox(
                    "📍 Filtrar procedência",
                    ["Todos os pacientes", "🏙️ Apenas Capital", "🚐 Apenas Interior"],
                    key="filtro_origem_agenda"
                )
            if filtro_origem_agenda.startswith("🏙️"):
                tab_filtrada = tabela_agenda[tabela_agenda["Procedência"] == "🏙️ Capital"]
            elif filtro_origem_agenda.startswith("🚐"):
                tab_filtrada = tabela_agenda[tabela_agenda["Procedência"] == "🚐 Interior"]
            else:
                tab_filtrada = tabela_agenda

            # No CSV o grupo vai sem emoji, com a cor por extenso (abre melhor no Excel)
            csv = tab_filtrada.assign(**{
                "Tipo de tratamento": ag.loc[tab_filtrada.index, "perfil"].map(
                    lambda g: g + (" (a confirmar)" if g in A_CONFIRMAR else "")).to_numpy(),
                "Cor na folha do setor": ag.loc[tab_filtrada.index, "perfil"].map(COR_DO_GRUPO).to_numpy()})
            c3.download_button("⬇️ Baixar agenda (CSV)",
                               csv.to_csv(index=False, sep=";").encode("utf-8-sig"),
                               file_name="agenda_otimizada.csv", mime="text/csv",
                               type="primary", width="stretch")

        with ui.bloco("gantt_poltronas"):
            ui.titulo_bloco("🪑 Agenda das poltronas", (
                "Cada linha é uma poltrona e cada barra é um paciente, do momento em que senta até a "
                "poltrona ser liberada (acomodação + infusão + alta). A cor e a hachura indicam "
                "o tipo de tratamento (cores da folha do setor, com o nome na legenda); o código "
                "do paciente aparece na barra."))
            ag["ini_dt"], ag["fim_dt"] = em_datetime(ag["senta"]), em_datetime(ag["sai"])
            ag["Poltrona"] = "Poltrona " + ag["poltrona"].astype(str).str.zfill(2)
            ag["Senta"], ag["Infusão"], ag["Sai"] = (ag["senta"].map(hhmm),
                                                     ag["inicio_infusao"].map(hhmm), ag["sai"].map(hhmm))
            fig = px.timeline(ag, x_start="ini_dt", x_end="fim_dt", y="Poltrona",
                              color="Tipo de tratamento", text="paciente",
                              pattern_shape="Tipo de tratamento",
                              color_discrete_map=ui.CORES_ROTULO,
                              pattern_shape_map=ui.HACHURA_ROTULO,
                              category_orders={"Tipo de tratamento": ordem_rotulos,
                                               "Poltrona": sorted(ag["Poltrona"].unique())},
                              hover_data={"ini_dt": False, "fim_dt": False, "Poltrona": False,
                                          "Senta": True, "Infusão": True, "Sai": True})
            fig.update_traces(marker_line_color="white", marker_line_width=2,
                              textfont=dict(size=12, color="#ffffff"), insidetextanchor="middle")
            fig.update_yaxes(autorange="reversed", title=None)
            eixo_horas(fig)
            st.plotly_chart(ui.estilo_grafico(fig, "Poltronas ao longo do dia",
                                              altura=max(500, 24 * prem.n_poltronas)),
                            width="stretch")

        with ui.bloco("gantt_capela"):
            ui.titulo_bloco("🧪 Agenda da capela", (
                "Cada linha é um posto de manipulação da capela e cada barra é o preparo de uma "
                "bolsa. O preparo termina a tempo de a bolsa chegar à poltrona na hora da infusão."))
            ag["pi_dt"], ag["pf_dt"] = em_datetime(ag["inicio_preparo"]), em_datetime(ag["fim_preparo"])
            ag["Posto"] = "Posto " + ag["posto_capela"].astype(str)
            ag["Preparo"] = ag["inicio_preparo"].map(hhmm)
            fig = px.timeline(ag, x_start="pi_dt", x_end="pf_dt", y="Posto",
                              color="Tipo de tratamento", color_discrete_map=ui.CORES_ROTULO,
                              pattern_shape="Tipo de tratamento",
                              pattern_shape_map=ui.HACHURA_ROTULO,
                              category_orders={"Tipo de tratamento": ordem_rotulos},
                              hover_data={"pi_dt": False, "pf_dt": False, "paciente": True,
                                          "Preparo": True, "Infusão": True})
            fig.update_traces(marker_line_color="white", marker_line_width=1)
            fig.update_yaxes(autorange="reversed", title=None)
            eixo_horas(fig)
            st.plotly_chart(ui.estilo_grafico(fig, "Capela ao longo do dia", altura=320),
                            width="stretch")

        with ui.bloco("tabela_agenda"):
            ui.titulo_bloco("📋 Tabela da agenda", (
                "Lista de todos os pacientes fictícios com os horários recomendados. "
                "A chegada recomendada fica sempre pelo menos "
                f"{prem.folga_limite} min antes do horário limite do protocolo. "
                "Use o botão **Baixar agenda** para abrir no Excel."))
            if filtro_origem_agenda != "Todos os pacientes":
                st.caption(f"Filtrando: **{filtro_origem_agenda}** ({len(tab_filtrada)} de {len(tabela_agenda)} pacientes)")
            ui.tabela(tab_filtrada)

# ---------------------------------------------------------------------------
# Aba 5 – Premissas
# ---------------------------------------------------------------------------
with aba_premissas:
    st.markdown("Valores usados no protótipo. **Todos são suposições a validar com o hospital.** "
                "Os tempos de preparo e de infusão são informados pelo hospital: "
                "o sistema nunca os calcula nem altera.")
    SUP = "🟡 suposição a validar"

    with st.form("form_premissas"):
        ui.titulo_bloco("🏥 Unidade", "Horário de funcionamento e capacidade da unidade.")
        c1, c2, c3, c4 = st.columns(4)
        ini_t = c1.time_input(f"Início do turno ({SUP})", time(prem.inicio_turno // 60,
                                                                prem.inicio_turno % 60), step=1800)
        fim_t = c2.time_input(f"Fim do turno ({SUP})", time(prem.fim_turno // 60,
                                                             prem.fim_turno % 60), step=1800)
        n_polt = c3.number_input(f"Número de poltronas ({SUP})", 5, 100, prem.n_poltronas)
        cap_c = c4.number_input(f"Bolsas preparadas ao mesmo tempo na capela ({SUP})", 1, 10,
                                prem.capacidade_capela)

        ui.titulo_bloco("👥 Pacientes do dia", (
            "Quantos pacientes são atendidos no dia e como se dividem por tipo de tratamento. "
            "Os pacientes são **fictícios** (PAC-001, PAC-002...)."))
        c1, c2 = st.columns(2)
        n_pac = c1.number_input(f"Total de pacientes no dia ({SUP})", 5, 200, prem.n_pacientes)
        antes10 = c2.number_input(f"Pacientes que chegam antes das 10h hoje, em % ({SUP})",
                                  0, 100, int(round(prem.frac_antes_10h * 100)))

        ui.titulo_bloco("💉 Tempos por tipo de tratamento", (
            "**Preparo**: minutos para manipular a bolsa na capela.\n\n"
            "**Infusão**: minutos de aplicação da medicação.\n\n"
            "**Parte dos pacientes**: porcentagem do dia com esse tipo de tratamento "
            "(a soma precisa dar 100%).\n\n"
            "Esses tempos são **informados pelo hospital**; o sistema só os usa para montar a agenda."))
        tab_perfis = pd.DataFrame({
            "Tipo de tratamento": PERFIS,
            "Cor na folha": [ROTULO[p].split(" ")[0] + " " + COR_DO_GRUPO[p]
                             + (" – a confirmar" if p in A_CONFIRMAR else "") for p in PERFIS],
            "Preparo (min)": [prem.perfis[p]["preparo"] for p in PERFIS],
            "Infusão (min)": [prem.perfis[p]["infusao"] for p in PERFIS],
            "Parte dos pacientes (%)": [round(prem.perfis[p]["mix"] * 100) for p in PERFIS],
        })
        editado = st.data_editor(tab_perfis, hide_index=True,
                                 disabled=["Tipo de tratamento", "Cor na folha"],
                                 width="stretch", column_config={
                                     c: st.column_config.NumberColumn(min_value=1, max_value=600,
                                                                      step=1)
                                     for c in tab_perfis.columns[2:]})
        st.caption(SUP)

        ui.titulo_bloco("⏰ Horário limite dos protocolos", (
            "Pela folha fixada na unidade, cada protocolo tem um **horário limite** para o "
            "paciente estar na triagem com o farmacêutico. Depois dele o paciente é "
            "**remarcado**.\n\n"
            "**Sexta-feira**: todos os horários limite ficam 1h mais cedo "
            "(encerramento do setor).\n\n"
            "**Folga**: na proposta, a chegada é marcada pelo menos esses minutos antes do "
            "limite."))
        c1, c2 = st.columns(2)
        sexta = c1.checkbox("📅 O dia é uma sexta-feira (limites 1h mais cedo)",
                            value=prem.sexta_feira)
        folga = c2.number_input(f"Folga antes do horário limite, em min ({SUP})", 0, 120,
                                prem.folga_limite)
        with st.expander("Ver a tabela de horários limite (folha do setor)"):
            tab_lim = carregar_protocolos()
            ui.tabela(pd.DataFrame({
                "Protocolo": tab_lim["protocolo"],
                "Horário limite": tab_lim["horario_limite"],
                "Tipo de tratamento": tab_lim["grupo"].map(ROTULO),
            }))

        ui.titulo_bloco("🚐 Pacientes do interior", (
            "Muitos pacientes vêm do interior no **transporte da prefeitura**: chegam cedo e "
            "precisam voltar num horário fixo. Se a poltrona só libera depois disso, o "
            "paciente **perde o transporte**.\n\n"
            "Os horários são sorteados dentro das faixas abaixo (pacientes fictícios). "
            "Todos os valores são **suposições a validar** com o setor."))
        c1, c2, c3 = st.columns(3)
        pct_int = c1.number_input(f"Pacientes do interior, em % ({SUP})", 0, 100,
                                  int(round(prem.frac_interior * 100)))
        chega_de = c2.time_input("Transporte chega a partir de",
                                 time(prem.transporte_chega_de // 60,
                                      prem.transporte_chega_de % 60), step=900)
        chega_ate = c3.time_input("…e até", time(prem.transporte_chega_ate // 60,
                                                prem.transporte_chega_ate % 60), step=900)
        c1, c2, c3 = st.columns(3)
        folga_t = c1.number_input(f"Folga antes do retorno, em min ({SUP})", 0, 120,
                                  prem.folga_transporte)
        espera_int = c1.number_input(
            f"Espera máxima do interior até sentar, em min ({SUP})", 15, 300,
            prem.espera_max_interior,
            help="Da chegada do transporte até sentar na poltrona (com o Sinfonia).")
        volta_de = c2.time_input("Transporte volta a partir de",
                                 time(prem.transporte_volta_de // 60,
                                      prem.transporte_volta_de % 60), step=900)
        volta_ate = c3.time_input("…e até", time(prem.transporte_volta_ate // 60,
                                                prem.transporte_volta_ate % 60), step=900,
                                  key="volta_ate")

        ui.titulo_bloco("🎯 Meta de espera", (
            "Tempo máximo desejado para o paciente ficar **sentado esperando a bolsa**. "
            "Usada nos gráficos e indicadores da aba **O que melhorou**."))
        meta = st.number_input(f"Meta de espera na poltrona, em min ({SUP})", 5, 180,
                               prem.meta_espera)

        ui.titulo_bloco("🚪 Alta e transporte", (
            "**Alta hoje**: minutos entre o fim da infusão e a liberação da poltrona no Tasy.\n\n"
            "**Alta antecipada**: o mesmo tempo quando a alta é preparada antes do fim da "
            "infusão (usado na proposta).\n\n"
            "**Transporte**: minutos para a bolsa ir da farmácia até a poltrona.\n\n"
            "**Acomodação**: na proposta, o paciente senta esses minutos antes da bolsa chegar."))
        c1, c2, c3, c4 = st.columns(4)
        alta_h = c1.number_input(f"Alta hoje, em min ({SUP})", 0, 120, prem.alta_atual)
        alta_a = c2.number_input(f"Alta antecipada, em min ({SUP})", 0, 120, prem.alta_antecipada)
        transp = c3.number_input(f"Transporte da bolsa, em min ({SUP})", 0, 60, prem.transporte)
        acom = c4.number_input(f"Acomodação na proposta, em min ({SUP})", 0, 60, prem.acomodacao)

        with st.expander("Ajustes avançados da simulação de hoje (calibração)"):
            st.markdown("Valores ajustados para a simulação reproduzir os números medidos no "
                        "hospital (espera mediana de 13 min, 21% acima de 30 min, 9% acima de 1h).")
            tab_calib = pd.DataFrame({
                "Tipo de tratamento": PERFIS,
                "Prescrições liberadas antes da chegada (%)":
                    [round(prem.calibracao[p]["pre"] * 100) for p in PERFIS],
                "Atraso típico da liberação após a chegada (min)":
                    [float(prem.calibracao[p]["atraso"]) for p in PERFIS],
            })
            calib_editada = st.data_editor(
                tab_calib, hide_index=True, disabled=["Tipo de tratamento"], width="stretch",
                column_config={
                    tab_calib.columns[1]: st.column_config.NumberColumn(min_value=0, max_value=100),
                    tab_calib.columns[2]: st.column_config.NumberColumn(min_value=0, max_value=120),
                })
            c1, c2 = st.columns(2)
            disp = c1.number_input("Variação do atraso", 0.0, 3.0,
                                   float(prem.atraso_liberacao_dispersao), step=0.1)
            sem = c2.number_input("Número do dia sintético (semente)", 0, 99999, prem.semente)

        gerar = st.form_submit_button("▶️ Gerar dia sintético e calcular agenda", type="primary",
                                      width="stretch")

    if st.button("↩️ Voltar aos valores padrão", width="stretch"):
        st.session_state.premissas = Premissas()
        st.rerun()

    if gerar:
        erros = []
        soma_mix = editado["Parte dos pacientes (%)"].sum()
        if abs(soma_mix - 100) > 0.5:
            erros.append(f"A soma das partes dos pacientes deu {soma_mix:.0f}%. Ela precisa dar 100%.")
        ini_min, fim_min = ini_t.hour * 60 + ini_t.minute, fim_t.hour * 60 + fim_t.minute
        if fim_min - ini_min < 120:
            erros.append("O fim do turno precisa ser pelo menos 2 horas depois do início.")
        if (chega_ate.hour * 60 + chega_ate.minute < chega_de.hour * 60 + chega_de.minute
                or volta_ate.hour * 60 + volta_ate.minute
                < volta_de.hour * 60 + volta_de.minute):
            erros.append("Nos horários do transporte, o \"até\" precisa ser depois do "
                         "\"a partir de\".")
        if editado[["Preparo (min)", "Infusão (min)"]].isna().any().any():
            erros.append("Preencha todos os tempos de preparo e de infusão.")
        if erros:
            for e in erros:
                st.error(f"❌ {e}")
        else:
            perfis = {r["Tipo de tratamento"]: {"preparo": int(r["Preparo (min)"]),
                                                "infusao": int(r["Infusão (min)"]),
                                                "mix": float(r["Parte dos pacientes (%)"]) / 100}
                      for _, r in editado.iterrows()}
            st.session_state.premissas = Premissas(
                inicio_turno=ini_min, fim_turno=fim_min, n_poltronas=int(n_polt),
                capacidade_capela=int(cap_c), n_pacientes=int(n_pac), perfis=perfis,
                frac_antes_10h=antes10 / 100, alta_atual=int(alta_h),
                alta_antecipada=int(alta_a), transporte=int(transp), acomodacao=int(acom),
                calibracao={r["Tipo de tratamento"]: {
                    "pre": float(r.iloc[1]) / 100, "atraso": float(r.iloc[2])}
                    for _, r in calib_editada.iterrows()},
                sexta_feira=bool(sexta), folga_limite=int(folga), meta_espera=int(meta),
                frac_interior=pct_int / 100,
                transporte_chega_de=chega_de.hour * 60 + chega_de.minute,
                transporte_chega_ate=chega_ate.hour * 60 + chega_ate.minute,
                transporte_volta_de=volta_de.hour * 60 + volta_de.minute,
                transporte_volta_ate=volta_ate.hour * 60 + volta_ate.minute,
                folga_transporte=int(folga_t), espera_max_interior=int(espera_int),
                atraso_liberacao_dispersao=float(disp), semente=int(sem))
            st.success("✅ Premissas salvas. Calculando o novo dia…")
            st.rerun()

ui.rodape()
