"""Consulta o índice FAISS já construído."""

import json
from pathlib import Path

import faiss
import numpy as np

from src.llm.llm_embedding import get_embeddings_batch

PASTA_INDEX = Path("output/faiss_v8")


def gerar_embedding_pergunta(pergunta: str) -> list[float]:
    """Gera o embedding de uma única pergunta, com o mesmo modelo dos chunks."""
    return get_embeddings_batch([pergunta], batch_size=1)[0]

class BancoFaiss:
    def __init__(self, pasta: Path = PASTA_INDEX) -> None:
        self.index = faiss.read_index(str(pasta / "index.faiss"))
        self.chunks = json.loads((pasta / "chunks.json").read_text(encoding="utf-8"))

    def buscar(self, texto_query: str, top_k: int = 10) -> list[dict]:
        vetor = np.array([gerar_embedding_pergunta(texto_query)], dtype="float32")
        faiss.normalize_L2(vetor)

        scores, ids = self.index.search(vetor, top_k)

        return [
            {"rank": r + 1, "score": float(s), "chunk": self.chunks[i]}
            for r, (s, i) in enumerate(zip(scores[0], ids[0]))
            if i != -1
        ]