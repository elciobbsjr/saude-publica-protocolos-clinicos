# Personas

## 1. Personas Próprias

**1. Dr. Carlos · Médico Auditor de Secretaria Municipal de Saúde**

- Situação: Analisa solicitações judiciais e administrativas de medicamentos de alto custo que estão fora da rotina padrão da atenção básica.

- Urgência: Média-alta (prazos judiciais apertados de 48h a 72h para resposta técnica).

**2. Mariana · Enfermeira da Estratégia Saúde da Família (ESF)**

- Situação: Realiza grupos educativos de pacientes crônicos (hipertensão e diabetes) e precisa orientar a comunidade com base estritamente nas diretrizes oficiais do SUS.

- Urgência: Baixa-média (busca tirar dúvidas rápidas durante o planejamento dos grupos ou atendimento compartilhado).

**3. Fábio · Farmacêutico Dispensador em Unidade Básica**

- Situação: Enfrenta pacientes no balcão da farmácia municipal questionando divergências entre o que o médico receitou, o que a RENAME possui e o que o PCDT orienta.

- Urgência: Alta (paciente na sua frente aguardando a liberação ou negação imediata do medicamento).

## 2. Nove Perguntas de Referência (3 por Persona Própria)

### Para a Persona 1: Dr. Carlos (Médico Auditor)

1.  Pergunta: "Quais são os critérios exatos de exclusão para o uso de dapagliflozina no PCDT de Diabetes Mellitus Tipo 2 vigente?"

        Rota esperada: Normativa
        Tipo: Factual / Vigência

2.  Pergunta: "O medicamento X consta na RENAME vigente com indicação aprovada para o tratamento de insuficiência cardíaca crônica?"

        Rota esperada: Estruturada
        Tipo: Filtro

3.  Pergunta: "O PCDT atual de uma determinada doença incorpora o medicamento Y, mas os registros de dispensação do DATASUS mostram que ele foi distribuído no município em 2025? Qual é a divergência temporal?"

        Rota esperada: Normativa + Agregada
        Tipo: Cross-source

### Para a Persona 2: Mariana (Enfermeira da ESF)

1.  Pergunta: "Quais são os parâmetros recomendados de frequência para automonitorização glicêmica capilar em pacientes com Diabetes Tipo 2 conforme o protocolo atual?"

        Rota esperada: Normativa
        Tipo: Factual

2.  Pergunta: "Quais foram os indicadores agregados de cobertura de vacinação ou acompanhamento de hipertensos na região sul do país no último consolidado do DATASUS?"

        Rota esperada: Agregada
        Tipo: Factual

3.  Pergunta: "Como devo proceder clinicamente para ajustar a dieta e os exercícios de um paciente específico que está com picos pressóricos de 160/100?"

        Rota esperada: Nenhuma (Recusa)
        Tipo: Recusa (Conduta individualizada)

### Para a Persona 3: Fábio (Farmacêutico Dispensador)

1.  Pergunta: "Este medicamento para tratamento de dislipidemia está listado na RENAME na apresentação de 20mg ou apenas 10mg?"

        Rota esperada: Estruturada
        Tipo: Filtro

2.  Pergunta: "O que mudou em termos de restrições de idade ou comorbidades entre a versão de 2022 e a versão de 2024 do PCDT de Asma Grave?"

        Rota esperada: Normativa (Pares de versão)
        Tipo: Vigência / Cross-source

3.  Pergunta: "Qual o impacto orçamentário médio ou o volume total de internações por hipertensão arterial no estado do Rio de Janeiro segundo os dados abertos mais recentes?"

        Rota esperada: Agregada
        Tipo: Fora de escopo / Indicadores

## A Pergunta que o Sistema Vai Errar (Diagnóstico Antecipado)

**"O protocolo de tratamento de Diabetes Tipo 2 atualizado em 2024 manteve a mesma diretriz de primeira linha da versão de 2022 para pacientes idosos com comorbidade renal?"**

Nossa Hipótese de Erro (Por que vamos errar):

- O sistema tentará fazer a busca semântica tradicional unificada. Como os trechos textuais das duas versões (antiga e vigente) tratam do mesmo tema com redações muito parecidas semanticamente, o recuperador poderá resgatar os dois chunks (ou apenas o mais antigo por viés de pontuação de BM25) e o gerador vai fazer uma média ponderada alucinatória ou ignorar a mudança sutil na data de vigência, respondendo que "nada mudou" ou misturando as regras de exclusão antigas com as novas.

- Como mitigaremos nas próximas Sprints: Forçar o Metadata Filtering obrigatório por campo_vigencia e injetar explicitamente instruções no prompt para contrastar datas caso a query contenha termos temporais ou de comparação de versões.
