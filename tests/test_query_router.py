import pytest

from src.query_router import QueryRouter


router = QueryRouter()


# ============================================================
# TESTES BÁSICOS
# ============================================================

def test_consulta_normativa_vigente():
    resultado = router.analisar(
        "Quais são os critérios do PCDT vigente "
        "de diabetes tipo 2?"
    )

    assert resultado["intent"] == "consulta_vigente"
    assert resultado["routes"] == ["normativa"]

    assert (
        "diabete_melito_tipo_2"
        in resultado["entities"]["doencas"]
    )

    assert resultado["temporal_filters"]["vigente"] is True


def test_consulta_medicamento():
    resultado = router.analisar(
        "A losartana está disponível na RENAME?"
    )

    assert resultado["intent"] == "consulta_medicamento"
    assert resultado["routes"] == ["estruturada"]

    assert (
        "losartana_potassica"
        in resultado["entities"]["medicamentos"]
    )


def test_consulta_agregada():
    resultado = router.analisar(
        "Qual foi o número de internações "
        "por hipertensão em 2025?"
    )

    assert resultado["intent"] == "consulta_indicador"
    assert resultado["routes"] == ["agregada"]

    assert (
        "hipertensao_arterial_sistemica"
        in resultado["entities"]["doencas"]
    )

    assert resultado["temporal_filters"]["anos"] == [2025]


def test_comparacao_temporal():
    resultado = router.analisar(
        "O que mudou no protocolo de asma "
        "entre 2021 e 2026?"
    )

    assert resultado["intent"] == "comparacao_temporal"
    assert resultado["routes"] == ["normativa"]

    assert "asma" in resultado["entities"]["doencas"]

    assert resultado["temporal_filters"]["anos"] == [
        2021,
        2026,
    ]

    assert (
        resultado["temporal_filters"]["comparacao"]
        is True
    )


def test_conduta_individualizada():
    resultado = router.analisar(
        "Meu pai tem pressão alta. "
        "Que remédio ele deve tomar?"
    )

    assert resultado["intent"] == "conduta_individualizada"
    assert resultado["routes"] == []
    assert resultado["requires_refusal"] is True


def test_consulta_multirrota():
    resultado = router.analisar(
        "O PCDT recomenda esse medicamento "
        "e quantas dispensações ocorreram em 2025?"
    )

    assert "normativa" in resultado["routes"]
    assert "agregada" in resultado["routes"]

    assert resultado["temporal_filters"]["anos"] == [2025]


# ============================================================
# PERSONA 1 — DR. CARLOS
# ============================================================

def test_persona_carlos_1_normativa():
    resultado = router.analisar(
        "Quais são os critérios exatos de exclusão "
        "para o uso de dapagliflozina no PCDT "
        "de Diabetes Mellitus Tipo 2 vigente?"
    )

    assert "normativa" in resultado["routes"]

    assert (
        "diabete_melito_tipo_2"
        in resultado["entities"]["doencas"]
    )

    assert resultado["temporal_filters"]["vigente"] is True


def test_persona_carlos_2_estruturada():
    resultado = router.analisar(
        "O medicamento X consta na RENAME vigente "
        "com indicação aprovada para o tratamento "
        "de insuficiência cardíaca crônica?"
    )

    assert "estruturada" in resultado["routes"]


def test_persona_carlos_3_cross_source():
    resultado = router.analisar(
        "O PCDT atual de uma determinada doença "
        "incorpora o medicamento Y, mas os registros "
        "de dispensação do DATASUS mostram que ele "
        "foi distribuído no município em 2025? "
        "Qual é a divergência temporal?"
    )

    assert "normativa" in resultado["routes"]
    assert "agregada" in resultado["routes"]

    assert resultado["temporal_filters"]["anos"] == [2025]

    assert (
        resultado["temporal_filters"]["comparacao"]
        is True
    )


# ============================================================
# PERSONA 2 — MARIANA
# ============================================================

def test_persona_mariana_1_normativa():
    resultado = router.analisar(
        "Quais são os parâmetros recomendados "
        "de frequência para automonitorização glicêmica "
        "capilar em pacientes com Diabetes Tipo 2 "
        "conforme o protocolo atual?"
    )

    assert resultado["routes"] == ["normativa"]

    assert (
        "diabete_melito_tipo_2"
        in resultado["entities"]["doencas"]
    )

    assert resultado["temporal_filters"]["vigente"] is True


def test_persona_mariana_2_agregada():
    resultado = router.analisar(
        "Quais foram os indicadores agregados "
        "de cobertura de vacinação ou acompanhamento "
        "de hipertensos na região sul do país "
        "no último consolidado do DATASUS?"
    )

    assert resultado["routes"] == ["agregada"]

    assert (
        resultado["entities"]["geografia"]["regiao"]
        == "Sul"
    )


