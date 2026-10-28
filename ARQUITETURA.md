ARQUITETURA.md - Sistema RAG Adaptativo (Saúde Pública e Protocolos Clínicos)

1. Cenário escolhido, com duas frases de justificativa.
Cenário Selecionado: Cenário 2 · Saúde Pública e Protocolos Clínicos.
Justificativa 1: Oferece o maior impacto demonstrável e guardrails de segurança extremamente claros (a distinção qualitativa entre responder o conteúdo geral de um protocolo e recusar a prescrição individualizada para um paciente).
2. Diagrama do pipeline planejado, com os estágios nomeados (os mesmos nomes que vão para o campo stage do log).

```mermaid
flowchart TD
    User([Entrada do Usuário / Query]) --> QA["1. query_analysis<br><i>Extração de intenção, entidades e filtros temporais</i>"]
    
    QA --> ROUTE{"2. roteamento<br><i>Decisão adaptativa da rota da evidência</i>"}
    
    ROUTE -->|Normativa / Estruturada / Agregada / Conversacional| RET["3. retrieval_hibrido<br><i>Busca Densa + BM25 com filtro de vigência</i>"]
    
    RET --> RRF["4. fusao_rrf<br><i>Reciprocal Rank Fusion</i>"]
    
    RRF --> RANK["5. rerank<br><i>Reclassificação por Cross-Encoder (Top-K)</i>"]
    
    RANK --> GEN["6. geracao<br><i>Síntese baseada estritamente nas evidências</i>"]
    
    GEN --> VAL{"7. validacao<br><i>Guardrails clínicos e mascaramento LGPD</i>"}
    
    VAL -->|Resposta Aprovada| OUT([Entrega ao Usuário])
    VAL --> LOG["8. feedback e obs<br><i>Logs estruturados em JSONL e métricas</i>"]
    OUT --> LOG

    classDef default fill:#1e1e2e,stroke:#89b4fa,stroke-width:1px,color:#cdd6f4;
    classDef decision fill:#313244,stroke:#f9e2af,stroke-width:1.5px,color:#f9e2af;
    classDef terminal fill:#11111b,stroke:#a6e3a1,stroke-width:1.5px,color:#a6e3a1;

    class ROUTE,VAL decision;
    class User,OUT terminal;
```

Divisão de responsabilidades
Coordenador da Equipe: Patricia Starck Responsável por orquestrar os prazos, revisar PRs cruciais, unificar os módulos e garantir a coesão das Sprints (além de colocar a mão na massa).
> ⚠️ **PROPOSTA — aguardando validação do grupo.** A tabela abaixo é uma sugestão de divisão para os módulos que ainda estavam sem responsável. Confirmar com todos antes de considerar fechada.
<!-- prettier-ignore -->
Módulo / Componente Descrição da Responsabilidade Responsáveis (Integrantes)

1. Core & Coleta (src/fetch_corpus.py) Implementação do manifesto, comandos fetch, update, inventory, tratamento de rate limits e geração do inventário em JSON e Markdown. Patricia Zan
2. Ingestão, Chunking e Metadados Estratégias de parsing de PDFs dos PCDTs, serialização da RENAME e aplicação obrigatória de metadados de vigência e sensibilidade. Paula + Silvio (apoio)
3. Roteador Adaptativo & Query Analysis Módulo de decisão de rota (para qual base enviar a pergunta) e extração inteligente de entidades/filtros da query do usuário. Elcio
4. Recuperação Híbrida & RRF (retrieval) Implementação da busca vetorial + BM25, aplicação de filtros por metadado (essencial para o cenário de vigência) e fusão por RRF. Lindemir
5. Geração, Guardrails e Recusas Construção dos prompts, integração com o LLM, aplicação dos guardrails de saúde (recusa de prescrição individualizada) e mascaramento de LGPD. Sueli
6. Observabilidade, Logging & Testes Garantia do padrão JSONL (logs/), decorator de rastreio (run_id, tokens, latência) e estruturação da suíte de testes (tests/ com pytest). Patricia Starck
