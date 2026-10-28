from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
import re
from pathlib import Path
from typing import Any

import yaml


GENERATED_MANIFEST_FILENAME = "corpus_manifest_bulas.yaml"
METADATA_FILENAME = "metadata.json"

# Campo de vigência das bulas: data do documento publicado no Bulário
# Eletrônico da ANVISA (campo "data" do metadata.json).
CAMPO_VIGENCIA_BULAS = "data_documento"

# Princípio ativo de cada medicamento, pelo slug do nome do produto.
# Fonte: seção COMPOSIÇÃO de cada bula (conferida nos PDFs da BULAS_dir).
# Quando o src/query_router.py já tem um identificador para o princípio
# ativo (ex.: "metformina" -> "cloridrato_de_metformina"), usa-se o mesmo,
# para que um filtro por princípio ativo encontre a bula genérica e a de marca.
# Bulas do mesmo princípio ativo recebem sempre o mesmo valor
# (ex.: Amoxil declara "amoxicilina" e Novocilin "amoxicilina tri-hidratada,
# equivalente a amoxicilina": ambas ficam como "amoxicilina").
PRINCIPIO_ATIVO_POR_MEDICAMENTO = {
    "advil": "ibuprofeno",
    "aerolin": "sulfato_de_salbutamol",
    "amoxil": "amoxicilina",
    "amytril": "cloridrato_de_amitriptilina",
    "aspirina": "acido_acetilsalicilico",
    "budesonida": "budesonida",
    "captosen": "captopril",
    "clorana": "hidroclorotiazida",
    "cloridrato_de_metformina": "cloridrato_de_metformina",
    "corus": "losartana_potassica",
    "cozaar": "losartana_potassica",
    "dolutegravir_sodico": "dolutegravir_sodico",
    "entecavir": "entecavir",
    "fumarato_de_tenofovir_desoproxila": "fumarato_de_tenofovir_desoproxila",
    "glifage": "cloridrato_de_metformina",
    "glifage_xr": "cloridrato_de_metformina",
    "hidroclorotiazida": "hidroclorotiazida",
    "humulin_n": "insulina_humana_isofana",
    "losartana_potassica": "losartana_potassica",
    "maleato_de_enalapril": "maleato_de_enalapril",
    "metotrexato": "metotrexato",
    "novalgina": "dipirona_monoidratada",
    "novocilin": "amoxicilina",
    "pratiprazol": "omeprazol",
    "puran_t4": "levotiroxina_sodica",
    "renitec": "maleato_de_enalapril",
    "sinvastacor": "sinvastatina",
    "sinvastatina": "sinvastatina",
    "sofosbuvir": "sofosbuvir",
    "sulfato_de_salbutamol": "sulfato_de_salbutamol",
    "tylenol": "paracetamol",
}


def get_principio_ativo(medicamento_slug: str) -> str:
    principio_ativo = PRINCIPIO_ATIVO_POR_MEDICAMENTO.get(medicamento_slug)

    if not principio_ativo:
        raise ValueError(
            f"Princípio ativo não mapeado para o medicamento '{medicamento_slug}'. "
            "Inclua-o em PRINCIPIO_ATIVO_POR_MEDICAMENTO."
        )

    return principio_ativo


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text)
    return ascii_text.strip("_").lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(5) == b"%PDF-"
    except OSError:
        return False


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"JSON inválido: {path}")

    return data


def infer_tipo_bula(pdf_path: Path) -> str | None:
    nome = pdf_path.stem.lower()

    if nome.endswith("_paciente"):
        return "paciente"

    if nome.endswith("_profissional"):
        return "profissional"

    return None


