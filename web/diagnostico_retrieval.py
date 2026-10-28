import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrieval.retrieval_hibrido import RetrievalHibrido
from src.retrieval.filtros import aplicar_filtros
from src.retrieval.bm25 import IndiceBM25
from src.retrieval.vetorial import IndiceVetorial
from src.retrieval.rrf import fusao_rrf

PERGUNTA = "Quais são os critérios para iniciar o tratamento com abatacepte?"

ESPERADOS = {
    "f8bc539d26c4f715_0040",
    "f8bc539d26c4f715_0041",
}

FILTROS = {
    "base_id": ["protocolos_conitec"],
    "doenca": ["artrite_idiopatica_juvenil"],
    "medicamento": [],
    "anos": [],
    "somente_vigente": True,
    "comparar_versoes": False,
    "historico": False,
    "regiao": None,
    "uf": None,
}


def chunk_id(chunk):
    return chunk.get("metadata", {}).get("chunk_id")


def posicao(resultados, identificador):
    for indice, item in enumerate(resultados, start=1):
        if chunk_id(item["chunk"]) == identificador:
            return indice
    return None


def main():
    retrieval = RetrievalHibrido()

    inicio = time.perf_counter()
    retrieval._garantir_corpus()

    corpus = retrieval._chunks_completos or []
    filtrados = aplicar_filtros(corpus, FILTROS)

    print("\n=== CORPUS ===")
    print("Total:", len(corpus))
    print("Após filtros:", len(filtrados))

    ids_corpus = {chunk_id(c) for c in corpus}
    ids_filtrados = {chunk_id(c) for c in filtrados}

    print("\n=== PRESENÇA DOS CHUNKS ===")
    for identificador in sorted(ESPERADOS):
        print(
            identificador,
            "| corpus:", identificador in ids_corpus,
            "| filtrado:", identificador in ids_filtrados,
        )

    print("\n=== BM25 ===")
    bm25 = IndiceBM25()
    bm25.construir(filtrados)
    resultados_bm25 = bm25.buscar(
        PERGUNTA, top_k=len(filtrados)
    )

    print("\n=== VETORIAL ===")
    vetorial = IndiceVetorial()
    vetorial.construir(filtrados)
    resultados_vetorial = vetorial.buscar(
        PERGUNTA, top_k=len(filtrados)
    )

    print("\n=== POSIÇÕES ===")
    for identificador in sorted(ESPERADOS):
        print(
            identificador,
            "| BM25:", posicao(resultados_bm25, identificador),
            "| Vetorial:", posicao(resultados_vetorial, identificador),
        )

    # Reproduz a configuração original:
    # 20 candidatos por índice, 10 resultados finais.
    resultado_rrf = fusao_rrf(
        resultados_vetorial=resultados_vetorial[:20],
        resultados_bm25=resultados_bm25[:20],
        top_k=10,
    )

    print("\n=== RRF TOP 10 ===")
    for item in resultado_rrf:
        print(
            item["rank"],
            chunk_id(item["chunk"]),
            f"RRF={item['score_rrf']:.6f}",
        )

    print("\n=== RESULTADO DO BENCHMARK ===")
    encontrados = {
        chunk_id(item["chunk"])
        for item in resultado_rrf
    }

    acertos = len(ESPERADOS & encontrados)

    print(f"Evidências esperadas recuperadas: {acertos}/2")
    print(f"Recall@10 dos chunks de referência: {acertos / 2:.2%}")
    print(f"Tempo total: {time.perf_counter() - inicio:.3f}s")


if __name__ == "__main__":
    main()