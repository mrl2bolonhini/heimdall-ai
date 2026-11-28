#!/usr/bin/env python3
"""Testa o nó de aviso do fluxo dos diários oficiais (flows/monitor/11-diarios-oficiais.json) rodando-o com Node: o aviso da Justiça traz o que o tipo de ato
significa e o que conferir, o nível urgente é mantido e a fonte indisponível continua avisando."""
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
NOS = {n["name"]: n for n in json.loads((RAIZ / "flows/monitor/11-diarios-oficiais.json").read_text(encoding="utf-8"))["nodes"]}
CODIGO = NOS["Itens de triagem"]["parameters"]["jsCode"]
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def rodar(entradas):
    js = "const itens = " + json.dumps([{"json": e} for e in entradas]) + ";\nconst $input = { all: () => itens };\nconst f = () => {\n" + CODIGO + "\n};\nconsole.log(JSON.stringify(f()));"
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return [x["json"] for x in json.loads(r.stdout)]


s = rodar([{"registros": [{"fonte": "justica", "id": "j1", "titulo": "Intimação de audiência", "data": "2026-11-26", "trecho": "Processo 123 designada audiência"}]}])[0]
confere("aviso traz o que significa e o que fazer", "O que significa:" in s["resumo"] and "Audiência" in s["resumo"] and "O que fazer:" in s["resumo"] and "homônimo" in s["resumo"], s)
confere("audiência é crítica", s["nivel"] == "critico", s["nivel"])
s2 = rodar([{"registros": [{"fonte": "justica", "id": "j2", "titulo": "Publicação genérica", "data": "2026-11-26", "trecho": "texto"}]}])[0]
confere("sem tipo reconhecido: explicação geral", "cita um termo que você acompanha" in s2["resumo"] and s2["nivel"] == "alto", s2)
s3 = rodar([{"registros": [{"fonte": "justica", "id": "j3", "titulo": "Citação CANCELADA", "trecho": "x"}]}])[0]
confere("cancelada mantém nível médio", s3["nivel"] == "medio", s3)
s4 = rodar([{"aviso24": True, "duracao": "24 horas", "corpo": "A fonte não respondeu."}])[0]
confere("fonte indisponível continua avisando", s4["fonte"] == "diarios" and s4["nivel"] == "alto", s4)
print(f"\n{falhas} falha(s)")
sys.exit(1 if falhas else 0)
