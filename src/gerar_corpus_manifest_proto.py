from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml


# O JSON é procurado no mesmo diretório do manifesto informado.
PROTOCOL_JSON_FILENAME = "protocolos_normativa.json"

# Manifesto gerado após a descoberta e validação dos documentos.
GENERATED_MANIFEST_FILENAME = "corpus_manifest_proto.yaml"

# Diretório solicitado para armazenar os PDFs.
PDF_DIRNAME = "PROTO_dir"

# Metadados dos PDFs baixados.
METADATA_FILENAME = "metadata.jsonl"

# Relatório legível das falhas da execução.
FAILURE_LOG_FILENAME = "gerar_corpus_manifest.log"

# Timeout HTTP.
HTTP_TIMEOUT = 45

# Intervalo entre requisições, para não sobrecarregar os sites.
REQUEST_DELAY_SECONDS = 0.5


# ---------------------------------------------------------------------------
# MODELOS
# ---------------------------------------------------------------------------
@dataclass
class ProtocolDocument:
    disease: str
    versao_portaria: str | None
    data_inicio: str | None
    data_fim: str | None
    status: str | None
    confirmacao: str | None
    fonte: str | None
    observacao: str | None
    source_url: str


# ---------------------------------------------------------------------------
# HTML: localizar links que possam ser PDFs
# ---------------------------------------------------------------------------
class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
            text = " ".join(self._text_parts).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text_parts = []


# ---------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------------------------
def normalize_url(value: str) -> str:
    """Adiciona https:// quando o JSON traz a URL sem esquema."""
    value = value.strip().strip("<>").rstrip(".,")
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def extract_urls_from_fonte(fonte: str | None) -> list[str]:
    """
    Extrai URLs do campo 'fonte'.

    Exemplo do JSON:
      gov.br/saude/... ; DOU nº244...

    Somente a parte que parece URL é aproveitada.
    """
    if not fonte:
        return []

    pattern = re.compile(
        r"(?:(?:https?://)?(?:www\.)?"
        r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
        r"(?:/[^\s;,\]\)\"']*)?)",
        flags=re.IGNORECASE,
    )

    urls: list[str] = []

    for match in pattern.finditer(fonte):
        candidate = normalize_url(match.group(0))
        if candidate not in urls:
            urls.append(candidate)

    return urls


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text)
    return ascii_text.strip("_").lower()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def is_pdf(content: bytes, content_type: str | None = None) -> bool:
    """
    Validação principal: assinatura real do PDF.
    Não basta o servidor dizer application/pdf.
    """
    if content.startswith(b"%PDF-"):
        return True

    if content_type and "application/pdf" in content_type.lower():
        # Alguns servidores podem adicionar bytes antes do header.
        return b"%PDF-" in content[:1024]

    return False


def pdf_link_score(url: str, link_text: str) -> int:
    """
    Dá prioridade a links que realmente parecem apontar para
    PCDT, portaria, protocolo ou PDF.
    """
    u = url.lower()
    t = link_text.lower()

    score = 0

    if ".pdf" in u:
        score += 100

    keywords = (
        "pdf",
        "pcdt",
        "protocolo",
        "portaria",
        "download",
        "baixar",
        "documento",
        "anexo",
    )

    for keyword in keywords:
        if keyword in u:
            score += 10
        if keyword in t:
            score += 5

    return score


