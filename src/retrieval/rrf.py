"""
Módulo de Fusão por Reciprocal Rank Fusion (RRF).

Combina as listas de resultados da busca densa (vetorial)
e da busca esparsa (BM25) em uma única lista ordenada,
sem depender dos scores absolutos — apenas dos ranks.

Referência:
    Cormack, Clarke & Buettcher (2009). Reciprocal Rank
    Fusion outperforms Condorcet and individual Rank Learning
    Methods. SIGIR 2009.

Fórmula do score RRF para um documento d:
    RRF(d) = Σ  1 / (k + rank_i(d))
             i
onde k=20 é a constante de suavização calibrada para pools curtos (evita achatamento e valoriza o Rank 1).
"""

from typing import Any


# Constante de suavização RRF calibrada para pools curtos (top-20)
K_RRF: int = 20


def fusao_rrf(
    resultados_vetorial: list[dict[str, Any]],
    resultados_bm25: list[dict[str, Any]],
    top_k: int = 10,
    k: int = K_RRF,
) -> list[dict[str, Any]]:
    """
    Aplica Reciprocal Rank Fusion nas duas listas de resultados.

    Cada item das listas de entrada deve ter o formato:
        {
            "chunk": { "texto": ..., "metadata": ..., ... },
            "score": float,
            "rank":  int,
        }

    O "chunk_id" dentro de metadata é usado como chave de
    deduplicação. Se não existir, usa o próprio texto como chave.

    Args:
        resultados_vetorial: Saída do IndiceVetorial.buscar().
        resultados_bm25:     Saída do IndiceBM25.buscar().
        top_k:               Número máximo de resultados finais.
        k:                   Constante de suavização do RRF.

    Returns:
        Lista de até `top_k` chunks com "chunk", "score_rrf" e "rank".
    """
    scores_rrf: dict[str, float] = {}
    chunks_por_chave: dict[str, dict[str, Any]] = {}

    def _chave(resultado: dict[str, Any]) -> str:
        chunk = resultado["chunk"]
        metadata = chunk.get("metadata", {})
        chunk_id = metadata.get("chunk_id")

        if chunk_id:
            return str(chunk_id)

        # Fallback: hash do texto (primeiros 200 chars)
        return chunk.get("texto", "")[:200]

    def _acumular(
        lista: list[dict[str, Any]],
    ) -> None:
        for item in lista:
            chave = _chave(item)
            rank = item["rank"]

            scores_rrf[chave] = (
                scores_rrf.get(chave, 0.0)
                + 1.0 / (k + rank)
            )

            if chave not in chunks_por_chave:
                chunks_por_chave[chave] = item["chunk"]

    _acumular(resultados_vetorial)
    _acumular(resultados_bm25)

    # Ordena por score RRF decrescente
    ordenados = sorted(
        scores_rrf.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    resultados = []

    for rank, (chave, score_rrf) in enumerate(
        ordenados[:top_k], start=1
    ):
        resultados.append(
            {
                "chunk": chunks_por_chave[chave],
                "score_rrf": round(score_rrf, 6),
                "rank": rank,
            }
        )

    return resultados
