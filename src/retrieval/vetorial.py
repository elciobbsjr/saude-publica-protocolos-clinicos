"""
Módulo de busca vetorial densa.

Realiza similaridade de cosseno entre o embedding
da query e os embeddings dos chunks já indexados.

Depende de:
    - src.llm.llm_embedding.get_embedding
      (que usa o servidor da ECOA com o modelo do config.py)

O formato esperado de cada chunk é o padrão do projeto:
    {
        "texto":     "...",
        "embedding": [0.123, ...],   # gerado pelo generate_embeddings.py
        "metadata":  { ... },
        "section":   "...",          # opcional
    }
"""

import math
from typing import Any

from src.llm.llm_embedding import get_embedding


# ------------------------------------------------------------------
# SIMILARIDADE DE COSSENO
# ------------------------------------------------------------------

def _similaridade_cosseno(
    vec_a: list[float],
    vec_b: list[float],
) -> float:
    """
    Calcula a similaridade de cosseno entre dois vetores.

    Returns:
        Valor entre -1.0 e 1.0. Quanto maior, mais similar.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(
            f"Vetores com dimensões diferentes: "
            f"{len(vec_a)} x {len(vec_b)}"
        )

    dot = sum(a * b for a, b in zip(vec_a, vec_b))

    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


# ------------------------------------------------------------------
# ÍNDICE VETORIAL
# ------------------------------------------------------------------

class IndiceVetorial:
    """
    Índice de busca densa por similaridade de cosseno.

    Recebe os chunks (com o campo "embedding" já preenchido
    pelo generate_embeddings.py da Patricia Zan) e retorna
    os mais similares à query do usuário.
    """

    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []
        self._embeddings: list[list[float]] = []
        self._construido: bool = False

    # ------------------------------------------------------------------
    # CONSTRUÇÃO
    # ------------------------------------------------------------------

    def construir(self, chunks: list[dict[str, Any]]) -> None:
        """
        Indexa os chunks que possuem campo "embedding".

        Chunks sem embedding são silenciosamente ignorados.

        Args:
            chunks: Lista de chunks no formato do projeto.
        """
        if not chunks:
            raise ValueError(
                "A lista de chunks não pode estar vazia."
            )

        self._chunks = []
        self._embeddings = []

        ignorados = 0

        for chunk in chunks:
            embedding = chunk.get("embedding")

            if not embedding or not isinstance(embedding, list):
                ignorados += 1
                continue

            self._chunks.append(chunk)
            self._embeddings.append(embedding)

        if not self._chunks:
            raise ValueError(
                "Nenhum chunk com campo 'embedding' válido "
                "foi encontrado. Execute o generate_embeddings.py "
                "antes de usar o índice vetorial."
            )

        if ignorados > 0:
            print(
                f"  [IndiceVetorial] Aviso: {ignorados} chunk(s) "
                f"ignorado(s) por falta de embedding."
            )

        self._construido = True

    # ------------------------------------------------------------------
    # BUSCA
    # ------------------------------------------------------------------

    def buscar(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Gera o embedding da query e retorna os `top_k` chunks
        mais similares por cosseno.

        Args:
            query:  Texto da pergunta do usuário.
            top_k:  Número máximo de resultados.

        Returns:
            Lista de dicionários com "chunk", "score" e "rank".
        """
        if not self._construido:
            raise RuntimeError(
                "O índice vetorial ainda não foi construído. "
                "Chame `construir()` antes de `buscar()`."
            )

        embedding_query = get_embedding(query)

        pontuacoes = [
            (
                i,
                _similaridade_cosseno(
                    embedding_query,
                    self._embeddings[i],
                ),
            )
            for i in range(len(self._chunks))
        ]

        pontuacoes = sorted(
            pontuacoes,
            key=lambda x: x[1],
            reverse=True,
        )

        resultados = []

        for rank, (doc_index, score) in enumerate(
            pontuacoes[:top_k], start=1
        ):
            resultados.append(
                {
                    "chunk": self._chunks[doc_index],
                    "score": score,
                    "rank": rank,
                }
            )

        return resultados
