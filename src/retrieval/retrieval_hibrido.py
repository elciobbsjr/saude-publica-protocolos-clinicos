"""
Recuperação Híbrida — Ponto de Entrada Principal.

stage: retrieval_hibrido

Integra:
    1. Carregamento do corpus (corpus_loader.py)
    2. Filtros de metadados (filtros.py) ← contrato do QueryRouter
    3. Busca densa por cosseno (vetorial.py)
    4. Busca esparsa BM25 (bm25.py)
    5. Fusão por Reciprocal Rank Fusion (rrf.py)

Uso típico (integração com o pipeline principal):

    from src.query_router import QueryRouter
    from src.retrieval.retrieval_hibrido import RetrievalHibrido

    router = QueryRouter()
    analise = router.analisar("Quais os critérios do PCDT de asma vigente?")

    retrieval = RetrievalHibrido()
    resultado = retrieval.executar(
        query=analise["query_original"],
        filtros=analise["retrieval_filters"],
    )

    for item in resultado["chunks"]:
        print(item["rank"], item["score_rrf"], item["chunk"]["texto"][:80])
"""

import time
from pathlib import Path
from typing import Any

from src.retrieval.bm25 import IndiceBM25
from src.retrieval.corpus_loader import carregar_todos_os_chunks
from src.retrieval.filtros import aplicar_filtros
from src.retrieval.rrf import fusao_rrf
from src.retrieval.vetorial import IndiceVetorial


# ------------------------------------------------------------------
# CONFIGURAÇÕES PADRÃO
# ------------------------------------------------------------------

TOP_K_BUSCA: int = 20    # Candidatos por índice antes do RRF
TOP_K_FINAL: int = 10    # Resultados finais após fusão RRF


# ------------------------------------------------------------------
# ORQUESTRADOR PRINCIPAL
# ------------------------------------------------------------------

