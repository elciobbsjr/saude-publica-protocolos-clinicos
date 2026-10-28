from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
import yaml


HTTP_TIMEOUT = 45
DEFAULT_RATE_LIMIT_SEG = 0.5

DATA_DIRNAME = "data"
RAW_DIRNAME = "raw"
INVENTORY_DIRNAME = "inventory"
STATE_DIRNAME = "state"
HUMAN_INVENTORY_FILENAME = "CORPUS_INVENTORY.md"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return

        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text_parts).strip()))
            self._href = None
            self._text_parts = []


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        manifest = yaml.safe_load(file)

    if not isinstance(manifest, dict):
        raise ValueError("O corpus_manifest.yaml deve conter um objeto YAML.")

    if not isinstance(manifest.get("documentos"), list):
        raise ValueError("O manifesto não contém a lista 'documentos'.")

    return manifest


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0 Safari/537.36"
            ),
            "Accept": (
                "application/pdf,text/html,"
                "application/xhtml+xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
    )
    return session


def is_pdf(content: bytes, content_type: str = "") -> bool:
    if content.startswith(b"%PDF-"):
        return True
    return (
        "application/pdf" in content_type.lower()
        and b"%PDF-" in content[:1024]
    )


def is_pdf_file(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(5) == b"%PDF-"
    except OSError:
        return False


def is_jsonl_file(path: Path) -> bool:
    """
    Confere se o arquivo é um JSONL válido: cada linha não vazia
    precisa ser um objeto JSON, e o arquivo precisa ter ao menos uma linha.
    """
    try:
        with path.open("r", encoding="utf-8") as file:
            has_line = False

            for line in file:
                line = line.strip()
                if not line:
                    continue

                if not isinstance(json.loads(line), dict):
                    return False

                has_line = True

            return has_line
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def is_valid_raw_file(path: Path) -> bool:
    """
    Valida o arquivo pelo formato: .jsonl confere JSONL;
    os demais continuam conferindo PDF, como antes.
    """
    if path.suffix.lower() == ".jsonl":
        return is_jsonl_file(path)

    return is_pdf_file(path)


def find_pdf_url(html: str, page_url: str) -> str | None:
    parser = LinkParser()
    parser.feed(html)
    candidates: list[tuple[int, str]] = []

    for href, text in parser.links:
        url = urljoin(page_url, href)
        value = f"{url} {text}".lower()
        score = 100 if ".pdf" in url.lower() else 0
        score += sum(
            weight
            for keyword, weight in (
                ("pcdt", 20),
                ("protocolo", 15),
                ("portaria", 15),
                ("download", 10),
                ("pdf", 10),
            )
            if keyword in value
        )
        if score:
            candidates.append((score, url))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])[1]


