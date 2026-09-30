"""
Protótipo – Fluxo da quimioterapia (Ideathon CBEB 2026, Desafio 1).

Rodar com:  streamlit run app.py

Abas:
1. Painel do dia            – tela inicial, para tablet ou TV do setor
2. Hoje x Proposta          – cenário atual simulado x agenda otimizada
3. Agenda do dia            – Gantt das poltronas e da capela, tabela e exportação
4. Premissas                – valores de entrada (todos "suposição a validar")
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, time, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import indicadores as I
import painel as P
import ui_componentes as ui
from dados import PERFIS, Premissas, gerar_dia, hhmm
from otimizador import otimizar
from simulacao_atual import simular_atual

st.set_page_config(page_title="Quimioterapia – Painel do dia", page_icon="💧", layout="wide")
ui.aplicar_estilo()

DATA_BASE = datetime(2026, 1, 1)  # data fictícia usada só para desenhar os gráficos de horário


# ---------------------------------------------------------------------------
# Cálculo (guardado em cache: só refaz quando as premissas mudam)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=10)
def calcular(premissas_json: str) -> dict:
    prem = Premissas(**json.loads(premissas_json))
    dia = gerar_dia(prem)
    atual = simular_atual(dia, prem)
    otim = otimizar(dia, prem, limite_s=20)
    k_atual = I.calcular_kpis(atual, prem, prem.alta_atual)
    k_otim = I.calcular_kpis(otim["agenda"], prem, prem.alta_antecipada) if otim["ok"] else None
    return {"dia": dia, "atual": atual, "otim": otim, "k_atual": k_atual, "k_otim": k_otim}


def para_json(prem: Premissas) -> str:
    return json.dumps(dataclasses.asdict(prem), sort_keys=True)


if "premissas" not in st.session_state:
    st.session_state.premissas = Premissas()
prem: Premissas = st.session_state.premissas

try:
    with st.spinner("⏳ Calculando a melhor agenda do dia… isso pode levar até 20 segundos."):
        R = calcular(para_json(prem))
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


ui.cabecalho(f"Organização do dia · dia sintético com {prem.n_pacientes} pacientes · "
             f"{prem.n_poltronas} poltronas · capela com {prem.capacidade_capela} postos")

aba_painel, aba_comparar, aba_agenda, aba_premissas = st.tabs(
    ["🏥 Painel do dia", "📊 Hoje x Proposta", "📅 Agenda do dia", "⚙️ Premissas"])

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
    ag = R["otim"]["agenda"] if escolha.startswith("Proposta") else R["atual"]

    estado = P.estado_poltronas(ag, t, prem.n_poltronas)
    cont = estado["situacao"].value_counts()
    recepcao = P.na_recepcao(ag, t)
    cartoes = [ui.cartao_resumo(ic, tx, int(cont.get(k, 0)), f, b)
               for k, (ic, tx, f, b) in ui.SITUACAO_POLTRONA.items()]
    if len(recepcao):
        cartoes.append(ui.cartao_resumo("🪑", "Na recepção sem poltrona", len(recepcao),
                                        *ui.ESPERA_LONGA[2:]))
    ui.resumo(cartoes)

    # Alertas
    with ui.bloco("alertas"):
        ui.titulo_bloco("🔔 Alertas agora", (
            "Avisos para a equipe no horário escolhido:\n\n"
            "- **⚠️ Espera acima de 30 min**: paciente sentado aguardando a bolsa há mais de meia hora.\n"
            "- **🔔 Preparar alta**: faltam 15 minutos ou menos para acabar a infusão. "
            "Adiantar a alta libera a poltrona mais rápido."))
        lista = P.alertas(ag, t)
        if not lista:
            ui.caixa_alerta("ok", "Nenhum alerta neste horário.")
        for a in lista[:8]:
            ui.caixa_alerta(a["tipo"], a["texto"])
        if len(lista) > 8:
            with st.expander(f"Ver mais {len(lista) - 8} alertas"):
                for a in lista[8:]:
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
            "**Libera às** é a previsão de quando a poltrona fica livre."))
        ui.grade_poltronas(estado, hhmm)

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
                "Paciente": bolsas["paciente"], "Tipo de tratamento": bolsas["perfil"],
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
        if otim["fora_do_turno"]:
            texto_status += (f" ⚠️ {len(otim['fora_do_turno'])} paciente(s) não couberam no "
                             f"turno: {', '.join(otim['fora_do_turno'])}.")
        st.info(texto_status)

        ka, ko = R["k_atual"], R["k_otim"]
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
# Aba 3 – Agenda do dia
# ---------------------------------------------------------------------------
with aba_agenda:
    if not otim_ok:
        st.warning("⚠️ Sem agenda organizada. Ajuste as premissas.")
    else:
        ag = R["otim"]["agenda"].dropna(subset=["inicio_infusao"]).copy()
        ag["Tipo de tratamento"] = pd.Categorical(ag["perfil"], PERFIS)

        tabela_agenda = pd.DataFrame({
            "Paciente": ag["paciente"],
            "Tipo de tratamento": ag["perfil"],
            "Chegada recomendada": ag["chegada"].map(hhmm),
            "Início do preparo": ag["inicio_preparo"].map(hhmm),
            "Início da infusão": ag["inicio_infusao"].map(hhmm),
            "Fim da infusão": ag["fim_infusao"].map(hhmm),
            "Poltrona": ag["poltrona"].astype("Int64"),
        })
        with ui.bloco("exportar"):
            c1, c2 = st.columns([3, 2], vertical_alignment="center")
            c1.markdown("Horários recomendados para cada paciente fictício. "
                        "As durações vêm das premissas informadas pelo hospital.")
            c2.download_button("⬇️ Baixar agenda (CSV)",
                               tabela_agenda.to_csv(index=False, sep=";").encode("utf-8-sig"),
                               file_name="agenda_otimizada.csv", mime="text/csv",
                               type="primary", width="stretch")

        with ui.bloco("gantt_poltronas"):
            ui.titulo_bloco("🪑 Agenda das poltronas", (
                "Cada linha é uma poltrona e cada barra é um paciente, do momento em que senta até a "
                "poltrona ser liberada (acomodação + infusão + alta). A cor indica o tipo de "
                "tratamento; o código do paciente aparece na barra."))
            ag["ini_dt"], ag["fim_dt"] = em_datetime(ag["senta"]), em_datetime(ag["sai"])
            ag["Poltrona"] = "Poltrona " + ag["poltrona"].astype(str).str.zfill(2)
            ag["Senta"], ag["Infusão"], ag["Sai"] = (ag["senta"].map(hhmm),
                                                     ag["inicio_infusao"].map(hhmm), ag["sai"].map(hhmm))
            fig = px.timeline(ag, x_start="ini_dt", x_end="fim_dt", y="Poltrona",
                              color="Tipo de tratamento", text="paciente",
                              color_discrete_map=ui.CORES_PERFIL,
                              category_orders={"Tipo de tratamento": PERFIS,
                                               "Poltrona": sorted(ag["Poltrona"].unique())},
                              hover_data={"ini_dt": False, "fim_dt": False, "Poltrona": False,
                                          "Senta": True, "Infusão": True, "Sai": True})
            fig.update_traces(marker_line_color="white", marker_line_width=2,
                              textfont=dict(size=12, color="#111111"), insidetextanchor="middle")
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
                              color="Tipo de tratamento", color_discrete_map=ui.CORES_PERFIL,
                              category_orders={"Tipo de tratamento": PERFIS},
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
                "Use o botão **Baixar agenda** para abrir no Excel."))
            ui.tabela(tabela_agenda)

# ---------------------------------------------------------------------------
# Aba 4 – Premissas
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
            "Preparo (min)": [prem.perfis[p]["preparo"] for p in PERFIS],
            "Infusão (min)": [prem.perfis[p]["infusao"] for p in PERFIS],
            "Parte dos pacientes (%)": [round(prem.perfis[p]["mix"] * 100) for p in PERFIS],
        })
        editado = st.data_editor(tab_perfis, hide_index=True, disabled=["Tipo de tratamento"],
                                 width="stretch", column_config={
                                     c: st.column_config.NumberColumn(min_value=1, max_value=600,
                                                                      step=1)
                                     for c in tab_perfis.columns[1:]})
        st.caption(SUP)

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
            c1, c2, c3, c4 = st.columns(4)
            f_pre = c1.number_input("Prescrições liberadas antes da chegada (%)", 0, 100,
                                    int(round(prem.frac_pre_liberada * 100)))
            atr = c2.number_input("Atraso típico da liberação após a chegada (min)", 0.0, 120.0,
                                  float(prem.atraso_liberacao_mediana))
            disp = c3.number_input("Variação desse atraso", 0.0, 3.0,
                                   float(prem.atraso_liberacao_dispersao), step=0.1)
            sem = c4.number_input("Número do dia sintético (semente)", 0, 99999, prem.semente)

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
        if editado.iloc[:, 1:3].isna().any().any():
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
                frac_pre_liberada=f_pre / 100, atraso_liberacao_mediana=float(atr),
                atraso_liberacao_dispersao=float(disp), semente=int(sem))
            st.success("✅ Premissas salvas. Calculando o novo dia…")
            st.rerun()
