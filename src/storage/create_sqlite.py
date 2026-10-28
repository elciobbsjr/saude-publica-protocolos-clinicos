"""Cria o banco SQLite do corpus SIH agregado a partir do JSONL."""

# python -m src.storage.create_sqlite


import hashlib
import json
import sqlite3
from pathlib import Path

import yaml



ROOT_DIR = Path(__file__).resolve().parent.parent.parent

JSONL = ROOT_DIR / "output" /"corpus_sih" /"corpus_sih_agregados_rag.jsonl"
MANIFESTO = ROOT_DIR / "corpus_manifest_sih.yaml"
BANCO = Path("output/sqlite/corpus_sih.db")

# Pode ser melhorado aqui
SCHEMA = """
CREATE TABLE documentos (
    id                      TEXT PRIMARY KEY,
    texto                   TEXT NOT NULL,
    doenca                  TEXT,
    periodo                 TEXT,
    granularidade_temporal  TEXT,
    nivel                   TEXT,
    dimensao_geografica     TEXT,
    regiao_atendimento      TEXT,
    uf_atendimento          TEXT,
    internacoes             INTEGER,
    obitos                  INTEGER,
    letalidade_percentual   REAL,
    metadata_json           TEXT NOT NULL
);

CREATE INDEX idx_doenca  ON documentos(doenca);
CREATE INDEX idx_periodo ON documentos(periodo);
CREATE INDEX idx_uf      ON documentos(uf_atendimento);
CREATE INDEX idx_regiao  ON documentos(regiao_atendimento);
"""


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _verificar_manifesto() -> None:
    """Confere se o JSONL é o mesmo arquivo descrito no manifesto."""
    manifesto = yaml.safe_load(MANIFESTO.read_text(encoding="utf-8"))
    esperado = manifesto["documentos"][0]["sha256"]
    obtido = _sha256(JSONL)

    if obtido != esperado:
        raise ValueError(
            f"SHA256 não confere.\n  esperado: {esperado}\n  obtido:   {obtido}"
        )
    print("SHA256 conferido com o manifesto.")


def _to_int(valor):
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(round(valor))
    try:
        return int(str(valor).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _to_float(valor):
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def _ler_linhas(caminho: Path):
    """Gera uma tupla (id, texto, metadata) por linha válida do JSONL."""
    with open(caminho, "r", encoding="utf-8") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except json.JSONDecodeError as erro:
                raise ValueError(f"JSON inválido na linha {numero}: {erro}") from erro

            if not obj.get("id") or not obj.get("text"):
                raise ValueError(f"Linha {numero} sem 'id' ou 'text'.")

            yield obj["id"], obj["text"], obj.get("metadata") or {}


def criar_banco() -> None:
    _verificar_manifesto()

    BANCO.parent.mkdir(parents=True, exist_ok=True)
    if BANCO.exists():
        BANCO.unlink()  # recria do zero: o script é idempotente

    conn = sqlite3.connect(BANCO)
    try:
        conn.executescript(SCHEMA)

        linhas = []
        for id_, texto, meta in _ler_linhas(JSONL):
            linhas.append((
                id_,
                texto,
                meta.get("doenca"),
                str(meta.get("periodo")) if meta.get("periodo") is not None else None,
                meta.get("granularidade_temporal"),
                meta.get("nivel"),
                meta.get("dimensao_geografica"),
                meta.get("regiao_atendimento"),
                meta.get("uf_atendimento"),
                _to_int(meta.get("internacoes")),
                _to_int(meta.get("obitos")),
                _to_float(meta.get("letalidade_percentual")),
                json.dumps(meta, ensure_ascii=False),
            ))

        conn.executemany(
            "INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            linhas,
        )
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
        print(f"Banco criado em {BANCO}: {total} documentos.")
    finally:
        conn.close()


if __name__ == "__main__":
    criar_banco()