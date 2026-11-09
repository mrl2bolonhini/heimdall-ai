#!/usr/bin/env python3
"""Limpa o que o Second Brain criou por engano a partir de notas do próprio Heimdall.

Quando o app Notas não informa a pasta de uma nota, o Second Brain antigo analisava os seus próprios
espelhos ("Cérebro: ...") e os digests ("Digest AAAA-MM-DD HHh") como se fossem notas suas. Este script
remove só isso, em três lugares, e não toca nas suas notas:
  1. a base vetorial (Qdrant, coleção heimdall_notas): pontos cujo título começa com "Cérebro:" ou "Digest ";
  2. os arquivos cerebro-cerebro-*.md e cerebro-digest-*.md do cofre (~/heimdall-ai/cerebro/heimdall-cerebro);
  3. as notas "Cérebro: Cérebro: ..." e "Cérebro: Digest ..." no app Notas (vão para "Apagadas Recentemente").

Uso (na pasta do projeto):   python3 limpar_espelhos.py
Opção --so-listar mostra o que seria apagado, sem apagar nada.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

QDRANT = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLECAO = "heimdall_notas"
COFRE = Path(os.environ.get("HEIMDALL_VAULT_DIR", str(Path(__file__).resolve().parent / "cerebro"))).expanduser()
RUIM = re.compile(r"^(C[ée]rebro: |Digest \d{4}-\d{2}-\d{2} \d{2}h$)")
SO_LISTAR = "--so-listar" in sys.argv


def qdrant(caminho: str, dado: dict) -> dict:
    req = urllib.request.Request(
        f"{QDRANT}/collections/{COLECAO}/points{caminho}", json.dumps(dado).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def limpar_qdrant() -> None:
    try:
        pontos, proximo = [], None
        while True:
            corpo = {"limit": 200, "with_payload": ["titulo"], "with_vector": False}
            if proximo is not None:
                corpo["offset"] = proximo
            r = qdrant("/scroll", corpo)["result"]
            pontos += r["points"]
            proximo = r.get("next_page_offset")
            if proximo is None:
                break
    except Exception as e:  # noqa: BLE001
        print(f"1. Base vetorial: não consegui consultar ({e}). O Qdrant está no ar?")
        return
    ids = [p["id"] for p in pontos if RUIM.match(str((p.get("payload") or {}).get("titulo", "")))]
    print(f"1. Base vetorial: {len(pontos)} ponto(s) no total, {len(ids)} a apagar.")
    for p in pontos:
        t = str((p.get("payload") or {}).get("titulo", ""))
        if RUIM.match(t):
            print(f"   - {t}")
    if ids and not SO_LISTAR:
        qdrant("/delete?wait=true", {"points": ids})
        print("   Apagados.")


def limpar_arquivos() -> None:
    pasta = COFRE / "heimdall-cerebro"
    alvos = sorted(list(pasta.glob("cerebro-cerebro-*.md")) + list(pasta.glob("cerebro-digest-*.md")))
    print(f"2. Arquivos do cofre: {len(alvos)} a apagar.")
    for f in alvos:
        print(f"   - {f.name}")
        if not SO_LISTAR:
            f.unlink()


def limpar_notas() -> None:
    script = (
        'tell application "Notes"\n'
        '  set n to 0\n'
        '  set alvos to (every note whose name starts with "Cérebro: Cérebro:" or name starts with "Cérebro: Digest ")\n'
        '  repeat with x in alvos\n'
        '    set n to n + 1\n'
        '    set nm to (get name of x)\n'
        '    log nm\n'
        + ('' if SO_LISTAR else '    delete x\n') +
        '  end repeat\n'
        '  return n as string\n'
        'end tell\n'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        print(f"3. App Notas: não consegui executar ({e}).")
        return
    if r.returncode != 0:
        print(f"3. App Notas: erro ({r.stderr.strip()[:200]}). Apague à mão na pasta 'Cérebro' as notas que começam com 'Cérebro: Cérebro:' ou 'Cérebro: Digest'.")
        return
    nomes = [l for l in r.stderr.splitlines() if l.strip()]
    print(f"3. App Notas: {r.stdout.strip() or 0} nota(s) {'encontrada(s)' if SO_LISTAR else 'apagada(s)'}.")
    for n in nomes:
        print(f"   - {n}")


if __name__ == "__main__":
    limpar_qdrant()
    limpar_arquivos()
    limpar_notas()
    print("Pronto." if not SO_LISTAR else "Nada foi apagado (--so-listar).")
