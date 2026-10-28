"""
Testes do merge_small_blocks (src/chunking/process_md.py).

Garante que título solto e tabela da mesma seção ficam no mesmo chunk,
sem misturar seções diferentes nem duas tabelas seguidas.
Roda offline, sem LLM.
"""

from src.chunking.process_md import merge_small_blocks, process_md


def _bloco(conteudo, secao=("6. TRATAMENTO",), tipo="content"):
    return {
        "type": tipo,
        "section": list(secao),
        "heading": secao[-1],
        "content": conteudo,
    }


def test_titulo_do_quadro_fica_junto_da_tabela():
    blocos = [
        _bloco("Quadro 4 - Medicamentos para o tratamento de AR"),
        _bloco("Medicamento: Metotrexato. Posologia: 7,5 a 25 mg, 1x/semana.", tipo="table"),
    ]
    resultado = merge_small_blocks(blocos)
    assert len(resultado) == 1
    assert "Quadro 4" in resultado[0]["content"]
    assert "Metotrexato" in resultado[0]["content"]


def test_secoes_diferentes_nao_sao_juntadas():
    blocos = [
        _bloco("Texto da primeira etapa.", secao=("6.2.1 Primeira etapa",)),
        _bloco("Texto da segunda etapa.", secao=("6.2.2 Segunda etapa",)),
    ]
    assert len(merge_small_blocks(blocos)) == 2


def test_duas_tabelas_seguidas_nao_sao_juntadas():
    blocos = [
        _bloco("Medicamento: A.", tipo="table"),
        _bloco("Medicamento: B.", tipo="table"),
    ]
    assert len(merge_small_blocks(blocos)) == 2


def test_respeita_o_limite_de_caracteres():
    blocos = [_bloco("x" * 900), _bloco("y" * 900), _bloco("z" * 900)]
    resultado = merge_small_blocks(blocos, max_chars=1800)
    assert len(resultado) == 3


def test_process_md_nao_gera_chunk_so_de_titulo(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(
        "## 6.2.5 Esquemas de administração\n\n"
        "Quadro 4 - Medicamentos para o tratamento de AR\n\n"
        "| Medicamento | Posologia |\n"
        "|---|---|\n"
        "| Metotrexato | 7,5 a 25 mg, 1x/semana |\n",
        encoding="utf-8",
    )
    chunks = process_md(md, "protocolo", folder_metadata={"source_sha256": "a" * 64, "source_file": "doc.pdf"})
    assert len(chunks) == 1
    assert "Quadro 4" in chunks[0]["texto"]
    assert "Metotrexato" in chunks[0]["texto"]
