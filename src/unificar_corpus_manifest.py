from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import yaml

DEFAULT_OUTPUT = "corpus_manifest.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"YAML inválido: {path}")

    return data


def merge_unique_strings(*values: Any) -> list[str]:
    result: list[str] = []

    for value in values:
        if not isinstance(value, list):
            continue

        for item in value:
            if item is None:
                continue

            text = str(item)

            if text not in result:
                result.append(text)

    return result


def merge_bases(
    *manifests: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for manifest in manifests:
        bases = manifest.get("bases", []) or []

        if not isinstance(bases, list):
            continue

        for base in bases:
            if not isinstance(base, dict):
                continue

            base_id = str(base.get("base_id") or "").strip()

            if not base_id:
                raise ValueError("Foi encontrada uma base sem base_id.")

            if base_id in seen:
                continue

            seen.add(base_id)
            result.append(base)

    return result


def document_key(
    document: dict[str, Any],
) -> tuple[str, str]:
    base_id = str(document.get("base_id") or "")
    arquivo = str(
        document.get("arquivo_pdf")
        or document.get("arquivo_origem")
        or ""
    )

    return base_id, arquivo


def prepare_document(
    document: dict[str, Any],
    default_tipo_documento: str,
) -> dict[str, Any]:
    prepared = dict(document)

    prepared.setdefault(
        "tipo_documento",
        default_tipo_documento,
    )

    return prepared


def merge_documents(
    protocolos: dict[str, Any],
    bulas: dict[str, Any],
    rename: dict[str, Any] | None = None,
    sih: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    warnings: list[str] = []

    sources = [
        ("protocolo", protocolos.get("documentos", []) or []),
        ("bula", bulas.get("documentos", []) or []),
    ]

    if rename:
        sources.append(("rename", rename.get("documentos", []) or []))

    if sih:
        sources.append(("agregado", sih.get("documentos", []) or []))

    for tipo_documento, documents in sources:
        if not isinstance(documents, list):
            raise ValueError(
                f"O campo documentos do manifesto de {tipo_documento} não é uma lista."
            )

        for index, document in enumerate(
            documents,
            start=1,
        ):
            if not isinstance(document, dict):
                warnings.append(
                    f"{tipo_documento} #{index}: entrada ignorada porque não é um objeto YAML."
                )
                continue

            prepared = prepare_document(
                document,
                tipo_documento,
            )

            if not prepared.get("base_id"):
                warnings.append(f"{tipo_documento} #{index}: documento sem base_id.")

            if not (
                prepared.get("arquivo_pdf")
                or prepared.get("arquivo_origem")
            ):
                warnings.append(
                    f"{tipo_documento} #{index}: documento sem arquivo_pdf/arquivo_origem."
                )

            key = document_key(prepared)

            if key[1] and key in seen:
                warnings.append(
                    f"Duplicado ignorado: base_id={key[0]} arquivo={key[1]}"
                )
                continue

            if key[1]:
                seen.add(key)

            result.append(prepared)

    return result, warnings


def merge_failures(
    **manifests: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for origem, manifest in manifests.items():
        if not manifest:
            continue

        failures = manifest.get("falhas", []) or []

        if not isinstance(failures, list):
            continue

        for failure in failures:
            if not isinstance(failure, dict):
                continue

            item = dict(failure)

            item.setdefault(
                "origem_manifesto",
                origem,
            )

            result.append(item)

    return result


def build_unified_manifest(
    protocolos: dict[str, Any],
    bulas: dict[str, Any],
    rename: dict[str, Any] | None = None,
    sih: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    documents, warnings = merge_documents(
        protocolos=protocolos,
        bulas=bulas,
        rename=rename,
        sih=sih,
    )

    all_manifests = {"protocolos": protocolos, "bulas": bulas}
    if rename:
        all_manifests["rename"] = rename
    if sih:
        all_manifests["sih"] = sih

    failures = merge_failures(**all_manifests)

    protocolo_count = sum(
        1 for d in documents if d.get("tipo_documento") == "protocolo"
    )
    bula_count = sum(1 for d in documents if d.get("tipo_documento") == "bula")
    rename_count = sum(
        1 for d in documents if d.get("tipo_documento") == "rename"
    )
    agregado_count = sum(
        1 for d in documents if d.get("tipo_documento") == "agregado"
    )

    manifest = {
        "scenario_id": "corpus-saude-rag",
        "version": time.strftime(
            "%Y-%m-%d",
            time.localtime(),
        ),
        "description": (
            "Corpus unificado de Protocolos Clínicos e Diretrizes Terapêuticas, bulas, RENAME e dados agregados do SIH/SUS para o RAG."
        ),
        "generated_by": "src.unificar_corpus_manifest",
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "bases": merge_bases(*all_manifests.values()),
        "doencas_disponiveis": merge_unique_strings(
            protocolos.get("doencas_disponiveis"),
            protocolos.get("doencas_processadas"),
            (rename.get("doencas_disponiveis") if rename else None),
        ),
        "medicamentos_disponiveis": merge_unique_strings(
            bulas.get("medicamentos_disponiveis"),
            (rename.get("medicamentos_disponiveis") if rename else None),
        ),
        "resumo": {
            "protocolos": protocolo_count,
            "bulas": bula_count,
            "rename": rename_count,
            "agregados": agregado_count,
            "total_documentos": len(documents),
            "falhas": len(failures),
        },
        "documentos": documents,
        "falhas": failures,
    }

    return manifest, warnings


def write_yaml(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        yaml.safe_dump(
            data,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def run(
    protocolo_path: Path,
    bula_path: Path,
    rename_path: Path | None,
    sih_path: Path | None,
    output_path: Path,
) -> int:
    try:
        protocolos = load_yaml(protocolo_path.resolve())
        bulas = load_yaml(bula_path.resolve())

        rename = None
        if rename_path and rename_path.exists():
            rename = load_yaml(rename_path.resolve())

        sih = None
        if sih_path and sih_path.exists():
            sih = load_yaml(sih_path.resolve())

        unified, warnings = build_unified_manifest(
            protocolos=protocolos,
            bulas=bulas,
            rename=rename,
            sih=sih,
        )

        write_yaml(
            output_path.resolve(),
            unified,
        )

    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 2

    resumo = unified["resumo"]

    print("=" * 70)
    print("UNIFICAR CORPUS MANIFEST")
    print("=" * 70)

    print(f"Protocolos : {resumo['protocolos']}")
    print(f"Bulas      : {resumo['bulas']}")
    print(f"RENAME     : {resumo['rename']}")
    print(f"Agregados  : {resumo['agregados']}")
    print(f"Total      : {resumo['total_documentos']}")
    print(f"Falhas     : {resumo['falhas']}")
    print(f"Saída      : {output_path.resolve()}")

    if warnings:
        print()
        print("AVISOS")

        for warning in warnings:
            print(f"- {warning}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.unificar_corpus_manifest",
        description=(
            "Unifica corpus_manifest_proto.yaml, corpus_manifest_bulas.yaml, corpus_manifest_rename.yaml e corpus_manifest_sih.yaml em corpus_manifest.yaml."
        ),
    )

    parser.add_argument(
        "--protocolos",
        default="corpus_manifest_proto.yaml",
        help="Manifesto dos protocolos. Padrão: corpus_manifest_proto.yaml",
    )

    parser.add_argument(
        "--bulas",
        default="corpus_manifest_bulas.yaml",
        help="Manifesto das bulas. Padrão: corpus_manifest_bulas.yaml",
    )

    parser.add_argument(
        "--rename",
        default="corpus_manifest_rename.yaml",
        help="Manifesto da RENAME. Padrão: corpus_manifest_rename.yaml",
    )

    parser.add_argument(
        "--sih",
        default="corpus_manifest_sih.yaml",
        help="Manifesto dos dados agregados do SIH/SUS. Padrão: corpus_manifest_sih.yaml",
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Manifesto unificado. Padrão: {DEFAULT_OUTPUT}",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    return run(
        protocolo_path=Path(args.protocolos),
        bula_path=Path(args.bulas),
        rename_path=Path(args.rename) if args.rename else None,
        sih_path=Path(args.sih) if args.sih else None,
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    sys.exit(main())
