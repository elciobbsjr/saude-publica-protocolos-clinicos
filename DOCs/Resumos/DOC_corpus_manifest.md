# Resumo / Doc sobre o Corpus Manifest

**Descrever os documentos que fazem parte da base de conhecimento.**

O manifesto serve para ditar a regra de coleta e a natureza da base, e não para ser o catálogo exato de cada registro (isso quem faz é o script de ingestão ou um arquivo auxiliar de mapeamento, como o seu `protocolos_normativa_verificados.json`)

- A abordagem correta para um manifesto de corpus é definir a **fonte**, o **padrão de acesso** e as **regras do jogo**, deixando que o script de fetch (src/fetch_corpus.py) ou uma lista dinâmica processe os arquivos com base em regras ou em um arquivo de metadados validado.

- O manifesto ideal para o projeto gerencia as fontes por regra, e não por listagem exaustiva de URLs

Exemplo de corpo simples

```json
corpus:
  name: programming_knowledge
  version: "1.0"
  description: str

documents:
  - id: python-basics
    path: corpus/python/basics.md
    type: markdown
    topic: python
    language: pt-BR

```

## Para o corpus_manifest presento no código

_"Exatamente quais dados esse RAG está autorizado/esperado a utilizar, de onde eles vêm, como foram selecionados e como devem ser preparados?"_

Estrutura geral

```json
scenario_id:
version:
description:

bases:
  - base_id:
    natureza:
    fonte:
    acesso:
        tipo:
        endpoint:
      params:
        dataInicial:
        dataFinal:
        uf:
      paginacao:
      rate_limit_seg:

    selecao_deterministica:
    volume_alvo:
    formato:
    licenca:
    sensitivity_default:
    campo_vigencia:
    chunking_sugerido:
    metadados_extras:


```

1. `scenario_id` - É o identificador do cenário/corpus.
2. `version` - Este RAG utiliza a versão do corpus congelada em DD/MM/AAAA.
3. `description` - É uma descrição humana do cenário.

4. `bases` - "Meu corpus é composto por diferentes bases de conhecimento."
5. `base_id` - É o identificador único da base | útil posteriormente no retrieval
6. `natureza` - classificação semântica da fonte.

<!-- prettier-ignore -->
| Natureza | Tipo de Documento | Exemplo |
| ---------| ------------------|---------|
| normativa|  regras, obrigações, critérios | Edital - Lei - Regulamento - Portaria - Contrato normativo |
| estruturada| Dados que originalmente têm estrutura de campos | Contratos de API - jsons |
| conversacional | Textos | Bases de FAQ - atendimento - chats |
| agregada | Dados já processados/sumarizados. | Total de contratos por município | Valor médio por modalidade | Quantidade de licitações por órgão

7. `fonte` - de onde os dados vieram
8. `acesso` - Define como o pipeline obtém os dados.

- `tipo` - tipo de acesso
- `endpoint` - url
- `params` - Isso define o universo de dados que você quer coletar = `params = base["acesso"]["params"]`
- `paginacao` - A API retorna os dados paginados
- `rate_limit_seg` - Espere aproximadamente 1 segundo entre requisições = `time.sleep(base["acesso"]["rate_limit_seg"])`

9. `selecao_deterministica` - Garante que os mesmos dados/docs serão coletados, mesmo filtro, ordenação, seleção
10. `volume_alvo` - expectativa de sanidade
11. `formato` - Isso permite que seu pipeline escolha o loader adequado
12. `licenca` - Isso documenta as condições de uso dos dados
13. `sensitivity_default` - Isso é uma classificação de acesso/sensibilidade. Deve ser classificado manualmente
14. `campo_vigencia` - Ele diz qual campo de data é relevante para a vigência temporal daquele conteúdo
15. `chunking_sugerido` - coração do RAG = `"1 contrato = 1 chunk, serializado em linguagem natural"`
16. `metadados_extras` - Além do conteúdo textual, esses campos devem ser preservados como metadata. = ` [orgao, modalidade, valor, municipio, ano]`
