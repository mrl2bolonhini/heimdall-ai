#!/usr/bin/env python3
"""Teste do modelo grande na nuvem (heimdall_nuvem.py) e da volta ao modelo local, sem rede e sem token real.

    python3 teste_nuvem.py
"""
import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_nuvem as nv  # noqa: E402
import heimdall_perguntar as pg  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


LIGADO = {"HEIMDALL_NUVEM": "1", "CLOUDFLARE_API_TOKEN": "segredo-de-teste", "CLOUDFLARE_ACCOUNT_ID": "a" * 32}


class Resp:
    def __init__(self, corpo): self._c = json.dumps(corpo).encode()
    def read(self, n=-1): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False


# --- interruptor -----------------------------------------------------------------------------------------
confere("ligada só com HEIMDALL_NUVEM=1 e a chave", nv.ativo(LIGADO))
confere("desligada com HEIMDALL_NUVEM=0", not nv.ativo({**LIGADO, "HEIMDALL_NUVEM": "0"}))
confere("desligada sem o interruptor", not nv.ativo({k: v for k, v in LIGADO.items() if k != "HEIMDALL_NUVEM"}))
confere("desligada sem a chave", not nv.ativo({"HEIMDALL_NUVEM": "1"}))
try:
    nv.chat("s", "u", env={"HEIMDALL_NUVEM": "0"})
    confere("chat desligado levanta erro", False)
except RuntimeError:
    confere("chat desligado levanta erro", True)

# --- pedido enviado ---------------------------------------------------------------------------------------
visto = {}


def abrir_ok(req, timeout):
    visto["url"], visto["h"], visto["corpo"] = req.full_url, {k.lower(): v for k, v in req.header_items()}, json.loads(req.data)
    return Resp({"choices": [{"message": {"content": "  resposta  "}}]})


r = nv.chat("sistema", "usuario", max_tokens=500, env=LIGADO, abrir=abrir_ok)
confere("devolve o texto sem espaços", r == "resposta", r)
confere("usa o gateway heimdall no endereço compatível", visto["url"] == "https://gateway.ai.cloudflare.com/v1/" + "a" * 32 + "/heimdall/compat/chat/completions", visto["url"])
confere("envia as duas autorizações", visto["h"].get("authorization") == "Bearer segredo-de-teste" and visto["h"].get("cf-aig-authorization") == "Bearer segredo-de-teste")
confere("tem User-Agent próprio (evita o erro 1010)", visto["h"].get("user-agent") == "heimdall-ai/1.0")
confere("modelo padrão é o gpt-oss-120b", visto["corpo"]["model"] == "workers-ai/@cf/openai/gpt-oss-120b", visto["corpo"]["model"])
confere("dá folga de tokens para o raciocínio", visto["corpo"]["max_tokens"] == 1500, visto["corpo"]["max_tokens"])
confere("modelo trocável pelo .env", True if nv.chat("s", "u", env={**LIGADO, "HEIMDALL_NUVEM_MODELO": "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast"}, abrir=abrir_ok) and visto["corpo"]["model"].endswith("llama-3.3-70b-instruct-fp8-fast") else False)

# --- falhas -----------------------------------------------------------------------------------------------
def abrir_403(req, timeout):
    raise urllib.error.HTTPError(req.full_url, 403, "x", {}, io.BytesIO(b"error code: 1010"))


for nome, abrir in (("HTTP 403", abrir_403), ("resposta vazia", lambda r_, t: Resp({"choices": [{"message": {"content": None}}]})),
                    ("rede fora", lambda r_, t: (_ for _ in ()).throw(OSError("sem rede")))):
    try:
        nv.chat("s", "u", env=LIGADO, abrir=abrir)
        confere("falha vira RuntimeError: " + nome, False)
    except RuntimeError:
        confere("falha vira RuntimeError: " + nome, True)
confere("o erro não mostra a chave", "segredo-de-teste" not in nv.ultimo_erro)

# --- Perguntar: nuvem primeiro, local como volta ----------------------------------------------------------
chamadas = []
orig_ativo, orig_chat, orig_urlopen = pg.nuvem.ativo, pg.nuvem.chat, pg.urllib.request.urlopen


class Local:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps({"choices": [{"message": {"content": "do modelo local"}}]}).encode()


def urlopen_local(req, timeout=0):
    chamadas.append("local")
    return Local()


pg.urllib.request.urlopen = urlopen_local
try:
    pg.nuvem.ativo = lambda env=None: True
    pg.nuvem.chat = lambda s, u, **k: (chamadas.append("nuvem"), "da nuvem")[1]
    confere("com a nuvem ligada, responde pela nuvem", pg.chamar_local("s", "u") == "da nuvem" and chamadas == ["nuvem"], chamadas)

    chamadas.clear()
    def falha(s, u, **k):
        chamadas.append("nuvem")
        raise RuntimeError("HTTP 500")
    pg.nuvem.chat = falha
    confere("se a nuvem falha, volta ao modelo local", pg.chamar_local("s", "u") == "do modelo local" and chamadas == ["nuvem", "local"], chamadas)

    chamadas.clear()
    pg.nuvem.ativo = lambda env=None: False
    confere("com a nuvem desligada, nem tenta a nuvem", pg.chamar_local("s", "u") == "do modelo local" and chamadas == ["local"], chamadas)
finally:
    pg.nuvem.ativo, pg.nuvem.chat, pg.urllib.request.urlopen = orig_ativo, orig_chat, orig_urlopen

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
