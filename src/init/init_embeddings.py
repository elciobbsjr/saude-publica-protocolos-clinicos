from pathlib import Path

from src.embedding.generate_embeddings import generate_embeddings_for_folder


def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    input_folder = root_dir / "output" / "output_chunking"

    print("=" * 60)
    print("INICIANDO GERAÇÃO DE EMBEDDINGS")
    print("=" * 60)

    generate_embeddings_for_folder(input_folder)

    print("\n" + "=" * 60)
    print("EMBEDDINGS FINALIZADOS")
    print("=" * 60)


if __name__ == "__main__":
    main()