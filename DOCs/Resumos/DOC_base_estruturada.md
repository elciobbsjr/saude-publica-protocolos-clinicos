# Base Estruturada — RENAME + Bulário (Cenário 2)

**Responsável:** Paula Femina
**base_id no manifesto:** `bulas_anvisa` (bulas) e `rename_medicamentos` (RENAME 2024)
**Natureza:** estruturada

Este documento detalha as decisões de coleta da base Estruturada, complementando o
que está registrado (de forma enxuta) no `corpus_manifest_bulas.yaml` e no
`corpus_manifest_rename.yaml`, que são unificados no `corpus_manifest.yaml`.

## Fontes

- **RENAME 2024** (PDF consolidado, Portaria GM/MS nº 6.324/2024) — fonte tabular.
  O link oficial (`bvsms.saude.gov.br`, Biblioteca Virtual em Saúde do Ministério da
  Saúde) retornou erro 503 persistente nos testes de 21-24/09/2026. Por isso, o
  arquivo é baixado de um espelho hospedado pela OMS/OPAS (`cdn.who.int`), com o
  mesmo conteúdo, verificado por SHA-256. Os dois endereços estão no manifesto
  (`url_origem` e `url_pdf_resolvida`).
- **Bulário Eletrônico da ANVISA** (`consultas.anvisa.gov.br/#/bulario/`) — fonte de
  PDFs de bula, um por medicamento.

## Por que PDF consolidado e não o painel "Rename em Tempo Real"

O painel dinâmico da RENAME muda de conteúdo a qualquer momento, o que quebraria
`selecao_deterministica` — duas execuções do manifesto em datas diferentes
poderiam trazer corpus diferentes. O PDF consolidado de 2024 é uma edição fechada
e datada (Portaria GM/MS nº 6.324/2024, vigente desde 26/12/2024), portanto
reprodutível.

## Critério de seleção das bulas: medicamento de referência ANVISA

O Bulário não indexa bula por nome genérico — a busca é por nome comercial, e um
mesmo princípio ativo pode ter dezenas de marcas registradas. Para evitar uma
escolha arbitrária, usei o critério oficial da **Lista de Medicamentos de
Referência (LMR)** da ANVISA (Lista A de Incluídos, IN 455, dados de 10/07/2026) —
a marca que a própria agência designa como parâmetro regulatório para cada
princípio ativo. É um critério público, fixo e citável.

A busca no Bulário é feita pelo nome comercial de referência, e o número de
registro ANVISA de cada item (abaixo) resolve qual resultado é o correto quando a
busca retorna mais de uma apresentação.

## Tabela de referências (verificadas linha a linha na LMR, 10/07/2026)

| # | Medicamento | Referência ANVISA | Registro |
|---|---|---|---|
| 1 | Metformina (cloridrato) | Glifage / Glifage XR — Merck S/A | 100890193 / 100890340 |
| 2 | Losartana potássica (25mg) | Corus — Aché | 105730793 |
| 2b | Losartana potássica (50/100mg) | Cozaar — Organon | 100290007 |
| 3 | Hidroclorotiazida | Clorana — Sanofi Medley | 183260436 |
| 4 | Enalapril (maleato) | Renitec — Organon | 100290031 |
| 5 | Sinvastatina | Sinvastacor — Sandoz | 100470270 (ver nota abaixo) |
| 6 | Paracetamol | Tylenol — Kenvue | 157211214 |
| 7 | Dipirona sódica (monoidratada) | Novalgina — Opella Healthcare | 186200018 |
| 8 | Omeprazol | Pratiprazol — Prati Donaduzzi | 125680337 |
| 9 | Amoxicilina | Amoxil — GSK | 101070003 |
| 9b | Amoxicilina (400mg/5mL, 875mg) | Novocilin — Aché | 105730076 |
| 10 | Insulina NPH humana | **Sem referência ANVISA** — coletada a Humulin N (Eli Lilly), ver nota abaixo | 112600057 |
| 11 | Salbutamol (sulfato) | Aerolin — GSK | 101070226 |
| 12 | Amitriptilina (cloridrato) | Amytril — Cristália | 102980225 / 102980364 |
| 13 | Levotiroxina sódica | Puran T4 — Sanofi Medley | 183260353 |
| 14 | Ibuprofeno | Advil — PF Consumer | 192900005 |
| 15 | Ácido acetilsalicílico | Aspirina — Bayer | 170560020 |
| 16 | Captopril | Captosen — Pharlab | 141070025 |

*(Item 16, Captopril, foi adicionado para completar o mínimo de 15 medicamentos
com referência ANVISA real, já que a Insulina NPH — item 10 — não tem.)*

**Nota sobre a Sinvastatina:** a LMR lista dois registros da Sandoz (100470270 e
100470472). Na coleta de 25/09/2026, só o 100470270 (Sinvastacor) foi encontrado no
Bulário; o 100470472 não foi coletado.

## Exceção documentada: Insulina NPH humana

Busca confirmada (10/07/2026) na Lista A de Medicamentos de Referência Incluídos:
nenhuma ocorrência de "insulina" no documento inteiro (46 páginas).

