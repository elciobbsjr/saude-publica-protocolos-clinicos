"""
Processador de arquivos Markdown (.md).

oque ele faz:
- Ler Markdown "normal" e Markdown parcialmente escapado/sujo.
- Preservar headings como contexto semântico durante o chunking.
- Converter tabelas Markdown em texto natural.
- Remover a formatação Markdown que não agrega valor ao embedding.
- Gerar chunks organizados.
      process_md(file_path, doc_type, sensitivity)
"""

import hashlib
import re
import uuid
from pathlib import Path


DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP = 200


def read_markdown(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Alguns arquivos podem ter BOM ou uma codificação ligeiramente diferente.
        return file_path.read_text(encoding="utf-8-sig")


def normalize_markdown(text: str) -> str:
    # Remove espaços invisíveis/problemáticos.
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Escapes comuns encontrados nos arquivos.
    text = text.replace(r"\|", "|")
    text = text.replace(r"\-", "-")
    text = text.replace(r"\+", "+")
    text = text.replace(r"\*", "*")
    text = text.replace(r"\_", "_")
    text = text.replace(r"\#", "#")

    # Corrige headings que foram colocados dentro de negrito:
    #
    # **# Título**
    # **## Seção**
    #
    # -> # Título
    # -> ## Seção
    text = re.sub(
        r"^\s*\*\*(#{1,6})\s*(.*?)\*\*\s*$",
        r"\1 \2",
        text,
        flags=re.MULTILINE,
    )

    # Também trata casos em que o fechamento não está na mesma linha.
    text = re.sub(
        r"^\s*\*\*(#{1,6})\s*(.*?)\*\*",
        r"\1 \2",
        text,
        flags=re.MULTILINE,
    )

    return text


def is_table_separator(line: str) -> bool:
    stripped = line.strip()

    if "|" not in stripped:
        return False

    cells = stripped.strip("|").split("|")

    if not cells:
        return False

    for cell in cells:
        cell = cell.strip()

        if not re.fullmatch(r":?-{3,}:?", cell):
            return False

    return True


def split_table_row(line: str) -> list[str]:
    line = line.strip()

    if line.startswith("|"):
        line = line[1:]

    if line.endswith("|"):
        line = line[:-1]

    return [cell.strip() for cell in line.split("|")]


def clean_inline_markdown(text: str) -> str:
    """
    Remove formatação Markdown de um trecho já identificado.

    A função não tenta interpretar headings/tabelas.
    Isso deve acontecer antes dela.
    """
    # Remove comentários HTML (ex: <!-- image -->)
    text = re.sub(r"<!--.*?-->", "", text)
    
    # Remove escapes que eventualmente tenham sobrado.
    text = re.sub(r"\\([\\`*_{}\[\]()#+.!|>~-])", r"\1", text)

    # Imagens:
    # ![alt](url) -> alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Links:
    # [texto](url) -> texto
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Código inline:
    # `texto` -> texto
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Negrito/itálico.
    # Fazemos várias passagens para lidar com combinações como **\*\*texto\*\***.
    for _ in range(3):
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"_(.*?)_", r"\1", text)

    # Marcadores de lista no início da linha.
    text = re.sub(r"^\s*[-*+]\s+", "", text)

    # Blockquote.
    text = re.sub(r"^\s*>\s?", "", text)

    # Heading que ainda tenha sobrado.
    text = re.sub(r"^\s*#{1,6}\s+", "", text)

    # Espaços duplicados.
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def table_to_text(lines: list[str]) -> str:
    """
    Converte uma tabela Markdown em texto natural.
    """

    if len(lines) < 2:
        return ""

    header = split_table_row(lines[0])
    rows = lines[2:]  # pula header + separador

    output = []

    for row_line in rows:
        values = split_table_row(row_line)

        if not values:
            continue

        # Evita problemas caso uma linha tenha quantidade diferente de colunas.
        pairs = []

        for index, value in enumerate(values):
            if index >= len(header):
                break

            field = clean_inline_markdown(header[index])
            value = clean_inline_markdown(value)

            if not field or not value:
                continue

            pairs.append(f"{field}: {value}.")

        if pairs:
            output.append(" ".join(pairs))

    return "\n\n".join(output)


def parse_markdown_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks = []
    current_content = []
    current_section = []
    current_heading = None

    def flush_content():
        nonlocal current_content

        if not current_content:
            return

        content = "\n".join(current_content).strip()

        if content:
            blocks.append(
                {
                    "type": "content",
                    "section": list(current_section),
                    "heading": current_heading,
                    "content": content,
                }
            )

        current_content = []

    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # Linha vazia encerra o bloco atual.
        if not stripped:
            flush_content()
            index += 1
            continue

        # ------------------------------------------------------------------------------------------------------------------
        # HEADING
        heading_match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", stripped)

        if heading_match:
            flush_content()

            level = len(heading_match.group(1))
            title = clean_inline_markdown(heading_match.group(2))

            # Remove níveis iguais ou mais profundos do contexto anterior.
            current_section = current_section[: level - 1]

            current_section.append(title)
            current_heading = title

            index += 1
            continue

        # ------------------------------------------------------------------------------------------------------------------
        # TABLE
        if (
            index + 1 < len(lines)
            and "|" in stripped
            and is_table_separator(lines[index + 1])
        ):
            flush_content()

            table_lines = [stripped, lines[index + 1].strip()]
            index += 2

            while index < len(lines):
                table_line = lines[index].strip()

                if not table_line or "|" not in table_line:
                    break

                table_lines.append(table_line)
                index += 1

            table_text = table_to_text(table_lines)

            if table_text:
                blocks.append(
                    {
                        "type": "table",
                        "section": list(current_section),
                        "heading": current_heading,
                        "content": table_text,
                    }
                )

            continue

        # ------------------------------------------------------------------------------------------------------------------
        # CONTEÚDO NORMAL
        current_content.append(stripped)
        index += 1

    flush_content()
    return blocks


