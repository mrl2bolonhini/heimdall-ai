#!/usr/bin/env python3
"""Avisos nativos no Mac: fila local, texto completo (saúde e finanças incluídos) só no Mac, Bark continua genérico, interruptor STUDIO_AVISOS_MAC=0.

    python3 tests/agent/teste_avisos_mac.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["STUDIO_DB_DIR"] = tmp
os.environ.pop("STUDIO_AVISOS_MAC", None)
import studio_avisos_mac as mac  # noqa: E402
import studio_alertas as alertas  # noqa: E402
import studio_bark as bk  # noqa: E402
import studio_banco as _banco  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


pasta = Path(tmp) / "alerts"
confere("publicar grava um JSON na pasta de avisos", mac.publicar({"title": "Olá", "body": "Corpo completo", "group": "teste", "level": "timeSensitive"}))
arqs = list(pasta.glob("*.json"))
confere("um arquivo, sem temporário sobrando", len(arqs) == 1 and not list(pasta.glob(".*.tmp")))
d = json.loads(arqs[0].read_text(encoding="utf-8"))
confere("campos do Bark viram titulo, corpo, grupo, nivel", d["titulo"] == "Olá" and d["corpo"] == "Corpo completo" and d["grupo"] == "teste" and d["nivel"] == "timeSensitive", d)
confere("pasta 700 e arquivo 600", oct(pasta.stat().st_mode & 0o777) == "0o700" and oct(arqs[0].stat().st_mode & 0o777) == "0o600")
mac.publicar({"title": "x", "level": "inventado"})
confere("nível desconhecido vira active", any(json.loads(a.read_text())["nivel"] == "active" for a in pasta.glob("*.json")))
confere("aviso vazio é recusado", mac.publicar({}) is False and mac.publicar("texto") is False)
os.environ["STUDIO_AVISOS_MAC"] = "0"
antes = len(list(pasta.glob("*.json")))
confere("STUDIO_AVISOS_MAC=0 desliga", mac.publicar({"title": "não"}) is False and len(list(pasta.glob("*.json"))) == antes)
os.environ.pop("STUDIO_AVISOS_MAC")

# alertas: o Bark segue genérico (com o link do produto); o Mac recebe título e resumo completos, mesmo de saúde
os.environ["STUDIO_AVISOS_DIR"] = tmp
enviados = []
bk.enviar_bark = lambda p: enviados.append(p) or True
for a in pasta.glob("*.json"):
    a.unlink()
r = alertas.publicar({"id": "teste|1", "titulo": "Resultado do hemograma", "resumo": "Glicose 62 mg/dL, abaixo da faixa", "nivel": "alto", "fonte": "saude"})
confere("alerta de saúde é novo e vai ao Mac", r["novo"] and r["mac"], r)
arq = [json.loads(a.read_text()) for a in pasta.glob("*.json")]
confere("Mac: título e resumo completos", any("hemograma" in a["titulo"] and "Glicose 62" in a["corpo"] for a in arq), arq)
confere("Mac: leva o link do produto", any(a.get("url", "").startswith("https://health.") for a in arq), arq)
confere("Bark: genérico, sem título nem resumo do exame, com link", len(enviados) == 1 and "hemograma" not in json.dumps(enviados[0]) and "Glicose" not in json.dumps(enviados[0]) and enviados[0].get("url"), enviados)
r2 = alertas.publicar({"id": "teste|1", "titulo": "Resultado do hemograma", "resumo": "x", "fonte": "saude"})
confere("mesma origem não repete o aviso", not r2["novo"] and len(enviados) == 1)
r3 = alertas.publicar({"id": "teste|2", "titulo": "Menção no diário", "resumo": "Processo 123", "nivel": "critico", "fonte": "justica"})
confere("alerta sem produto próprio: Mac completo e Bark genérico com link do Miner", r3["novo"] and r3["mac"] and enviados[-1].get("url", "").endswith("/cidadania") and "Processo" not in json.dumps(enviados[-1]), enviados[-1])
os.environ["STUDIO_MINER"] = "0"
r4 = alertas.publicar({"id": "teste|3", "titulo": "Outra menção", "resumo": "Processo 456", "nivel": "alto", "fonte": "justica"})
confere("Miner desligado: Bark genérico sem link", r4["novo"] and "url" not in enviados[-1] and "Processo" not in json.dumps(enviados[-1]), enviados[-1])
os.environ.pop("STUDIO_MINER", None)
confere("sem lembrete: o alerta não toca a agenda", "lembrete" not in r3 and "lembrete" not in r)

sys.exit(1 if falhas else 0)
