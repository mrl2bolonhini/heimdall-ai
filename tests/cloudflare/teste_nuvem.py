#!/usr/bin/env python3
"""Teste do modelo grande na nuvem (studio_nuvem.py) e da volta ao modelo local, sem rede e sem token real.

    python3 tests/cloudflare/teste_nuvem.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import studio_nuvem as nv  # noqa: E402
import studio_perguntar as pg  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


LIGADO = {"STUDIO_NUVEM": "1", "CLOUDFLARE_API_TOKEN": "segredo-de-teste", "CLOUDFLARE_ACCOUNT_ID": "a" * 32}


class Resp:
    def __init__(self, corpo): self._c = json.dumps(corpo).encode()
    def read(self, n=-1): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False


# --- interruptor -----------------------------------------------------------------------------------------
confere("ligada só com STUDIO_NUVEM=1 e a chave", nv.ativo(LIGADO))
confere("desligada com STUDIO_NUVEM=0", not nv.ativo({**LIGADO, "STUDIO_NUVEM": "0"}))
confere("desligada sem o interruptor", not nv.ativo({k: v for k, v in LIGADO.items() if k != "STUDIO_NUVEM"}))
confere("desligada sem a chave", not nv.ativo({"STUDIO_NUVEM": "1"}))
try:
    nv.chat("s", "u", env={"STUDIO_NUVEM": "0"})
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
confere("modelo trocável pelo .env", True if nv.chat("s", "u", env={**LIGADO, "STUDIO_NUVEM_MODELO": "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast"}, abrir=abrir_ok) and visto["corpo"]["model"].endswith("llama-3.3-70b-instruct-fp8-fast") else False)

confere("modelo do Perguntar: Qwen3 30B por padrão, trocável pelo .env", nv.modelo_perguntar(LIGADO) == "workers-ai/@cf/qwen/qwen3-30b-a3b-fp8" and nv.modelo_perguntar({**LIGADO, "STUDIO_NUVEM_PERGUNTAR_MODELO": "x/y"}) == "x/y")
nv.chat("s", "u", max_tokens=500, env=LIGADO, abrir=abrir_ok, modelo=nv.modelo_perguntar(LIGADO), folga=300)
confere("modelo e folga escolhidos por quem chama (sem raciocínio, folga menor)", visto["corpo"]["model"].endswith("qwen3-30b-a3b-fp8") and visto["corpo"]["max_tokens"] == 800, visto["corpo"])
import studio_perguntar as _pg
_vistos = []
_orig = (_pg.nuvem.ativo, _pg.nuvem.chat)
_pg.nuvem.ativo = lambda *a, **k: True
_pg.nuvem.chat = lambda sistema, usuario, **kw: (_vistos.append((sistema, kw)) or "<think>pensando</think>Resposta limpa.")
_t = _pg.responder("ctx", "pergunta?", "SIS")
confere("responder usa o modelo leve com /no_think e tira o raciocínio do texto", _t["texto"] == "Resposta limpa." and _vistos[0][0].endswith("/no_think") and _vistos[0][1]["modelo"].endswith("qwen3-30b-a3b-fp8") and _vistos[0][1]["folga"] == 300, _vistos)
_pg.nuvem.ativo, _pg.nuvem.chat = _orig
confere("forcar liga a nuvem só nesta chamada, mesmo com o interruptor em 0", nv.chat("s", "u", env={**LIGADO, "STUDIO_NUVEM": "0"}, abrir=abrir_ok, forcar=True) == "resposta")
try:
    nv.chat("s", "u", env={"STUDIO_NUVEM": "0"}, abrir=abrir_ok, forcar=True)
    confere("forcar sem chave continua recusando", False)
except RuntimeError as ex:
    confere("forcar sem chave continua recusando", "chave" in str(ex), str(ex))

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

# --- studio ask: nuvem ou local, com aviso ---------------------------------------------------------------
import studio_ask as ask  # noqa: E402
_ativo0 = ask.nuvem.ativo
try:
    ask.nuvem.ativo = lambda env=None: True
    r, quem, aviso = ask.perguntar_ao_modelo("oi", nuvem_chat=lambda s, u: "da nuvem", local_chat=lambda s, u: "do local")
    confere("ask com a nuvem ligada responde pela nuvem e diz qual modelo", r == "da nuvem" and quem.startswith("nuvem (gpt-oss-120b") and aviso == "", (r, quem, aviso))

    def cai(s, u): raise RuntimeError("HTTP 500")
    r, quem, aviso = ask.perguntar_ao_modelo("oi", nuvem_chat=cai, local_chat=lambda s, u: "do local")
    confere("ask: se a nuvem falha, usa o local e avisa", r == "do local" and quem.startswith("modelo local") and "HTTP 500" in aviso, (r, quem, aviso))

    try:
        ask.perguntar_ao_modelo("oi", modo="cloud", nuvem_chat=cai, local_chat=lambda s, u: "do local")
        confere("ask --cloud não cai para o local", False)
    except RuntimeError:
        confere("ask --cloud não cai para o local", True)

    r, quem, aviso = ask.perguntar_ao_modelo("oi", modo="local", nuvem_chat=lambda s, u: "da nuvem", local_chat=lambda s, u: "do local")
    confere("ask --local ignora a nuvem", r == "do local" and quem.startswith("modelo local") and aviso == "")

    ask.nuvem.ativo = lambda env=None: False
    r, quem, aviso = ask.perguntar_ao_modelo("oi", nuvem_chat=lambda s, u: "da nuvem", local_chat=lambda s, u: "do local")
    confere("ask com a nuvem desligada vai direto ao local", r == "do local" and aviso == "")
    r, quem, aviso = ask.perguntar_ao_modelo("oi", modo="cloud", nuvem_chat=lambda s, u: "da nuvem", local_chat=lambda s, u: "do local")
    confere("ask --cloud tenta a nuvem mesmo desligada pelo interruptor", r == "da nuvem", r)
finally:
    ask.nuvem.ativo = _ativo0

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
