from pathlib import Path

from src.chunking.run_chunking import run_chunking
from src.embedding.generate_embeddings import generate_embeddings_for_folder

# dados → chunking → JSON com chunks → embeddings → JSON final

def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    embeddings_folder = root_dir / "output" / "output_chunking"

    try:
        print("\n" + "=" * 60)
        print("ETAPA 1/2 - CHUNKING")
        print("=" * 60)

        resultados = run_chunking()

        print(f"\nChunking finalizado.")
        print(f"Arquivos processados: {len(resultados)}")

        print("\n" + "=" * 60)
        print("ETAPA 2/2 - EMBEDDINGS")
        print("=" * 60)

        generate_embeddings_for_folder(embeddings_folder)

        print("\n" + "=" * 60)
        print("PIPELINE FINALIZADO COM SUCESSO!")
        print("=" * 60)

    except Exception as error:
        print("\n" + "=" * 60)
        print("PIPELINE INTERROMPIDO")
        print("=" * 60)
        print(f"Erro: {error}")


if __name__ == "__main__":
    main()