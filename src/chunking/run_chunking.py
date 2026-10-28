import json
from pathlib import Path

import yaml

from src.chunking.process_md import process_md
from src.generate_json.generate_json import generate_json

VERSION_INVENTORY = "v8"
FILE_NAME = f"{VERSION_INVENTORY}.json"


def load_inventory(inventory_path: Path) -> dict:
    """Carrega o inventory da versão do corpus."""

    if not inventory_path.exists():
        raise FileNotFoundError(f"Inventory não encontrado: {inventory_path}")

    if not inventory_path.is_file():
        raise ValueError(f"O caminho informado não é um arquivo: {inventory_path}")

    try:
        with inventory_path.open("r", encoding="utf-8") as file:
            inventory = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido no inventory: {inventory_path}"
        ) from error

    if not isinstance(inventory, dict):
        raise ValueError("O inventory deve ser um objeto JSON.")

    if "arquivos" not in inventory:
        raise ValueError(
            "Inventory inválido: campo 'arquivos' não encontrado."
        )

    if not isinstance(inventory["arquivos"], list):
        raise ValueError(
            "Inventory inválido: 'arquivos' deve ser uma lista."
        )

    return inventory


def load_corpus_manifest(manifest_path: Path) -> dict:
    """Carrega o corpus_manifest.yaml."""

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Corpus manifest não encontrado: {manifest_path}"
        )

    if not manifest_path.is_file():
        raise ValueError(
            f"O caminho informado não é um arquivo: {manifest_path}"
        )

    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            manifest = yaml.safe_load(file)
    except yaml.YAMLError as error:
        raise ValueError(
            f"YAML inválido: {manifest_path}"
        ) from error

    if not isinstance(manifest, dict):
        raise ValueError(
            "O corpus_manifest.yaml deve conter um objeto."
        )

    return manifest


def get_manifest_file_name(document: dict) -> str | None:
    """
    Nome do arquivo de origem de um documento do manifest
    (arquivo_pdf, arquivo_origem ou acesso.caminho).
    """

    access = document.get("acesso") or {}

    if not isinstance(access, dict):
        access = {}

    relative = (
        document.get("arquivo_pdf")
        or document.get("arquivo_origem")
        or access.get("caminho")
        or access.get("caminho_origem")
    )

    if not relative:
        return None

    return Path(str(relative)).name


def build_manifest_index(manifest: dict) -> dict:
    """
    Cria um índice dos documentos do manifest pelo par
    (SHA-256, nome do arquivo).

    O SHA-256 sozinho não basta: o mesmo PDF pode entrar no corpus
    mais de uma vez (ex.: o PCDT de 2021 vale para artrite reumatoide
    e para artrite idiopática juvenil), e cada entrada tem a sua doença.

    Exemplo:

        {
            ("cf0edbd7...", "artrite_reumatoide__2021-09-10__revogado.pdf"): {
                "base_id": "protocolos_conitec",
                "doenca": "artrite_reumatoide",
                "status": "revogado",
                ...
            }
        }
    """

    documents = manifest.get("documentos", [])

    if not isinstance(documents, list):
        raise ValueError(
            "O campo 'documentos' do manifest deve ser uma lista."
        )

    index = {}

    for document in documents:
        sha256 = document.get("sha256")
        file_name = get_manifest_file_name(document)

        if sha256 and file_name:
            index[(sha256, file_name)] = document

    return index


def get_processed_markdown_path(
    raw_path: Path,
    root_dir: Path,
    corpus_version: str,
) -> Path:
    """
    Converte o caminho do arquivo original para o Markdown processado.

    Exemplo:

        data/raw/v3/bulas/advil/arquivo.pdf

    vira:

        data/processed/v3/bulas/advil/arquivo.md
    """

    raw_root = (
        root_dir
        / "data"
        / "raw"
        / corpus_version
    )

    processed_root = (
        root_dir
        / "data"
        / "processed"
        / corpus_version
    )

    try:
        relative_path = raw_path.relative_to(raw_root)
    except ValueError as error:
        raise ValueError(
            f"O arquivo do inventory está fora de "
            f"{raw_root}: {raw_path}"
        ) from error

    return processed_root / relative_path.with_suffix(".md")


