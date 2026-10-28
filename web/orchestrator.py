import time

from src.query_router import QueryRouter
from src.retrieval.retrieval_hibrido import RetrievalHibrido
from src.generate import GenerationModule


import logging

logger = logging.getLogger(__name__)

DOENCAS = {
    "Artrite idiopática juvenil": "artrite_idiopatica_juvenil",
    "Artrite reumatoide": "artrite_reumatoide",
}


class Orchestrator:
    def __init__(self):
        self.router = QueryRouter()
        self.retrieval = RetrievalHibrido()
        self.generator = GenerationModule()

    def consultar(self, pergunta, doenca, vigencia, nivel_resposta="Completa"):
        inicio_total = time.perf_counter()

        analise = self.router.analisar(pergunta)

        if analise.get("requires_refusal"):
            return {
                "recusado": True,
                "motivo": "Consulta classificada como conduta individualizada.",
                "analise": analise,
                "recuperacao": None,
                "geracao": None,
            }

        # Os filtros dinâmicos extraídos pelo QueryRouter passam diretamente para a busca.
        filtros = dict(analise.get("retrieval_filters", {}))

        # Aplica ajuste de vigência da interface quando especificado.
        if vigencia == "Vigente":
            filtros["somente_vigente"] = True
            filtros["historico"] = False
        elif vigencia == "Histórico":
            filtros["somente_vigente"] = False
            filtros["historico"] = True

        recuperacao = self.retrieval.executar(
            query=pergunta,
            filtros=filtros,
        )

        contexto = []
        for item in recuperacao.get("chunks", []):
            chunk = item.get("chunk", {})
            metadata = chunk.get("metadata", {})

            contexto.append({
                "chunk_id": metadata.get("chunk_id"),
                "text": chunk.get("texto", "") or chunk.get("text", ""),
                "texto": chunk.get("texto", "") or chunk.get("text", ""),
                "vigencia": metadata.get("status"),
                "rank": item.get("rank"),
                "score_rrf": item.get("score_rrf"),
                "secao": chunk.get("section") or metadata.get("section") or metadata.get("secao") or "Seção não informada",
                "source": metadata.get("source_file") or metadata.get("file_name") or "Documento não informado",
            })

        inicio_geracao = time.perf_counter()

        geracao = self.generator.generate_response(
            query=pergunta,
            context_chunks=contexto,
            call_llm=True,
            validate=True,
           nivel_resposta=nivel_resposta,
        )

        tempo_geracao = time.perf_counter() - inicio_geracao
        tempo_total = time.perf_counter() - inicio_total

        return {
            "recusado": False,
            "analise": analise,
            "recuperacao": recuperacao,
            "geracao": geracao,
            "tempo_geracao": round(tempo_geracao, 3),
            "tempo_total": round(tempo_total, 3),
        }
