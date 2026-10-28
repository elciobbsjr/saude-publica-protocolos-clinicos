"""
Módulo de Carregamento do Corpus para o Retrieval.

Responsável por localizar e carregar todos os chunks
gerados pelo pipeline de chunking + embedding do projeto
(output/output_chunking/**/*.json), retornando uma lista
unificada de chunks no formato padrão.

Também oferece suporte a filtro por base_id via argumento,
mas o filtro de metadados fino fica no módulo filtros.py.
"""

import json
from pathlib import Path
from typing import Any


# Pasta padrão de saída do run_chunking.py + generate_embeddings.py
PASTA_OUTPUT_PADRAO = Path("output") / "output_chunking"


def carregar_chunks_de_arquivo(
    caminho_json: Path,
) -> list[dict[str, Any]]:
    """
    Carrega os chunks de um único arquivo JSON de chunking.

    O formato esperado é o gerado pelo run_chunking.py:
        {
            "base_id": "...",
            "resultado": [
                {
                    "texto":     "...",
                    "section":   "...",
                    "embedding": [...],   # adicionado pelo generate_embeddings.py
                    "metadata":  { ... }
                },
                ...
            ]
        }

    Args:
        caminho_json: Caminho para o arquivo .json.

    Returns:
        Lista de chunks prontos para indexação.
    """
    with caminho_json.open("r", encoding="utf-8") as f:
        dados = json.load(f)

    resultado = dados.get("resultado", [])
    base_id = dados.get("base_id", "")

    chunks = []

    for item in resultado:
        if not item.get("texto"):
            continue

        # Garante que base_id do documento raiz
        # fique disponível em cada chunk
        if "metadata" not in item:
            item["metadata"] = {}

        if not item["metadata"].get("base_id"):
            item["metadata"]["base_id"] = base_id

        chunks.append(item)

    return chunks


def carregar_todos_os_chunks(
    pasta_output: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Varre recursivamente a pasta de output de chunking e
    carrega todos os chunks de todos os arquivos JSON.

    Args:
        pasta_output: Caminho da pasta de output.
                      Se None, usa o padrão do projeto.

    Returns:
        Lista unificada de todos os chunks do corpus.

    Raises:
        FileNotFoundError: Se a pasta não existir.
    """
    if pasta_output is None:
        raiz = Path(__file__).resolve().parent.parent.parent
        pasta_output = raiz / PASTA_OUTPUT_PADRAO

    if not pasta_output.exists():
        raise FileNotFoundError(
            f"Pasta de output de chunking não encontrada: "
            f"{pasta_output}\n"
            f"Execute run_chunking.py e generate_embeddings.py "
            f"antes de usar o retrieval."
        )

    arquivos_json = list(pasta_output.rglob("*.json"))

    if not arquivos_json:
        raise FileNotFoundError(
            f"Nenhum arquivo JSON encontrado em: {pasta_output}"
        )

    todos_os_chunks: list[dict[str, Any]] = []

    for caminho in arquivos_json:
        try:
            chunks = carregar_chunks_de_arquivo(caminho)
            todos_os_chunks.extend(chunks)
        except Exception as erro:
            print(
                f"  [corpus_loader] Aviso: erro ao ler "
                f"{caminho.name}: {erro}"
            )

    return todos_os_chunks