def build_document_metadata(
    inventory_item: dict,
    manifest_document: dict | None,
    inventory: dict,
    manifest: dict,
) -> dict:
    """
    Junta os metadados do inventory com os metadados
    específicos do documento encontrados no manifest.
    """

    metadata = {
        # Identificação do corpus
        "corpus_version": inventory.get("version"),
        "manifest_version": manifest.get("version"),
        "manifest_hash": inventory.get("manifest_hash"),

        # Identificação da fonte
        "base_id": inventory_item.get("base_id"),
        "source_path": inventory_item.get("path"),
        "source_sha256": inventory_item.get("sha256"),
        "source_type": inventory_item.get("tipo"),
        "source_bytes": inventory_item.get("bytes"),
        "source_origin": inventory_item.get("origem"),
    }

    # ---------------------------------------------------------
    # Metadata específica do documento
    # ---------------------------------------------------------

    if manifest_document:
        fields = [
            "scenario_id",
            "description",
            "natureza",
            "fonte",
            "licenca",
            "sensitivity_default",
            "campo_vigencia",
            "doenca",
            "versao_portaria",
            "status",
            "data_inicio",
            "data_fim",
            "confirmacao",
            "observacao",
            "tipo_documento",
            # Bulas (corpus_manifest_bulas.yaml)
            "medicamento",
            "principio_ativo",
            "nome_produto",
            "tipo_bula",
            "numero_registro",
            "data_documento",
            "data_atualizacao",
            # RENAME (corpus_manifest_rename.yaml)
            "versao_edicao",
        ]

        for field in fields:
            if field in manifest_document:
                metadata[field] = manifest_document[field]

    # ---------------------------------------------------------
    # Campos obrigatórios do contrato do chunk (enunciado, 2.5):
    # source_file, doc_type, chunk_id, sensitivity e base_id.
    # "sensitivity_default" e "file_name" continuam existindo.
    # ---------------------------------------------------------

    source_path = inventory_item.get("path")
    metadata["source_file"] = (
        Path(str(source_path)).name if source_path else None
    )
    metadata["sensitivity"] = metadata.get("sensitivity_default")

    return metadata


def get_doc_type(
    manifest_document: dict | None,
    markdown_path: Path,
) -> str:
    """
    Tipo do documento (protocolo, bula, rename, agregado), vindo do
    campo "tipo_documento" do manifest. Sem manifest, usa o nome da
    pasta do Markdown (comportamento anterior).
    """

    return (
        (manifest_document or {}).get("tipo_documento")
        or markdown_path.parent.name
    )


