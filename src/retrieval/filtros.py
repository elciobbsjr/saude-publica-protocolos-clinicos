"""
Módulo de Filtros de Metadados.

Aplica os filtros gerados pelo QueryRouter (query_router.py do Elcio)
sobre uma lista de chunks antes de enviá-los aos índices de busca.

Filtros suportados:
    - base_id       → natureza/base do corpus (normativa, estruturada…)
    - doenca        → doença mencionada na query
    - medicamento   → medicamento mencionado na query
    - somente_vigente → se True, descarta documentos com status != "vigente"
    - historico     → se True, mantém somente documentos revogados
    - anos          → filtra por data_inicio/data_fim do documento
    - regiao        → filtro geográfico opcional (quando disponível)
    - uf            → filtro de UF opcional (quando disponível)
"""

from datetime import date
from typing import Any


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def _obter_meta(chunk: dict[str, Any], campo: str) -> Any:
    """Acessa um campo de metadata do chunk com segurança."""
    return chunk.get("metadata", {}).get(campo)


def _normalizar(texto: str) -> str:
    """Lowercase simples para comparações."""
    return texto.strip().lower()


# ------------------------------------------------------------------
# FILTROS INDIVIDUAIS
# ------------------------------------------------------------------

def _filtrar_base_id(
    chunks: list[dict[str, Any]],
    base_ids: list[str],
) -> list[dict[str, Any]]:
    """
    Mantém apenas chunks cujo base_id esteja na lista informada.
    Se a lista estiver vazia, não filtra.
    """
    if not base_ids:
        return chunks

    ids_normalizados = {_normalizar(b) for b in base_ids}

    return [
        c
        for c in chunks
        if _normalizar(str(_obter_meta(c, "base_id") or ""))
        in ids_normalizados
    ]


def _filtrar_doenca(
    chunks: list[dict[str, Any]],
    doencas: list[str],
) -> list[dict[str, Any]]:
    """
    Mantém chunks cujo campo "doenca" no metadata bata
    com pelo menos uma das doenças extraídas pela query.
    Se a lista estiver vazia, não filtra.
    """
    if not doencas:
        return chunks

    doencas_norm = {_normalizar(d) for d in doencas}

    return [
        c
        for c in chunks
        if _normalizar(str(_obter_meta(c, "doenca") or ""))
        in doencas_norm
    ]


def _filtrar_vigencia(
    chunks: list[dict[str, Any]],
    somente_vigente: bool,
    historico: bool,
) -> list[dict[str, Any]]:
    """
    Aplica filtro de vigência com base no campo "status" do metadata.

    - somente_vigente=True → mantém status == "vigente" e chunks
                             sem status (bulas, SIH)
    - historico=True       → mantém apenas status != "vigente"
                             (revogado, histórico, etc.)
    - ambos False          → não filtra
    """
    if not somente_vigente and not historico:
        return chunks

    resultado = []

    for chunk in chunks:
        status = _normalizar(
            str(_obter_meta(chunk, "status") or "")
        )

        # Documentos sem versionamento (bulas, SIH) não têm
        # "status" e não podem ser descartados pelo filtro.
        if somente_vigente and status in ("vigente", ""):
            resultado.append(chunk)
        elif historico and status != "vigente":
            resultado.append(chunk)

    return resultado


def _filtrar_anos(
    chunks: list[dict[str, Any]],
    anos: list[int],
) -> list[dict[str, Any]]:
    """
    Mantém chunks cujo intervalo [data_inicio, data_fim] cubra
    pelo menos um dos anos informados.

    Se a lista de anos estiver vazia, não filtra.
    data_fim=None significa documento ainda vigente (sem fim).
    """
    if not anos:
        return chunks

    resultado = []

    for chunk in chunks:
        inicio_raw = _obter_meta(chunk, "data_inicio")
        fim_raw = _obter_meta(chunk, "data_fim")

        try:
            inicio = (
                date.fromisoformat(str(inicio_raw))
                if inicio_raw
                else None
            )
        except ValueError:
            inicio = None

        try:
            fim = (
                date.fromisoformat(str(fim_raw))
                if fim_raw
                else None
            )
        except ValueError:
            fim = None

        for ano in anos:
            ano_inicio = date(ano, 1, 1)
            ano_fim = date(ano, 12, 31)

            # O documento cobre o ano se:
            # - início do doc ≤ fim do ano  AND
            # - fim do doc ≥ início do ano  (ou doc sem fim)
            inicio_ok = inicio is None or inicio <= ano_fim
            fim_ok = fim is None or fim >= ano_inicio

            if inicio_ok and fim_ok:
                resultado.append(chunk)
                break

    return resultado


# ------------------------------------------------------------------
# PONTO DE ENTRADA PRINCIPAL
# ------------------------------------------------------------------

def aplicar_filtros(
    chunks: list[dict[str, Any]],
    filtros: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Aplica todos os filtros de metadados sobre os chunks.

    O dicionário `filtros` deve seguir o contrato do QueryRouter:
        {
            "base_id":        list[str],
            "doenca":         list[str],
            "medicamento":    list[str],
            "anos":           list[int],
            "somente_vigente": bool,
            "comparar_versoes": bool,
            "historico":      bool,
            "regiao":         str | None,
            "uf":             str | None,
        }

    Args:
        chunks:  Lista completa de chunks carregados do corpus.
        filtros: Dicionário gerado por QueryRouter.analisar().

    Returns:
        Lista de chunks que passaram em todos os filtros.
    """
    resultado = list(chunks)

    # 1. Filtro por base/natureza
    resultado = _filtrar_base_id(
        resultado,
        filtros.get("base_id", []),
    )

    # 2. Filtro por doença
    resultado = _filtrar_doenca(
        resultado,
        filtros.get("doenca", []),
    )

    # 3. Filtro de vigência
    resultado = _filtrar_vigencia(
        resultado,
        somente_vigente=filtros.get("somente_vigente", False),
        historico=filtros.get("historico", False),
    )

    # 4. Filtro por anos
    resultado = _filtrar_anos(
        resultado,
        filtros.get("anos", []),
    )

    # Nota: filtros de "regiao" e "uf" ficam disponíveis nos
    # metadados do chunk para uso futuro (base SIH já inclui UF).
    # Não são aplicados aqui por enquanto pois dependem de campos
    # ainda em definição pela equipe de ingestão (Paula + Silvio).

    return resultado
