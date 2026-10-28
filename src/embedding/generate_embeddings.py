import json
from pathlib import Path

from src.llm.llm_embedding import get_embeddings_batch, BATCH_SIZE


def _save_json_atomic(path: Path, data: dict) -> None:
    """Grava em arquivo temporário e substitui o original, evitando corromper o JSON se algo falhar."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    tmp_path.replace(path)


def generate_embeddings_for_folder(
        input_dir: Path,
        batch_size: int = BATCH_SIZE,
        skip_existing: bool = True,
):
    if not input_dir.exists():
        raise FileNotFoundError(f"A pasta informada não foi encontrada: {input_dir}")

    # Encontra todos os arquivos JSON recursivamente (pasta e subpastas)
    json_files = list(input_dir.rglob("*.json"))
    print(f"Total de arquivos JSON encontrados: {len(json_files)}")

    for json_path in json_files:
        print(f"\nProcessando arquivo: {json_path.relative_to(input_dir)}")

        try:
            # Lê o JSON original
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Valida se a chave "resultado" existe e é uma lista
            if "resultado" not in data or not isinstance(data["resultado"], list):
                print("  -> Aviso: Chave 'resultado' não encontrada ou vazia. Pulando.")
                continue

            resultado_items = data["resultado"]

            # Guarda os itens que têm texto (referência direta ao item, sem depender de índice)
            items_com_texto = [
                item for item in resultado_items
                if isinstance(item.get("texto"), str) and item["texto"].strip()
            ]

            if not items_com_texto:
                print("  -> Aviso: Nenhum texto encontrado nos itens do resultado.")
                continue

            # Permite retomar: ignora itens que já possuem embedding
            if skip_existing:
                items_pendentes = [item for item in items_com_texto if not item.get("embedding")]
            else:
                items_pendentes = items_com_texto

            if not items_pendentes:
                print("  -> Todos os chunks já possuem embedding. Pulando.")
                continue

            textos = [item["texto"] for item in items_pendentes]
            print(f"  -> Solicitando embeddings para {len(textos)} chunks via ECOA...")

            # A função já divide em batches e faz retry internamente
            embeddings = get_embeddings_batch(textos, batch_size=batch_size)

            # Cada embedding volta na mesma ordem dos textos enviados
            for item, embedding in zip(items_pendentes, embeddings):
                item["embedding"] = embedding

            # Salva o arquivo JSON atualizado (escrita atômica)
            _save_json_atomic(json_path, data)

            print(f"  -> Sucesso! Embeddings adicionados em {json_path.name}")

        except Exception as error:
            print(f"  -> Erro ao processar o arquivo {json_path.name}: {error}")
