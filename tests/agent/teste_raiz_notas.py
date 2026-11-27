#!/usr/bin/env python3
"""Testa a raiz Studio Hub do app Notas: caminhos, nomes antigos aceitos, laço evitado e a cópia sem apagar nada (sem Mac)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
os.environ.pop("STUDIO_NOTAS_RAIZ", None)
import heimdall_agente as ag  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


confere("raiz nova", ag.RAIZ_NOTAS == "Studio Hub" and ag.RAIZ_ANTIGA == "Heimdall-ai")
confere("digest vai para a raiz nova", ag.caminho_notas("Digest") == "Studio Hub/Digest")
confere("tema de estudo vai para Estudos", ag.caminho_notas("python") == "Studio Hub/Estudos/python")
confere("nome antigo de finanças grava na pasta nova", ag.caminho_notas("Heimdall Finanças") == "Studio Hub/Studio Finance")
confere("nome antigo do catálogo grava na pasta nova", ag.caminho_notas("Heimdall Notas") == "Studio Hub/Catálogo")
confere("nome antigo do digest cai na pasta atual", ag.caminho_notas("Heimdall Digest") == "Studio Hub/Digest")
confere("raiz nova, raiz antiga e pastas novas nunca são lidas como fonte",
        all(ag.pasta_ignorada(n) for n in ("Studio Hub", "Heimdall-ai", "Studio Finance", "Catálogo", "Heimdall Notas")))
confere("pasta pessoal comum continua lida", not ag.pasta_ignorada("Receitas") and not ag.pasta_ignorada("Notas"))
confere("nenhum nome do caminho novo leva Heimdall", "heimdall" not in ag.caminho_notas("Heimdall Finanças").lower())

import mover_notas_antigas as mv  # noqa: E402

destinos = [d for _, d in mv.MAPA]
confere("destinos todos dentro da raiz nova", all(d.startswith("Studio Hub/") for d in destinos))
confere("só copia: o script não move nem apaga", "move" not in mv.AS_COPIAR.split("on run")[1].lower() and "delete" not in mv.AS_COPIAR.lower())
confere("cria nota nova e pula as que já existem", "make new note" in mv.AS_COPIAR and "jaTem does not contain" in mv.AS_COPIAR)
confere("origem da raiz antiga está no mapa", (f"{ag.RAIZ_ANTIGA}/Saúde", "Studio Hub/Saúde") in mv.MAPA and ("Heimdall Finanças", "Studio Hub/Studio Finance") in mv.MAPA)
sys_exit = 1 if falhas else 0
print("FALHAS:", falhas)
raise SystemExit(sys_exit)
