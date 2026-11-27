#!/usr/bin/env python3
"""Compatibilidade STUDIO_ x HEIMDALL_: helper, leitor do .env, Ajustes (heimdall_config) e script de shell."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
falhas = 0


def confere(nome, cond):
    global falhas
    print(("ok   " if cond else "FALHA"), nome)
    if not cond:
        falhas += 1


import heimdall_envcompat as e
confere("interno troca STUDIO_ por HEIMDALL_", e.interno("STUDIO_LAB_PORT") == "HEIMDALL_LAB_PORT")
confere("interno deixa outros nomes", e.interno("HEIMDALL_X") == "HEIMDALL_X" and e.interno("LITELLM_MASTER_KEY") == "LITELLM_MASTER_KEY")

confere("Studio Hub: STUDIO_HUB_PORT vira HEIMDALL_MEMORY_PORT", e.interno("STUDIO_HUB_PORT") == "HEIMDALL_MEMORY_PORT" and e.interno("STUDIO_HUB") == "HEIMDALL_MEMORY")
confere("STUDIO_HUBX não é alias", e.interno("STUDIO_HUBBLE") == "HEIMDALL_HUBBLE")

import heimdall_config as c
tmp = Path(tempfile.mkdtemp()) / ".env"
tmp.write_text("STUDIO_LAB_PORT='8011'\nHEIMDALL_NEWS_PORT=8020\n# STUDIO_X=1\n", encoding="utf-8")
c.ARQUIVO = tmp
lido = {x["nome"]: x["valor"] for x in c.ler()}
confere("config.ler vê STUDIO_ como HEIMDALL_", lido.get("HEIMDALL_LAB_PORT") == "8011" and lido.get("HEIMDALL_NEWS_PORT") == "8020")
confere("config.salvar troca a linha STUDIO_ sem repetir", c.salvar("HEIMDALL_LAB_PORT", "9000") == "" and tmp.read_text().count("LAB_PORT") == 1)
confere("config.remover tira a linha STUDIO_", c.remover("HEIMDALL_LAB_PORT") == "" and "LAB_PORT" not in tmp.read_text())

env = {k: v for k, v in os.environ.items() if not k.startswith(("STUDIO_", "HEIMDALL_"))}
env.update({"STUDIO_TESTE_A": "novo", "HEIMDALL_TESTE_A": "velho", "HEIMDALL_TESTE_B": "so_antigo", "STUDIO_TESTE_C": "so novo com espaço"})
r = subprocess.run(["bash", "-c", f'source "{RAIZ}/scripts/studio_env.sh"; echo "$HEIMDALL_TESTE_A|$HEIMDALL_TESTE_B|$HEIMDALL_TESTE_C"'],
                   env=env, capture_output=True, text=True)
confere("shell: STUDIO_ vale também como HEIMDALL_ (STUDIO_ vence), antigo continua", r.stdout.strip() == "novo|so_antigo|so novo com espaço")
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