def download_pdf(
    session: requests.Session,
    source_url: str,
) -> tuple[bytes, str, str]:
    response = session.get(
        source_url,
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")

    if is_pdf(response.content, content_type):
        return response.content, response.url, content_type

    pdf_url = find_pdf_url(response.text, response.url)
    if not pdf_url:
        raise RuntimeError(
            "a fonte não retornou um PDF nem apontou para um PDF"
        )

    pdf_response = session.get(
        pdf_url,
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    pdf_response.raise_for_status()
    pdf_content_type = pdf_response.headers.get("Content-Type", "")

    if not is_pdf(pdf_response.content, pdf_content_type):
        raise RuntimeError(
            "o link encontrado não retornou um arquivo PDF válido"
        )

    return (
        pdf_response.content,
        pdf_response.url,
        pdf_content_type,
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_sha256(path: Path) -> str:
    return sha256_file(path)


def utc_now() -> str:
    return datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"JSON inválido: {path}")

    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    temp_path.replace(path)


def inventory_number(path: Path) -> int | None:
    stem = path.stem

    if stem.endswith("_state"):
        stem = stem[:-6]

    if not stem.startswith("v"):
        return None

    value = stem[1:]
    return int(value) if value.isdigit() else None


def list_state_versions(state_dir: Path) -> list[Path]:
    if not state_dir.exists():
        return []

    versions: list[tuple[int, Path]] = []

    for path in state_dir.glob("v*_state.json"):
        number = inventory_number(path)
        if number is not None:
            versions.append((number, path))

    versions.sort(key=lambda item: item[0])
    return [path for _, path in versions]


def migrate_legacy_runtime_inventories(
    inventory_dir: Path,
    state_dir: Path,
) -> None:
    """
    Migra inventários operacionais das versões anteriores do script.

    Antes desta separação, data/inventory/vN.json era usado como estado
    de retomada. Agora esse estado fica em data/inventory/state/vN_state.json
    e vN.json passa a ser exclusivamente o inventário oficial entregável.
    """
    state_dir.mkdir(parents=True, exist_ok=True)

    for legacy_path in inventory_dir.glob("v*.json"):
        number = inventory_number(legacy_path)
        if number is None:
            continue

        state_path = state_dir / f"v{number}_state.json"
        if state_path.exists():
            continue

        try:
            data = load_json(legacy_path)
        except Exception:
            continue

        # Reconhece o formato operacional antigo.
        if (
            isinstance(data.get("documents"), list)
            and "manifest_sha256" in data
            and "state" in data
        ):
            save_json(state_path, data)


def choose_version(
    state_dir: Path,
    manifest_hash: str,
) -> tuple[str, Path, dict[str, Any] | None, bool]:
    """
    fetch:
      - mesmo manifesto incompleto -> retoma a mesma versão;
      - mesmo manifesto completo -> reutiliza sem alterar;
      - se não houver versão anterior -> cria v1;
      - se já houver versões e o manifesto for diferente, exige 'update'.
    """
    versions = list_state_versions(state_dir)

    for state_path in reversed(versions):
        try:
            state = load_json(state_path)
        except Exception:
            continue

        if state.get("manifest_sha256") == manifest_hash:
            number = inventory_number(state_path)
            version = str(
                state.get("version")
                or (f"v{number}" if number is not None else "")
            )
            return version, state_path, state, False

    if versions:
        raise RuntimeError(
            "O manifesto mudou em relação às versões existentes. "
            "Use o comando 'update' para criar uma nova versão imutável."
        )

    version = "v1"
    state_path = state_dir / "v1_state.json"
    return version, state_path, None, True


def choose_next_version(
    state_dir: Path,
) -> tuple[str, Path]:
    """
    update sempre cria v(n+1), sem sobrescrever versões anteriores.
    """
    versions = list_state_versions(state_dir)

    next_number = 1
    if versions:
        numbers = [
            inventory_number(path)
            for path in versions
            if inventory_number(path) is not None
        ]
        if numbers:
            next_number = max(numbers) + 1

    version = f"v{next_number}"
    state_path = state_dir / f"{version}_state.json"

    return version, state_path


def get_base_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for base in manifest.get("bases", []) or []:
        if not isinstance(base, dict):
            continue

        base_id = str(base.get("base_id") or "").strip()
        if base_id:
            result[base_id] = base

    return result


def get_rate_limit_seg(
    document: dict[str, Any],
    base_map: dict[str, dict[str, Any]],
) -> float:
    base = base_map.get(str(document.get("base_id") or ""), {})
    access = base.get("acesso") or {}

    candidates = [
        document.get("rate_limit_seg"),
        base.get("rate_limit_seg"),
        access.get("rate_limit_seg")
        if isinstance(access, dict)
        else None,
    ]

    for value in candidates:
        if value is None:
            continue

        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            continue

    return DEFAULT_RATE_LIMIT_SEG


def get_access_type(document: dict[str, Any]) -> str:
    access = document.get("acesso") or {}

    if not isinstance(access, dict):
        return ""

    access_type = str(
        access.get("tipo_origem")
        or access.get("tipo")
        or ""
    ).strip()

    if access_type == "corpus_local":
        if access.get("url_pdf_resolvida"):
            return "http_pdf"

        if (
            access.get("caminho_origem")
            or document.get("arquivo_origem")
        ):
            return "local_pdf"

    return access_type


def get_remote_source_url(document: dict[str, Any]) -> str | None:
    access = document.get("acesso") or {}

    if not isinstance(access, dict):
        return None

    value = (
        access.get("url_pdf_resolvida")
        or access.get("url_origem")
    )

    return str(value) if value else None


def get_local_source_path(
    project_dir: Path,
    document: dict[str, Any],
) -> Path:
    access = document.get("acesso") or {}
    access_path = None

    if isinstance(access, dict):
        access_path = (
            access.get("caminho_origem")
            or access.get("caminho")
        )

    relative = (
        document.get("arquivo_origem")
        or access_path
        or document.get("arquivo_pdf")
    )

    if not relative:
        raise ValueError("documento local sem caminho de origem")

    path = Path(str(relative))
    if not path.is_absolute():
        path = project_dir / path

    return path.resolve()


def relative_inside_source(
    path_value: str,
    tipo_documento: str,
) -> Path:
    path = Path(path_value)
    parts = list(path.parts)

    markers = (
        ["PROTO_dir", "PDFS_dir"]
        if tipo_documento == "protocolo"
        else ["BULAS_dir"]
    )

    lower_parts = [part.lower() for part in parts]

    for marker in markers:
        marker_lower = marker.lower()
        if marker_lower in lower_parts:
            index = lower_parts.index(marker_lower)
            remaining = parts[index + 1:]
            if remaining:
                return Path(*remaining)

    if len(parts) > 1:
        return Path(*parts[-2:])

    return Path(path.name)


def corpus_destination(
    raw_version_dir: Path,
    document: dict[str, Any],
) -> Path:
    tipo = str(
        document.get("tipo_documento") or ""
    ).strip().lower()

    if tipo == "protocolo":
        category = "protocolos"
    elif tipo == "bula":
        category = "bulas"
    elif tipo == "rename":
        category = "rename"
    elif tipo == "agregado":
        category = "agregados"
    else:
        raise ValueError(
            f"tipo_documento não suportado: {tipo or 'não informado'}"
        )

    origin_hint = str(
        document.get("arquivo_origem")
        or document.get("arquivo_pdf")
        or ""
    )

    if not origin_hint:
        raise ValueError("documento sem arquivo_pdf/arquivo_origem")

    return (
        raw_version_dir
        / category
        / relative_inside_source(origin_hint, tipo)
    )


def document_key(document: dict[str, Any]) -> str:
    tipo = str(document.get("tipo_documento") or "")
    base_id = str(document.get("base_id") or "")

    if tipo == "protocolo":
        identity = "|".join(
            [
                str(document.get("doenca") or ""),
                str(document.get("versao_portaria") or ""),
                str(document.get("data_inicio") or ""),
            ]
        )
    elif tipo == "bula":
        identity = "|".join(
            [
                str(document.get("medicamento") or ""),
                str(document.get("numero_registro") or ""),
                str(document.get("tipo_bula") or ""),
            ]
        )
    else:
        identity = str(
            document.get("arquivo_origem")
            or document.get("arquivo_pdf")
            or ""
        )

    return f"{base_id}|{tipo}|{identity}"


def display_name(document: dict[str, Any]) -> str:
    if document.get("tipo_documento") == "agregado":
        return (
            f"{document.get('base_id', 'agregado')} "
            f"(período {document.get('periodo', 'não informado')})"
        )

    if document.get("tipo_documento") == "bula":
        return (
            f"{document.get('medicamento', 'bula')} "
            f"({document.get('tipo_bula', 'tipo não informado')})"
        )

    return (
        f"{document.get('doenca', 'protocolo')} - "
        f"{document.get('versao_portaria', 'versão não informada')}"
    )


def build_inventory_record(
    document: dict[str, Any],
    destination: Path,
    project_dir: Path,
) -> dict[str, Any]:
    access_type = get_access_type(document)

    return {
        "document_key": document_key(document),
        "tipo_documento": document.get("tipo_documento"),
        "base_id": document.get("base_id"),
        "doenca": document.get("doenca"),
        "medicamento": document.get("medicamento"),
        "tipo_bula": document.get("tipo_bula"),
        "versao_portaria": document.get("versao_portaria"),
        "numero_registro": document.get("numero_registro"),
        "access_type": access_type,
        "source_url": (
            get_remote_source_url(document)
            if access_type == "http_pdf"
            else None
        ),
        "arquivo_origem": (
            document.get("arquivo_origem")
            or document.get("arquivo_pdf")
        ),
        "arquivo_raw": destination.relative_to(
            project_dir
        ).as_posix(),
        "status": "pendente",
        "sha256_esperado": str(document.get("sha256") or ""),
        "sha256": None,
        "tamanho_bytes": None,
        "content_type": None,
        "url_final": None,
        "erro": None,
        "updated_at": utc_now(),
    }


def summarize_inventory(inventory: dict[str, Any]) -> dict[str, int]:
    documents = inventory.get("documents", []) or []

    return {
        "total": len(documents),
        "ok": sum(
            1 for item in documents
            if item.get("status") == "ok"
        ),
        "falhou": sum(
            1 for item in documents
            if item.get("status") == "falhou"
        ),
        "pendente": sum(
            1 for item in documents
            if item.get("status") == "pendente"
        ),
    }


def update_inventory_summary(inventory: dict[str, Any]) -> None:
    summary = summarize_inventory(inventory)
    inventory["summary"] = summary
    inventory["updated_at"] = utc_now()

    if (
        summary["total"] > 0
        and summary["ok"] == summary["total"]
    ):
        inventory["state"] = "complete"
        inventory.setdefault("completed_at", utc_now())
    else:
        inventory["state"] = "incomplete"
        inventory.pop("completed_at", None)


def detect_format(path_value: str | None) -> str:
    if not path_value:
        return "desconhecido"

    suffix = Path(str(path_value)).suffix.lower().lstrip(".")
    return suffix or "desconhecido"


def build_official_inventory(
    manifest: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Monta o inventário oficial da Etapa 1 a partir do estado de coleta.
    """
    base_map = get_base_map(manifest)
    documents = state.get("documents", []) or []

    arquivos: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []
    per_base: dict[str, dict[str, Any]] = {}

    for item in documents:
        base_id = str(item.get("base_id") or "sem_base")
        base = base_map.get(base_id, {})

        natureza = (
            base.get("natureza")
            or item.get("natureza")
            or "-"
        )

        bucket = per_base.setdefault(
            base_id,
            {
                "base_id": base_id,
                "natureza": natureza,
                "arquivos": 0,
                "formatos": {},
                "bytes": 0,
                "volume_alvo": base.get("volume_alvo"),
                "divergencia_alvo": None,
            },
        )

        status = str(item.get("status") or "pendente")
        origem = (
            item.get("source_url")
            or item.get("arquivo_origem")
        )

        if status == "ok":
            path_value = str(item.get("arquivo_raw") or "")
            formato = detect_format(path_value)
            size = int(item.get("tamanho_bytes") or 0)

            bucket["arquivos"] += 1
            bucket["bytes"] += size
            bucket["formatos"][formato] = (
                bucket["formatos"].get(formato, 0) + 1
            )

            arquivos.append(
                {
                    "path": path_value.replace("\\", "/"),
                    "base_id": base_id,
                    "tipo": formato,
                    "bytes": size,
                    "sha256": item.get("sha256"),
                    "origem": origem,
                    "coletado_em": item.get("updated_at"),
                    "status": "ok",
                }
            )

        elif status == "falhou":
            falhas.append(
                {
                    "origem": origem,
                    "erro": item.get("erro") or "erro não informado",
                }
            )

    for bucket in per_base.values():
        volume_alvo = bucket.get("volume_alvo")

        if volume_alvo is None:
            bucket["divergencia_alvo"] = None
            continue

        try:
            bucket["divergencia_alvo"] = (
                int(bucket["arquivos"]) - int(volume_alvo)
            )
        except (TypeError, ValueError):
            bucket["divergencia_alvo"] = None

    return {
        "scenario_id": manifest.get("scenario_id") or "corpus-saude-rag",
        "version": state.get("version"),
        "coletado_em": (
            state.get("completed_at")
            or state.get("updated_at")
            or utc_now()
        ),
        "manifest_hash": (
            "sha256:" + str(state.get("manifest_sha256") or "")
        ),
        "totais": {
            "arquivos": len(arquivos),
            "bytes": sum(
                int(item.get("bytes") or 0)
                for item in arquivos
            ),
            "falhas": len(falhas),
        },
        "por_base": sorted(
            per_base.values(),
            key=lambda item: str(item.get("base_id") or ""),
        ),
        "arquivos": sorted(
            arquivos,
            key=lambda item: str(item.get("path") or ""),
        ),
        "falhas": falhas,
    }


def human_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{value} B"


def write_official_human_inventory(
    path: Path,
    inventory: dict[str, Any],
) -> Path:
    totals = inventory.get("totais", {})
    bases = inventory.get("por_base", []) or []
    failures = inventory.get("falhas", []) or []

    lines = [
        "# CORPUS INVENTORY",
        "",
        f"- Scenario ID: `{inventory.get('scenario_id')}`",
        f"- Versão: **{inventory.get('version')}**",
        f"- Data da coleta: `{inventory.get('coletado_em')}`",
        f"- Manifest hash: `{inventory.get('manifest_hash')}`",
        f"- Total de arquivos: **{totals.get('arquivos', 0)}**",
        f"- Tamanho total: **{human_size(int(totals.get('bytes', 0) or 0))}**",
        f"- Falhas: **{totals.get('falhas', 0)}**",
        "",
        "## Resumo por base",
        "",
        "| Base | Natureza | Arquivos | Formatos | Tamanho | Volume alvo | Divergência |",
        "|---|---|---:|---|---:|---:|---:|",
    ]

    for base in bases:
        formatos = ", ".join(
            f"{fmt}: {count}"
            for fmt, count in sorted(
                (base.get("formatos") or {}).items()
            )
        ) or "-"

        volume_alvo = base.get("volume_alvo")
        divergencia = base.get("divergencia_alvo")

        lines.append(
            "| "
            + " | ".join(
                [
                    str(base.get("base_id") or "-"),
                    str(base.get("natureza") or "-"),
                    str(base.get("arquivos") or 0),
                    formatos,
                    human_size(int(base.get("bytes") or 0)),
                    str(volume_alvo) if volume_alvo is not None else "-",
                    str(divergencia) if divergencia is not None else "-",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Falhas", ""])

    if failures:
        for failure in failures:
            lines.append(
                f"- `{failure.get('origem') or '-'}` — "
                f"{failure.get('erro') or 'erro não informado'}"
            )
    else:
        lines.append("- Nenhuma falha registrada.")

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f"{path.stem}_tmp{path.suffix}"
    )
    temp_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    try:
        temp_path.replace(path)
        return path
    except PermissionError:
        fallback = path.with_name(
            f"{path.stem}_pendente{path.suffix}"
        )
        temp_path.replace(fallback)
        print(
            f"[AVISO] {path.name} está bloqueado. "
            f"Inventário humano salvo em {fallback.name}."
        )
        return fallback


def generate_official_inventory_artifacts(
    manifest_path: Path,
    state_path: Path,
    official_inventory_path: Path,
) -> tuple[dict[str, Any], Path]:
    manifest = load_manifest(manifest_path.resolve())
    state = load_json(state_path.resolve())

    official = build_official_inventory(
        manifest=manifest,
        state=state,
    )

    save_json(
        official_inventory_path.resolve(),
        official,
    )

    human_path = (
        manifest_path.resolve().parent
        / DATA_DIRNAME
        / HUMAN_INVENTORY_FILENAME
    )
    actual_human_path = write_official_human_inventory(
        human_path,
        official,
    )

    return official, actual_human_path


def write_human_inventory(
    path: Path,
    inventory: dict[str, Any],
) -> None:
    summary = inventory.get("summary", {})
    documents = inventory.get("documents", []) or []

    lines = [
        "# CORPUS INVENTORY",
        "",
        f"- Versão corrente: **{inventory.get('version')}**",
        f"- Estado: **{inventory.get('state')}**",
        f"- Manifesto: `{inventory.get('manifest_path')}`",
        f"- Gerado/atualizado em: `{inventory.get('updated_at')}`",
        f"- Total: **{summary.get('total', 0)}**",
        f"- OK: **{summary.get('ok', 0)}**",
        f"- Falhou: **{summary.get('falhou', 0)}**",
        f"- Pendente: **{summary.get('pendente', 0)}**",
        "",
        "## Documentos",
        "",
        "| Tipo | Documento | Status | Arquivo raw |",
        "|---|---|---|---|",
    ]

    for item in documents:
        if item.get("tipo_documento") == "bula":
            name = (
                f"{item.get('medicamento') or '-'} / "
                f"{item.get('tipo_bula') or '-'}"
            )
        else:
            name = (
                f"{item.get('doenca') or '-'} / "
                f"{item.get('versao_portaria') or '-'}"
            )

        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("tipo_documento") or "-"),
                    str(name).replace("|", "/"),
                    str(item.get("status") or "-"),
                    f"`{item.get('arquivo_raw') or '-'}`",
                ]
            )
            + " |"
        )

    failures = [
        item for item in documents
        if item.get("status") == "falhou"
    ]

    if failures:
        lines.extend(
            [
                "",
                "## Falhas",
                "",
            ]
        )

        for item in failures:
            lines.append(
                f"- `{item.get('document_key')}`: "
                f"{item.get('erro') or 'erro não informado'}"
            )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_name(
            f"{path.stem}_tmp{path.suffix}"
        )

        temp_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        try:
            temp_path.replace(path)
        except PermissionError:
            # No Windows, o Markdown pode estar aberto/bloqueado por
            # editor, sincronizador ou antivírus. O inventário JSON é a
            # fonte oficial para retomada; portanto essa falha não deve
            # interromper a coleta.
            fallback = path.with_name(
                f"{path.stem}_pendente{path.suffix}"
            )
            temp_path.replace(fallback)

            print(
                f"      [AVISO] Não foi possível atualizar {path.name}. "
                f"Inventário humano salvo temporariamente em "
                f"{fallback.name}."
            )

    except PermissionError as exc:
        # O inventário humano é derivado do JSON e pode ser regenerado.
        # Nunca aborta o fetch por causa de bloqueio deste arquivo.
        print(
            f"      [AVISO] Inventário humano não pôde ser gravado: "
            f"{exc}"
        )


def write_log(
    log_path: Path,
    message: str,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"[{utc_now()}] {message}\n")


def generate_diff(
    previous_inventory: dict[str, Any],
    current_inventory: dict[str, Any],
    output_path: Path,
) -> None:
    previous_docs = {
        str(item.get("document_key")): item
        for item in previous_inventory.get("documents", []) or []
        if item.get("document_key")
    }
    current_docs = {
        str(item.get("document_key")): item
        for item in current_inventory.get("documents", []) or []
        if item.get("document_key")
    }

    previous_keys = set(previous_docs)
    current_keys = set(current_docs)

    added = sorted(current_keys - previous_keys)
    removed = sorted(previous_keys - current_keys)
    common = sorted(previous_keys & current_keys)

    changed = [
        key
        for key in common
        if (
            previous_docs[key].get("sha256")
            != current_docs[key].get("sha256")
        )
    ]

    identical = [
        key
        for key in common
        if (
            previous_docs[key].get("sha256")
            == current_docs[key].get("sha256")
            and previous_docs[key].get("status") == "ok"
            and current_docs[key].get("status") == "ok"
        )
    ]

    lines = [
        (
            f"# DIFF {previous_inventory.get('version')} "
            f"→ {current_inventory.get('version')}"
        ),
        "",
        f"- Adicionados: **{len(added)}**",
        f"- Removidos: **{len(removed)}**",
        f"- Alterados: **{len(changed)}**",
        f"- Idênticos: **{len(identical)}**",
        "",
        "## Adicionados",
        "",
    ]

    lines.extend(
        [f"- `{key}`" for key in added]
        or ["- Nenhum"]
    )

    lines.extend(
        [
            "",
            "## Removidos",
            "",
        ]
    )
    lines.extend(
        [f"- `{key}`" for key in removed]
        or ["- Nenhum"]
    )

    lines.extend(
        [
            "",
            "## Alterados",
            "",
        ]
    )
    lines.extend(
        [f"- `{key}`" for key in changed]
        or ["- Nenhum"]
    )

    lines.extend(
        [
            "",
            "## Idênticos",
            "",
        ]
    )
    lines.extend(
        [f"- `{key}`" for key in identical]
        or ["- Nenhum"]
    )

    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def previous_inventory_before(
    inventory_dir: Path,
    current_version: str,
) -> dict[str, Any] | None:
    current_number = int(current_version[1:])
    candidate_number = current_number - 1

    if candidate_number < 1:
        return None

    path = inventory_dir / f"v{candidate_number}.json"
    if not path.exists():
        return None

    try:
        return load_json(path)
    except Exception:
        return None


def prepare_inventory(
    version: str,
    manifest_path: Path,
    manifest_hash: str,
    documents: list[dict[str, Any]],
    raw_version_dir: Path,
    project_dir: Path,
) -> dict[str, Any]:
    records = [
        build_inventory_record(
            document=document,
            destination=corpus_destination(
                raw_version_dir,
                document,
            ),
            project_dir=project_dir,
        )
        for document in documents
    ]

    inventory = {
        "version": version,
        "state": "incomplete",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "manifest_path": manifest_path.relative_to(
            project_dir
        ).as_posix(),
        "manifest_sha256": manifest_hash,
        "raw_dir": raw_version_dir.relative_to(
            project_dir
        ).as_posix(),
        "summary": {},
        "documents": records,
    }

    update_inventory_summary(inventory)
    return inventory


def find_existing_record(
    inventory: dict[str, Any],
    key: str,
) -> dict[str, Any] | None:
    for item in inventory.get("documents", []) or []:
        if item.get("document_key") == key:
            return item

    return None


def run_fetch(
    manifest_path: Path,
    force_new_version: bool = False,
) -> int:
    manifest_path = manifest_path.resolve()

    if not manifest_path.exists():
        print(f"[ERRO] Manifesto não encontrado: {manifest_path}")
        return 2

    project_dir = manifest_path.parent
    manifest = load_manifest(manifest_path)

    documents = [
        document
        for document in manifest["documentos"]
        if isinstance(document, dict)
    ]

    if not documents:
        print("[ERRO] O manifesto não contém documentos para coletar.")
        return 3

    data_dir = project_dir / DATA_DIRNAME
    raw_dir = data_dir / RAW_DIRNAME
    inventory_dir = data_dir / INVENTORY_DIRNAME
    state_dir = inventory_dir / STATE_DIRNAME

    raw_dir.mkdir(parents=True, exist_ok=True)
    inventory_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    # Compatibilidade com execuções anteriores do script.
    migrate_legacy_runtime_inventories(
        inventory_dir=inventory_dir,
        state_dir=state_dir,
    )

    manifest_hash = manifest_sha256(manifest_path)

    try:
        if force_new_version:
            version, state_path = choose_next_version(
                state_dir=state_dir,
            )
            existing_inventory = None
            is_new_version = True
        else:
            (
                version,
                state_path,
                existing_inventory,
                is_new_version,
            ) = choose_version(
                state_dir=state_dir,
                manifest_hash=manifest_hash,
            )
    except RuntimeError as exc:
        print(f"[ERRO] {exc}")
        return 4

    official_inventory_path = inventory_dir / f"{version}.json"
    raw_version_dir = raw_dir / version
    raw_version_dir.mkdir(parents=True, exist_ok=True)

    log_path = inventory_dir / f"fetch_corpus_{version}_log.txt"
    human_inventory_path = data_dir / HUMAN_INVENTORY_FILENAME

    if (
        existing_inventory
        and existing_inventory.get("state") == "complete"
    ):
        print("=" * 70)
        print("FETCH CORPUS")
        print("=" * 70)
        print(f"Manifesto : {manifest_path}")
        print(f"Versão    : {version}")
        print("Estado    : complete")
        print()
        print(
            "Este manifesto já possui uma versão completa e imutável. "
            "Nenhum arquivo foi alterado."
        )
        print(f"Estado     : {state_path}")

        _, actual_human_path = generate_official_inventory_artifacts(
            manifest_path=manifest_path,
            state_path=state_path,
            official_inventory_path=official_inventory_path,
        )
        print(f"Inventário: {official_inventory_path}")
        print(f"Humano    : {actual_human_path}")
        return 0

    if existing_inventory:
        inventory = existing_inventory
        print(f"Retomando versão incompleta: {version}")
    else:
        inventory = prepare_inventory(
            version=version,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
            documents=documents,
            raw_version_dir=raw_version_dir,
            project_dir=project_dir,
        )
        save_json(state_path, inventory)

    session = build_session()
    base_map = get_base_map(manifest)

    print("=" * 70)
    print("FETCH CORPUS")
    print("=" * 70)
    print(f"Manifesto : {manifest_path}")
    print(f"Versão    : {version}")
    print(f"Destino   : {raw_version_dir}")
    print(f"Documentos: {len(documents)}")
    print()

    write_log(
        log_path,
        (
            f"Início/retomada fetch; manifesto={manifest_path}; "
            f"version={version}; new_version={is_new_version}"
        ),
    )

    for index, document in enumerate(documents, start=1):
        key = document_key(document)
        record = find_existing_record(inventory, key)

        if record is None:
            destination = corpus_destination(
                raw_version_dir,
                document,
            )
            record = build_inventory_record(
                document=document,
                destination=destination,
                project_dir=project_dir,
            )
            inventory.setdefault("documents", []).append(record)
        else:
            destination = project_dir / Path(
                str(record["arquivo_raw"])
            )

        print(
            f"[{index}/{len(documents)}] "
            f"{display_name(document)}"
        )

        # Retomada idempotente: documento já concluído e íntegro.
        if (
            record.get("status") == "ok"
            and destination.exists()
            and is_valid_raw_file(destination)
        ):
            expected = str(record.get("sha256") or "")
            actual = sha256_file(destination)

            if not expected or actual == expected:
                print("      já concluído: ignorado")
                continue

        try:
            access_type = get_access_type(document)
            expected_hash = str(document.get("sha256") or "").strip()

            if access_type == "http_pdf":
                source_url = get_remote_source_url(document)

                if not source_url:
                    raise ValueError(
                        "documento http_pdf sem URL de origem"
                    )

                # Caso a versão incompleta já tenha o arquivo íntegro,
                # registra como concluído sem baixar novamente.
                if (
                    destination.exists()
                    and is_pdf_file(destination)
                    and expected_hash
                    and sha256_file(destination) == expected_hash
                ):
                    content_hash = expected_hash
                    content_size = destination.stat().st_size
                    final_url = source_url
                    content_type = "application/pdf"
                    print(
                        "      arquivo já presente e íntegro: "
                        "download dispensado"
                    )
                else:
                    content, final_url, content_type = download_pdf(
                        session,
                        source_url,
                    )

                    content_hash = sha256_bytes(content)

                    if (
                        expected_hash
                        and content_hash != expected_hash
                    ):
                        raise ValueError(
                            "SHA-256 baixado diverge do manifesto"
                        )

                    destination.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    destination.write_bytes(content)
                    content_size = len(content)

                    print(f"      baixado: {destination}")

                rate_limit = get_rate_limit_seg(
                    document,
                    base_map,
                )
                if rate_limit > 0:
                    time.sleep(rate_limit)

            elif access_type == "local_pdf":
                source_path = get_local_source_path(
                    project_dir,
                    document,
                )

                if not source_path.exists():
                    raise FileNotFoundError(
                        f"arquivo local não encontrado: {source_path}"
                    )

                if not source_path.is_file():
                    raise ValueError(
                        f"origem local não é arquivo: {source_path}"
                    )

                if not is_pdf_file(source_path):
                    raise ValueError(
                        f"origem local não é PDF válido: {source_path}"
                    )

                source_hash = sha256_file(source_path)

                if (
                    expected_hash
                    and source_hash != expected_hash
                ):
                    raise ValueError(
                        "SHA-256 do arquivo local diverge do manifesto"
                    )

                # Retomada: se já existe íntegro no raw, não recopia.
                if (
                    destination.exists()
                    and is_pdf_file(destination)
                    and sha256_file(destination) == source_hash
                ):
                    print(
                        "      arquivo raw já presente e íntegro: "
                        "cópia dispensada"
                    )
                else:
                    destination.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    shutil.copy2(source_path, destination)
                    print(f"      copiado: {destination}")

                content_hash = source_hash
                content_size = destination.stat().st_size
                final_url = None
                content_type = "application/pdf"

            elif access_type == "local_jsonl":
                source_path = get_local_source_path(
                    project_dir,
                    document,
                )

                if not source_path.exists():
                    raise FileNotFoundError(
                        f"arquivo local não encontrado: {source_path}"
                    )

                if not source_path.is_file():
                    raise ValueError(
                        f"origem local não é arquivo: {source_path}"
                    )

                if not is_jsonl_file(source_path):
                    raise ValueError(
                        f"origem local não é JSONL válido: {source_path}"
                    )

                source_hash = sha256_file(source_path)

                if (
                    expected_hash
                    and source_hash != expected_hash
                ):
                    raise ValueError(
                        "SHA-256 do arquivo local diverge do manifesto"
                    )

                # Retomada: se já existe íntegro no raw, não recopia.
                if (
                    destination.exists()
                    and is_jsonl_file(destination)
                    and sha256_file(destination) == source_hash
                ):
                    print(
                        "      arquivo raw já presente e íntegro: "
                        "cópia dispensada"
                    )
                else:
                    destination.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    shutil.copy2(source_path, destination)
                    print(f"      copiado: {destination}")

                content_hash = source_hash
                content_size = destination.stat().st_size
                final_url = None
                content_type = "application/jsonl"

            else:
                raise ValueError(
                    f"tipo de acesso não suportado: "
                    f"{access_type or 'não informado'}"
                )

            record["status"] = "ok"
            record["sha256"] = content_hash
            record["tamanho_bytes"] = content_size
            record["content_type"] = content_type
            record["url_final"] = final_url
            record["erro"] = None
            record["updated_at"] = utc_now()

            write_log(
                log_path,
                f"OK {key} -> {record['arquivo_raw']}",
            )

        except Exception as exc:
            record["status"] = "falhou"
            record["erro"] = str(exc)
            record["updated_at"] = utc_now()

            print(f"      [FALHA] {exc}")

            write_log(
                log_path,
                f"FALHA {key}: {exc}",
            )

        # Persistência após CADA documento => retomável.
        update_inventory_summary(inventory)
        save_json(state_path, inventory)

    update_inventory_summary(inventory)
    save_json(state_path, inventory)
    # Gera o inventário oficial da versão.
    _, actual_human_path = generate_official_inventory_artifacts(
        manifest_path=manifest_path,
        state_path=state_path,
        official_inventory_path=official_inventory_path,
    )

    # update gera DIFF em relação à versão imediatamente anterior.
    current_number = int(version[1:])
    if force_new_version and current_number > 1:
        previous_state_path = (
            state_dir / f"v{current_number - 1}_state.json"
        )

        if previous_state_path.exists():
            previous_inventory = load_json(previous_state_path)
            diff_path = inventory_dir / (
                f"DIFF_v{current_number - 1}_{version}.md"
            )
            generate_diff(
                previous_inventory,
                inventory,
                diff_path,
            )

    summary = inventory["summary"]

    print()
    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Versão   : {version}")
    print(f"Estado   : {inventory['state']}")
    print(f"Total    : {summary['total']}")
    print(f"OK       : {summary['ok']}")
    print(f"Falhou   : {summary['falhou']}")
    print(f"Pendente : {summary['pendente']}")
    print(f"Raw      : {raw_version_dir}")
    print(f"Estado     : {state_path}")
    print(f"Log      : {log_path}")
    print(f"Inventário: {official_inventory_path}")
    print(f"Humano   : {actual_human_path}")

    # Falhas não abortam a coleta inteira.
    return 0


def run_inventory(
    manifest_path: Path,
    version: str | None,
) -> int:
    manifest_path = manifest_path.resolve()

    if not manifest_path.exists():
        print(f"[ERRO] Manifesto não encontrado: {manifest_path}")
        return 2

    project_dir = manifest_path.parent
    inventory_dir = (
        project_dir
        / DATA_DIRNAME
        / INVENTORY_DIRNAME
    )
    state_dir = inventory_dir / STATE_DIRNAME

    inventory_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    migrate_legacy_runtime_inventories(
        inventory_dir=inventory_dir,
        state_dir=state_dir,
    )

    states = list_state_versions(state_dir)

    if not states:
        print("[ERRO] Nenhuma versão coletada encontrada.")
        return 3

    if version:
        state_path = state_dir / f"{version}_state.json"
    else:
        state_path = states[-1]
        number = inventory_number(state_path)
        version = f"v{number}"

    if not state_path.exists():
        print(
            f"[ERRO] Estado da versão não encontrado: {state_path}"
        )
        return 3

    official_inventory_path = (
        inventory_dir / f"{version}.json"
    )

    try:
        official, actual_human_path = (
            generate_official_inventory_artifacts(
                manifest_path=manifest_path,
                state_path=state_path,
                official_inventory_path=official_inventory_path,
            )
        )
    except Exception as exc:
        print(f"[ERRO] Falha ao gerar inventário: {exc}")
        return 4

    totals = official.get("totais", {})

    print("=" * 70)
    print("CORPUS INVENTORY")
    print("=" * 70)
    print(f"Scenario ID : {official.get('scenario_id')}")
    print(f"Versão      : {official.get('version')}")
    print(f"Coletado em : {official.get('coletado_em')}")
    print(f"Arquivos    : {totals.get('arquivos', 0)}")
    print(f"Bytes       : {totals.get('bytes', 0)}")
    print(f"Falhas      : {totals.get('falhas', 0)}")
    print(f"JSON        : {official_inventory_path}")
    print(f"Markdown    : {actual_human_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.fetch_corpus"
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    fetch_parser = subparsers.add_parser(
        "fetch",
        help=(
            "Materializa o manifesto em data/raw/vN, "
            "com inventário versionado e retomável."
        ),
    )
    fetch_parser.add_argument(
        "--manifest",
        required=True,
        help="Caminho para corpus_manifest.yaml.",
    )

    update_parser = subparsers.add_parser(
        "update",
        help=(
            "Cria sempre uma nova versão v(n+1), preserva as anteriores "
            "e gera DIFF entre a versão anterior e a nova."
        ),
    )
    update_parser.add_argument(
        "--manifest",
        required=True,
        help="Caminho para corpus_manifest.yaml.",
    )

    inventory_parser = subparsers.add_parser(
        "inventory",
        help="Gera/regera vN.json e CORPUS_INVENTORY.md para uma versão.",
    )
    inventory_parser.add_argument(
        "--manifest",
        default="corpus_manifest.yaml",
        help="Caminho para corpus_manifest.yaml.",
    )
    inventory_parser.add_argument(
        "--version",
        help="Versão desejada, por exemplo v1. Sem informar, usa a mais recente.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        return run_fetch(
            Path(args.manifest),
            force_new_version=False,
        )

    if args.command == "update":
        return run_fetch(
            Path(args.manifest),
            force_new_version=True,
        )

    if args.command == "inventory":
        return run_inventory(
            Path(args.manifest),
            args.version,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
