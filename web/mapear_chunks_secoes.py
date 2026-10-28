"""Experimento offline: associa chunks existentes a secoes de Markdown.

Executar da raiz do projeto:
 python web/mapear_chunks_secoes.py --zip data/raw/v7/md_pdf.zip

Somente leitura; nao chama embeddings/LLM, nao altera src/ nem indices.
A correspondencia e aproximada: revisar confianca baixa e empates.
"""
import argparse
import csv
import json
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

DOCS = {
    'artrite_reumatoide': 'artrite_reumatoide__2026-01-19__vigente',
    'artrite_idiopatica_juvenil': 'artrite_idiopatica_juvenil__2026-01-19__vigente',
}
HEAD = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)

def normalizar(s):
    s = unicodedata.normalize('NFKD', s.lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.findall(r'[a-z0-9]+', s)

def shingles(tokens, n=5):
    return set(tuple(tokens[i:i+n]) for i in range(max(0, len(tokens)-n+1)))

def extrair_chunks(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('texto'), str) and isinstance(obj.get('metadata'), dict):
            yield obj
            return
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from extrair_chunks(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from extrair_chunks(v)

def secoes_md(md):
    hits = list(HEAD.finditer(md))
    secoes = []
    for i, h in enumerate(hits):
        fim = hits[i+1].start() if i+1 < len(hits) else len(md)
        secoes.append({'ordem': i+1, 'nivel': len(h.group(1)), 'titulo': h.group(2).strip(),
                       'texto': md[h.end():fim].strip()})
    return secoes

def carregar_chunks(path):
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    saida = []
    vistos = set()
    for chunk in extrair_chunks(obj):
        cid = str(chunk['metadata'].get('chunk_id', ''))
        if cid and cid not in vistos:
            saida.append((cid, chunk['texto']))
            vistos.add(cid)
    return saida

def associar(texto, secoes_indexadas):
    tokens = normalizar(texto)
    grams = shingles(tokens)
    pontuacoes = []
    for secao, sec_grams in secoes_indexadas:
        comum = len(grams & sec_grams)
        pontuacoes.append((comum / max(len(grams), 1), comum, secao))
    pontuacoes.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if not pontuacoes:
        return None, 0, 0, 'sem_secoes'
    melhor, nmatch, secao = pontuacoes[0]
    segundo = pontuacoes[1][0] if len(pontuacoes) > 1 else 0
    if len(grams) == 0 or nmatch < 2 or melhor < 0.15:
        qualidade = 'baixa'
    elif melhor >= 0.65 and melhor - segundo >= 0.10:
        qualidade = 'alta'
    elif melhor >= 0.30 and melhor - segundo >= 0.05:
        qualidade = 'media'
    else:
        qualidade = 'revisar'
    return secao, melhor, segundo, qualidade

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', default='data/raw/v7/md_pdf.zip')
    parser.add_argument('--chunks-dir', default='output/output_chunking/v7/protocolos')
    parser.add_argument('--saida', default='web/associacao_chunks_secoes.csv')
    args = parser.parse_args()
    linhas = []
    with zipfile.ZipFile(args.zip) as z:
        for doenca, base in DOCS.items():
            md_name = f'protocolos/{doenca}/{base}.md'
            json_path = Path(args.chunks_dir) / doenca / f'{base}.json'
            if md_name not in z.namelist():
                print(f'AVISO: Markdown ausente: {md_name}')
                continue
            if not json_path.is_file():
                print(f'AVISO: JSON de chunks ausente: {json_path}')
                continue
            md = z.read(md_name).decode('utf-8-sig', errors='replace')
            secoes = secoes_md(md)
            indexadas = [(s, shingles(normalizar(s['texto']))) for s in secoes]
            chunks = carregar_chunks(json_path)
            contagem = Counter()
            for cid, texto in chunks:
                secao, score, segundo, qualidade = associar(texto, indexadas)
                contagem[qualidade] += 1
                linhas.append({
                    'doenca': doenca, 'chunk_id': cid, 'caracteres_chunk': len(texto),
                    'ordem_secao': secao['ordem'] if secao else '',
                    'titulo_secao': secao['titulo'] if secao else '',
                    'score': f'{score:.3f}', 'segundo_score': f'{segundo:.3f}',
                    'confianca': qualidade,
                })
            print(f'\n{doenca}: {len(chunks)} chunks, {len(secoes)} secoes')
            print('Qualidade da associacao:', dict(contagem))
            alvos = range(55, 60) if doenca == 'artrite_reumatoide' else (40, 41)
            for n in alvos:
                achados = [r for r in linhas if r['doenca'] == doenca and r['chunk_id'].endswith(f'_{n:04d}')]
                if achados:
                    r = achados[0]
                    print(f"  _{n:04d}: {r['titulo_secao']} | score={r['score']} | {r['confianca']}")
                else:
                    print(f'  _{n:04d}: NAO ENCONTRADO')
    if not linhas:
        raise SystemExit('Nenhum chunk analisado. Confira --chunks-dir e --zip.')
    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=';')
        w.writeheader()
        w.writerows(linhas)
    print(f'\nCSV: {destino.resolve()}')
    print('IMPORTANTE: nao aplicar filtros ainda; revisar correspondencias de baixa confianca.')

if __name__ == '__main__':
    main()
