#!/usr/bin/env python3
"""Teste do Notes sem estudos: com STUDIO_LEARN=1 os temas de knowledge/ e os livros do cofre ficam só no Learn;
o Notes mostra triagem, diários e privacidade. STUDIO_LEARN=0 devolve tudo. Convidado não entra no Notes.

    python3 tests/notes/teste_notas_sem_estudos.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="notas_sem_estudos_"))
cofre, conh = tmp / "cerebro", tmp / "knowledge"
for p in (cofre / "triagem", cofre / "diarios", cofre / "python", conh / "python", conh / "ingles"):
    p.mkdir(parents=True)
(cofre / "triagem" / "a.md").write_text("# a\n", encoding="utf-8")
(cofre / "python" / "b.md").write_text("# b\n", encoding="utf-8")
os.environ["STUDIO_VAULT_DIR"], os.environ["STUDIO_KNOWLEDGE_DIR"] = str(cofre), str(conh)
os.environ["STUDIO_LEARN"] = "1"

import heimdall_notas as n  # noqa: E402
import heimdall_usuarios as u  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else "\n     " + extra))
    falhas += 0 if ok else 1


p = n.pastas()
confere("com o Learn ligado, os temas de estudo saem do Notes", "python" not in p and "ingles" not in p, str(sorted(p)))
confere("triagem e diários continuam", "triagem" in p and "diarios" in p, str(sorted(p)))
os.environ["STUDIO_LEARN"] = "0"
p = n.pastas()
confere("com STUDIO_LEARN=0 os estudos voltam", "python" in p and "ingles" in p, str(sorted(p)))
confere("Notes não é dado a convidado", u.SERVICOS["notas"][3] is False)
print("TUDO OK" if not falhas else f"{falhas} FALHA(S)")
raise SystemExit(1 if falhas else 0)
