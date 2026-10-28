
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.query_router import QueryRouter
from src.retrieval.retrieval_hibrido import RetrievalHibrido


def main():
    pergunta = (
        "Quais são os critérios para iniciar "
        "o tratamento com abatacepte?"
    )

    router = QueryRouter()
    analise = router.analisar(pergunta)

    filtros = dict(analise["retrieval_filters"])

    # Escolhas explícitas da interface têm prioridade.
    filtros["doenca"] = ["artrite_idiopatica_juvenil"]
    filtros["somente_vigente"] = True
    filtros["historico"] = False
    filtros["comparar_versoes"] = False

    print("=== FILTROS ===")
    print(json.dumps(filtros, ensure_ascii=False, indent=2))

    retrieval = RetrievalHibrido()
    resultado = retrieval.executar(
        query=pergunta,
        filtros=filtros,
    )

    print("\n=== RECUPERAÇÃO ===")
    print("Chunks antes:", resultado["chunks_antes_filtro"])
    print("Chunks após:", resultado["chunks_apos_filtro"])
    print("Chunks finais:", len(resultado["chunks"]))
    print("Latência:", resultado["latencia_segundos"])

    for item in resultado["chunks"]:
        chunk = item["chunk"]
        metadata = chunk.get("metadata", {})

        print("\n--- Evidência ---")
        print("Rank:", item["rank"])
        print("Score RRF:", item["score_rrf"])
        print("Chunk ID:", metadata.get("chunk_id"))
        print("Status:", metadata.get("status"))
        print("Texto:", chunk.get("texto", "")[:300])


if __name__ == "__main__":
    main()
