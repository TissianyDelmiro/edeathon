Quero um protótipo funcional em Python usando Streamlit \+ Google OR-Tools (CP-SAT) \+ pandas \+ plotly, para o Ideathon CBEB 2026 (Desafio 1: fluxo de quimioterapia do SUS em um hospital oncológico de Fortaleza).

\#\# Contexto do problema
Hoje a unidade de quimioterapia é ineficiente: 57% dos pacientes chegam antes das 10h, a sala fica no limite entre 9h45 e 13h (pico de 49 pacientes simultâneos), e a capela da farmácia (onde as bolsas de quimio são manipuladas) vira uma fila única sem prioridade. O paciente senta na poltrona e espera a bolsa ficar pronta (tempo T2): mediana de 13 min, mas 21% esperam mais de 30 min e 9% mais de 1h. São cerca de 54 horas de poltrona por dia ocupadas só com espera. De manhã a capela fica sobrecarregada e à tarde sobra capacidade. A poltrona só é liberada quando a enfermagem dá alta no sistema Tasy.
Perfis de infusão: perfil A (curto, \~51 min, hoje espera \~43 min), terapia de suporte (\~15 min, hoje espera \~47 min), perfil médio e perfil longo.

\#\# Regras obrigatórias do evento
\- NÃO usar nenhum dado real ou sensível de paciente. Gerar dados sintéticos com IDs fictícios (PAC-001, PAC-002...).
\- NÃO tomar nenhuma decisão clínica. A duração de infusão e de preparo de cada perfil é um parâmetro de entrada informado pelo hospital, nunca calculado ou alterado pelo sistema.
\- Mostrar um aviso fixo no topo: "Protótipo com dados sintéticos. Não substitui decisão clínica nem o sistema Tasy."

\#\# O que o app deve ter (4 abas)

\#\#\# Aba 1: Premissas
Parâmetros editáveis, com valores padrão e marcados como "suposição a validar":
\- turno de 7h às 18h
\- número de poltronas (padrão 40\)
\- capacidade da capela em bolsas simultâneas (padrão 3\)
\- tempo de preparo por perfil
\- duração de infusão por perfil (A=51, suporte=15, médio=120, longo=240 min)
\- mix de pacientes por perfil e total de pacientes no dia (padrão 90\)
\- tempo de alta após o fim da infusão (padrão 15 min hoje, 5 min com alta antecipada)
Botão para gerar o dia sintético.

\#\#\# Aba 2: Cenário atual x Cenário otimizado
\- Cenário atual: simulação de eventos discretos (fila FIFO) com as chegadas concentradas de manhã (57% antes das 10h), a capela atendendo por ordem de chegada e o paciente sentando na poltrona ao chegar. Calibrar para ficar próximo dos números reais citados acima e mostrar essa comparação.
\- Cenário otimizado com CP-SAT:
  \- variável: horário de início de cada paciente em slots de 10 min;
  \- intervalo de preparo na capela antes da infusão, com restrição cumulativa da capacidade da capela;
  \- intervalo de poltrona (infusão \+ alta), com restrição cumulativa do número de poltronas;
  \- o paciente só ocupa a poltrona quando a bolsa está pronta;
  \- objetivo: minimizar a espera total, suavizar a carga da capela ao longo do dia e maximizar as horas de QT realizadas dentro do turno;
  \- limite de tempo do solver de 20 s e exibição do status da solução.
\- KPIs lado a lado com a variação em %: horas de QT/dia, horas de poltrona em espera, T2 mediano e p90, % de pacientes com espera \> 30 min, pico de pacientes simultâneos e ocupação da capela manhã x tarde.
\- Gráfico de carga da capela por hora (atual x otimizado) e gráfico de poltronas ocupadas por hora.

\#\#\# Aba 3: Agenda otimizada
\- Gantt por poltrona e Gantt da capela, com cor por perfil.
\- Tabela da agenda: paciente fictício, perfil, horário de chegada recomendado, início do preparo, início e fim da infusão.
\- Botão para exportar CSV.

\#\#\# Aba 4: Painel do dia (simulação de operação)
Um slider de "hora atual" que avança o dia e mostra:
\- mapa de poltronas em grade (livre, aguardando bolsa, em infusão, em alta), com a previsão de liberação de cada uma;
\- fila da capela ordenada pela próxima poltrona a liberar (sistema puxado);
\- status de cada bolsa: prescrita, em preparo, pronta, em transporte, instalada;
\- alertas de "faltam 15 min para acabar a infusão" (preparar alta) e "espera acima de 30 min".

\#\# Qualidade do código
\- Separar em módulos: gerador de dados, simulação do cenário atual, modelo CP-SAT, cálculo de KPIs e interface.
\- Código comentado em português e interface toda em português do Brasil.
\- Incluir requirements.txt e um README curto explicando como rodar e quais premissas foram usadas.
\- Funcionar com \`streamlit run app.py\`, sem nenhuma API externa.