def test_persona_mariana_3_recusa():
    resultado = router.analisar(
        "Como devo proceder clinicamente para ajustar "
        "a dieta e os exercícios de um paciente específico "
        "que está com picos pressóricos de 160/100?"
    )

    assert resultado["intent"] == "conduta_individualizada"
    assert resultado["routes"] == []
    assert resultado["requires_refusal"] is True


# ============================================================
# PERSONA 3 — FÁBIO
# ============================================================

def test_persona_fabio_1_estruturada():
    resultado = router.analisar(
        "Este medicamento para tratamento de dislipidemia "
        "está listado na RENAME na apresentação de 20mg "
        "ou apenas 10mg?"
    )

    assert resultado["routes"] == ["estruturada"]

    assert (
        "dislipidemia"
        in resultado["entities"]["doencas"]
    )


def test_persona_fabio_2_comparacao_pcdt():
    resultado = router.analisar(
        "O que mudou em termos de restrições de idade "
        "ou comorbidades entre a versão de 2022 "
        "e a versão de 2024 do PCDT de Asma Grave?"
    )

    assert resultado["routes"] == ["normativa"]

    assert "asma" in resultado["entities"]["doencas"]

    assert resultado["temporal_filters"]["anos"] == [
        2022,
        2024,
    ]

    assert (
        resultado["temporal_filters"]["comparacao"]
        is True
    )


def test_persona_fabio_3_agregada():
    resultado = router.analisar(
        "Qual o impacto orçamentário médio "
        "ou o volume total de internações "
        "por hipertensão arterial no estado "
        "do Rio de Janeiro segundo os dados "
        "abertos mais recentes?"
    )

    assert resultado["routes"] == ["agregada"]

    assert resultado["intent"] == "consulta_indicador"

    assert (
        "hipertensao_arterial_sistemica"
        in resultado["entities"]["doencas"]
    )

    assert resultado["entities"]["geografia"]["uf"] == "RJ"


# ============================================================
# CASO DE RISCO IDENTIFICADO NO PERSONAS.MD
# ============================================================

def test_pergunta_que_o_sistema_poderia_errar():
    resultado = router.analisar(
        "O protocolo de tratamento de Diabetes Tipo 2 "
        "atualizado em 2024 manteve a mesma diretriz "
        "de primeira linha da versão de 2022 "
        "para pacientes idosos com comorbidade renal?"
    )

    assert resultado["routes"] == ["normativa"]

    assert (
        "diabete_melito_tipo_2"
        in resultado["entities"]["doencas"]
    )

    assert resultado["temporal_filters"]["anos"] == [
        2022,
        2024,
    ]

    assert (
        resultado["temporal_filters"]["comparacao"]
        is True
    )


# ============================================================
# VALIDAÇÃO DE ENTRADA
# ============================================================

def test_query_vazia():
    with pytest.raises(ValueError):
        router.analisar("")


def test_query_apenas_espacos():
    with pytest.raises(ValueError):
        router.analisar("   ")


def test_query_tipo_invalido():
    with pytest.raises(TypeError):
        router.analisar(None)


# ============================================================
# TESTES DE BASE_ID E MANIFESTOS
# ============================================================

def test_base_normativa_encontrada():
    resultado = router.analisar(
        "Qual é o PCDT vigente de asma?"
    )

    assert resultado["routes"] == ["normativa"]

    assert (
        "protocolos_conitec"
        in resultado["retrieval_filters"]["base_id"]
    )


def test_base_rename_encontrada():
    resultado = router.analisar(
        "A losartana consta na RENAME?"
    )

    assert resultado["routes"] == ["estruturada"]

    assert (
        "rename_medicamentos"
        in resultado["retrieval_filters"]["base_id"]
    )


def test_consulta_historica_retrieval():
    resultado = router.analisar(
        "Qual era o protocolo antigo de asma?"
    )

    assert resultado["routes"] == ["normativa"]

    assert (
        resultado["temporal_filters"]["historico"]
        is True
    )

    assert (
        resultado["retrieval_filters"]["historico"]
        is True
    )

    assert (
        resultado["retrieval_filters"]["somente_vigente"]
        is False
    )


def test_base_id_dinamico(tmp_path):
    manifesto_teste = tmp_path / "manifesto_teste.yaml"

    manifesto_teste.write_text(
        """
bases:
  - base_id: qualquer_nome_de_pcdt
    natureza: normativa

doencas_disponiveis:
  - asma

medicamentos_disponiveis: []
""",
        encoding="utf-8",
    )

    router_teste = QueryRouter(
        manifest_path=str(manifesto_teste),
        extra_manifest_paths=[],
    )

    resultado = router_teste.analisar(
        "Qual é o PCDT vigente de asma?"
    )

    assert (
        resultado["retrieval_filters"]["base_id"]
        == ["qualquer_nome_de_pcdt"]
    )