"""Constrói o índice FAISS a partir dos chunks que já tem embeddings."""

import json
from pathlib import Path

import faiss
import numpy as np

from src.retrieval.corpus_loader import carregar_todos_os_chunks

PASTA_V7 = Path("output/output_chunking/v8")
PASTA_INDEX = Path("output/faiss_v8")

CHAVES_EMBEDDING = ("embedding", "vetor", "vector")


def _extrair_embedding(chunk: dict) -> list[float] | None:
    for chave in CHAVES_EMBEDDING:
        if chunk.get(chave):
            return chunk[chave]
    return None


def main() -> None:
    chunks = carregar_todos_os_chunks(PASTA_V7)
    print(f"Chunks carregados: {len(chunks)}")

    if not chunks:
        raise RuntimeError("Nenhum chunk encontrado em PASTA_VERSION.")

    print("Chaves do primeiro chunk:", list(chunks[0].keys()))

    vetores, metadados = [], []
    for chunk in chunks:
        emb = _extrair_embedding(chunk)
        if emb is None:
            continue  # descarta chunks sem embedding
        vetores.append(emb)
        # guarda o chunk sem o vetor, para não duplicar espaço
        metadados.append({k: v for k, v in chunk.items() if k not in CHAVES_EMBEDDING})

    if not vetores:
        raise RuntimeError("Nenhum embedding encontrado. Veja as chaves impressas acima e ajuste CHAVES_EMBEDDING.")

    matriz = np.array(vetores, dtype="float32")
    faiss.normalize_L2(matriz)  # normaliza para usar similaridade de cosseno

    index = faiss.IndexFlatIP(matriz.shape[1])  # IP + vetores normalizados = cosseno
    index.add(matriz)

    PASTA_INDEX.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(PASTA_INDEX / "index.faiss"))
    (PASTA_INDEX / "chunks.json").write_text(
        json.dumps(metadados, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Índice salvo em {PASTA_INDEX}: {index.ntotal} vetores, dim={matriz.shape[1]}")


if __name__ == "__main__":
    main()