def run_chunking():
    """Executa o chunking do corpus congelado."""

    # DIRETÓRIOS
    root_dir = Path(__file__).resolve().parent.parent.parent

    inventory_path = (
        root_dir
        / "data"
        / "inventory"
        / FILE_NAME
    )

    manifest_path = (
        root_dir
        / "corpus_manifest.yaml"
    )

    corpus_version = VERSION_INVENTORY

    processed_folder = (
        root_dir
        / "data"
        / "processed"
        / corpus_version
    )

    output_folder = (
        root_dir
        / "output"
        / "output_chunking"
        / corpus_version
    )

    # CABEÇALHO
    print("\n" + "=" * 70)
    print("PROCESSAMENTO DE CHUNKING")
    print("=" * 70)

    print(f"\nCorpus: {corpus_version}")
    print(f"Inventory: {inventory_path}")
    print(f"Markdowns: {processed_folder}")
    print(f"Output: {output_folder}")

    # CARREGA INVENTORY
    print("\nCarregando inventory...")

    inventory = load_inventory(inventory_path)
    inventory_files = inventory["arquivos"]

    print(
        f"Arquivos declarados no inventory: "
        f"{len(inventory_files)}"
    )


    # CARREGA MANIFEST
    print("\nCarregando corpus manifest...")

    manifest = load_corpus_manifest(manifest_path)

    manifest_index = build_manifest_index(manifest)

    print(
        f"Documentos no corpus manifest: "
        f"{len(manifest_index)}"
    )

    # VALIDA PASTA DE MARKDOWN
    if not processed_folder.exists():
        raise FileNotFoundError(
            f"Pasta de Markdown não encontrada: "
            f"{processed_folder}"
        )

    # RESULTADOS
    resultados = []

    total = len(inventory_files)

    processed_count = 0
    missing_markdown_count = 0
    failed_count = 0
    manifest_missing_count = 0

    # PROCESSAMENTO
    for index, inventory_item in enumerate(
        inventory_files,
        start=1,
    ):

        print("\n" + "-" * 70)
        print(f"[{index}/{total}]")

        # STATUS DO INVENTORY
        inventory_status = inventory_item.get("status")

        if inventory_status != "ok":
            print(
                f"Ignorando documento com status: "
                f"{inventory_status}"
            )
            continue


        # DADOS DO INVENTORY
        relative_raw_path = Path(inventory_item["path"])

        raw_path = root_dir / relative_raw_path

        base_id = inventory_item.get("base_id")
        sha256 = inventory_item.get("sha256")

        print(f"Arquivo: {raw_path.name}")
        print(f"Base: {base_id}")
        print(f"SHA256: {sha256}")

        # ENCONTRA MARKDOWN
        markdown_path = get_processed_markdown_path(
            raw_path=raw_path,
            root_dir=root_dir,
            corpus_version=corpus_version,
        )

        print(f"Markdown: {markdown_path}")

        if not markdown_path.exists():
            print("AVISO: Markdown correspondente não encontrado.")

            missing_markdown_count += 1
            continue

        if not markdown_path.is_file():
            print("AVISO: Caminho do Markdown não é um arquivo.")

            missing_markdown_count += 1
            continue


        # METADATA DO MANIFEST
        manifest_document = manifest_index.get(
            (sha256, raw_path.name)
        )

        if manifest_document:
            print("Metadata do manifest: encontrada")
        else:
            print("Metadata do manifest: não encontrada")

            manifest_missing_count += 1

        document_metadata = build_document_metadata(
            inventory_item=inventory_item,
            manifest_document=manifest_document,
            inventory=inventory,
            manifest=manifest,
        )

        # DOC TYPE
        doc_type = get_doc_type(manifest_document, markdown_path)

        # CHUNKING
        try:
            chunks = process_md(
                markdown_path,
                doc_type,
                folder_metadata=document_metadata,
            )

            documento = {
                "corpus_version": inventory.get("version"),
                "manifest_version": manifest.get("version"),
                "manifest_hash": inventory.get("manifest_hash"),

                "source_file": raw_path.name,
                "source_path": inventory_item["path"],
                "source_sha256": sha256,

                "base_id": base_id,

                "doc_type": doc_type,
                "doc_extension": markdown_path.suffix.lower(),

                "metadata": document_metadata,

                "resultado": chunks,
            }

            resultados.append(documento)

            # -------------------------------------------------
            # OUTPUT
            # -------------------------------------------------

            relative_markdown_path = markdown_path.relative_to(
                processed_folder
            )

            output_subfolder = (
                output_folder
                / relative_markdown_path.parent
            )

            output_subfolder.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_path = (
                output_subfolder
                / f"{markdown_path.stem}.json"
            )

            generate_json(
                documento,
                output_path,
            )

            processed_count += 1

            print(
                f"OK - {len(chunks)} chunks gerados"
            )

            print(
                f"Output: {output_path}"
            )

        except Exception as error:
            failed_count += 1

            print(
                f"ERRO ao processar "
                f"{markdown_path.name}: {error}"
            )

    # ---------------------------------------------------------
    # RESUMO
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESUMO DO CHUNKING")
    print("=" * 70)

    print(f"Corpus: {corpus_version}")
    print(f"Arquivos no inventory: {total}")
    print(f"Processados: {processed_count}")
    print(f"Markdowns ausentes: {missing_markdown_count}")
    print(f"Sem metadata no manifest: {manifest_missing_count}")
    print(f"Falhas: {failed_count}")

    print(f"\nOutput:")
    print(output_folder)

    print("=" * 70)

    return resultados


if __name__ == "__main__":
    result = run_chunking()

    print(
        f"\nProcessamento concluído: "
        f"{len(result)} documentos."
    )