def merge_small_blocks(
    blocks: list[dict],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """
    Junta blocos seguidos da MESMA seção enquanto o texto final couber
    em max_chars.

    Sem isso, cada parágrafo vira um chunk sozinho: um título solto
    (ex.: "Quadro 4 - Medicamentos...") fica num chunk e a tabela que
    vem logo depois fica em outro.

    Duas tabelas seguidas nunca são juntadas, para não misturar
    registros diferentes (ex.: medicamentos distintos da RENAME).
    """
    merged: list[dict] = []

    for block in blocks:
        if merged:
            previous = merged[-1]
            same_section = previous.get("section") == block.get("section")
            two_tables = (
                previous.get("type") == "table"
                and block.get("type") == "table"
            )

            if same_section and not two_tables:
                candidate = {
                    **previous,
                    "content": f"{previous['content']}\n\n{block['content']}",
                    "type": (
                        "table"
                        if "table" in (previous.get("type"), block.get("type"))
                        else "content"
                    ),
                }

                if len(build_block_text(candidate)) <= max_chars:
                    merged[-1] = candidate
                    continue

        merged.append(dict(block))

    return merged


def build_block_text(block: dict) -> str:
    """
    Monta o texto final de um bloco.
    O contexto dos headings é incluído no chunk para ajudar o embedding.
    """
    section = block.get("section", [])
    content = clean_inline_markdown(block.get("content", ""))

    if not content:
        return ""

    context = []
    for title in section:
        if title:
            context.append(title)

    if context:
        return "\n\n".join(context + [content])
    return content


def split_large_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:

    if len(text) <= max_chars:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            candidate = (
                f"{current}\n\n{paragraph}"
                if current
                else paragraph
            )
            if len(candidate) <= max_chars:
                current = candidate
                continue

        # Salva o que já acumulamos.
        if current:
            chunks.append(current)
            current = ""

        # Parágrafo maior que o limite.
        if len(paragraph) > max_chars:
            sentences = re.split(
                r"(?<=[.!?])\s+",
                paragraph,
            )

            sentence_chunk = ""

            for sentence in sentences:
                if not sentence:
                    continue

                candidate = (
                    f"{sentence_chunk} {sentence}"
                    if sentence_chunk
                    else sentence
                )

                if len(candidate) <= max_chars:
                    sentence_chunk = candidate
                else:
                    if sentence_chunk:
                        chunks.append(sentence_chunk.strip())

                    sentence_chunk = sentence

            if sentence_chunk:
                current = sentence_chunk.strip()

        else:
            current = paragraph

    if current:
        chunks.append(current)

    # Overlap simples entre chunks.
    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped = [chunks[0]]

    for index in range(1, len(chunks)):
        previous = chunks[index - 1]

        # Pega o final do chunk anterior sem quebrar a palavra.
        overlap_text = previous[-overlap:]

        if " " in overlap_text:
            overlap_text = overlap_text[
                overlap_text.find(" ") + 1:
            ]

        combined = f"{overlap_text} {chunks[index]}".strip()

        if len(combined) <= max_chars + overlap:
            overlapped.append(combined)
        else:
            overlapped.append(chunks[index])

    return overlapped


def process_md(
        file_path,
        doc_type,
        folder_metadata: dict = None,  # <- Adicionado parâmetro para receber o metadado
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap: int = DEFAULT_OVERLAP,
) -> list[dict]:
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo Markdown não encontrado: {file_path}")

    if file_path.suffix.lower() != ".md":
        raise ValueError(f"O process_md espera um arquivo .md: {file_path}")

    raw_text = read_markdown(file_path)
    if not raw_text.strip():
        return []

    normalized_text = normalize_markdown(raw_text)
    blocks = merge_small_blocks(
        parse_markdown_blocks(normalized_text),
        max_chars=max_chars,
    )
    chunks = []
    global_chunk_index = 1

    if folder_metadata is None:
        folder_metadata = {}

    # chunk_id determinístico: o mesmo documento (SHA-256 + nome do
    # arquivo de origem) e a mesma posição geram sempre o mesmo id.
    # Sem SHA-256, mantém o id aleatório (comportamento anterior).
    source_sha256 = folder_metadata.get("source_sha256")
    document_id = None

    if source_sha256:
        source_file = folder_metadata.get("source_file") or ""
        document_id = hashlib.sha256(
            f"{source_sha256}|{source_file}".encode("utf-8")
        ).hexdigest()[:16]

    for block in blocks:
        block_text = build_block_text(block)

        if not block_text:
            continue

        block_chunks = split_large_text(
            block_text,
            max_chars=max_chars,
            overlap=overlap,
        )



        for text in block_chunks:
            # Mesclando os dados básicos com o metadata.json da pasta
            metadata = {
                "doc_type": doc_type,
                "chunk_id": (
                    f"{document_id}_{global_chunk_index:04d}"
                    if document_id
                    else uuid.uuid4().hex
                ),
                "chunk_index": global_chunk_index,
                "file_name": file_path.name,
                **folder_metadata,
            }
            chunks.append(
                {
                    "texto": text,
                    "section": block.get("heading"),
                    "metadata": metadata,
                }
            )

            global_chunk_index += 1
    return chunks