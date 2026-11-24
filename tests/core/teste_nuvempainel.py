#!/usr/bin/env python3
"""Teste dos dados da aba Nuvem (heimdall_nuvempainel.py): limites de gasto lidos da Cloudflare, erros e interruptor, sem rede."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_nuvempainel.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import sys
import urllib.error

import heimdall_nuvempainel as n  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {detalhe}"))
    falhas += 0 if ok else 1


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


ENV = {"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "c"}
visto = {}


def abrir_ok(req, timeout):
    visto["url"], visto["auth"] = req.full_url, req.get_header("Authorization")
    return Resp(json.dumps({"result": [
        {"product_id": "durable_objects", "action": "usage_block", "threshold_cents": 500, "current_state": {"status": "below_limit"}},
        {"product_id": "workers", "action": "notification", "threshold_cents": 500, "current_state": {"status": "below_limit"}},
        {"product_id": "ai_gateway", "action": "usage_block", "threshold_cents": 100}]}).encode())


r = n.politicas(ENV, abrir_ok)
confere("lê as políticas de Workers e Durable Objects e ignora outros produtos", r["ok"] and len(r["itens"]) == 2 and r["itens"][0]["produto"].startswith("Durable") and r["itens"][0]["limite"] == 5.0, r)
confere("usa a conta e o token do .env", visto["url"].endswith("/accounts/c/billing/spend-policies") and visto["auth"] == "Bearer t")
confere("sem token no .env, explica o que falta", not n.politicas({})["ok"] and "CLOUDFLARE_API_TOKEN" in n.politicas({})["erro"])


def abrir_403(req, timeout):
    raise urllib.error.HTTPError(req.full_url, 403, "x", {}, None)


confere("403 vira aviso de permissão, sem vazar o token", "Faturamento" in n.politicas(ENV, abrir_403)["erro"] and "t" != n.politicas(ENV, abrir_403)["erro"])


def abrir_rede(req, timeout):
    raise OSError("sem rede")


confere("sem rede, mensagem em português", not n.politicas(ENV, abrir_rede)["ok"] and "Cloudflare" in n.politicas(ENV, abrir_rede)["erro"])
e = n.estado({**ENV, "HEIMDALL_CONTINUIDADE": "1"}, abrir_ok)
def abrir_paygo(req, timeout):
    visto["url2"], visto["auth2"] = req.full_url, req.get_header("Authorization")
    return Resp(json.dumps({"result": [{"ServiceName": "Workers Standard", "BilledCost": 5}, {"ServiceName": "Containers", "BilledCost": 1.5},
                                       {"ServiceName": "Containers", "BilledCost": 0.25}]}).encode())


c = n.consumo({**ENV, "HEIMDALL_CF_LEITURA_TOKEN": "leitura"}, abrir_paygo)
confere("consumo soma por serviço e usa o token de leitura", c["ok"] and abs(c["total"] - 6.75) < 1e-9 and c["itens"][0]["servico"] == "Workers Standard" and visto["auth2"] == "Bearer leitura" and visto["url2"].endswith("/billing/usage/paygo"), c)
confere("consumo sem token de leitura usa o do .env", n.consumo(ENV, abrir_paygo)["ok"] and visto["auth2"] == "Bearer t")
confere("consumo: 403 e 404 em português, sem valor inventado", "Faturamento" in n.consumo(ENV, abrir_403)["erro"] and not n.consumo(ENV, lambda r, t: (_ for _ in ()).throw(urllib.error.HTTPError(r.full_url, 404, "x", {}, None)))["ok"])
confere("estado sem a senha de continuidade avisa e não derruba", e["ligado"] and not e["copia"]["ok"] and "heimdall continuity --prepare" in e["copia"]["erro"] and e["gastos"]["ok"])
confere("estado desligado por padrão", not n.estado({}, abrir_ok, com_nuvem=False)["ligado"])
print("\nTUDO OK" if not falhas else f"\n{falhas} FALHA(S)")
sys.exit(1 if falhas else 0)
