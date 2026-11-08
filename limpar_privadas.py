#!/usr/bin/env python3
"""Apaga tudo o que o Second Brain guardou a partir de notas que depois foram para uma pasta privada.

Use depois de mover uma nota para a pasta "Privado" (ou outra listada em HEIMDALL_NOTAS_PRIVADAS) se ela já tinha
sido analisada antes. O agente do Mac precisa estar no ar. O script remove, só dessas notas:
  1. os pontos na base vetorial (Qdrant, coleção heimdall_notas);
  2. a cópia em Markdown em cerebro/heimdall-cerebro/;
  3. a nota espelho "Cérebro: <título>" na pasta "Heimdall Cérebro" do app Notas (vai para "Apagadas Recentemente").
A nota original nunca é tocada.

Uso (na pasta do projeto):   python3 limpar_privadas.py
Opção --so-listar mostra o que seria apagado, sem apagar nada.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SO_LISTAR = "--so-listar" in sys.argv
QDRANT = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
AGENTE = f"http://localhost:{os.environ.get('HEIMDALL_AGENTE_PORT', '8003')}"
COFRE = Path(os.environ.get("HEIMDALL_VAULT_DIR", str(AQUI / "cerebro"))).expanduser()
COLECAO = "heimdall_notas"


def token() -> str:
    t = os.environ.get("HEIMDALL_AGENTE_TOKEN", "")
    if t:
        return t
    try:
        for linha in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            m = re.match(r"^HEIMDALL_AGENTE_TOKEN=(['\"]?)(.*?)\1\s*$", linha)
            if m:
                return m.group(2)
    except OSError:
        pass
    sys.exit("Não achei HEIMDALL_AGENTE_TOKEN (nem no ambiente nem no .env).")


def http(url: str, dado=None, cabecalhos=None):
    req = urllib.request.Request(url, json.dumps(dado).encode() if dado is not None else None,
                                 {"Content-Type": "application/json", **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> None:
    try:
        priv = http(f"{AGENTE}/notas/privadas", cabecalhos={"X-Heimdall-Token": token()})
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Não consegui falar com o agente do Mac ({e}). Ele está no ar? curl -s {AGENTE}/saude")
    ids = set(priv["ids"])
    print(f"Pastas privadas: {', '.join(priv['pastas'])}. Notas protegidas: {len(ids)}.")
    if not ids:
        print("Nada a limpar.")
        return

    # 1. Base vetorial
    try:
        pontos, off = [], None
        while True:
            corpo = {"limit": 200, "with_payload": ["note_id", "titulo"], "with_vector": False}
            if off is not None:
                corpo["offset"] = off
            r = http(f"{QDRANT}/collections/{COLECAO}/points/scroll", corpo)["result"]
            pontos += r["points"]
            off = r.get("next_page_offset")
            if off is None:
                break
        alvo = [p for p in pontos if (p.get("payload") or {}).get("note_id") in ids]
        print(f"1. Base vetorial: {len(alvo)} ponto(s) de notas privadas.")
        for p in alvo:
            print(f"   - {p['payload'].get('titulo')}")
        if alvo and not SO_LISTAR:
            http(f"{QDRANT}/collections/{COLECAO}/points/delete?wait=true", {"points": [p["id"] for p in alvo]})
            print("   Apagados.")
    except Exception as e:  # noqa: BLE001
        print(f"1. Base vetorial: não consegui consultar ({e}).")

    # 2 e 3. Cópias em Markdown e notas espelho
    pasta = COFRE / "heimdall-cerebro"
    espelhos = []
    for f in sorted(pasta.glob("*.md")) if pasta.exists() else []:
        cab = f.read_text(encoding="utf-8", errors="replace")[:2000]
        m_id = re.search(r'^nota_id:\s*"(.*)"\s*$', cab, re.M)
        m_ti = re.search(r'^titulo:\s*(".*")\s*$', cab, re.M)
        if m_id and m_id.group(1) in ids:
            titulo = json.loads(m_ti.group(1)) if m_ti else ""
            espelhos.append((f, titulo))
    print(f"2. Arquivos do cofre: {len(espelhos)} de notas privadas.")
    for f, titulo in espelhos:
        print(f"   - {f.name}")
        if not SO_LISTAR:
            f.unlink()
    nomes = [f"Cérebro: {t}"[:190] for _, t in espelhos if t]
    print(f"3. App Notas: {len(nomes)} nota(s) espelho.")
    for n in nomes:
        print(f"   - {n}")
    if nomes and not SO_LISTAR:
        for n in nomes:
            script = ('on run argv\n  tell application "Notes"\n    delete (every note whose name is (item 1 of argv))\n'
                      '  end tell\nend run\n')
            r = subprocess.run(["osascript", "-e", script, n], capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                print(f"   (não consegui apagar '{n}': {r.stderr.strip()[:120]}; apague à mão em 'Heimdall Cérebro')")
        print("   Apagadas.")
    print("Pronto." if not SO_LISTAR else "Nada foi apagado (--so-listar).")


if __name__ == "__main__":
    main()
