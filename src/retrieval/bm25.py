"""
Módulo de busca BM25 (Okapi BM25).

Implementação própria sem dependências externas,
compatível com o padrão de chunks do projeto
(campo "texto" + campo "metadata").

Referência do algoritmo:
    Robertson & Zaragoza (2009). The Probabilistic
    Relevance Framework: BM25 and Beyond.
"""

import math
import re
import unicodedata
from collections import Counter
from typing import Any


# ------------------------------------------------------------------
# CONSTANTES DO ALGORITMO
# ------------------------------------------------------------------

K1: float = 1.5   # Saturação de frequência de termos
B: float = 0.75   # Penalização por comprimento do documento


# ------------------------------------------------------------------
# NORMALIZAÇÃO
# ------------------------------------------------------------------

def _normalizar(texto: str) -> list[str]:
    """
    Normaliza e tokeniza o texto para o BM25.

    - Converte para minúsculas.
    - Remove acentos.
    - Mantém apenas letras e números.
    - Tokeniza por espaços/não-alfanuméricos.
    """
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto if not unicodedata.combining(c)
    )
    tokens = re.findall(r"[a-z0-9]+", texto)
    return tokens


# ------------------------------------------------------------------
# ÍNDICE BM25
# ------------------------------------------------------------------

class IndiceBM25:
    """
    Índice BM25 construído a partir de uma lista de chunks.

    Cada chunk deve seguir o formato do projeto:
        {
            "texto": "...",
            "metadata": { ... },
            "section": "...",   # opcional
        }

    Após a construção (via `construir`), use `buscar` para
    recuperar os chunks mais relevantes para uma query.
    """

    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []
        self._tokens_por_doc: list[list[str]] = []
        self._freq_por_doc: list[Counter] = []
        self._df: Counter = Counter()         # document frequency
        self._idf: dict[str, float] = {}
        self._comprimento_medio: float = 0.0
        self._n_docs: int = 0
        self._construido: bool = False

    # ------------------------------------------------------------------
    # CONSTRUÇÃO
    # ------------------------------------------------------------------

    def construir(self, chunks: list[dict[str, Any]]) -> None:
        """
        Indexa a lista de chunks.

        Args:
            chunks: Lista de chunks no formato do projeto.
        """
        if not chunks:
            raise ValueError(
                "A lista de chunks não pode estar vazia."
            )

        self._chunks = chunks
        self._tokens_por_doc = []
        self._freq_por_doc = []
        self._df = Counter()

        total_tokens = 0

        for chunk in chunks:
            texto = chunk.get("texto", "")
            tokens = _normalizar(texto)

            self._tokens_por_doc.append(tokens)

            freq = Counter(tokens)
            self._freq_por_doc.append(freq)

            for termo in freq:
                self._df[termo] += 1

            total_tokens += len(tokens)

        self._n_docs = len(chunks)
        self._comprimento_medio = (
            total_tokens / self._n_docs
            if self._n_docs > 0
            else 0.0
        )

        self._calcular_idf()
        self._construido = True

    def _calcular_idf(self) -> None:
        """Calcula o IDF para cada termo do vocabulário."""
        n = self._n_docs

        for termo, df in self._df.items():
            # Fórmula IDF suavizada (Robertson & Zaragoza, 2009)
            self._idf[termo] = math.log(
                (n - df + 0.5) / (df + 0.5) + 1.0
            )

    # ------------------------------------------------------------------
    # PONTUAÇÃO
    # ------------------------------------------------------------------

    def _pontuar_documento(
        self,
        doc_index: int,
        termos_query: list[str],
    ) -> float:
        """Calcula o score BM25 de um documento para a query."""
        freq = self._freq_por_doc[doc_index]
        comprimento_doc = len(self._tokens_por_doc[doc_index])

        score = 0.0

        for termo in termos_query:
            if termo not in self._idf:
                continue

            tf = freq.get(termo, 0)

            if tf == 0:
                continue

            # Normalização por comprimento (fator b)
            norm = (
                1.0
                - B
                + B * comprimento_doc / self._comprimento_medio
            )

            # Pontuação BM25 do termo
            score += self._idf[termo] * (
                tf * (K1 + 1.0) / (tf + K1 * norm)
            )

        return score

    # ------------------------------------------------------------------
    # BUSCA
    # ------------------------------------------------------------------

    def buscar(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Retorna os `top_k` chunks mais relevantes para a query.

        Args:
            query:  Texto da pergunta do usuário.
            top_k:  Número máximo de resultados.

        Returns:
            Lista de dicionários com "chunk", "score" e "rank".
        """
        if not self._construido:
            raise RuntimeError(
                "O índice BM25 ainda não foi construído. "
                "Chame `construir()` antes de `buscar()`."
            )

        termos_query = _normalizar(query)

        if not termos_query:
            return []

        pontuacoes = [
            (i, self._pontuar_documento(i, termos_query))
            for i in range(self._n_docs)
        ]

        # Ordena do maior para o menor score, descartando score zero
        pontuacoes = sorted(
            ((i, s) for i, s in pontuacoes if s > 0),
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
