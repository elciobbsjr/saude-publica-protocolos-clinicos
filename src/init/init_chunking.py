from src.chunking.run_chunking import run_chunking


def main():
    print("=" * 60)
    print("INICIANDO CHUNKING")
    print("=" * 60)

    resultados = run_chunking()

    print("\n" + "=" * 60)
    print("CHUNKING FINALIZADO")
    print("=" * 60)
    print(f"Total de arquivos processados: {len(resultados)}")


if __name__ == "__main__":
    main()