#!/usr/bin/env python3
"""Testa o nó de aviso do fluxo de segurança (flows/advanced/19-seguranca.json) com Node: aviso de gravidade média ou alta traz o significado e o que fazer; sem gravidade, nada."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import shutil
import subprocess
import sys

NODE = shutil.which("node")
if not NODE:
    print("pulado: o Node não está instalado nesta máquina.")
    sys.exit(0)
NOS = {n["name"]: n for n in json.loads((RAIZ / "flows/advanced/19-seguranca.json").read_text(encoding="utf-8"))["nodes"]}
CODIGO = NOS["Decidir aviso"]["parameters"]["jsCode"]
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def rodar(entrada):
    js = "const $input = { first: () => ({ json: " + json.dumps(entrada) + " }) };\nconst f = () => {\n" + CODIGO + "\n};\nconsole.log(JSON.stringify(f()));"
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return [x["json"] for x in json.loads(r.stdout)]


a = rodar({"ok": True, "tarefa": "exposicao", "gravidade": "alta", "linha": "Porta 8022 aberta para a rede."})[0]
confere("exposição alta: significado e o que fazer no aviso e na triagem", "O que significa:" in a["linha"] and "O que fazer:" in a["triagem"]["resumo"] and a["urgente"] is True, a)
confere("título da triagem sem o texto de contexto", a["triagem"]["titulo"] == "Exposição do Mac: Porta 8022 aberta para a rede.", a["triagem"]["titulo"])
b = rodar({"ok": True, "tarefa": "logs", "gravidade": "media", "linha": "Três falhas de login."})[0]
confere("logs médios explicam o que fazer", "Uma ou duas ocorrências" in b["linha"] and b["urgente"] is False, b)
confere("sem gravidade: nenhum aviso", rodar({"ok": True, "tarefa": "commits", "gravidade": "nenhuma"}) == [])
print(f"\n{falhas} falha(s)")
sys.exit(1 if falhas else 0)
