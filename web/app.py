import json
import re
from collections import deque
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.observability import configurar_logging

configurar_logging()

from web.orchestrator import Orchestrator, DOENCAS

BENCHMARK_FILE = ROOT / "benchmarks" / "perguntas.json"

st.set_page_config(
    page_title="RAG Clínico — v1",
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


def montar_pergunta_contextualizada(doenca_selecionada: str, pergunta_usuario: str) -> str:
    """Fixa o escopo documental sem modificar o texto digitado pelo usuário."""
    return f"Sobre {doenca_selecionada}: {pergunta_usuario.strip()}"


def outra_doenca_selecionavel(pergunta_usuario: str, doenca_selecionada: str):
    """Detecta apenas nomes explícitos de OUTRAS doenças cadastradas.

    Não tenta inferir sinônimos ou doenças fora do catálogo; esses casos
    continuam sujeitos à verificação documental do RAG.
    """
    texto = pergunta_usuario.casefold()
    for nome in DOENCAS:
        if nome == doenca_selecionada:
            continue
        if re.search(r"(?<!\w)" + re.escape(nome.casefold()) + r"(?!\w)", texto):
            return nome
    return None


col1, col2 = st.columns(2)

with col1:
    doenca = st.selectbox("Doença", list(DOENCAS))

with col2:
    vigencia = st.radio(
        "Situação documental",
        ["Vigente", "Histórico"],
        horizontal=True,
    )

    nivel_resposta = st.radio(
        "Tamanho da resposta",
        ["Mínima", "Intermediária", "Completa"],
        index=1,
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

st.text_input(
    "Doença selecionada (não editável)",
    value=doenca,
    disabled=True,
    help="Para alterar a doença, utilize a lista de seleção acima.",
)

pergunta = st.text_area(
    "O que deseja saber sobre a doença selecionada?",
    value=pergunta_inicial,
    height=110,
    placeholder="Ex.: Quais são os critérios de diagnóstico?",
)

outra_doenca = outra_doenca_selecionavel(pergunta, doenca)
if outra_doenca:
    st.warning(
        f"Sua pergunta menciona '{outra_doenca}', mas a doença selecionada é "
        f"'{doenca}'. Altere a seleção ou reformule a pergunta."
    )

if st.button("Executar consulta", type="primary"):
    st.session_state.pop("resultado", None)
    if not pergunta.strip():
        st.warning("Informe uma pergunta.")
    elif outra_doenca:
        st.error("Consulta não executada: a pergunta menciona outra doença cadastrada.")
    else:
        try:
            with st.spinner("Recuperando evidências..."):
                pergunta_contextualizada = montar_pergunta_contextualizada(doenca, pergunta)
                resultado = obter_orquestrador().consultar(
                    pergunta_contextualizada,
                    doenca,
                    vigencia,
                    nivel_resposta,
                )

            st.session_state["resultado"] = resultado
            st.session_state["consulta_exibida"] = {
                "doenca": doenca,
                "vigencia": vigencia,
                "pergunta": pergunta.strip(),
            }

        except Exception as erro:
            st.error(f"Erro na consulta: {erro}")

st.divider()

aba_resposta, aba_evidencias, aba_observabilidade, aba_logs = st.tabs(
    ["Resposta", "Evidências", "Observabilidade", "Logs"]
)

resultado = st.session_state.get("resultado")
consulta_exibida = st.session_state.get("consulta_exibida") or {}
if resultado and (
    consulta_exibida.get("doenca") != doenca
    or consulta_exibida.get("vigencia") != vigencia
    or consulta_exibida.get("pergunta") != pergunta.strip()
):
    resultado = None


if resultado:
    if resultado.get("recusado"):
        with aba_resposta:
            st.warning(resultado.get("motivo", "Consulta não permitida."))
        with aba_evidencias:
            st.info("Nenhuma evidência apresentada para esta consulta.")
        with aba_observabilidade:
            st.subheader("Diagnóstico da consulta")
            st.json(resultado.get("analise", {}))
    else:
        recuperacao = resultado.get("recuperacao") or {}
        geracao = resultado.get("geracao") or {}
        chunks = recuperacao.get("chunks") or []

        with aba_resposta:
            st.subheader("Resposta do RAG")
            if not chunks:
                st.warning("Não foram encontradas evidências suficientes para responder.")
            else:
                validacao = geracao.get("validation") or {}

                if validacao.get("validated") is True:
                    st.success("Verificação documental automática aprovada.")
                elif validacao.get("status") == "review_required":
                    st.warning(
                        "Verificação documental não aprovada ou inconclusiva. "
                        "A resposta abaixo é experimental; confira as evidências."
                    )
                else:
                    st.info("Verificação documental não concluída.")

                if geracao.get("response"):
                    st.markdown(str(geracao["response"]))
                else:
                    st.info("O módulo de geração não retornou resposta textual.")
            st.metric("Chunks recuperados", len(chunks))
            with st.expander("Resultado da validação automática"):
                st.json({
                    "status": geracao.get("status"),
                    "validation": geracao.get("validation"),
                    "sources_used": geracao.get("sources_used"),
                })

        with aba_evidencias:
            if not chunks:
                st.info("Nenhum chunk recuperado.")
            for indice, item in enumerate(chunks, start=1):
                chunk = item.get("chunk") or {}
                metadata = chunk.get("metadata") or {}
                with st.expander(
                    f"Rank {item.get('rank', indice)} — "
                    f"{metadata.get('chunk_id', 'sem ID')}"
                ):
                    st.write(chunk.get("texto", ""))
                    st.json({
                        "rank": item.get("rank"),
                        "score_rrf": item.get("score_rrf"),
                        "metadata": metadata,
                    })

        with aba_observabilidade:
            st.subheader("Diagnóstico da validação")
            st.json(geracao.get("validation") or {})

            latencia = recuperacao.get("latencia_segundos")
            if isinstance(latencia, (int, float)):
                st.metric("Latência de recuperação", f"{latencia:.3f} s")
            st.json({
                "filtros": recuperacao.get("filtros_aplicados"),
                "chunks_antes": recuperacao.get("chunks_antes_filtro"),
                "chunks_apos": recuperacao.get("chunks_apos_filtro"),
                "chunks_retornados": len(chunks),
            })
            st.metric("Latência de geração e validação", f"{resultado.get('tempo_geracao', 0):.3f} s")
            st.metric("Tempo total da consulta", f"{resultado.get('tempo_total', 0):.3f} s")
            with st.expander("Metadados da geração"):
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
    with aba_observabilidade:
        st.info("Os dados da execução aparecerão aqui.")

with aba_logs:
    st.subheader("Logs de execução")

    arquivo_log = ROOT / "logs" / "rag_web.log"

    if st.button("Atualizar logs"):
        st.rerun()

    if arquivo_log.exists():
        with arquivo_log.open(
            "r", encoding="utf-8", errors="replace"
        ) as arquivo:
            ultimas_linhas = deque(arquivo, maxlen=100)

        conteudo = "".join(ultimas_linhas)

        st.code(
            conteudo or "Arquivo de log vazio.",
            language="text",
        )
    else:
        st.info(
            "O arquivo de log ainda não foi criado."
        )
