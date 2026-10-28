"""Experimento offline: Top 10 observado + dois chunks seguintes do mesmo documento.
Executar na raiz do repositorio: python web/teste_2_vizinhos.py
Nao altera src/, nao chama LLM ou embeddings.
"""
import json
import re
from pathlib import Path
from time import perf_counter

ARQUIVO = Path('output/output_chunking/v7/protocolos/artrite_reumatoide/artrite_reumatoide__2026-01-19__vigente.json')
TOP10 = [54, 66, 51, 50, 87, 88, 64, 52, 53, 62]  # evidencias observadas na interface v0.2
ALVOS = set(range(55, 60))
N_VIZINHOS = 2  # dois seguintes, nao dois de cada lado

def extrair_chunks(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('texto'), str) and isinstance(obj.get('metadata'), dict):
            yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from extrair_chunks(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from extrair_chunks(v)

def numero_chunk(c):
    cid = str(c.get('metadata', {}).get('chunk_id', ''))
    m = re.search(r'_(\d+)$', cid)
    return int(m.group(1)) if m else None

def main():
    inicio = perf_counter()
    if not ARQUIVO.exists():
        raise SystemExit(f'Arquivo nao encontrado: {ARQUIVO}\nExecute na raiz do repositorio.')
    corpus = json.loads(ARQUIVO.read_text(encoding='utf-8'))
    chunks = {}
    for c in extrair_chunks(corpus):
        n = numero_chunk(c)
        if n is not None:
            chunks[n] = c
    if not chunks:
        raise SystemExit('Nao foram encontrados chunks com metadata.chunk_id e texto. Confira o formato JSON.')
    ausentes = [n for n in TOP10 if n not in chunks]
    if ausentes:
        raise SystemExit(f'Chunks Top 10 nao encontrados no JSON: {ausentes}. Confira se e o corpus da consulta.')
    selecionados = list(TOP10)
    for n in TOP10:
        for deslocamento in range(1, N_VIZINHOS + 1):
            vizinho = n + deslocamento
            if vizinho in chunks and vizinho not in selecionados:
                selecionados.append(vizinho)
    cobertura = sorted(ALVOS.intersection(selecionados))
    faltantes = sorted(ALVOS.difference(selecionados))
    caracteres = sum(len(chunks[n]['texto']) for n in selecionados)
    print('Pergunta: Qual o tratamento recomendado para artrite reumatoide?')
    print(f'Corpus AR: {len(chunks)} chunks')
    print(f'Top 10 original: {TOP10}')
    print(f'Vizinhos por chunk: {N_VIZINHOS} seguintes')
    print(f'Selecao final sem duplicatas ({len(selecionados)}): {selecionados}')
    print(f'Cobertura 55-59: {len(cobertura)}/5 -> {cobertura}')
    print(f'Alvos ausentes: {faltantes}')
    print(f'Caracteres de contexto: {caracteres}')
    print(f'Tokens estimados (caracteres/4, aproximacao): {round(caracteres/4)}')
    print(f'Tempo de expansao e leitura local: {perf_counter()-inicio:.3f} s')
    print('OBS: tempo acima NAO inclui a recuperacao hibrida; Top 10 foi fixado do resultado observado.')

if __name__ == '__main__':
    main()
