# Base Agregada — Internações do SIH/SUS (Cenário 2)

**Integração no corpus:** Paula Femina
**Geração dos dados:** Silvio Lima (PySUS)
**base_id no manifesto:** `sih_agregados`
**Natureza:** agregada

Este documento explica de onde vêm os dados agregados de internações, como estão
organizados e como entram no corpus, complementando o `corpus_manifest_sih.yaml`.

## Fonte

- **SIH/SUS — Sistema de Informações Hospitalares do SUS** (DATASUS / Ministério
  da Saúde), dados abertos.
- Extraídos com a biblioteca **PySUS** por Silvio Lima, apenas para o ano de
  **2025**, baixados por região.
- As tabelas agregadas de cada região foram convertidas em frases em linguagem
  natural, uma por linha, no arquivo `corpus_sih_agregados_rag.jsonl`.

## O arquivo

| Item | Valor |
|---|---|
| Arquivo | `SIH_dir/corpus_sih_agregados_rag.jsonl` |
| Registros | 8.317 (1 por linha) |
| Período | 2025 |
| Tamanho | 9.309.112 bytes |
| SHA-256 | `c5cb08ed1d15aad99c9aa4dcfe97d19cbd896b3ee714ba475a4da3bd144f384b` |
| Onde fica | Fora do Git (`SIH_dir/` está no `.gitignore`); no Drive da equipe em `Time2RAG/protocolos_normativa_verificados/Base-agregada/SIH_dir` |

**Doenças (11):** artrite idiopática juvenil, artrite psoriática, artrite
reumatoide, asma, diabete melito tipo 1, diabete melito tipo 2, dislipidemia,
hepatite B, hepatite C, hipertensão arterial sistêmica e psoríase.

**Regiões:** Centro-Oeste, Nordeste, Norte, Sudeste e Sul.

### Estrutura de cada linha

Cada linha é um JSON com três campos:

- `id` — identificador sequencial (ex.: `SIH|000001`);
- `text` — a frase pronta usada na busca;
- `metadata` — os dados estruturados da frase.

Exemplo real (primeira linha):

```json
{"id": "SIH|000001",
 "text": "Em 2025, na região Centro-Oeste, foram registradas 60 internações hospitalares relacionadas a artrite idiopática juvenil, considerando o local de atendimento, com 0 óbitos. A letalidade hospitalar foi de 0,00%. Fonte: SIH/SUS (DATASUS).",
 "metadata": {"doenca": "artrite_idiopatica_juvenil", "periodo": "2025",
              "granularidade_temporal": "anual", "nivel": "regiao",
              "dimensao_geografica": "atendimento", "regiao_atendimento": "Centro-Oeste",
              "internacoes": 60, "obitos": 0, "letalidade_percentual": 0.0,
              "tabela_origem": "agregado_regiao.csv",
              "arquivo_zip_origem": "sih_rag_resultado_centro-oeste.zip", "...": "..."}}
```

### Tipos de agregação

Contagem feita sobre o arquivo (`nivel | granularidade | tabela de origem`):

| Nível | Granularidade | Tabela de origem | Registros |
|---|---|---|---:|
| região | anual | `agregado_regiao.csv` | 55 |
| região (residência) | anual | `agregado_regiao_residencia.csv` | 133 |
| UF | anual | `agregado_uf.csv` | 282 |
| UF (residência) | anual | `agregado_uf_residencia.csv` | 442 |
| sexo | anual | `agregado_sexo.csv` | 110 |
| UF × sexo | anual | `agregado_uf_sexo.csv` | 530 |
| fluxo entre UFs | anual | `agregado_fluxo_uf.csv` | 715 |
| região | mensal | `mensal_regiao.csv` | 633 |
| região (residência) | mensal | `mensal_regiao_residencia.csv` | 873 |
| UF | mensal | `mensal_uf.csv` | 2.078 |
| UF (residência) | mensal | `mensal_uf_residencia.csv` | 2.466 |
| **Total** | | | **8.317** |

**Atenção ao responder:** há agregações pelo **local de atendimento** e pelo
**local de residência** do paciente (campo `dimensao_geografica`), além de uma
agregação de fluxo entre UFs. Para a mesma região ou UF, os dois recortes podem
dar números diferentes. A frase de cada registro diz qual recorte está sendo
usado; a resposta deve citá-lo.

