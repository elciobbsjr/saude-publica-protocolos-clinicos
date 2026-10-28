import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


class QueryRouter:
    """
    Módulo de Query Analysis e Roteamento Adaptativo.

    Responsabilidades:
    - normalizar a pergunta;
    - identificar intenção;
    - extrair doenças e medicamentos;
    - extrair filtros temporais;
    - identificar filtros geográficos simples;
    - decidir quais rotas de evidência devem ser consultadas;
    - preparar filtros para o módulo de retrieval.
    """

    def __init__(
        self,
        manifest_path: str = "corpus_manifest.yaml",
        extra_manifest_paths: list[str] | None = None,
    ):
        self.manifest_path = Path(manifest_path)

        self.extra_manifest_paths = [
            Path(path)
            for path in (
                extra_manifest_paths
                if extra_manifest_paths is not None
                else ["corpus_manifest_rename.yaml"]
            )
        ]

        self.doencas_disponiveis: list[str] = []
        self.medicamentos_disponiveis: list[str] = []
        self.bases_disponiveis: dict[str, dict[str, Any]] = {}

        self._carregar_manifesto()

        # Aliases humanos -> identificadores utilizados no corpus.
        self.doenca_aliases = {
            "asma": "asma",

            "diabetes tipo 1": "diabete_melito_tipo_1",
            "diabetes mellitus tipo 1": "diabete_melito_tipo_1",
            "diabete tipo 1": "diabete_melito_tipo_1",
            "dm1": "diabete_melito_tipo_1",

            "diabetes tipo 2": "diabete_melito_tipo_2",
            "diabetes mellitus tipo 2": "diabete_melito_tipo_2",
            "diabete tipo 2": "diabete_melito_tipo_2",
            "dm2": "diabete_melito_tipo_2",

            "hipertensao": "hipertensao_arterial_sistemica",
            "hipertensao arterial": "hipertensao_arterial_sistemica",
            "hipertensao arterial sistemica": "hipertensao_arterial_sistemica",
            "has": "hipertensao_arterial_sistemica",

            "hepatite b": "hepatite_b",
            "hepatite c": "hepatite_c",

            "artrite reumatoide": "artrite_reumatoide",
            "artrite idiopatica juvenil": "artrite_idiopatica_juvenil",
            "aij": "artrite_idiopatica_juvenil",
            "artrite psoriasica": "artrite_psoriasica",

            "psoriase": "psoriase",
            "dislipidemia": "dislipidemia",
            "pep": "pep",
        }

        self.medicamento_aliases = {
            "budesonida": "budesonida",

            "metformina": "cloridrato_de_metformina",
            "cloridrato de metformina": "cloridrato_de_metformina",

            "dolutegravir": "dolutegravir_sodico",
            "dolutegravir sodico": "dolutegravir_sodico",

            "entecavir": "entecavir",

            "tenofovir": "fumarato_de_tenofovir_desoproxila",
            "fumarato de tenofovir desoproxila":
                "fumarato_de_tenofovir_desoproxila",

            "hidroclorotiazida": "hidroclorotiazida",

            "losartana": "losartana_potassica",
            "losartana potassica": "losartana_potassica",

            "enalapril": "maleato_de_enalapril",
            "maleato de enalapril": "maleato_de_enalapril",

            "metotrexato": "metotrexato",
            "sinvastatina": "sinvastatina",
            "sofosbuvir": "sofosbuvir",

            "salbutamol": "sulfato_de_salbutamol",
            "sulfato de salbutamol": "sulfato_de_salbutamol",
        }

    # ------------------------------------------------------------------
    # MANIFESTOS
    # ------------------------------------------------------------------

    def _carregar_manifesto(self) -> None:
        caminhos = [
            self.manifest_path,
            *self.extra_manifest_paths,
        ]

        for caminho in caminhos:
            if not caminho.exists():
                continue

            with caminho.open(
                "r",
                encoding="utf-8",
            ) as arquivo:
                manifesto = yaml.safe_load(arquivo) or {}

            for doenca in manifesto.get(
                "doencas_disponiveis",
                [],
            ):
                if doenca not in self.doencas_disponiveis:
                    self.doencas_disponiveis.append(doenca)

            for medicamento in manifesto.get(
                "medicamentos_disponiveis",
                [],
            ):
                if medicamento not in self.medicamentos_disponiveis:
                    self.medicamentos_disponiveis.append(
                        medicamento
                    )

            for base in manifesto.get("bases", []) or []:
                if not isinstance(base, dict):
                    continue

                base_id = base.get("base_id")

                if base_id:
                    self.bases_disponiveis[
                        str(base_id)
                    ] = base

    # ------------------------------------------------------------------
    # NORMALIZAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def _normalizar_texto(texto: str) -> str:
        texto = texto.lower()

        texto = unicodedata.normalize(
            "NFKD",
            texto,
        )

        texto = "".join(
            caractere
            for caractere in texto
            if not unicodedata.combining(caractere)
        )

        return texto

    @staticmethod
    def _contem_termo(texto: str, termo: str) -> bool:
        """
        Verifica se o termo aparece como palavra inteira.
        Evita falsos positivos como "has" dentro de "linhas"
        ou "sul" dentro de "insulina".
        """
        padrao = r"(?<!\w)" + re.escape(termo) + r"(?!\w)"
        return re.search(padrao, texto) is not None

    # ------------------------------------------------------------------
    # ENTIDADES
    # ------------------------------------------------------------------

    def extrair_doencas(self, query: str) -> list[str]:
        query_normalizada = self._normalizar_texto(query)

        encontradas = []

        aliases = sorted(
            self.doenca_aliases.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )

        for alias, identificador in aliases:
            if self._contem_termo(query_normalizada, alias):
                if identificador not in encontradas:
                    encontradas.append(identificador)

        return encontradas

    def extrair_medicamentos(self, query: str) -> list[str]:
        query_normalizada = self._normalizar_texto(query)

        encontrados = []

        aliases = sorted(
            self.medicamento_aliases.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )

        for alias, identificador in aliases:
            if self._contem_termo(query_normalizada, alias):
                if identificador not in encontrados:
                    encontrados.append(identificador)

        return encontrados

    # ------------------------------------------------------------------
    # TEMPORALIDADE
    # ------------------------------------------------------------------

    @staticmethod
    def extrair_anos(query: str) -> list[int]:
        anos = re.findall(
            r"\b(19\d{2}|20\d{2})\b",
            query,
        )

        return sorted(
            set(int(ano) for ano in anos)
        )

    def analisar_temporalidade(self, query: str) -> dict:
        query_normalizada = self._normalizar_texto(query)

        termos_vigencia = [
            "vigente",
            "atual",
            "atualmente",
            "mais recente",
            "ultima versao",
            "versao atual",
            "protocolo atual",
        ]

        termos_comparacao = [
            "mudou",
            "mudanca",
            "mudancas",
            "diferenca",
            "diferencas",
            "divergencia",
            "divergencias",
            "comparar",
            "comparacao",
            "entre",
            "manteve a mesma",
            "versao anterior",
        ]

        termos_historicos = [
            "anterior",
            "antigo",
            "antiga",
            "revogado",
            "revogada",
            "historico",
        ]

        anos = self.extrair_anos(query)

        vigente = any(
            termo in query_normalizada
            for termo in termos_vigencia
        )

        comparacao = (
            any(
                termo in query_normalizada
                for termo in termos_comparacao
            )
            or len(anos) >= 2
        )

        historico = any(
            termo in query_normalizada
            for termo in termos_historicos
        )

        return {
            "anos": anos,
            "vigente": vigente,
            "comparacao": comparacao,
            "historico": historico,
        }

    # ------------------------------------------------------------------
    # GEOGRAFIA
    # ------------------------------------------------------------------

    def extrair_geografia(self, query: str) -> dict:
        q = self._normalizar_texto(query)

        regioes = {
            "norte": "Norte",
            "nordeste": "Nordeste",
            "centro-oeste": "Centro-Oeste",
            "centro oeste": "Centro-Oeste",
            "sudeste": "Sudeste",
            "sul": "Sul",
        }

        estados = {
            "rio de janeiro": "RJ",
            "sao paulo": "SP",
            "maranhao": "MA",
            "minas gerais": "MG",
            "bahia": "BA",
            "parana": "PR",
            "santa catarina": "SC",
            "rio grande do sul": "RS",
        }

        regiao = None
        uf = None

        for nome, valor in regioes.items():
            if self._contem_termo(q, nome):
                regiao = valor
                break

        for nome, sigla in estados.items():
            if nome in q:
                uf = sigla
                break

        return {
            "regiao": regiao,
            "uf": uf,
        }

    # ------------------------------------------------------------------
    # SEGURANÇA / CONDUTA INDIVIDUAL
    # ------------------------------------------------------------------

    @staticmethod
    def _eh_conduta_individualizada(query: str) -> bool:
        termos_conduta = [
            "devo tomar",
            "posso tomar",
            "o que tomar",
            "que remedio",
            "qual remedio",
            "qual medicamento devo",
            "que medicamento devo",
            "qual dose",
            "que dose",
            "ajustar a dose",
            "ajustar a dieta",
            "ajustar os exercicios",
            "como devo proceder clinicamente",
            "paciente especifico",
            "para mim",
        ]

        contexto_pessoal = [
            "meu pai",
            "minha mae",
            "meu filho",
            "minha filha",
            "meu marido",
            "minha esposa",
            "paciente especifico",
        ]

        if any(
            termo in query
            for termo in termos_conduta
        ):
            return True

        if any(
            termo in query
            for termo in contexto_pessoal
        ):
            if any(
                termo in query
                for termo in [
                    "tomar",
                    "usar",
                    "remedio",
                    "medicamento",
                    "dose",
                    "tratamento",
                ]
            ):
                return True

        return False

    # ------------------------------------------------------------------
    # INTENÇÃO
    # ------------------------------------------------------------------

    def identificar_intencao(self, query: str) -> str:
        q = self._normalizar_texto(query)

        temporal = self.analisar_temporalidade(query)

        if self._eh_conduta_individualizada(q):
            return "conduta_individualizada"

        if temporal["comparacao"]:
            return "comparacao_temporal"

        termos_indicador = [
            "internacao",
            "internacoes",
            "mortalidade",
            "prevalencia",
            "indicador",
            "indicadores",
            "cobertura",
            "datasus",
            "quantidade",
            "dispensacao",
            "dispensacoes",
            "volume total",
            "impacto orcamentario",
            "dados agregados",
            "registros de dispensacao",
        ]

        if any(
            termo in q
            for termo in termos_indicador
        ):
            return "consulta_indicador"

        termos_medicamento = [
            "rename",
            "bula",
            "anvisa",
            "apresentacao",
            "registro anvisa",
        ]

        if any(
            termo in q
            for termo in termos_medicamento
        ):
            return "consulta_medicamento"

        if temporal["vigente"]:
            return "consulta_vigente"

        if temporal["historico"]:
            return "consulta_historica"

        return "consulta_factual"

    # ------------------------------------------------------------------
    # ROTEAMENTO
    # ------------------------------------------------------------------

    def definir_rotas(
        self,
        query: str,
        intencao: str,
    ) -> list[str]:

        q = self._normalizar_texto(query)

        if intencao == "conduta_individualizada":
            return []

        rotas: list[str] = []

        termos_normativos = [
            "pcdt",
            "protocolo",
            "protocolos",
            "diretriz",
            "diretrizes",
            "portaria",
            "criterio",
            "criterios",
            "exclusao",
            "inclusao",
            "versao",
            "vigente",
            "incorpora",
            "recomenda",
            "antigo",
            "antiga",
            "revogado",
            "revogada",
            "historico",
        ]

        termos_estruturados = [
            "rename",
            "bula",
            "bulas",
            "anvisa",
            "apresentacao",
            "registro anvisa",
            "consta",
            "listado",
            "listada",
        ]

        termos_agregados = [
            "datasus",
            "internacao",
            "internacoes",
            "mortalidade",
            "prevalencia",
            "indicador",
            "indicadores",
            "cobertura",
            "dispensacao",
            "dispensacoes",
            "volume total",
            "impacto orcamentario",
            "dados agregados",
            "dados abertos",
            "registros de dispensacao",
        ]

        termos_conversacionais = [
            "faq",
            "pergunta frequente",
            "perguntas frequentes",
            "atendimento",
            "dialogo",
            "conversa",
        ]

        if any(
            termo in q
            for termo in termos_normativos
        ):
            rotas.append("normativa")

        if any(
            termo in q
            for termo in termos_estruturados
        ):
            rotas.append("estruturada")

        if any(
            termo in q
            for termo in termos_agregados
        ):
            rotas.append("agregada")

        if any(
            termo in q
            for termo in termos_conversacionais
        ):
            rotas.append("conversacional")

        if not rotas:
            if self.extrair_medicamentos(query):
                rotas.append("estruturada")
            else:
                rotas.append("normativa")

        return rotas

    # ------------------------------------------------------------------
    # RESOLUÇÃO DINÂMICA DAS BASES
    # ------------------------------------------------------------------

    def obter_base_ids_por_natureza(
        self,
        naturezas: list[str],
    ) -> list[str]:

        naturezas_normalizadas = {
            self._normalizar_texto(natureza)
            for natureza in naturezas
        }

        encontrados = []

        for base_id, dados_base in (
            self.bases_disponiveis.items()
        ):
            natureza = dados_base.get("natureza")

            if not natureza:
                continue

            natureza_normalizada = self._normalizar_texto(
                str(natureza)
            )

            if (
                natureza_normalizada
                in naturezas_normalizadas
            ):
                encontrados.append(base_id)

        return encontrados

    # ------------------------------------------------------------------
    # FILTROS DO RETRIEVAL
    # ------------------------------------------------------------------

    def gerar_filtros_recuperacao(
        self,
        rotas: list[str],
        doencas: list[str],
        medicamentos: list[str],
        temporal: dict,
        geografia: dict,
    ) -> dict:

        bases = []

        mapeamento_naturezas = {
            "normativa": [
                "normativa",
            ],
            "estruturada": [
                "estruturada",
            ],
            "agregada": [
                "agregada",
            ],
            "conversacional": [
                "conversacional",
            ],
        }

        for rota in rotas:
            naturezas = mapeamento_naturezas.get(
                rota,
                [],
            )

            bases_da_rota = (
                self.obter_base_ids_por_natureza(
                    naturezas
                )
            )

            for base_id in bases_da_rota:
                if base_id not in bases:
                    bases.append(base_id)

        return {
            "base_id": bases,
            "doenca": doencas,
            "medicamento": medicamentos,
            "anos": temporal["anos"],

            # Vigente por padrão: só libera documentos revogados
            # quando a pergunta é histórica, compara versões ou
            # cita anos explicitamente.
            "somente_vigente": (
                not temporal["historico"]
                and not temporal["comparacao"]
                and not temporal["anos"]
            ),

            "comparar_versoes": temporal["comparacao"],
            "historico": temporal["historico"],
            "regiao": geografia["regiao"],
            "uf": geografia["uf"],
        }

    # ------------------------------------------------------------------
    # CONTRATO PRINCIPAL
    # ------------------------------------------------------------------

    def analisar(self, query: str) -> dict:
        if not isinstance(query, str):
            raise TypeError("A query deve ser uma string.")

        query = query.strip()

        if not query:
            raise ValueError("A query não pode ser vazia.")

        doencas = self.extrair_doencas(query)
        medicamentos = self.extrair_medicamentos(query)
        temporal = self.analisar_temporalidade(query)
        geografia = self.extrair_geografia(query)

        intencao = self.identificar_intencao(query)

        rotas = self.definir_rotas(
            query=query,
            intencao=intencao,
        )

        filtros = self.gerar_filtros_recuperacao(
            rotas=rotas,
            doencas=doencas,
            medicamentos=medicamentos,
            temporal=temporal,
            geografia=geografia,
        )

        return {
            "stage": "roteamento",
            "query_original": query,
            "intent": intencao,

            "entities": {
                "doencas": doencas,
                "medicamentos": medicamentos,
                "geografia": geografia,
            },

            "temporal_filters": temporal,

            "routes": rotas,

            "retrieval_filters": filtros,

            "requires_refusal": (
                intencao == "conduta_individualizada"
            ),
        }


if __name__ == "__main__":
    router = QueryRouter()

    perguntas = [
        (
            "Quais são os critérios do PCDT vigente "
            "de diabetes tipo 2?"
        ),
        "A losartana está disponível na RENAME?",
        (
            "Qual foi o número de internações por "
            "hipertensão em 2025?"
        ),
        (
            "O que mudou no protocolo de asma "
            "entre 2021 e 2026?"
        ),
        "Qual era o protocolo antigo de asma?",
    ]

    for pergunta in perguntas:
        print("=" * 80)
        print(pergunta)
        print(router.analisar(pergunta))