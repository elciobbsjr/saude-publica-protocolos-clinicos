"""
Testes de contrato da integração (main.py): roteamento → retrieval → geração.
Rodam offline, sem LLM e sem a pasta output/.
"""

from main import adaptar_chunks
from src.generate import GenerationModule
from src.query_router import QueryRouter
from src.retrieval.filtros import aplicar_filtros


def _item(texto, chunk_id, status=None, data_inicio=None, doenca="artrite_reumatoide"):
    meta = {"chunk_id": chunk_id, "doenca": doenca}
    if status is not None:
        meta["status"] = status
    if data_inicio is not None:
        meta["data_inicio"] = data_inicio
    return {"chunk": {"texto": texto, "metadata": meta}, "score_rrf": 0.01, "rank": 1}


router = QueryRouter()


def test_adaptador_preserva_texto_id_e_vigencia():
    saida = adaptar_chunks([_item("Metotrexato 1a linha", "ar_c1", "vigente", "2026-01-19")])
    assert saida[0]["text"] == "Metotrexato 1a linha"
    assert saida[0]["chunk_id"] == "ar_c1"
    assert saida[0]["vigencia"] == "vigente desde 2026-01-19"


def test_adaptador_sem_status_nao_inventa_vigencia():
    saida = adaptar_chunks([_item("Bula metformina", "bula_c1")])
    assert saida[0]["vigencia"] is None


def test_gerador_recebe_versoes_diferentes():
    chunks = adaptar_chunks([
        _item("Esquema 2026", "ar_2026", "vigente", "2026-01-19"),
        _item("Esquema 2021", "ar_2021", "revogado", "2021-09-10"),
    ])
    prompt = GenerationModule().build_prompt("O que mudou?", chunks)
    assert "vigências diferentes" in prompt
    assert "vigente desde 2026-01-19" in prompt


def test_pergunta_clinica_sem_termo_temporal_usa_so_vigente():
    filtros = router.analisar("Qual é o tratamento da artrite reumatoide?")["retrieval_filters"]
    assert filtros["somente_vigente"] is True
    assert filtros["doenca"] == ["artrite_reumatoide"]


def test_pergunta_historica_libera_revogado():
    filtros = router.analisar("Qual era o protocolo antigo de asma?")["retrieval_filters"]
    assert filtros["somente_vigente"] is False


def test_alias_curto_nao_casa_dentro_de_palavra():
    # "has" (hipertensão) não pode casar com "linhas" nem "falhas"
    doencas = router.analisar("Quais as linhas de tratamento da artrite reumatoide?")["retrieval_filters"]["doenca"]
    assert doencas == ["artrite_reumatoide"]
    # "sul" não pode casar com "insulina"
    geo = router.analisar("Qual a dose de insulina no protocolo de diabetes tipo 1?")["entities"]["geografia"]
    assert geo["regiao"] is None


def test_filtro_vigente_mantem_chunks_sem_status():
    chunks = [
        _item("PCDT vigente", "p1", "vigente")["chunk"],
        _item("PCDT revogado", "p2", "revogado")["chunk"],
        _item("Bula sem status", "b1")["chunk"],
    ]
    ids = [c["metadata"]["chunk_id"] for c in aplicar_filtros(chunks, {"somente_vigente": True})]
    assert ids == ["p1", "b1"]