## Como entra no corpus

1. **Manifesto da base:** `corpus_manifest_sih.yaml` declara o JSONL como **1
   documento**, com acesso `local_jsonl`, `campo_vigencia: periodo`,
   `sensitivity_default: publico` e o SHA-256 acima.
2. **Unificação:** `python -m src.unificar_corpus_manifest` inclui o SIH no
   `corpus_manifest.yaml` (por padrão lê `corpus_manifest_sih.yaml`), com
   `tipo_documento: agregado`.
3. **Coleta e inventário:** o `src/fetch_corpus.py` valida o arquivo como JSONL,
   confere o SHA-256 com o manifesto e copia para `data/raw/vN/agregados/SIH_dir/`.
   A base entrou na **v4** (DIFF v3→v4: 1 adicionado, 83 idênticos).
4. **Padronização do nome da doença (07/10/2026):** no JSONL, o campo `doenca`
   passou de `artrite_psoriatica` para `artrite_psoriasica` (353 registros), o mesmo
   nome usado nos protocolos e no `query_router.py`, para o filtro por doença juntar
   as bases. O `text` e o `doenca_nome` continuam "artrite psoriática". O arquivo
   mudou de hash e gerou uma nova versão do inventário.

## Chunking e embeddings

- **Não passa pelo chunking** de protocolos e bulas: cada linha do JSONL já é uma
  frase completa e vira **1 chunk**.
- Os embeddings foram gerados à parte, no Google Colab, a partir dos arquivos que o
  Silvio preparou (`gerar_embeddings_sih_jsonl.py`, `consultar_sih_rag_hibrido.py`
  e o notebook de geração):
  - modelo `sentence-transformers/all-MiniLM-L6-v2`;
  - banco vetorial **ChromaDB**, coleção `sih_agregados`.
- Tudo fica no Drive da equipe, em `Time2RAG/protocolos_normativa_verificados/Base-agregada/`:

  ```
  Base-agregada/
  ├── SIH_dir/
  │   └── corpus_sih_agregados_rag.jsonl   ← dados (entrada do corpus)
  ├── chroma_sih_embeddings/               ← índices ChromaDB (coleção sih_agregados)
  └── gerar_embedding_sih                  ← notebook Colab que gerou os índices
  ```

  Os índices foram gerados originalmente no "Meu Drive" de quem rodou o notebook e
  depois movidos para esta pasta. Para rodar o notebook de novo, confira o caminho
  de saída e aponte para a pasta acima.
- Validação (30/09/2026): as consultas de teste bateram com os valores do Silvio
  (ex.: 168 óbitos por asma no Sudeste). Em teste posterior, a resposta certa veio
  em 2º lugar, o que mostra a necessidade de **filtro por metadado** (região, UF,
  período) antes da busca semântica.

## Como reproduzir

1. Baixar `corpus_sih_agregados_rag.jsonl` do Drive para a pasta `SIH_dir/` na raiz
   do projeto.
2. Conferir o hash (PowerShell):
   ```powershell
   Get-FileHash SIH_dir\corpus_sih_agregados_rag.jsonl -Algorithm SHA256
   ```
   Deve resultar em `C5CB08ED1D15AAD99C9AA4DCFE97D19CBD896B3EE714BA475A4DA3BD144F384B`.
3. Unificar e coletar:
   ```powershell
   python -m src.unificar_corpus_manifest
   python -m src.fetch_corpus fetch --manifest corpus_manifest.yaml
   ```

## Limitações conhecidas

- **O script PySUS que gera o JSONL não está versionado** no repositório; sem ele,
  o arquivo só pode ser reproduzido a partir da cópia no Drive.
- Segundo o Silvio, algumas UFs **não tinham todos os meses de 2025** carregados no
  momento da extração, e houve **divergência entre valores do TabNet e do PySUS**
  (as bases do DATASUS não são atualizadas ao mesmo tempo). Os números refletem a
  data da extração.
- Os embeddings do SIH usam um modelo diferente do das outras bases e do modelo
  oficial da residência (`qwen3-embedding`). A unificação do modelo está pendente.
- A base cobre só **internações**. Dados de dispensação ainda não fazem parte do corpus.
