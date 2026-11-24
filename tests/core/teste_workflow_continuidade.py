#!/usr/bin/env python3
"""Confere o workflow do GitHub Actions que implanta a continuidade: só na main, com teste do Worker, trava de gasto e sem segredo escrito no arquivo."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / ".github" / "workflows" / "deploy-continuidade.yml").exists())
_sys.path.insert(0, str(RAIZ))
import re
import sys

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {detalhe}"))
    falhas += 0 if ok else 1


t = (RAIZ / ".github" / "workflows" / "deploy-continuidade.yml").read_text(encoding="utf-8")
linhas = [l for l in t.splitlines() if not l.lstrip().startswith("#")]
corpo = "\n".join(linhas)
confere("roda só ao avançar a main (e manualmente)", "branches: [main]" in corpo and "workflow_dispatch:" in corpo and "branches: [develop" not in corpo)
confere("só roda se mudou o que entra na imagem ou o Worker", all(x in corpo for x in ('"*.py"', '"cloudflare/continuity/**"', '".dockerignore"')))
confere("testa o Worker antes de implantar", corpo.index("teste_continuity.mjs") < corpo.index("wrangler deploy"))
confere("confere o bloqueio de gasto em Workers e Durable Objects antes de implantar", "usage_block" in corpo and "durable_objects" in corpo and corpo.index("usage_block") < corpo.index("wrangler deploy"))
confere("preserva o interruptor da continuidade (--off) ao implantar", "--var CONTINUIDADE:" in corpo and "interruptor" in corpo)
confere("uma implantação por vez e permissão mínima", "cancel-in-progress: false" in corpo and "contents: read" in corpo)
confere("segredos só por secrets.*, nenhum valor escrito no arquivo", len(re.findall(r"\$\{\{ secrets\.[A-Z_]+ \}\}", corpo)) >= 4 and not re.search(r"(?i)(token|secret|senha)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{24,}", corpo))
print("\nTUDO OK" if not falhas else f"\n{falhas} FALHA(S)")
sys.exit(1 if falhas else 0)
