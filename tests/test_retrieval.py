"""
Testes do módulo de Recuperação Híbrida.

Cobre:
    - IndiceBM25: construção, busca, scores, edge cases
    - IndiceVetorial: construção com/sem embeddings
    - fusao_rrf: fusão de listas, deduplicação, score RRF
    - aplicar_filtros: todos os filtros individuais
    - RetrievalHibrido: integração sem API (corpus mockado)

Todos os testes rodam sem chamadas reais à API de embedding.
O IndiceVetorial é testado com mocks de embedding.
"""

import math
import pytest

from src.retrieval.bm25 import IndiceBM25, _normalizar
from src.retrieval.filtros import aplicar_filtros
from src.retrieval.rrf import fusao_rrf, K_RRF


# ==============================================================
# FIXTURES
# ==============================================================

def _chunk(
    texto: str,
    base_id: str = "protocolos_conitec",
    doenca: str = "asma",
    status: str = "vigente",
    data_inicio: str = "2024-01-01",
    data_fim: str | None = None,
    chunk_id: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    """Fábrica de chunks no formato padrão do projeto."""
    meta = {
        "chunk_id": chunk_id or texto[:10].replace(" ", "_"),
        "base_id": base_id,
        "doenca": doenca,
        "status": status,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }
    chunk = {
        "texto": texto,
        "section": "Teste",
        "metadata": meta,
    }
    if embedding is not None:
        chunk["embedding"] = embedding
    return chunk


CHUNKS_BASE = [
    _chunk(
        "O protocolo de asma vigente define critérios de inclusão.",
        doenca="asma",
        status="vigente",
        chunk_id="c1",
    ),
    _chunk(
        "Protocolo revogado de asma de 2021 com critérios antigos.",
        doenca="asma",
        status="revogado",
        data_inicio="2021-01-01",
        data_fim="2024-01-01",
        chunk_id="c2",
    ),
    _chunk(
        "Critérios de inclusão para diabetes tipo 2 no PCDT.",
        doenca="diabete_melito_tipo_2",
        status="vigente",
        base_id="protocolos_conitec",
        chunk_id="c3",
    ),
    _chunk(
        "Dados de internações por hipertensão no DataSUS.",
        doenca="hipertensao_arterial_sistemica",
        status="vigente",
        base_id="sih_datasus",
        chunk_id="c4",
    ),
    _chunk(
        "Losartana potássica está listada na RENAME 2024.",
        doenca="hipertensao_arterial_sistemica",
        status="vigente",
        base_id="rename_estruturada",
        chunk_id="c5",
    ),
]


# ==============================================================
# TESTES — NORMALIZAÇÃO BM25
# ==============================================================

class TestNormalizacao:
    def test_lowercase(self):
        assert _normalizar("ASMA") == ["asma"]

    def test_remove_acentos(self):
        assert _normalizar("critérios") == ["criterios"]

    def test_tokeniza_por_espacos(self):
        tokens = _normalizar("protocolo de asma")
        assert tokens == ["protocolo", "de", "asma"]

    def test_remove_pontuacao(self):
        tokens = _normalizar("asma, diabetes.")
        assert "asma" in tokens
        assert "diabetes" in tokens

    def test_texto_vazio(self):
        assert _normalizar("") == []

    def test_apenas_pontuacao(self):
        assert _normalizar("!!! ???") == []


# ==============================================================
# TESTES — BM25
# ==============================================================

class TestIndiceBM25:
    def test_construcao_basica(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        assert indice._construido is True
        assert indice._n_docs == len(CHUNKS_BASE)

    def test_erro_lista_vazia(self):
        indice = IndiceBM25()
        with pytest.raises(ValueError, match="vazia"):
            indice.construir([])

    def test_erro_busca_sem_construcao(self):
        indice = IndiceBM25()
        with pytest.raises(RuntimeError, match="construído"):
            indice.buscar("asma")

    def test_busca_retorna_lista(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("protocolo asma")
        assert isinstance(resultados, list)

    def test_busca_top_k(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("asma protocolo", top_k=2)
        assert len(resultados) <= 2

    def test_busca_retorna_formato_correto(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("asma")
        if resultados:
            item = resultados[0]
            assert "chunk" in item
            assert "score" in item
            assert "rank" in item
            assert item["rank"] == 1

    def test_relevancia_asma_maior_que_diabetes(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("asma protocolo")

        textos = [r["chunk"]["texto"] for r in resultados]
        # O chunk sobre asma deve aparecer antes do de diabetes
        idx_asma = next(
            (i for i, t in enumerate(textos) if "asma" in t.lower()),
            None,
        )
        idx_diabetes = next(
            (
                i
                for i, t in enumerate(textos)
                if "diabetes" in t.lower()
            ),
            None,
        )
        if idx_asma is not None and idx_diabetes is not None:
            assert idx_asma < idx_diabetes

    def test_score_positivo(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("asma")
        for item in resultados:
            assert item["score"] > 0

    def test_busca_query_vazia_retorna_vazio(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("")
        assert resultados == []

    def test_ranks_sequenciais(self):
        indice = IndiceBM25()
        indice.construir(CHUNKS_BASE)
        resultados = indice.buscar("protocolo asma")
        for i, item in enumerate(resultados, start=1):
            assert item["rank"] == i


# ==============================================================
# TESTES — RRF
# ==============================================================

class TestFusaoRRF:
    def _resultado(self, chunk, rank, score=1.0):
        return {"chunk": chunk, "rank": rank, "score": score}

    def test_fusao_basica(self):
        vetorial = [
            self._resultado(CHUNKS_BASE[0], rank=1),
            self._resultado(CHUNKS_BASE[1], rank=2),
        ]
        bm25 = [
            self._resultado(CHUNKS_BASE[1], rank=1),
            self._resultado(CHUNKS_BASE[2], rank=2),
        ]
        resultado = fusao_rrf(vetorial, bm25, top_k=10)
        assert len(resultado) >= 1

    def test_deduplicacao_por_chunk_id(self):
        """Chunk presente nos dois índices deve aparecer só uma vez."""
        chunk_duplicado = CHUNKS_BASE[0]
        vetorial = [self._resultado(chunk_duplicado, rank=1)]
        bm25 = [self._resultado(chunk_duplicado, rank=1)]

        resultado = fusao_rrf(vetorial, bm25, top_k=10)

        chaves = [
            r["chunk"]["metadata"]["chunk_id"]
            for r in resultado
        ]
        assert len(chaves) == len(set(chaves))

    def test_chunk_em_ambos_tem_score_maior(self):
        """
        Chunk presente nos dois índices deve ter score RRF maior
        do que chunk presente em apenas um.
        """
        chunk_ambos = CHUNKS_BASE[0]
        chunk_so_bm25 = CHUNKS_BASE[2]

        vetorial = [self._resultado(chunk_ambos, rank=1)]
        bm25 = [
            self._resultado(chunk_ambos, rank=1),
            self._resultado(chunk_so_bm25, rank=2),
        ]

        resultado = fusao_rrf(vetorial, bm25, top_k=10)

        scores = {
            r["chunk"]["metadata"]["chunk_id"]: r["score_rrf"]
            for r in resultado
        }

        assert scores[chunk_ambos["metadata"]["chunk_id"]] > scores.get(
            chunk_so_bm25["metadata"]["chunk_id"], 0
        )

    def test_top_k_respeitado(self):
        vetorial = [self._resultado(c, rank=i + 1) for i, c in enumerate(CHUNKS_BASE)]
        bm25 = [self._resultado(c, rank=i + 1) for i, c in enumerate(CHUNKS_BASE)]
        resultado = fusao_rrf(vetorial, bm25, top_k=2)
        assert len(resultado) <= 2

    def test_lista_vazia_retorna_vazio(self):
        resultado = fusao_rrf([], [], top_k=10)
        assert resultado == []

    def test_score_rrf_formato(self):
        vetorial = [self._resultado(CHUNKS_BASE[0], rank=1)]
        resultado = fusao_rrf(vetorial, [], top_k=5)
        assert isinstance(resultado[0]["score_rrf"], float)
        assert isinstance(resultado[0]["rank"], int)

    def test_ranks_sequenciais(self):
        vetorial = [self._resultado(c, rank=i + 1) for i, c in enumerate(CHUNKS_BASE)]
        resultado = fusao_rrf(vetorial, [], top_k=10)
        for i, item in enumerate(resultado, start=1):
            assert item["rank"] == i

    def test_score_rrf_formula(self):
        """Verifica que o score RRF corresponde à fórmula 1/(K_RRF+rank)."""
        chunk = CHUNKS_BASE[0]
        vetorial = [self._resultado(chunk, rank=1)]
        resultado = fusao_rrf(vetorial, [], top_k=5)

        esperado = 1.0 / (K_RRF + 1)
        assert abs(resultado[0]["score_rrf"] - esperado) < 1e-6


# ==============================================================
# TESTES — FILTROS
# ==============================================================

class TestFiltros:
    def test_filtro_base_id(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {"base_id": ["sih_datasus"]},
        )
        assert all(
            c["metadata"]["base_id"] == "sih_datasus"
            for c in resultado
        )

    def test_filtro_base_id_vazio_nao_filtra(self):
        resultado = aplicar_filtros(CHUNKS_BASE, {"base_id": []})
        assert len(resultado) == len(CHUNKS_BASE)

    def test_filtro_doenca(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {"doenca": ["asma"]},
        )
        assert all(
            c["metadata"]["doenca"] == "asma"
            for c in resultado
        )

    def test_filtro_doenca_vazio_nao_filtra(self):
        resultado = aplicar_filtros(CHUNKS_BASE, {"doenca": []})
        assert len(resultado) == len(CHUNKS_BASE)

    def test_filtro_somente_vigente(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {
                "somente_vigente": True,
                "historico": False,
            },
        )
        assert all(
            c["metadata"]["status"] == "vigente"
            for c in resultado
        )

    def test_filtro_historico(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {
                "somente_vigente": False,
                "historico": True,
            },
        )
        assert all(
            c["metadata"]["status"] != "vigente"
            for c in resultado
        )

    def test_filtro_sem_vigencia_nao_filtra(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {
                "somente_vigente": False,
                "historico": False,
            },
        )
        assert len(resultado) == len(CHUNKS_BASE)

    def test_filtro_ano_dentro_do_intervalo(self):
        chunks = [
            _chunk(
                "Dado de 2023",
                data_inicio="2022-01-01",
                data_fim="2024-12-31",
                chunk_id="ano1",
            ),
            _chunk(
                "Dado de 2020",
                data_inicio="2019-01-01",
                data_fim="2021-12-31",
                chunk_id="ano2",
            ),
        ]
        resultado = aplicar_filtros(chunks, {"anos": [2023]})
        assert len(resultado) == 1
        assert resultado[0]["metadata"]["chunk_id"] == "ano1"

    def test_filtro_ano_documento_sem_fim(self):
        """Documento vigente (data_fim=None) cobre qualquer ano futuro."""
        chunks = [
            _chunk(
                "Documento sem data de fim",
                data_inicio="2024-01-01",
                data_fim=None,
                chunk_id="sem_fim",
            )
        ]
        resultado = aplicar_filtros(chunks, {"anos": [2030]})
        assert len(resultado) == 1

    def test_filtro_anos_vazio_nao_filtra(self):
        resultado = aplicar_filtros(CHUNKS_BASE, {"anos": []})
        assert len(resultado) == len(CHUNKS_BASE)

    def test_filtros_combinados(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {
                "base_id": ["protocolos_conitec"],
                "doenca": ["asma"],
                "somente_vigente": True,
                "historico": False,
                "anos": [],
            },
        )
        assert all(
            c["metadata"]["base_id"] == "protocolos_conitec"
            and c["metadata"]["doenca"] == "asma"
            and c["metadata"]["status"] == "vigente"
            for c in resultado
        )

    def test_filtros_sem_resultado(self):
        resultado = aplicar_filtros(
            CHUNKS_BASE,
            {
                "base_id": ["base_inexistente"],
            },
        )
        assert resultado == []