def find_pdf_url_in_html(html: str, page_url: str) -> str | None:
    parser = LinkParser()
    parser.feed(html)

    candidates: list[tuple[int, str]] = []

    for href, text in parser.links:
        absolute_url = urljoin(page_url, href)
        score = pdf_link_score(absolute_url, text)

        if score > 0:
            candidates.append((score, absolute_url))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def get_http_pdf_base_template(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    O YAML fornecido é usado como template de campos.

    Como este teste trabalha com PDFs, procuramos a base cujo
    acesso.tipo seja 'http_pdf'. Se não existir, retornamos um
    template vazio.
    """
    for base in manifest.get("bases", []) or []:
        if not isinstance(base, dict):
            continue

        acesso = base.get("acesso") or {}

        if isinstance(acesso, dict) and acesso.get("tipo") == "http_pdf":
            return base

    return {}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError("O manifesto informado não contém um objeto YAML válido.")

    return data


def load_protocol_documents(
    json_path: Path,
    diseases_to_process: list[str],
) -> list[ProtocolDocument]:
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("O arquivo JSON deve ter as doenças na raiz.")

    documents: list[ProtocolDocument] = []

    for disease in diseases_to_process:
        if disease not in data:
            print(f"[AVISO] Doença não encontrada no JSON: {disease}")
            continue

        entries = data[disease]

        if not isinstance(entries, list):
            continue

        for item in entries:
            if not isinstance(item, dict):
                continue

            fonte = item.get("fonte")
            urls = extract_urls_from_fonte(fonte)

            if not urls:
                print(
                    f"[AVISO] {disease}: nenhuma URL encontrada em 'fonte': "
                    f"{fonte!r}"
                )
                continue

            for source_url in urls:
                documents.append(
                    ProtocolDocument(
                        disease=disease,
                        versao_portaria=item.get("versao_portaria"),
                        data_inicio=item.get("data_inicio"),
                        data_fim=item.get("data_fim"),
                        status=item.get("status"),
                        confirmacao=item.get("confirmacao"),
                        fonte=fonte,
                        observacao=item.get("observacao"),
                        source_url=source_url,
                    )
                )

    return documents


def load_disease_list(json_path: Path) -> list[str]:
    """Retorna as doenças do JSON, com hepatite_c sempre em primeiro."""
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("O arquivo JSON deve ter as doenças na raiz.")

    diseases = list(data.keys())
    if "hepatite_c" in diseases:
        diseases.remove("hepatite_c")
        diseases.insert(0, "hepatite_c")

    return diseases


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
                "text/html,application/xhtml+xml,application/pdf,"
                "application/octet-stream;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
    )

    return session


def resolve_pdf(
    session: requests.Session,
    source_url: str,
) -> tuple[bytes, str, str]:
    """
    1. Acessa a URL existente no JSON.
    2. Se ela já for PDF, retorna o conteúdo.
    3. Se for HTML, procura um link para PDF.
    4. Baixa e valida o PDF encontrado.

    Retorna:
      (conteudo_pdf, url_final_pdf, content_type)
    """
    print(f"      acessando: {source_url}")

    response = session.get(
        source_url,
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")

    if is_pdf(response.content, content_type):
        return response.content, response.url, content_type

    # Se a primeira URL for uma página HTML, procura o PDF nela.
    html = response.text
    pdf_url = find_pdf_url_in_html(html, response.url)

    if not pdf_url:
        raise RuntimeError(
            "a URL abriu uma página HTML, mas nenhum link de PDF "
            "compatível foi encontrado"
        )

    print(f"      PDF encontrado na página: {pdf_url}")

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


def build_pdf_filename(document: ProtocolDocument) -> str:
    """
    Nome determinístico para facilitar comparação entre versões.
    """
    date = document.data_inicio or "sem_data"
    status = document.status or "sem_status"

    return (
        f"{slugify(document.disease)}"
        f"__{date}"
        f"__{slugify(status)}.pdf"
    )


def build_metadata(
    manifest: dict[str, Any],
    base_template: dict[str, Any],
    document: ProtocolDocument,
    final_url: str,
    local_pdf: Path,
    pdf_sha256: str,
    pdf_size: int,
) -> dict[str, Any]:
    """
    Monta um registro de metadados usando:
      - campos gerais do YAML;
      - campos da base http_pdf do YAML;
      - informações específicas do JSON;
      - informações obtidas durante o download.
    """
    acesso = base_template.get("acesso") or {}

    return {
        # Campos gerais do manifesto
        "scenario_id": manifest.get("scenario_id"),
        "manifest_version": manifest.get("version"),
        "description": manifest.get("description"),

        # Template da base definida no YAML
        "base_id": base_template.get("base_id"),
        "natureza": base_template.get("natureza"),
        "fonte": base_template.get("fonte"),
        "acesso": {
            "tipo": acesso.get("tipo") if isinstance(acesso, dict) else None,
            "url_origem": document.source_url,
            "url_pdf_resolvida": final_url,
        },
        "selecao_deterministica": base_template.get(
            "selecao_deterministica"
        ),
        "volume_alvo": base_template.get("volume_alvo"),
        "formato": base_template.get("formato"),
        "licenca": base_template.get("licenca"),
        "sensitivity_default": base_template.get(
            "sensitivity_default"
        ),
        "campo_vigencia": base_template.get("campo_vigencia"),
        "chunking_sugerido": base_template.get("chunking_sugerido"),
        "metadados_extras": base_template.get("metadados_extras"),

        # Informações vindas do JSON
        "doenca": document.disease,
        "versao_portaria": document.versao_portaria,
        "data_inicio": document.data_inicio,
        "data_fim": document.data_fim,
        "status": document.status,
        "confirmacao": document.confirmacao,
        "fonte_json": document.fonte,
        "observacao": document.observacao,

        # Informações do arquivo local
        "arquivo_pdf": str(local_pdf),
        "sha256": pdf_sha256,
        "tamanho_bytes": pdf_size,
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_failure_log(
    path: Path,
    selected_diseases: list[str],
    total: int,
    downloaded: int,
    failures: list[dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for failure in failures:
        grouped.setdefault(failure.get("doenca", "desconhecida"), []).append(
            failure
        )

    with path.open("w", encoding="utf-8") as file:
        file.write("GERAR CORPUS MANIFEST - LOG DE FALHAS\n")
        file.write(f"Gerado em: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        file.write(f"Doencas processadas: {', '.join(selected_diseases)}\n")
        file.write(f"Fontes encontradas: {total}\n")
        file.write(f"Downloads concluidos: {downloaded}\n")
        file.write(f"Falhas: {len(failures)}\n\n")

        if not failures:
            file.write("Nenhuma falha registrada.\n")
            return

        for disease, disease_failures in grouped.items():
            file.write(f"[{disease}] {len(disease_failures)} falha(s)\n")
            for failure in disease_failures:
                file.write(
                    f"- Versao: {failure.get('versao_portaria') or 'nao informada'}\n"
                )
                file.write(
                    f"  URL: {failure.get('acesso', {}).get('url_origem', '')}\n"
                )
                file.write(f"  Falha: {failure.get('erro', 'nao informada')}\n")
            file.write("\n")


def write_generated_manifest(
    path: Path,
    source_manifest: dict[str, Any],
    available_diseases: list[str],
    selected_diseases: list[str],
    documents: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    """Escreve o manifesto materializado que será consumido pelo RAG."""
    manifest = dict(source_manifest)
    manifest["generated_by"] = "src.gerar_corpus_manifest"
    manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["doencas_disponiveis"] = available_diseases
    manifest["doencas_processadas"] = selected_diseases
    manifest["documentos"] = documents
    manifest["falhas"] = failures

    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            manifest,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


# ---------------------------------------------------------------------------
# COMANDO FETCH
# ---------------------------------------------------------------------------
def run_fetch(
    manifest_path: Path,
    requested_diseases: list[str] | None,
) -> int:
    manifest_path = manifest_path.resolve()

    if not manifest_path.exists():
        print(f"[ERRO] Manifest não encontrado: {manifest_path}")
        return 2

    project_dir = manifest_path.parent

    json_path = project_dir / PROTOCOL_JSON_FILENAME

    if not json_path.exists():
        print(
            "[ERRO] JSON não encontrado.\n"
            f"Esperado em: {json_path}"
        )
        return 2

    manifest = load_manifest(manifest_path)
    available_diseases = load_disease_list(json_path)
    requested_set = set(requested_diseases or available_diseases)
    selected_diseases = [
        disease for disease in available_diseases
        if disease in requested_set
    ]

    unknown_diseases = [
        disease for disease in selected_diseases
        if disease not in available_diseases
    ]
    if unknown_diseases:
        print(
            "[ERRO] Doenças não encontradas no JSON: "
            + ", ".join(unknown_diseases)
        )
        return 2

    base_template = get_http_pdf_base_template(manifest)

    if not base_template:
        print(
            "[AVISO] Nenhuma base com acesso.tipo=http_pdf foi encontrada "
            "no YAML. Os campos do template serão salvos como null."
        )

    documents = load_protocol_documents(
        json_path=json_path,
        diseases_to_process=selected_diseases,
    )

    if not documents:
        print("[ERRO] Nenhum documento com URL foi encontrado.")
        return 3

    pdf_root = project_dir / PDF_DIRNAME
    metadata_paths: dict[str, Path] = {}

    for disease in selected_diseases:
        disease_dir = pdf_root / disease
        disease_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = disease_dir / METADATA_FILENAME
        if metadata_path.exists():
            metadata_path.unlink()
        metadata_paths[disease] = metadata_path

    session = build_session()

    total = len(documents)
    downloaded = 0
    failed = 0
    generated_documents: list[dict[str, Any]] = []
    generated_failures: list[dict[str, Any]] = []

    print("=" * 70)
    print("GERAR CORPUS MANIFEST")
    print("=" * 70)
    print(f"Manifest : {manifest_path}")
    print(f"JSON     : {json_path}")
    print(f"Doenças  : {', '.join(selected_diseases)}")
    print(f"Fontes   : {total}")
    print()

    for index, document in enumerate(documents, start=1):
        print(
            f"[{index}/{total}] "
            f"{document.versao_portaria or 'versão não informada'}"
        )

        try:
            content, final_url, content_type = resolve_pdf(
                session,
                document.source_url,
            )

            disease_dir = pdf_root / document.disease
            filename = build_pdf_filename(document)
            destination = disease_dir / filename

            destination.write_bytes(content)

            digest = sha256_bytes(content)

            metadata = build_metadata(
                manifest=manifest,
                base_template=base_template,
                document=document,
                final_url=final_url,
                local_pdf=destination.relative_to(project_dir).as_posix(),
                pdf_sha256=digest,
                pdf_size=len(content),
            )

            metadata["content_type"] = content_type

            append_jsonl(metadata_paths[document.disease], metadata)
            generated_documents.append(metadata)

            downloaded += 1

            print(f"      salvo: {destination}")
            print(f"      SHA256: {digest}")
            print()

        except Exception as exc:
            failed += 1

            error_record = build_metadata(
                manifest=manifest,
                base_template=base_template,
                document=document,
                final_url="",
                local_pdf=Path(""),
                pdf_sha256="",
                pdf_size=0,
            )

            error_record["erro"] = str(exc)

            append_jsonl(metadata_paths[document.disease], error_record)
            generated_failures.append(error_record)

            print(f"      [ERRO] {exc}")
            print()

        if index < total:
            time.sleep(REQUEST_DELAY_SECONDS)

    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Encontrados : {total}")
    print(f"Baixados    : {downloaded}")
    print(f"Falhas      : {failed}")
    print(f"PDFs        : {pdf_root}")
    print(f"Metadados   : {len(metadata_paths)} arquivo(s)")

    failure_log_path = project_dir / FAILURE_LOG_FILENAME
    write_failure_log(
        path=failure_log_path,
        selected_diseases=selected_diseases,
        total=total,
        downloaded=downloaded,
        failures=generated_failures,
    )
    print(f"Log falhas  : {failure_log_path}")

    if generated_failures:
        print("\nFALHAS POR DOENCA")
        failures_by_disease: dict[str, int] = {}
        for failure in generated_failures:
            disease = failure.get("doenca", "desconhecida")
            failures_by_disease[disease] = failures_by_disease.get(disease, 0) + 1

        for disease, disease_failures in failures_by_disease.items():
            print(f"\n - {disease}: {disease_failures} falha(s)")
            for failure in generated_failures:
                if failure.get("doenca") == disease:
                    print(
                        f"  {failure.get('versao_portaria') or 'versao nao informada'}: "
                        f"{failure.get('erro', 'falha nao informada')}"
                    )

    generated_manifest_path = project_dir / GENERATED_MANIFEST_FILENAME
    write_generated_manifest(
        path=generated_manifest_path,
        source_manifest=manifest,
        available_diseases=available_diseases,
        selected_diseases=selected_diseases,
        documents=generated_documents,
        failures=generated_failures,
    )
    print(f"Manifesto   : {generated_manifest_path}")

    # Não aborta todo o lote por uma URL ruim.
    # O erro fica registrado no metadata.jsonl.
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.gerar_corpus_manifest"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Descobre, valida e registra os PDFs do corpus.",
    )

    fetch_parser.add_argument(
        "--manifest",
        required=True,
        help="Caminho para corpus_manifest_template.yaml",
    )
    fetch_parser.add_argument(
        "--doencas",
        nargs="+",
        help=(
            "Doenças a processar. Sem este argumento, usa todas as doenças "
            "do JSON, com hepatite_c em primeiro."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        return run_fetch(Path(args.manifest), args.doencas)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
