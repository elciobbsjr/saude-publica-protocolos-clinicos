import json
from pathlib import Path


def load_inventory(inventory_path: Path) -> dict:
    if not inventory_path.exists():
        raise FileNotFoundError(f"Inventory não encontrado: {inventory_path}")

    if not inventory_path.is_file():
        raise ValueError(f"O caminho informado não é um arquivo: {inventory_path}")

    with inventory_path.open("r", encoding="utf-8") as file:
        inventory = json.load(file)

    if not isinstance(inventory, dict):
        raise ValueError("O inventory deve ser um objeto JSON.")

    if "arquivos" not in inventory:
        raise ValueError("Inventory inválido: campo 'arquivos' não encontrado.")

    if not isinstance(inventory["arquivos"], list):
        raise ValueError("Inventory inválido: 'arquivos' deve ser uma lista.")

    return inventory


def get_documents_from_inventory(
    inventory: dict,
    root_dir: Path,
) -> list[dict]:

    documents = []

    for item in inventory["arquivos"]:
        if item.get("status") != "ok":
            continue

        relative_path = Path(item["path"])
        file_path = root_dir / relative_path

        documents.append({
            "path": file_path,
            "relative_path": relative_path,
            "base_id": item["base_id"],
            "tipo": item["tipo"],
            "sha256": item["sha256"],
            "bytes": item["bytes"],
            "origem": item.get("origem"),
            "coletado_em": item.get("coletado_em"),
        })

    return documents