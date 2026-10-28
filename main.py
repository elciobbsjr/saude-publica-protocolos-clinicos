
from pathlib import Path
import argparse

from src.query_router import QueryRouter
from src.retrieval.retrieval_hibrido import (
    RetrievalHibrido,
    TOP_K_BUSCA,
    TOP_K_FINAL,
)
from src.generate import GenerationModule, HealthGuardrails
from src.save_response.save_response import save_response


PASTA_CORPUS_PADRAO = Path("output/output_chunking/v8")


def _montar_vigencia(metadata):
    """
    Monta a vigência a partir dos campos que o chunking grava
    (status e data_inicio). O chunk não tem um campo "vigencia".
    Bulas e SIH não têm status: nesse caso retorna None.
    """
    status = metadata.get("status")
    data_inicio = metadata.get("data_inicio")

    if status and data_inicio:
        return f"{status} desde {data_inicio}"

    return status or None


def adaptar_chunks(resultados):
    """Converte os resultados RRF para o formato do gerador."""
    chunks = []

    for item in resultados:
        chunk = item["chunk"]
        metadata = chunk.get("metadata") or {}

        chunks.append({
            "text": chunk.get("texto", ""),
            "chunk_id": metadata.get("chunk_id"),
            "vigencia": _montar_vigencia(metadata),
        })

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline RAG de protocolos clínicos"
    )
    parser.add_argument(
        "pergunta",
        help="Pergunta a ser respondida"
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Executa a geração com o LLM"
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=PASTA_CORPUS_PADRAO,
        help="Pasta do output_chunking (padrão: output/output_chunking/v8)"
    )
    parser.add_argument(
        "--top-k-busca",
        type=int,
        default=TOP_K_BUSCA,
        help="Candidatos de cada busca (BM25 e vetorial) antes do RRF"
    )
    parser.add_argument(
        "--top-k-final",
        type=int,
        default=TOP_K_FINAL,
        help="Chunks enviados ao gerador depois do RRF"
    )
    args = parser.parse_args()

    if not args.corpus.is_dir():
        raise FileNotFoundError(
            f"Corpus não encontrado: {args.corpus}"
        )

    # Registro da consulta (save_response). A pergunta é salva já
    # anonimizada (LGPD).
    registro = {
        "pergunta_sanitizada": HealthGuardrails.mask_lgpd(args.pergunta),
        "llm_ativado": args.llm,
        "corpus": str(args.corpus),
    }

    # Etapa 1: roteamento
    print("\n=== ROTEAMENTO ===")
    router = QueryRouter()
    roteamento = router.analisar(args.pergunta)
    registro["roteamento"] = roteamento

    print("Intenção:", roteamento["intent"])
    print("Rotas:", roteamento["routes"])
    print("Filtros:", roteamento["retrieval_filters"])

    # Etapa 2: recuperação híbrida
    print("\n=== RECUPERAÇÃO ===")
    retrieval = RetrievalHibrido(
        pasta_output=args.corpus,
        top_k_busca=args.top_k_busca,
        top_k_final=args.top_k_final,
    )

    resultado = retrieval.executar(
        query=args.pergunta,
        filtros=roteamento["retrieval_filters"]
    )

    print(
        "Chunks recuperados:",
        len(resultado["chunks"])
    )

    registro["recuperacao"] = {
        "top_k_busca": args.top_k_busca,
        "top_k_final": args.top_k_final,
        "chunks_antes_filtro": resultado["chunks_antes_filtro"],
        "chunks_apos_filtro": resultado["chunks_apos_filtro"],
        "latencia_segundos": resultado["latencia_segundos"],
        "chunks": [
            {
                "rank": item["rank"],
                "score_rrf": item["score_rrf"],
                "chunk_id": (item["chunk"].get("metadata") or {}).get("chunk_id"),
                "texto": item["chunk"].get("texto", ""),
                "metadata": item["chunk"].get("metadata") or {},
            }
            for item in resultado["chunks"]
        ],
    }

    for item in resultado["chunks"]:
        meta = item["chunk"].get("metadata") or {}
        print(
            f"  #{item['rank']} RRF={item['score_rrf']} "
            f"{meta.get('chunk_id')} | {meta.get('doenca')} | "
            f"{meta.get('status')} | {meta.get('source_file')}"
        )

    # Etapa 3: adaptação
    context_chunks = adaptar_chunks(
        resultado["chunks"]
    )

    if not context_chunks:
        print("Nenhum contexto encontrado.")
        registro["geracao"] = None
        registro["status"] = "sem_contexto"
        caminho = save_response(registro)
        print(f"\nRegistro salvo em: {caminho}")
        return

    # Etapa 4: geração
    print("\n=== GERAÇÃO ===")
    gerador = GenerationModule()

    resposta = gerador.generate_response(
        query=args.pergunta,
        context_chunks=context_chunks,
        call_llm=args.llm
    )

    registro["status"] = resposta["status"]
    registro["geracao"] = {
        "is_refusal": resposta["is_refusal"],
        "sources_used": resposta["sources_used"],
        "resposta": resposta["response"],
        "prompt": resposta["prompt"],
        "tokens": resposta["tokens"],
    }
    caminho = save_response(registro)

    print(resposta["response"])
    print(f"\nRegistro salvo em: {caminho}")


if __name__ == "__main__":
    main()
