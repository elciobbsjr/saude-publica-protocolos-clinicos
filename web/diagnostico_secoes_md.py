"""Diagnostico exploratorio de secoes dos Markdown de protocolos, sem alterar corpus.
Uso: python web/diagnostico_secoes_md.py --zip md_pdf.zip
"""
import argparse
import csv
import re
import zipfile
from pathlib import Path

HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)
CLINICO = re.compile(r'tratamento|terap[eê]utic|f[aá]rmac|medicamen|monitor|diagn[oó]stic|crit[eé]ri|contraindica|inclus[aã]o|exclus[aã]o|dose|posolog|fluxograma|ap[eê]ndice|anexo|interrup|suspens', re.I)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', default='md_pdf.zip', help='Arquivo zip contendo os Markdown')
    ap.add_argument('--saida', default='web/resultado_secoes_md.csv')
    args = ap.parse_args()
    zpath = Path(args.zip)
    if not zpath.is_file():
        raise SystemExit(f'Arquivo nao encontrado: {zpath}. Passe --zip com caminho correto.')
    linhas = []
    with zipfile.ZipFile(zpath) as z:
        nomes = sorted(n for n in z.namelist() if n.startswith('protocolos/') and n.lower().endswith('.md'))
        for nome in nomes:
            conteudo = z.read(nome).decode('utf-8-sig', errors='replace')
            titulos = list(HEADING.finditer(conteudo))
            if not titulos:
                linhas.append(dict(arquivo=nome, ordem=0, nivel='', titulo='SEM TITULOS MARKDOWN', caracteres=len(conteudo), classificacao='revisao_manual'))
                continue
            for i, match in enumerate(titulos):
                fim = titulos[i+1].start() if i+1 < len(titulos) else len(conteudo)
                titulo = match.group(2).strip()
                linhas.append(dict(arquivo=nome, ordem=i+1, nivel=len(match.group(1)), titulo=titulo, caracteres=len(conteudo[match.end():fim].strip()), classificacao='candidata_clinica' if CLINICO.search(titulo) else 'revisar'))
    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['arquivo','ordem','nivel','titulo','caracteres','classificacao'], delimiter=';')
        writer.writeheader()
        writer.writerows(linhas)
    print(f'Markdown de protocolos: {len(nomes)}')
    print(f'Secoes identificadas: {len(linhas)}')
    print(f'CSV: {destino.resolve()}')
    print('ATENCAO: classificacao apenas exploratoria, sem exclusao automatica.')
    for row in linhas:
        if 'artrite_reumatoide__2026' in row['arquivo']:
            print(f"[{row['ordem']:02}] {row['titulo']} ({row['caracteres']} caracteres) - {row['classificacao']}")

if __name__ == '__main__':
    main()
