#!/usr/bin/env python3
"""Teste dos estudos por dia na agenda do Learn: 3 por dia (6h, 13h, 20h) em pastas sorteadas, ajuste 0 a 3, sem repetir no mesmo horário.

    python3 tests/learn/teste_learn_estudos_dia.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import random
import tempfile
from datetime import datetime
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="learn_estudos_dia_"))
os.environ["STUDIO_DB_DIR"] = str(tmp / "db")
os.environ["STUDIO_KNOWLEDGE_DIR"] = str(tmp / "knowledge")
os.environ["STUDIO_LEARN"] = "1"
import studio_learn_dados as dados  # noqa: E402
import studio_learn_cards as cards  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else "\n     " + extra))
    falhas += 0 if ok else 1


p1 = dados.criar_pasta("Python", categoria="sequencial", tipo=dados.listar_tipos()[0]["nome"] if isinstance(dados.listar_tipos()[0], dict) else dados.listar_tipos()[0])
dados.importar_documento(p1["caminho"], "livro.md", ("# Livro\n\n" + "Python usa indentação para blocos de código. " * 80).encode())
dados.criar_pasta("Vazia", categoria="sequencial", tipo=p1["tipo"])   # sem material: deve ser pulada
avisos = []
mod = lambda sistema, usuario, max_tokens=300: "Qual a ideia principal do trecho?"   # noqa: E731
nt = lambda t, c, r: avisos.append(t)   # noqa: E731
rng = random.Random(1)
hoje0 = datetime.now().replace(hour=5, minute=0)
confere("antes das 6h não faz estudo", cards.executar_agenda(hoje0, mod, mod, nt, rng) == [])
r = cards.executar_agenda(hoje0.replace(hour=6, minute=5), mod, mod, nt, rng)
confere("às 6h faz o primeiro estudo, na pasta com material", len(r) == 1 and r[0].startswith("estudo python"), str(r))
confere("não repete no mesmo horário", cards.executar_agenda(hoje0.replace(hour=6, minute=30), mod, mod, nt, rng) == [])
confere("às 13h faz o segundo", len(cards.executar_agenda(hoje0.replace(hour=13), mod, mod, nt, rng)) == 1)
confere("às 20h faz o terceiro", len(cards.executar_agenda(hoje0.replace(hour=20), mod, mod, nt, rng)) == 1)
confere("no máximo três por dia", cards.executar_agenda(hoje0.replace(hour=23), mod, mod, nt, rng) == [])
linhas = dados.conectar().execute("SELECT origem, estado FROM estudos").fetchall()
confere("os três ficam com origem agenda e esperando resposta", len(linhas) == 3 and all(l["origem"] == "agenda" and l["estado"] == "perguntado" for l in linhas))
confere("avisou três vezes", len(avisos) == 3, str(avisos))
dados.definir_ajuste("estudos_dia", "0")
confere("ajuste 0 não faz estudo", cards.executar_agenda(hoje0.replace(hour=21), mod, mod, nt, rng) == [])
dados.definir_ajuste("estudos_dia", "1")
hoje = datetime.now().replace(hour=21, minute=0)
c0 = dados.conectar(); c0.execute("DELETE FROM estudos"); c0.commit()   # a data gravada é a de verdade; recomeça o dia
ra = cards.executar_agenda(hoje, mod, mod, nt, rng); rb = cards.executar_agenda(hoje.replace(hour=22), mod, mod, nt, rng)
confere("ajuste 1 faz só um por dia", len(ra) == 1 and rb == [], str((ra, rb)))
try:
    dados.definir_ajuste("estudos_dia", "9")
    confere("ajuste inválido é recusado", False)
except dados.ErroLearn:
    confere("ajuste inválido é recusado", True)
print("TUDO OK" if not falhas else f"{falhas} FALHA(S)")
raise SystemExit(1 if falhas else 0)
