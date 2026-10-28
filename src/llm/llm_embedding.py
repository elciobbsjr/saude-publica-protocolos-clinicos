"""
Converte texto em embedding (vetor numérico) usando o servidor da ECOA
(endpoint compatível com a API da OpenAI).

Funções principais:
    get_embedding(text)           -> embedding de um único texto
    get_embeddings_batch(texts)   -> embeddings de vários textos, enviados em
                                     lotes (batches) menores, com retry automático

O endereço e o modelo vêm do config.py (OLLAMA_URL e EMBEDDING_MODEL).
Seguindo o enunciado (seção 2.1), os lotes têm 50 textos e há uma pausa
de 10 segundos entre eles, porque o servidor é compartilhado pela turma.

Erros transitórios (timeout, conexão, 429, 5xx) são repetidos com backoff
exponencial. Erros definitivos (ex.: 400, 404) falham imediatamente.
"""

import random
import time
from typing import List, Optional

import requests

from config import EMBEDDING_MODEL, OLLAMA_URL

# Configuração
EMBEDDINGS_URL = f"{OLLAMA_URL.rstrip('/')}/embeddings"
API_KEY = "ollama"        # o servidor da ECOA não exige chave real
TIMEOUT = 60

BATCH_SIZE = 50           # quantidade de textos por requisição (enunciado, seção 2.1)
PAUSA_ENTRE_LOTES = 10.0  # segundos entre um lote e outro (enunciado, seção 2.1)
MAX_RETRIES = 5           # tentativas por requisição
RETRY_BASE_DELAY = 2.0    # segundos (2, 4, 8, 16...)
RETRY_MAX_DELAY = 60.0    # teto do backoff
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class EmbeddingError(Exception):
    """Erro ao obter embeddings do servidor da ECOA."""


def _retry_after_seconds(response: requests.Response) -> Optional[float]:
    """Lê o header Retry-After (em segundos), se existir."""
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _post_with_retry(
        payload: dict,
        timeout: int = TIMEOUT,
        max_retries: int = MAX_RETRIES,
) -> dict:
    """Faz o POST ao servidor de embeddings com retry e backoff exponencial."""
    last_error = "erro desconhecido"

    for attempt in range(1, max_retries + 1):
        retry_after = None

        try:
            response = requests.post(
                EMBEDDINGS_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )

            if response.status_code in RETRYABLE_STATUS:
                retry_after = _retry_after_seconds(response)
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"

            elif not response.ok:
                # Erro definitivo (400, 401, 402, 404...): não adianta tentar de novo
                raise EmbeddingError(f"Erro da API de embeddings: {response.status_code} - {response.text[:500]}")

            else:
                data = response.json()
                # A API pode devolver 200 com {"error": ...} no corpo
                if data.get("data"):
                    return data
                last_error = f"Resposta sem dados de embedding: {str(data)[:200]}"

        except requests.exceptions.Timeout:
            last_error = f"Timeout após {timeout}s"
        except requests.exceptions.ConnectionError:
            last_error = "Erro de conexão com o servidor de embeddings"
        except ValueError:  # JSON inválido na resposta
            last_error = "Resposta da API não é um JSON válido"

        if attempt < max_retries:
            delay = retry_after or min(RETRY_MAX_DELAY, RETRY_BASE_DELAY * 2 ** (attempt - 1))
            delay += random.uniform(0, 1)  # jitter
            print(f"    [retry {attempt}/{max_retries - 1}] {last_error} — aguardando {delay:.1f}s")
            time.sleep(delay)

    raise EmbeddingError(f"Falha após {max_retries} tentativas. Último erro: {last_error}")


def get_embedding(
        text: str,
        model: Optional[str] = None,
        timeout: int = TIMEOUT,
        max_retries: int = MAX_RETRIES,
) -> List[float]:
    """Retorna o embedding de um único texto."""
    if not text or not text.strip():
        raise ValueError("O texto não pode estar vazio")

    data = _post_with_retry(
        {"model": model or EMBEDDING_MODEL, "input": text},
        timeout=timeout,
        max_retries=max_retries,
    )
    return data["data"][0]["embedding"]


def get_embeddings_batch(
        texts: List[str],
        model: Optional[str] = None,
        timeout: int = TIMEOUT,
        batch_size: int = BATCH_SIZE,
        max_retries: int = MAX_RETRIES,
) -> List[List[float]]:
    """
    Retorna os embeddings de uma lista de textos, na mesma ordem da entrada.

    A lista é dividida em lotes de `batch_size` textos, e cada lote é uma
    requisição separada (com retry próprio). Se um lote falhar após todas as
    tentativas, a exceção EmbeddingError é propagada.
    """
    if not texts:
        raise ValueError("Lista de textos não pode estar vazia")
    if batch_size < 1:
        raise ValueError("batch_size deve ser >= 1")

    model = model or EMBEDDING_MODEL
    total_batches = (len(texts) + batch_size - 1) // batch_size
    all_embeddings: List[List[float]] = []

    for batch_number, start in enumerate(range(0, len(texts), batch_size), start=1):
        if batch_number > 1:
            time.sleep(PAUSA_ENTRE_LOTES)  # pausa entre lotes para não sobrecarregar o servidor

        batch = texts[start:start + batch_size]
        print(f"    Batch {batch_number}/{total_batches} ({len(batch)} textos)")

        data = _post_with_retry(
            {"model": model, "input": batch},
            timeout=timeout,
            max_retries=max_retries,
        )

        # Ordena por índice para garantir ordem correta dentro do lote
        items = sorted(data["data"], key=lambda x: x["index"])

        if len(items) != len(batch):
            raise EmbeddingError(
                f"O batch {batch_number} retornou {len(items)} embeddings, esperado {len(batch)}"
            )

        all_embeddings.extend(item["embedding"] for item in items)

    return all_embeddings