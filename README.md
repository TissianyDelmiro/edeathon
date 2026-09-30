# Protótipo – Fluxo da quimioterapia (Ideathon CBEB 2026, Desafio 1)

> **Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy.**

Organiza o dia da unidade de quimioterapia para que a bolsa esteja pronta quando o
paciente senta na poltrona, e para que o trabalho da capela da farmácia seja
distribuído ao longo do dia.

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

O app abre no navegador. Ao abrir, a agenda do dia padrão é calculada
automaticamente, o que leva até 20 segundos. Não usa nenhuma API externa.

Para rodar os testes: `python -m pytest tests`

## Telas

| Aba | Para quê |
|---|---|
| 🏥 **Painel do dia** (tela inicial) | Para tablet ou TV do setor. Arraste a "hora atual" e veja o mapa das poltronas, os alertas, a fila da farmácia e a situação das bolsas. |
| 📊 **Hoje x Proposta** | Indicadores lado a lado com a variação em %, gráficos por hora e a comparação da simulação com os números reais. |
| 📅 **Agenda do dia** | Gantt das poltronas e da capela, tabela de horários e exportação em CSV. |
| ⚙️ **Premissas** | Edição de todos os valores de entrada e geração de um novo dia sintético. |

## Módulos

| Arquivo | Conteúdo |
|---|---|
| `dados.py` | Premissas e gerador do dia sintético (PAC-001, PAC-002...) |
| `simulacao_atual.py` | Simulação de eventos discretos do funcionamento atual (filas por ordem de chegada) |
| `otimizador.py` | Modelo CP-SAT (OR-Tools) da agenda otimizada |
| `indicadores.py` | Cálculo dos indicadores e das séries por hora |
| `painel.py` | Estado da unidade em uma hora qualquer (poltronas, bolsas, fila, alertas) |
| `ui_componentes.py` / `app.py` | Interface acessível em Streamlit |

## Premissas usadas (todas são suposições a validar com o hospital)

| Premissa | Valor padrão |
|---|---|
| Turno | 7h às 18h |
| Poltronas | 40 |
| Capela | 3 bolsas manipuladas ao mesmo tempo |
| Pacientes no dia | 90 (57% chegam antes das 10h no cenário atual) |
| Alta após o fim da infusão | 15 min hoje · 5 min com alta antecipada (proposta) |
| Transporte da bolsa | 5 min |
| Acomodação (proposta) | o paciente senta 10 min antes da bolsa chegar |

| Tipo de tratamento | Preparo (min) | Infusão (min) | Parte dos pacientes |
|---|---|---|---|
| A (curto) | 9 | 51 | 35% |
| Suporte | 6 | 15 | 20% |
| Médio | 12 | 120 | 30% |
| Longo | 15 | 240 | 15% |

**Regra do evento:** os tempos de preparo e de infusão são **parâmetros informados
pelo hospital**. O sistema só os usa para agendar e nunca os calcula nem altera.
Nenhuma decisão clínica é tomada.

### Cenário atual (simulação)
- O paciente senta ao chegar; se não houver poltrona, espera na recepção.
- A capela é uma fila única por ordem de liberação da prescrição.
- 60% das prescrições já estão liberadas antes da chegada. As demais são liberadas
  cerca de 4 min depois da chegada, com variação.
- **Calibração.** Os tempos de preparo e a liberação das prescrições foram ajustados
  para reproduzir os números medidos no hospital. No dia padrão (semente 125):

| Número | Real | Simulado |
|---|---|---|
| Espera na poltrona (mediana) | 13 min | 13 min |
| Esperam mais de 30 min | 21% | 27% |
| Esperam mais de 1h | 9% | 9% |
| Horas de poltrona sem tratamento | ~54 h | 52 h |
| Maior número de pacientes ao mesmo tempo | 49 | 42 |

O pico fica abaixo do real porque o protótipo usa 40 poltronas. Confirmar esse
número com o hospital.

### Proposta (CP-SAT)
- **Variável de decisão:** o início da infusão de cada paciente, em slots de 10 min.
- **Restrições:**
  - o preparo na capela respeita a capacidade da capela (restrição cumulativa);
  - a poltrona (acomodação + infusão + alta) respeita o número de poltronas (restrição cumulativa);
  - a infusão só começa depois que a bolsa foi preparada e transportada;
  - tudo acontece dentro do turno.
- **Objetivo, em ordem de peso:**
  1. maximizar as horas de quimioterapia dentro do turno;
  2. suavizar a carga da capela (menor pico de preparo por hora);
  3. minimizar a espera na poltrona;
  4. minimizar o tempo em que a bolsa pronta fica parada.
- **Limite de tempo:** 20 s. O solver para antes quando a solução está a menos de 2%
  da melhor possível, e o status aparece na tela.
- **Hipóteses da proposta:**
  - a prescrição é liberada com antecedência (agendamento prévio);
  - a alta é preparada antes do fim da infusão.
- **Reprodutibilidade:** o solver usa várias linhas de execução em paralelo, então
  duas execuções podem gerar agendas um pouco diferentes, com a mesma qualidade.
# edeathon
