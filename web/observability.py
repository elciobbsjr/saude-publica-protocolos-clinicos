import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def configurar_logging():
    logger = logging.getLogger()

    if getattr(logger, "_rag_web_configurado", False):
        return

    logger.setLevel(logging.INFO)

    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] "
        "%(name)s: %(message)s"
    )

    arquivo = RotatingFileHandler(
        LOG_DIR / "rag_web.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    arquivo.setFormatter(formato)
    logger.addHandler(arquivo)

    logger._rag_web_configurado = True