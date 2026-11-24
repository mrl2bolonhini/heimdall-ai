#!/usr/bin/env python3
"""Teste do modo enxuto do Open WebUI (start_heimdall.sh): variáveis, interruptores e documentação."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import re
import shutil
import subprocess

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:400])


start = (RAIZ / "start_heimdall.sh").read_text(encoding="utf-8")
bloco = start[start.index("WEBUI_ENXUTO=()"):start.index("ghcr.io/open-webui/open-webui:main > /dev/null")]
for var in ("ENABLE_NOTES=False", "ENABLE_AUTOMATIONS=False", "ENABLE_IMAGE_GENERATION=False", "ENABLE_CODE_EXECUTION=False",
            "ENABLE_CODE_INTERPRETER=False", "ENABLE_AUTOCOMPLETE_GENERATION=False", "ENABLE_TAGS_GENERATION=False",
            "ENABLE_FOLLOW_UP_GENERATION=False", "ENABLE_TITLE_GENERATION=False", "AUDIO_STT_ENGINE=webapi"):
    confere("o modo enxuto define " + var, var in bloco)
confere("o contêiner recebe as opções do modo enxuto", '${WEBUI_ENXUTO[@]+"${WEBUI_ENXUTO[@]}"}' in bloco)
confere("o modo enxuto liga por padrão e o 0 desliga", 'HEIMDALL_WEBUI_ENXUTO:-1}" != "0"' in bloco)
confere("embeddings externos só com HEIMDALL_WEBUI_EMBEDDING=ollama", 'HEIMDALL_WEBUI_EMBEDDING:-}" = "ollama"' in bloco and "RAG_EMBEDDING_ENGINE=ollama" in bloco)
confere("os títulos têm interruptor próprio", 'HEIMDALL_WEBUI_TITULOS:-0}" = "1"' in bloco)

# Executa só o trecho de montagem das opções, com combinações do .env.
bash = shutil.which("bash")
trecho = bloco[:bloco.index("docker run -d --name open-webui")]


def montar(**env):
    exportar = " ".join(f"export {k}={v};" for k, v in env.items())
    cmd = f'{exportar} {trecho}\nprintf "%s\\n" "${{WEBUI_ENXUTO[@]}}"'
    r = subprocess.run([bash, "-c", cmd], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l and not l.startswith("     ")] if r.returncode == 0 else None


if bash:
    padrao = montar()
    confere("padrão: Notas e Automações desligadas", padrao is not None and "ENABLE_NOTES=False" in padrao and "ENABLE_AUTOMATIONS=False" in padrao, padrao)
    confere("padrão: sem embeddings externos", padrao is not None and not any(l.startswith("RAG_") for l in padrao), padrao)
    zero = montar(HEIMDALL_WEBUI_ENXUTO=0)
    confere("HEIMDALL_WEBUI_ENXUTO=0: nenhuma opção extra", zero == [], zero)
    titulos = montar(HEIMDALL_WEBUI_TITULOS=1)
    confere("HEIMDALL_WEBUI_TITULOS=1 mantém os títulos", titulos is not None and "ENABLE_TITLE_GENERATION=False" not in titulos and "ENABLE_NOTES=False" in titulos, titulos)
    emb = montar(HEIMDALL_WEBUI_EMBEDDING="ollama")
    confere("embedding=ollama usa o modelo padrão", emb is not None and "RAG_EMBEDDING_MODEL=nomic-embed-text" in emb and "RAG_EMBEDDING_ENGINE=ollama" in emb, emb)
    emb2 = montar(HEIMDALL_WEBUI_EMBEDDING="ollama", HEIMDALL_WEBUI_EMBEDDING_MODELO="outro")
    confere("embedding=ollama aceita outro modelo", emb2 is not None and "RAG_EMBEDDING_MODEL=outro" in emb2, emb2)
else:
    print("pulado: bash não encontrado")

import heimdall_config_ajuda as aj
ajuda = str(getattr(aj, "AJUDA", "")) or (RAIZ / "heimdall_config_ajuda.py").read_text(encoding="utf-8")
for v in ("HEIMDALL_WEBUI_ENXUTO", "HEIMDALL_WEBUI_TITULOS", "HEIMDALL_WEBUI_EMBEDDING", "HEIMDALL_WEBUI_EMBEDDING_MODELO"):
    confere("a ajuda do .env descreve " + v, v in ajuda)
for arq in ("CHANGELOG.md", "guides/heimdall_ajuda.txt", "gerar_docs.py"):
    confere(arq + " cita o modo enxuto", "HEIMDALL_WEBUI_ENXUTO" in (RAIZ / arq).read_text(encoding="utf-8"))
# O README é gerado por gerar_docs.py e mostra a descrição, sem a coluna com o nome da variável.
confere("README.md descreve o modo enxuto", "modo enxuto" in (RAIZ / "README.md").read_text(encoding="utf-8"))

print(f"\n{falhas} falha(s)")
_sys.exit(1 if falhas else 0)
