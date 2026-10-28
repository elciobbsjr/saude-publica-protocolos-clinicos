"""Registra cada consulta do pipeline em um arquivo JSON dentro de output/results."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

PASTA_RESULTS = Path("output/results")


def save_response(registro: dict[str, Any], pasta: Path = PASTA_RESULTS) -> Path:
    """Grava o registro da consulta em um JSON próprio e retorna o caminho do arquivo."""
    pasta.mkdir(parents=True, exist_ok=True)

    agora = datetime.now()
    id_consulta = f"{agora:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"

    registro_final = {
        "id": id_consulta,
        "timestamp": agora.isoformat(timespec="seconds"),
        **registro,
    }

    caminho = pasta / f"{id_consulta}.json"
    caminho.write_text(
        json.dumps(registro_final, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return caminho