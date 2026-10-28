# 🩺 RAG Clínico — Saúde Pública e Protocolos Clínicos

Sistema experimental de consulta documental que utiliza **Retrieval-Augmented Generation (RAG)** para buscar evidências em Protocolos Clínicos e Diretrizes Terapêuticas (PCDTs) e gerar respostas fundamentadas em trechos recuperados.

> **Aviso:** ferramenta educacional e de apoio à consulta documental. **Não realiza diagnóstico, não prescreve medicamentos e não substitui profissionais de saúde.** Respostas produzidas por IA exigem conferência das fontes; a validação automática não garante correção clínica.

## Objetivo

Ajudar na localização e síntese de informações sobre protocolos clínicos, incluindo critérios documentais de inclusão, histórico de versões e evidências consultadas. O código organiza a coleta/manifestos, o processamento dos documentos, a recuperação de trechos relevantes, a geração de respostas e a observabilidade.

### Recursos implementados

- Interface **Streamlit** com seleção entre **Artrite reumatoide** e **Artrite idiopática juvenil**, situação documental (**Vigente** ou **Histórico**) e nível de detalhamento (**Mínima**, **Intermediária** ou **Completa**).
- Perguntas livres e perguntas de referência definidas em `benchmarks/perguntas.json`.
- **Roteamento adaptativo** por intenção, doença, medicamento e filtros em `src/query_router.py`.
- **Recuperação híbrida** usando BM25 e embeddings (similaridade de cosseno), combinados por **Reciprocal Rank Fusion (RRF)**.
- Geração de resposta baseada nos trechos recuperados, **verificação documental automática** e identificação de pedidos de conduta clínica individualizada.
- Abas para **resposta, evidências, observabilidade e logs**.

> O roteador reconhece mais temas do que os dois disponíveis no seletor da interface. A disponibilidade de respostas depende dos documentos efetivamente processados na pasta `output/`.

## Arquitetura

```mermaid
flowchart LR
    UI[Interface Streamlit] --> ORQ[Orchestrator]
    ORQ --> R[QueryRouter]
    R --> SAFE{Conduta individualizada?}
    SAFE -->|Sim| REF[Recusa]
    SAFE -->|Não| FILT[Filtros de metadados]
    FILT --> BM[Busca BM25]
    FILT --> VET[Busca vetorial por cosseno]
    BM --> RRF[Fusão RRF]
    VET --> RRF
    RRF --> LLM[Geração com LLM]
    LLM --> VAL[Validação documental]
    VAL --> RESP[Resposta + evidências + métricas]
```

O módulo vetorial empregado na recuperação principal utiliza **similaridade de cosseno em Python**; o projeto também contém utilitários auxiliares para FAISS, mas **não** utiliza FAISS diretamente no fluxo principal mostrado acima.

## Organização dos códigos

| Caminho | Responsabilidade |
| --- | --- |
| `web/app.py` | Interface visual, formulário, abas e apresentação dos resultados. |
| `web/orchestrator.py` | Coordena roteamento, busca, geração, validação e tempo total da consulta. |
| `src/query_router.py` | Interpreta perguntas, identifica entidades/intenções e prepara filtros; sinaliza consultas individualizadas. |
| `src/retrieval/corpus_loader.py` | Carrega os JSONs dos trechos processados. |
| `src/retrieval/filtros.py` | Filtra documentos por doença, vigência e metadados. |
| `src/retrieval/bm25.py` | Calcula a relevância textual BM25. |
| `src/retrieval/vetorial.py` | Calcula similaridade com embeddings. |
| `src/retrieval/rrf.py` | Combina os rankings das duas buscas. |
| `src/retrieval/retrieval_hibrido.py` | Integra carregamento, filtros, buscas e RRF. |
| `src/generate.py` | Cria prompts, consulta o LLM, aplica regras de segurança e verifica respostas. |
| `src/llm/llm_embedding.py` | Solicita embeddings à API configurada. |
| `src/fetch_corpus.py` | Coleta fontes do manifesto e administra inventários/versionamento. |
| `src/chunking/process_md.py` e `src/chunking/run_chunking.py` | Transformam arquivos Markdown já preparados em trechos com metadados. |
| `src/embedding/generate_embeddings.py` | Adiciona vetores numéricos aos trechos JSON. |
| `config.py` e `corpus_manifest*.yaml` | Definições dos modelos, API e catálogo/fonte dos documentos. |
| `main.py` | Execução alternativa do pipeline pelo terminal. |
| `tests/` e `benchmarks/` | Testes automatizados e perguntas de referência. |

## Como executar localmente

### Pré-requisitos

- **Python 3.14** (versão mínima declarada pelo `pyproject.toml` e `.python-version`).
- **uv** (gerenciador de pacotes Python): <https://docs.astral.sh/uv/>.
- Acesso a um serviço de geração **compatível com a API da OpenAI**, com os modelos indicados no `config.py` ou equivalentes que estejam configurados.
- **Corpus processado** com os JSONs dos chunks, e embeddings quando quiser usar a busca vetorial.

