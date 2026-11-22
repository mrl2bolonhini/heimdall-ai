#!/usr/bin/env python3
"""Teste do monitor da Cloudflare (heimdall_cfmonitor.py), sem rede e sem token real.

    python3 tests/cloud/teste_cfmonitor.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import heimdall_cfmonitor as cm  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


ENV = {"CLOUDFLARE_API_TOKEN": "segredo-de-teste", "CLOUDFLARE_ACCOUNT_ID": "b" * 32}
AGORA = datetime(2026, 11, 21, 19, 40, tzinfo=timezone.utc)


class Resp:
    def __init__(self, c): self._c = json.dumps(c).encode()
    def read(self, n=-1): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False


visto = {}


def abrir_ok(req, timeout):
    visto["h"], visto["corpo"] = {k.lower(): v for k, v in req.header_items()}, json.loads(req.data)
    return Resp({"data": {"viewer": {"accounts": [{"r": [
        {"count": 2, "sum": {"cost": 0.0001, "tokensIn": 157, "tokensOut": 99, "erroredRequests": 0, "cachedRequests": 0}, "dimensions": {"model": "@cf/openai/gpt-oss-120b", "date": "2026-11-21"}},
        {"count": 10, "sum": {"cost": 0.02, "tokensIn": 9000, "tokensOut": 3000, "erroredRequests": 1, "cachedRequests": 0}, "dimensions": {"model": "@cf/openai/gpt-oss-120b", "date": "2026-11-20"}},
        {"count": 1, "sum": {"cost": 0.5, "tokensIn": 100, "tokensOut": 50, "erroredRequests": 0, "cachedRequests": 0}, "dimensions": {"model": "outro", "date": "2026-11-20"}}]}]}}, "errors": None})


r = cm.consultar(30, env=ENV, abrir=abrir_ok, agora=AGORA)
t = r["total"]
confere("soma requisições, tokens e custo", r["ok"] and t["requisicoes"] == 13 and t["tokens_in"] == 9257 and t["tokens_out"] == 3149 and abs(t["custo"] - 0.5201) < 1e-9 and t["erros"] == 1, t)
confere("agrupa por modelo, do mais caro ao mais barato", [m["modelo"] for m in r["por_modelo"]] == ["outro", "@cf/openai/gpt-oss-120b"] and r["por_modelo"][1]["requisicoes"] == 12)
confere("agrupa por dia, do mais recente ao mais antigo", [d["dia"] for d in r["por_dia"]] == ["2026-11-21", "2026-11-20"] and r["por_dia"][1]["requisicoes"] == 11)
confere("pede só o gateway heimdall e o período certo", visto["corpo"]["variables"]["g"] == "heimdall" and visto["corpo"]["variables"]["s"] == "2026-10-22T19:00:00Z" and visto["corpo"]["variables"]["e"] == "2026-11-21T19:00:00Z", visto["corpo"]["variables"])
confere("manda o token como Bearer e identifica o programa", visto["h"]["authorization"] == "Bearer segredo-de-teste" and visto["h"]["user-agent"] == "heimdall-ai/1.0")
confere("o período fica entre 1 e 31 dias", cm.consultar(99, env=ENV, abrir=abrir_ok, agora=AGORA)["dias"] == 31 and cm.consultar(0, env=ENV, abrir=abrir_ok, agora=AGORA)["dias"] == 1)
tx = cm.texto(r, ligada=True)
confere("texto: estado, totais, teto e tabelas", "Nuvem LIGADA" in tx and "13 requisições" in tx and "US$ 0.52" in tx and "de US$ 10.00 por mês (5.2%)" in tx and "Por modelo:" in tx and "Por dia" in tx, tx)
confere("texto nunca mostra o token", "segredo-de-teste" not in tx)

vazio = cm.consultar(7, env=ENV, abrir=lambda q, t: Resp({"data": {"viewer": {"accounts": [{"r": []}]}}, "errors": None}), agora=AGORA)
confere("sem uso: zeros e aviso, sem inventar valor", vazio["ok"] and vazio["total"]["custo"] == 0 and "Ainda não há uso" in cm.texto(vazio, ligada=False))


def abrir_403(req, timeout):
    raise urllib.error.HTTPError(req.full_url, 403, "x", {}, io.BytesIO(b"{}"))


erro = cm.consultar(30, env=ENV, abrir=abrir_403, agora=AGORA)
confere("HTTP 403: explica a permissão que falta", not erro["ok"] and "Account Analytics" in erro["erro"] and "segredo-de-teste" not in erro["erro"], erro)
erro = cm.consultar(30, env=ENV, abrir=lambda q, t: Resp({"data": None, "errors": [{"message": "not authorized to access this resource"}]}), agora=AGORA)
confere("erro de GraphQL por autorização vira o mesmo aviso", not erro["ok"] and "Account Analytics" in erro["erro"], erro)
erro = cm.consultar(30, env=ENV, abrir=lambda q, t: (_ for _ in ()).throw(OSError("sem rede")), agora=AGORA)
confere("rede fora: mensagem curta", not erro["ok"] and "OSError" in erro["erro"])
erro = cm.consultar(30, env={}, abrir=abrir_ok, agora=AGORA)
confere("sem chave no .env: manda rodar heimdall cloudflare", not erro["ok"] and "heimdall cloudflare" in erro["erro"])
confere("texto com erro mostra o erro", "Account Analytics" in cm.texto(cm.consultar(30, env=ENV, abrir=abrir_403, agora=AGORA), ligada=False))

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
