import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega o .env localizado na raiz
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Endpoints e modelos oficiais do Grande Desafio
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ecoa-llm.duckdns.org:11434/v1")
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "qcwind/qwen3-8b-instruct-Q4-K-M")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "xagi/qwen3-embedding:0.6b-q4_k_m")