#!/usr/bin/env python3
"""Testa as funções de leitura das notas (studio_notas.py), usadas pela aba Notas do Studio Hub, com um cofre de mentira."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
import unicodedata as ud
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hub-leitura-"))
cofre, conh = TMP / "cofre", TMP / "conh"
(cofre / "python").mkdir(parents=True)
conh.mkdir()
(cofre / "python" / "a.md").write_text("# Aula 1: listas\n\nIntrodução a listas em Python, com exemplos.\n\n- item um\n- item dois\n", encoding="utf-8")
os.environ.update({"STUDIO_VAULT_DIR": str(cofre), "STUDIO_KNOWLEDGE_DIR": str(conh), "STUDIO_LEARN": "0"})
import studio_notas as n  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


confere("a pasta do cofre aparece como tema", "python" in n.pastas(), str(list(n.pastas())))
notas = n.notas_da_pasta("python")
confere("a nota é listada", len(notas) == 1, str(notas))
confere("contexto das notas traz trecho da nota", "Aula 1" in n.contexto_notas("introdução listas"))
confere("busca acha a nota", any("python" in str(x) for x in n.busca("listas")))
longo = "palavra " * 30
cor = n.inicio_do_titulo(longo)
confere("título longo é cortado num espaço, com reticências", cor.endswith("…") and len(cor) <= 112, cor)
confere("título curto não muda", n.inicio_do_titulo("Aula curta") == "Aula curta")
confere("Markdown vira lista em HTML", "<li>item um</li>" in n.markdown_html("- item um\n- item dois\n"))
confere("HTML da nota é escapado", "<script>" not in n.markdown_html("<script>alert(1)</script>"))
confere("título inteiro não é suspeito", n.motivos_de_corte("Média móvel simples") == [])
confere("título cortado é suspeito", bool(n.motivos_de_corte("Arquitetura de data lakes com Glue e")))
confere("acentos decompostos (macOS) não geram falso alarme", n.motivos_de_corte(ud.normalize("NFD", "Estudo 2026-11-10 06h: Fundamentos")) == [])
confere("caminho fora da pasta é recusado", n.doc_seguro(conh, "../x.md") is None)
print("TUDO OK" if not falhas else f"{falhas} FALHA(S)")
raise SystemExit(1 if falhas else 0)