Abra o terminal **na pasta raiz** do repositório. No PowerShell (Windows):

```powershell
uv python install 3.14
uv sync
uv pip install -r requirements-interface.txt
Copy-Item .env.example .env
```

Edite `.env` para informar o endpoint e os modelos **a que você realmente tem acesso**. O projeto originalmente aponta para um servidor externo compartilhado; sua disponibilidade **não é garantida**. Não coloque credenciais reais no GitHub.

> O arquivo `uv.lock` foi mantido como recebido. O Streamlit não estava declarado no `pyproject.toml` original, portanto é instalado separadamente por `requirements-interface.txt`. Este procedimento não modifica o lockfile.

### Preparação dos documentos (etapa obrigatória para consultas reais)

O ZIP original **não contém** `output/output_chunking/v8/`, nem o corpus Markdown completo em `data/processed/v8/`. Sem esses dados, a interface pode abrir, mas a recuperação de evidências não funcionará.

**Opção A — mais fácil para a demonstração:** obtenha da equipe os **JSONs de chunks já processados** da versão `v8`, salve-os em `output/output_chunking/v8/` e confira se os documentos relevantes estão presentes.

**Opção B — reconstruir o processamento:** a coleta usa o manifesto e cria os arquivos brutos e inventários; é necessário preparar os Markdown correspondentes em `data/processed/v8/` e então executar chunking e embeddings. **O ZIP não inclui uma rotina única de conversão em lote dos PDFs brutos para esses arquivos Markdown.**

```powershell
uv run --no-sync python -m src.fetch_corpus fetch --manifest corpus_manifest.yaml
# Após obter e preparar os Markdown de data/processed/v8/:
uv run --no-sync python -m src.init.init_chunking
uv run --no-sync python -m src.init.init_embeddings
```

A preparação dos embeddings depende do modelo e do servidor configurados; confira metadados, licenças e vigência das fontes antes de usá-las.

### Iniciar a interface

```powershell
uv run --no-sync python -m streamlit run web/app.py
```

Acesse a URL local exibida no terminal (em geral `http://localhost:8501`). Na primeira consulta, o orquestrador carrega o corpus e inicia a recuperação dos trechos.

### Utilizar pelo terminal (opcional)

```powershell
uv run --no-sync python main.py "Quais são os critérios do PCDT vigente para artrite reumatoide?" --llm
```

O comando do terminal exige `output/output_chunking/v8/`. Sem `--llm`, o comando prepara a geração sem consultar o modelo de linguagem.

### Executar os testes

```powershell
uv run --no-sync python -m pytest -q
```

Os módulos podem ser testados separadamente; os testes que dependem de integração/serviços externos precisam das respectivas dependências e configuração. Na análise deste pacote, **33 testes do roteador e chunking passaram em ambiente isolado**; a suíte completa e a consulta ponta a ponta **não foram validadas** neste ambiente.

## Demonstração sugerida

1. Abra a interface e selecione **Artrite reumatoide** + **Vigente** + **Intermediária**.
2. Selecione no benchmark **“Quais são os critérios de inclusão no PCDT vigente?”** e clique em **Executar consulta**.
3. Mostre as abas **Resposta**, **Evidências** e **Observabilidade**. A apresentação dos resultados depende do corpus e do servidor de IA estarem disponíveis.
4. Em uma nova consulta, digite **“Meu pai tem artrite reumatoide. Que remédio ele deve tomar?”** para demonstrar a recusa de orientação individualizada.

O roteiro narrado, com marcações de tela para cinco minutos, está em [`ROTEIRO_VIDEO_5_MIN.md`](ROTEIRO_VIDEO_5_MIN.md). O passo a passo de publicação está em [`PUBLICAR_NO_GITHUB.md`](PUBLICAR_NO_GITHUB.md).

## Limitações e cuidados

- A verificação de fontes é **automática e experimental**, não uma auditoria de qualidade médica.
- O mascaramento de alguns identificadores pessoais é feito por **expressões regulares**, portanto não cobre todos os formatos ou tipos de dado sensível.
- A interface contém atualmente **duas doenças selecionáveis**, apesar de o roteador reconhecer outras.
- O fluxo depende de **arquivos externos processados** e de um **servidor de modelos acessível**.
- **Não utilize dados de pacientes reais** em testes, capturas de tela, vídeos ou logs; mantenha `data/raw/`, `data/processed/`, `output/` e `logs/` fora do repositório público.

## Equipe e créditos

Projeto acadêmico coletivo **Time 02 — Saúde**. Integrantes informados no README original:

- Elcio Berilo
- Lindemir Hoffmann
- Patrícia Starck
- Patrícia Zan
- Paula Femina
- Silvio Lima
- Sueli da Hora

Respeite a autoria coletiva, as permissões para divulgação dos documentos e o uso dos serviços externos. O projeto não traz licença de software explícita; nenhuma foi presumida.
