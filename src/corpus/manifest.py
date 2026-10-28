import yaml
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest não encontrado: {manifest_path}" )

    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = yaml.safe_load(file)

    if not isinstance(manifest, dict):
        raise ValueError("Manifest inválido.")

    return manifest


def build_document_index(manifest: dict) -> dict:
    documents = manifest.get("documentos", [])

    return {
        document["sha256"]: document
        for document in documents
        if document.get("sha256")
    }

manifest = load_manifest(
    ROOT_DIR / "corpus_manifest.yaml"
)

manifest_index = build_document_index(manifest)