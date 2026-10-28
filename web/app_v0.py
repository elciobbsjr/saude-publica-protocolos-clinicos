import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.orchestrator import Orchestrator, DOENCAS

BENCHMARK_FILE = ROOT / "benchmarks" / "perguntas.json"

st.set_page_config(
    page_title="RAG Clínico — v0.1",
    page_icon="🩺",
    layout="wide",
)


@st.cache_resource
def obter_orquestrador():
    return Orchestrator()


def carregar_benchmark():
    if not BENCHMARK_FILE.exists():
        return []

    with BENCHMARK_FILE.open(encoding="utf-8-sig") as arquivo:
        return json.load(arquivo)


st.title("RAG Clínico — v0.1")
st.caption("Consulta e recuperação de evidências dos PCDTs")

perguntas = carregar_benchmark()

col1, col2 = st.columns(2)

with col1:
    doenca = st.selectbox("Doença", list(DOENCAS))

with col2:
    vigencia = st.radio(
        "Situação documental",
        ["Vigente", "Histórico"],
        horizontal=True,
    )

perguntas_disponiveis = [
    p for p in perguntas
    if p["doenca"] == doenca
]

opcoes = ["Pergunta livre"] + [
    p["pergunta"] for p in perguntas_disponiveis
]

selecionada = st.selectbox("Perguntas de benchmark", opcoes)

pergunta_inicial = (
    "" if selecionada == "Pergunta livre"
    else selecionada
)

pergunta = st.text_area(
    "Pergunta",
    value=pergunta_inicial,
    height=110,
)

if st.button("Executar consulta", type="primary"):
    if not pergunta.strip():
        st.warning("Informe uma pergunta.")
    else:
        try:
            with st.spinner("Recuperando evidências..."):
                resultado = obter_orquestrador().consultar(
                    pergunta,
                    doenca,
                    vigencia,
                )

            st.session_state["resultado"] = resultado

        except Exception as erro:
            st.error(f"Erro na consulta: {erro}")

st.divider()

aba_resposta, aba_evidencias, aba_logs = st.tabs(
    ["Resposta", "Evidências", "Observabilidade"]
)

resultado = st.session_state.get("resultado")

if resultado:
    if resultado["recusado"]:
        with aba_resposta:
            st.warning(resultado["motivo"])

        with aba_logs:
            st.json(resultado["analise"])

    else:
        recuperacao = resultado["recuperacao"]
        
        with aba_resposta:
            geracao = resultado["geracao"]

            st.subheader("Resposta do RAG")

            resposta = geracao.get("response")

            if resposta:
                st.markdown(str(resposta))
            else:
                st.warning(
                    "O módulo de geração não retornou "
                    "uma resposta textual."
                )

            st.caption(
                "Resposta gerada automaticamente com base "
                "nas evidências recuperadas. "
                "Não substitui avaliação clínica."
            )

            st.metric(
                "Chunks recuperados",
                len(recuperacao["chunks"]),
            )

    with st.expander("Resultado da validação automática"):
        st.json({
            "status": geracao.get("status"),
            "validation": geracao.get("validation"),
            "sources_used": geracao.get("sources_used"),
        })
        
        
        with aba_evidencias:
            for item in recuperacao["chunks"]:
                chunk = item["chunk"]
                metadata = chunk.get("metadata", {})

                with st.expander(
                    f"Rank {item['rank']} — "
                    f"{metadata.get('chunk_id', 'sem ID')}"
                ):
                    st.write(chunk.get("texto", ""))

                    st.json({
                        "rank": item["rank"],
                        "score_rrf": item["score_rrf"],
                        "metadata": metadata,
                    })

        with aba_logs:
            st.metric(
                "Latência de recuperação",
                f"{recuperacao['latencia_segundos']:.3f} s",
            )

            st.json({
                "filtros": recuperacao["filtros_aplicados"],
                "chunks_antes": recuperacao["chunks_antes_filtro"],
                "chunks_apos": recuperacao["chunks_apos_filtro"],
                "chunks_retornados": len(recuperacao["chunks"]),
            })
            st.metric(
                "Latência de geração e validação",
                f"{resultado['tempo_geracao']:.3f} s",
            )

            st.metric(
                "Tempo total da consulta",
                f"{resultado['tempo_total']:.3f} s",
            )

            with st.expander("Metadados da geração"):
                geracao = resultado["geracao"]

                st.json({
                    "status": geracao.get("status"),
                    "is_refusal": geracao.get("is_refusal"),
                    "tokens": geracao.get("tokens"),
                    "sources_used": geracao.get("sources_used"),
                })
else:
    with aba_resposta:
        st.info("Execute uma consulta para visualizar os resultados.")

    with aba_evidencias:
        st.info("As evidências recuperadas aparecerão aqui.")

    with aba_logs:
        st.info("Os dados da execução aparecerão aqui.")