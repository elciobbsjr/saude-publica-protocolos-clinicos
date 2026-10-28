"""
Teste de contrato do chunking (enunciado, seção 2.5).

Confere que todo chunk sai com os metadados obrigatórios e que o
chunk_id é determinístico e único. Roda offline, sem LLM, usando os
Markdowns pequenos de tests/fixtures/chunking/.
"""

from pathlib import Path

from src.chunking.process_md import process_md
from src.chunking.run_chunking import (
    build_document_metadata,
    build_manifest_index,
    get_doc_type,
)

FIXTURES = Path(__file__).parent / "fixtures" / "chunking"

OBRIGATORIOS = {"source_file", "doc_type", "chunk_id", "sensitivity", "base_id"}

INVENTORY = {"version": "v5", "manifest_hash": "sha256:teste"}
MANIFEST = {"version": "2026-10-07"}

# O mesmo PDF entra duas vezes no corpus (como o PCDT de 2021, que vale
# para artrite reumatoide e artrite idiopática juvenil).
SHA_COMPARTILHADO = "cf0edbd7" + "0" * 56

DOCUMENTOS = [
    {
        "markdown": "bula_exemplo.md",
        "inventory_item": {
            "path": "data/raw/v5/bulas/glifage/100890193_paciente.pdf",
            "base_id": "bulas_anvisa",
            "tipo": "pdf",
            "sha256": "8" * 64,
            "status": "ok",
        },
        "manifest_document": {
            "base_id": "bulas_anvisa",
            "tipo_documento": "bula",
            "sensitivity_default": "publico",
            "medicamento": "glifage",
            "principio_ativo": "cloridrato_de_metformina",
            "arquivo_pdf": "BULAS_dir/glifage/100890193_paciente.pdf",
            "sha256": "8" * 64,
        },
    },
    {
        "markdown": "protocolo_exemplo.md",
        "inventory_item": {
            "path": "data/raw/v5/protocolos/artrite_reumatoide/artrite_reumatoide__2021-09-10__revogado.pdf",
            "base_id": "protocolos_conitec",
            "tipo": "pdf",
            "sha256": SHA_COMPARTILHADO,
            "status": "ok",
        },
        "manifest_document": {
            "base_id": "protocolos_conitec",
            "tipo_documento": "protocolo",
            "sensitivity_default": "publico",
            "doenca": "artrite_reumatoide",
            "arquivo_pdf": "PROTO_dir/artrite_reumatoide/artrite_reumatoide__2021-09-10__revogado.pdf",
            "sha256": SHA_COMPARTILHADO,
        },
    },
    {
        "markdown": "protocolo_exemplo.md",
        "inventory_item": {
            "path": "data/raw/v5/protocolos/artrite_idiopatica_juvenil/artrite_idiopatica_juvenil__2021-09-10__revogado.pdf",
            "base_id": "protocolos_conitec",
            "tipo": "pdf",
            "sha256": SHA_COMPARTILHADO,
            "status": "ok",
        },
        "manifest_document": {
            "base_id": "protocolos_conitec",
            "tipo_documento": "protocolo",
            "sensitivity_default": "publico",
            "doenca": "artrite_idiopatica_juvenil",
            "arquivo_pdf": "PROTO_dir/artrite_idiopatica_juvenil/artrite_idiopatica_juvenil__2021-09-10__revogado.pdf",
            "sha256": SHA_COMPARTILHADO,
        },
    },
]


def gerar_chunks(documento: dict) -> list[dict]:
    """Reproduz o caminho do run_chunking para um documento."""
    manifest_index = build_manifest_index(
        {"documentos": [d["manifest_document"] for d in DOCUMENTOS]}
    )
    item = documento["inventory_item"]
    raw_name = Path(item["path"]).name
    manifest_document = manifest_index.get((item["sha256"], raw_name))

    metadata = build_document_metadata(
        inventory_item=item,
        manifest_document=manifest_document,
        inventory=INVENTORY,
        manifest=MANIFEST,
    )
    markdown_path = FIXTURES / documento["markdown"]
    doc_type = get_doc_type(manifest_document, markdown_path)

    return process_md(markdown_path, doc_type, folder_metadata=metadata)


def todos_os_chunks() -> list[dict]:
    chunks = []
    for documento in DOCUMENTOS:
        chunks.extend(gerar_chunks(documento))
    return chunks


def test_todo_chunk_tem_metadado_obrigatorio():
    chunks = todos_os_chunks()
    assert chunks, "Nenhum chunk gerado a partir das fixtures."

    for chunk in chunks:
        metadata = chunk["metadata"]
        faltando = {
            campo for campo in OBRIGATORIOS if not metadata.get(campo)
        }
        assert not faltando, f"{metadata.get('chunk_id')} sem: {faltando}"


def test_doc_type_vem_do_manifesto():
    chunks = gerar_chunks(DOCUMENTOS[0])
    assert {c["metadata"]["doc_type"] for c in chunks} == {"bula"}


def test_source_file_e_sensitivity():
    metadata = gerar_chunks(DOCUMENTOS[0])[0]["metadata"]
    assert metadata["source_file"] == "100890193_paciente.pdf"
    assert metadata["sensitivity"] == "publico"


def test_chunk_id_deterministico_e_unico():
    primeira = [c["metadata"]["chunk_id"] for c in todos_os_chunks()]
    segunda = [c["metadata"]["chunk_id"] for c in todos_os_chunks()]

    assert primeira == segunda
    assert len(primeira) == len(set(primeira))


def test_mesmo_pdf_em_duas_doencas_mantem_cada_doenca():
    reumatoide = gerar_chunks(DOCUMENTOS[1])[0]["metadata"]
    juvenil = gerar_chunks(DOCUMENTOS[2])[0]["metadata"]

    assert reumatoide["doenca"] == "artrite_reumatoide"
    assert juvenil["doenca"] == "artrite_idiopatica_juvenil"
    assert reumatoide["chunk_id"] != juvenil["chunk_id"]