def build_document(
    bulas_root: Path,
    medication_dir: Path,
    pdf_path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    tipo_bula = infer_tipo_bula(pdf_path)
    if not tipo_bula:
        raise ValueError(
            f"Não foi possível identificar o tipo da bula pelo nome: {pdf_path.name}"
        )

    relative_pdf = pdf_path.relative_to(bulas_root.parent).as_posix()
    medicamento = slugify(str(metadata.get("nomeProduto") or medication_dir.name))

    return {
        "scenario_id": "bulas-medicamentos-anvisa",
        "manifest_version": time.strftime("%Y-%m-%d", time.localtime()),
        "description": "Bulas de medicamentos previamente baixadas do Bulário Eletrônico da ANVISA",
        "base_id": "bulas_anvisa",
        "tipo_documento": "bula",
        "natureza": "estruturada",
        "fonte": "ANVISA - Bulário Eletrônico",
        "acesso": {
            "tipo": "local_pdf",
            "caminho": relative_pdf,
        },
        "selecao_deterministica": True,
        "formato": "pdf",
        "sensitivity_default": "publico",
        "campo_vigencia": CAMPO_VIGENCIA_BULAS,
        "chunking_sugerido": "Split por seção da bula, com overlap",

        # Identificação do medicamento/bula
        "medicamento": medicamento,
        "principio_ativo": get_principio_ativo(medicamento),
        "nome_produto": metadata.get("nomeProduto"),
        "tipo_bula": tipo_bula,
        "numero_registro": str(metadata.get("numeroRegistro") or ""),

        # Metadados vindos do metadata.json gerado pelo fetch_bula
        "id_produto": metadata.get("idProduto"),
        "expediente": metadata.get("expediente"),
        "razao_social": metadata.get("razaoSocial"),
        "cnpj": metadata.get("cnpj"),
        "numero_transacao": metadata.get("numeroTransacao"),
        "data_documento": metadata.get("data"),
        "numero_processo": metadata.get("numProcesso"),
        "data_atualizacao": metadata.get("dataAtualizacao"),

        # Arquivo local
        "arquivo_pdf": relative_pdf,
        "sha256": sha256_file(pdf_path),
        "tamanho_bytes": pdf_path.stat().st_size,
        "content_type": "application/pdf",
    }


def generate_manifest(
    bulas_dir: Path,
    output_path: Path,
) -> int:
    bulas_dir = bulas_dir.resolve()

    if not bulas_dir.exists():
        print(f"[ERRO] Diretório de bulas não encontrado: {bulas_dir}")
        return 2

    if not bulas_dir.is_dir():
        print(f"[ERRO] O caminho informado não é um diretório: {bulas_dir}")
        return 2

    metadata_files = sorted(bulas_dir.rglob(METADATA_FILENAME))

    if not metadata_files:
        print(
            "[ERRO] Nenhum metadata.json encontrado em "
            f"{bulas_dir}"
        )
        return 3

    documents: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    medications: list[str] = []

    print("=" * 70)
    print("GERAR CORPUS MANIFEST - BULAS")
    print("=" * 70)
    print(f"Diretório : {bulas_dir}")
    print(f"Metadados : {len(metadata_files)} arquivo(s)")
    print()

    for metadata_path in metadata_files:
        medication_dir = metadata_path.parent

        try:
            metadata = load_json(metadata_path)
        except Exception as exc:
            failures.append({
                "pasta": medication_dir.name,
                "metadata": str(metadata_path),
                "erro": str(exc),
            })
            print(f"[ERRO] {medication_dir.name}: {exc}")
            continue

        nome_produto = str(metadata.get("nomeProduto") or medication_dir.name)
        medicamento_slug = slugify(nome_produto)

        if medicamento_slug not in medications:
            medications.append(medicamento_slug)

        pdf_files = sorted(medication_dir.glob("*.pdf"))

        if not pdf_files:
            failures.append({
                "medicamento": medicamento_slug,
                "metadata": str(metadata_path),
                "erro": "Nenhum PDF encontrado na pasta do medicamento.",
            })
            print(f"[AVISO] {nome_produto}: nenhum PDF encontrado.")
            continue

        print(f"{nome_produto}:")

        for pdf_path in pdf_files:
            try:
                if not is_pdf(pdf_path):
                    raise ValueError("Arquivo não possui assinatura válida de PDF.")

                tipo_bula = infer_tipo_bula(pdf_path)
                if not tipo_bula:
                    raise ValueError(
                        "Nome do PDF não termina em _paciente.pdf "
                        "nem _profissional.pdf."
                    )

                numero_registro = str(metadata.get("numeroRegistro") or "")
                if numero_registro and not pdf_path.name.startswith(numero_registro):
                    print(
                        f"  [AVISO] {pdf_path.name}: número de registro do nome "
                        f"difere do metadata.json ({numero_registro})."
                    )

                document = build_document(
                    bulas_root=bulas_dir,
                    medication_dir=medication_dir,
                    pdf_path=pdf_path,
                    metadata=metadata,
                )

                documents.append(document)

                print(
                    f"  [OK] {tipo_bula:<12} "
                    f"{pdf_path.name} "
                    f"({document['tamanho_bytes']} bytes)"
                )

            except Exception as exc:
                failures.append({
                    "medicamento": medicamento_slug,
                    "arquivo_pdf": pdf_path.relative_to(
                        bulas_dir.parent
                    ).as_posix(),
                    "erro": str(exc),
                })
                print(f"  [ERRO] {pdf_path.name}: {exc}")

        print()

    documents.sort(
        key=lambda item: (
            item.get("medicamento") or "",
            item.get("tipo_bula") or "",
        )
    )

    manifest = {
        "scenario_id": "bulas-medicamentos-anvisa",
        "version": time.strftime("%Y-%m-%d", time.localtime()),
        "description": (
            "Bulas de medicamentos previamente baixadas do "
            "Bulário Eletrônico da ANVISA"
        ),
        "bases": [
            {
                "base_id": "bulas_anvisa",
                "natureza": "estruturada",
                "fonte": "ANVISA - Bulário Eletrônico",
                "acesso": {
                    "tipo": "local_pdf",
                    "diretorio": bulas_dir.name,
                },
                "selecao_deterministica": True,
                "volume_alvo": "todos os PDFs de bula disponíveis localmente",
                "formato": "pdf",
                "sensitivity_default": "publico",
                "campo_vigencia": CAMPO_VIGENCIA_BULAS,
                "chunking_sugerido": "Split por seção da bula, com overlap",
                "metadados_extras": [
                    "medicamento",
                    "principio_ativo",
                    "nome_produto",
                    "tipo_bula",
                    "numero_registro",
                    "id_produto",
                    "expediente",
                    "razao_social",
                    "cnpj",
                    "numero_transacao",
                    "data_documento",
                    "numero_processo",
                    "data_atualizacao",
                ],
            }
        ],
        "generated_by": "src.gerar_corpus_manifest_bulas",
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "medicamentos_disponiveis": sorted(medications),
        "total_medicamentos": len(medications),
        "total_documentos": len(documents),
        "documentos": documents,
        "falhas": failures,
    }

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            manifest,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Medicamentos : {len(medications)}")
    print(f"Documentos   : {len(documents)}")
    print(f"Falhas       : {len(failures)}")
    print(f"Manifesto    : {output_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.gerar_corpus_manifest_bulas",
        description=(
            "Gera corpus_manifest_bulas.yaml a partir dos PDFs e "
            "metadata.json previamente baixados pelo fetch_bula."
        ),
    )

    parser.add_argument(
        "--bulas-dir",
        required=True,
        help=(
            "Diretório raiz das bulas extraídas. "
            "Ex.: BULAS_dir ou bulas_comprimidas"
        ),
    )

    parser.add_argument(
        "--output",
        default=GENERATED_MANIFEST_FILENAME,
        help=(
            "Arquivo YAML de saída. "
            f"Padrão: {GENERATED_MANIFEST_FILENAME}"
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    return generate_manifest(
        bulas_dir=Path(args.bulas_dir),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    sys.exit(main())