**Motivo:** insulina é um produto **biológico**. O sistema de medicamento de
referência (RDC 35/2012) foi desenhado para medicamentos sintéticos comparáveis
por bioequivalência — biológicos seguem via regulatória própria (biosimilares).

**Decisão:** a Insulina NPH humana permanece na base, mesmo sem medicamento de
referência ANVISA no sentido regulatório do termo. A base já atinge o mínimo de 15
medicamentos exigido com referência ANVISA confirmada (itens 1-9, 9b, 11-15 e 16),
então a insulina não é necessária para cumprir esse mínimo — ela é mantida por
relevância clínica (é um medicamento de uso corrente no SUS) e porque documentar a
exceção, em vez de substituí-la por um item "mais fácil", registra com transparência
uma limitação real do sistema de referência da ANVISA para produtos biológicos. A
bula foi coletada pela marca comercial **Humulin N — Eli Lilly (registro
112600057)**, sem o rótulo de "medicamento de referência ANVISA" — exceção
reconhecida e documentada, não seleção arbitrária.

## Composição atual da base de bulas

Em 25/09/2026 a equipe combinou manter os dois critérios de seleção, com a origem
documentada:

- **Marcas de referência ANVISA** (tabela acima, coletadas por Paula Femina):
  20 pastas em `BULAS_dir/` (Glifage e Glifage XR em pastas separadas, e o Amytril
  em duas pastas, uma por registro).
- **Genéricos** (coletados por Silvio Lima): 12 pastas em `BULAS_dir/` (budesonida,
  cloridrato de metformina, dolutegravir sódico, entecavir, fumarato de tenofovir
  desoproxila, hidroclorotiazida, losartana potássica, maleato de enalapril,
  metotrexato, sinvastatina, sofosbuvir e sulfato de salbutamol).

Total no `corpus_manifest_bulas.yaml`: **31 medicamentos e 59 documentos** (bula do
paciente e bula do profissional, quando existem).

## Como a coleta é feita

- **Bulas:** o notebook `notebook/fetch_bula_estruturada.ipynb` (Google Colab, com
  Playwright, que passa pela proteção Cloudflare do Bulário) busca cada marca de
  referência e confere o número de registro antes de baixar. Cada medicamento tem
  uma pasta em `BULAS_dir/` com os PDFs e um `metadata.json` (registro, empresa,
  CNPJ, expediente, data do documento etc.). Os PDFs ficam fora do Git, na pasta
  Base-estruturada do Drive da equipe; no Git ficam só os `metadata.json` e os
  manifestos.
- **RENAME:** o notebook `notebook/corpus_manifest_rename.ipynb` gera o
  `corpus_manifest_rename.yaml`, com acesso `http_pdf` pelo espelho `cdn.who.int`.
- **Corpus:** o `src/unificar_corpus_manifest.py` junta os manifestos no
  `corpus_manifest.yaml`, e o `src/fetch_corpus.py` coleta as bulas como
  `local_pdf` e a RENAME como `http_pdf`, conferindo o SHA-256 de cada arquivo. No
  inventário atual (**v7**), a base tem 59 bulas e 1 RENAME, sem falhas.

## Metadados de cada documento

- `natureza: estruturada` nas duas bases (as bulas estavam como `regulatoria`, valor
  que o desafio não aceita; corrigido no inventário v5).
- **Bulas:** `campo_vigencia: data_documento`, com `medicamento`, `principio_ativo`,
  `nome_produto`, `tipo_bula`, `numero_registro` e os demais campos do
  `metadata.json` (a partir da v6).
- **RENAME:** `campo_vigencia: data_inicio` (26/12/2024), com `versao_edicao`,
  `versao_portaria`, `status: vigente` e `data_fim` vazio.
- `sensitivity_default: publico` nas duas bases.

## Limitação conhecida: chunking da RENAME

O manifesto da RENAME sugere `1 medicamento/apresentação = 1 chunk`, mas hoje a
RENAME passa pelo mesmo chunking por tamanho usado nos outros PDFs. No teste de
02/10/2026 (notebook Teste_bases), a RENAME gerou 70 chunks e a busca por
metformina falhou, por causa do chunk grande numa tabela e do modelo de embedding
fraco em português. Separar a RENAME por medicamento é a próxima melhoria da base.

## Erros cometidos e corrigidos durante o processo

Cheguei a citar Zocor (Merck) como referência da Sinvastatina e Tryptanol (Merck)
como referência da Amitriptilina — ambos foram excluídos da LMR (2017 e 2013,
respectivamente) e substituídos pelas referências atuais (Sinvastacor/Sandoz e
Amytril/Cristália). O erro só foi percebido ao cruzar com a lista oficial de
exclusões — reforça que citar marca "de memória" não é confiável para um dado que
muda por norma regulatória periódica.

Na coleta (25/09/2026), corrigi o registro do Corus (105730593 → 105730793, o
registro que consta no Bulário). Também corrigi o Amytril: os dois registros
(102980225 e 102980364) caíam na mesma pasta e um `metadata.json` sobrescrevia o
outro; hoje cada registro tem a sua pasta.