class RetrievalHibrido:
    """
    Orquestrador da Recuperação Híbrida.

    Combina busca vetorial densa e BM25 com RRF,
    aplicando filtros de metadados do QueryRouter antes
    de enviar os chunks aos índices de busca.

    O corpus é carregado e indexado na primeira chamada
    a `executar()` (lazy loading) e reutilizado nas
    chamadas seguintes para economizar tempo e API calls.

    Args:
        pasta_output:  Pasta de output de chunking.
                       Se None, usa o padrão do projeto.
        top_k_busca:   Candidatos recuperados por índice.
        top_k_final:   Resultados finais após RRF.
    """

    def __init__(
        self,
        pasta_output: Path | None = None,
        top_k_busca: int = TOP_K_BUSCA,
        top_k_final: int = TOP_K_FINAL,
    ) -> None:
        self._pasta_output = pasta_output
        self._top_k_busca = top_k_busca
        self._top_k_final = top_k_final

        # Corpus completo (carregado na primeira chamada)
        self._chunks_completos: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # CARREGAMENTO (LAZY)
    # ------------------------------------------------------------------

    def _garantir_corpus(self) -> None:
        """Carrega o corpus na primeira chamada."""
        if self._chunks_completos is None:
            print("[RetrievalHibrido] Carregando corpus...")
            self._chunks_completos = carregar_todos_os_chunks(
                self._pasta_output
            )
            print(
                f"[RetrievalHibrido] Corpus carregado: "
                f"{len(self._chunks_completos)} chunks."
            )

    # ------------------------------------------------------------------
    # EXECUÇÃO
    # ------------------------------------------------------------------

    def executar(
        self,
        query: str,
        filtros: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executa a recuperação híbrida para uma query.

        Args:
            query:   Texto da pergunta do usuário.
            filtros: Dicionário de filtros gerado pelo QueryRouter.
                     Se None, nenhum filtro de metadado é aplicado.

        Returns:
            Dicionário com:
                {
                    "stage":            "retrieval_hibrido",
                    "query":            str,
                    "filtros_aplicados": dict,
                    "chunks_antes_filtro": int,
                    "chunks_apos_filtro":  int,
                    "chunks":           list[dict],  # top_k_final chunks
                    "latencia_segundos": float,
                }
        """
        inicio = time.monotonic()

        if not query or not query.strip():
            raise ValueError("A query não pode estar vazia.")

        if filtros is None:
            filtros = {}

        # 1. Carrega corpus (lazy)
        self._garantir_corpus()

        chunks_completos = self._chunks_completos or []
        total_antes = len(chunks_completos)

        # 2. Aplica filtros de metadados
        chunks_filtrados = aplicar_filtros(chunks_completos, filtros)
        total_apos = len(chunks_filtrados)

        print(
            f"[RetrievalHibrido] Filtros: "
            f"{total_antes} → {total_apos} chunks."
        )

        # Edge case: sem chunks após filtro
        if not chunks_filtrados:
            print(
                "[RetrievalHibrido] Aviso: nenhum chunk passou "
                "pelos filtros. Retornando lista vazia."
            )
            latencia = time.monotonic() - inicio
            return self._montar_resultado(
                query=query,
                filtros=filtros,
                chunks_antes=total_antes,
                chunks_apos=total_apos,
                chunks_finais=[],
                latencia=latencia,
            )

        # 3. Busca BM25
        print("[RetrievalHibrido] Executando BM25...")
        indice_bm25 = IndiceBM25()
        indice_bm25.construir(chunks_filtrados)
        resultados_bm25 = indice_bm25.buscar(
            query, top_k=self._top_k_busca
        )

        # 4. Busca vetorial densa
        print("[RetrievalHibrido] Executando busca vetorial...")
        indice_vetorial = IndiceVetorial()

        try:
            indice_vetorial.construir(chunks_filtrados)
            resultados_vetorial = indice_vetorial.buscar(
                query, top_k=self._top_k_busca
            )
        except ValueError as erro:
            # Chunks sem embedding: usa apenas BM25
            print(
                f"[RetrievalHibrido] Aviso — busca vetorial "
                f"ignorada: {erro}"
            )
            resultados_vetorial = []

        # 5. Fusão RRF
        print("[RetrievalHibrido] Aplicando RRF...")
        chunks_finais = fusao_rrf(
            resultados_vetorial=resultados_vetorial,
            resultados_bm25=resultados_bm25,
            top_k=self._top_k_final,
        )

        latencia = time.monotonic() - inicio

        print(
            f"[RetrievalHibrido] Concluído em "
            f"{latencia:.2f}s — {len(chunks_finais)} chunks retornados."
        )

        return self._montar_resultado(
            query=query,
            filtros=filtros,
            chunks_antes=total_antes,
            chunks_apos=total_apos,
            chunks_finais=chunks_finais,
            latencia=latencia,
        )

    # ------------------------------------------------------------------
    # MONTAGEM DO RESULTADO
    # ------------------------------------------------------------------

    @staticmethod
    def _montar_resultado(
        query: str,
        filtros: dict[str, Any],
        chunks_antes: int,
        chunks_apos: int,
        chunks_finais: list[dict[str, Any]],
        latencia: float,
    ) -> dict[str, Any]:
        return {
            "stage": "retrieval_hibrido",
            "query": query,
            "filtros_aplicados": filtros,
            "chunks_antes_filtro": chunks_antes,
            "chunks_apos_filtro": chunks_apos,
            "chunks": chunks_finais,
            "latencia_segundos": round(latencia, 3),
        }


# ------------------------------------------------------------------
# EXECUÇÃO DIRETA (SMOKE TEST)
# ------------------------------------------------------------------

if __name__ == "__main__":
    from src.query_router import QueryRouter

    perguntas_teste = [
        "Quais são os critérios do PCDT vigente de asma?",
        "Quantas internações por hipertensão houve em 2025?",
        "A losartana está disponível na RENAME?",
        "O que mudou no protocolo de hepatite C entre 2018 e 2026?",
    ]

    router = QueryRouter()
    retrieval = RetrievalHibrido(top_k_final=5)

    for pergunta in perguntas_teste:
        print("\n" + "=" * 70)
        print(f"QUERY: {pergunta}")
        print("=" * 70)

        analise = router.analisar(pergunta)

        if analise.get("requires_refusal"):
            print("⚠️  Recusado: conduta individualizada.")
            continue

        resultado = retrieval.executar(
            query=analise["query_original"],
            filtros=analise["retrieval_filters"],
        )

        print(f"\nChunks retornados: {len(resultado['chunks'])}")
        print(f"Latência: {resultado['latencia_segundos']}s")
        print(f"Filtros: {resultado['filtros_aplicados']}")

        for item in resultado["chunks"]:
            chunk = item["chunk"]
            meta = chunk.get("metadata", {})
            print(
                f"\n  [#{item['rank']}] RRF={item['score_rrf']:.4f} | "
                f"base={meta.get('base_id')} | "
                f"doença={meta.get('doenca')} | "
                f"status={meta.get('status')}"
            )
            print(f"  {chunk.get('texto', '')[:120]}...")
