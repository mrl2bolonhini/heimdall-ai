#!/usr/bin/env python3
"""Testa a migração do nome antigo das pastas de dados (dados_financas para finance) e a organização do repositório."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from pathlib import Path

import heimdall_pastas as hp

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


d = Path(tempfile.mkdtemp())
(d / "dados_financas").mkdir()
(d / "dados_financas" / "financas.db").write_text("dados")
r = hp.finance(d)
confere("só a pasta antiga existe: renomeia para finance", r == d / "finance" and not (d / "dados_financas").exists())
confere("os dados vão junto (mesma pasta, só mudou o nome)", (d / "finance" / "financas.db").read_text() == "dados")
confere("chamar de novo não muda nada", hp.finance(d) == d / "finance" and (d / "finance" / "financas.db").exists())

d2 = Path(tempfile.mkdtemp())
confere("sem nenhuma pasta: devolve finance sem criar", hp.finance(d2) == d2 / "finance" and not (d2 / "finance").exists())

d3 = Path(tempfile.mkdtemp())
(d3 / "dados_financas").mkdir()
(d3 / "finance").mkdir()
(d3 / "finance" / "novo.txt").write_text("n")
(d3 / "dados_financas" / "velho.txt").write_text("v")
confere("as duas existem: não mexe em nenhuma", hp.finance(d3) == d3 / "finance" and (d3 / "dados_financas" / "velho.txt").exists() and (d3 / "finance" / "novo.txt").exists())

# organização do repositório
soltos = [p.name for p in RAIZ.iterdir() if p.is_file() and (p.name.startswith(("teste_", "test_")) or p.name.startswith("LEIAME_") or p.name.startswith("prompt_chat_"))]
confere("nenhum teste, guia LEIAME ou prompt solto na raiz", not soltos, ", ".join(soltos))
confere("nenhuma pasta com o nome antigo no repositório", not any((RAIZ / n).exists() for n in ("n8n_flows", "n8n_flows_avancados", "n8n_flows_monitor", "jogos")))
sys.exit(1 if falhas else 0)
