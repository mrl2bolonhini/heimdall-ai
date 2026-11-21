#!/usr/bin/env python3
"""Monitor da Cloudflare: tokens, requisições e custo estimado do gateway de IA "heimdall", mais o teto de gasto combinado.

    python3 heimdall_cfmonitor.py            resumo dos últimos 30 dias, no terminal
    python3 heimdall_cfmonitor.py --dias 7   outro período (de 1 a 31 dias)

Lê o consumo pela API de análises (GraphQL) da Cloudflare. O token do .env (o mesmo do News) precisa da permissão
Conta > Análises (Account Analytics) > Leitura. O custo é uma estimativa feita pela Cloudflare a partir dos tokens; a fatura é a
referência. Usado também pela aba Monitor do Heimdall Controls.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import heimdall_nuvem as nuvem

GATEWAY = nuvem.GATEWAY
TETO_GATEWAY = 10.0   # US$ por mês: o limite criado no gateway
TETO_TOTAL = 15.0     # US$ por mês: o limite combinado da migração (CLAUDE.md)
URL = "https://api.cloudflare.com/client/v4/graphql"
CONSULTA = ("query($a:string!,$s:Time!,$e:Time!,$g:string!){viewer{accounts(filter:{accountTag:$a}){"
            "r:aiGatewayRequestsAdaptiveGroups(limit:1000,filter:{datetimeHour_geq:$s,datetimeHour_leq:$e,gateway:$g}){"
            "count sum{cost tokensIn tokensOut erroredRequests cachedRequests} dimensions{model date}}}}}")
_cache: dict = {}


def _abrir(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def consultar(dias: int = 30, env: dict = None, abrir=None, agora: datetime = None, usar_cache: bool = False) -> dict:
    """{'ok': True, 'dias', 'linhas': [...], 'por_modelo': [...], 'por_dia': [...], 'total': {...}} ou {'ok': False, 'erro': texto}."""
    dias = max(1, min(31, int(dias)))
    e = env if env is not None else nuvem._env()
    token, conta = e.get("CLOUDFLARE_API_TOKEN", ""), e.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not conta:
        return {"ok": False, "erro": "Falta a chave da Cloudflare no .env. Rode heimdall cloudflare."}
    chave = (conta, dias)
    if usar_cache and chave in _cache and time.time() - _cache[chave][0] < 60:
        return _cache[chave][1]
    fim = (agora or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    ini = fim - timedelta(days=dias)
    corpo = {"query": CONSULTA, "variables": {"a": conta, "g": GATEWAY, "s": ini.strftime("%Y-%m-%dT%H:%M:%SZ"), "e": fim.strftime("%Y-%m-%dT%H:%M:%SZ")}}
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode(), method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": nuvem.USER_AGENT})
    try:
        with (abrir or _abrir)(req, 30) as r:
            d = json.loads(r.read(2_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as ex:
        return {"ok": False, "erro": _erro_http(ex.code)}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "erro": f"Não consegui falar com a Cloudflare ({type(ex).__name__})."}
    if d.get("errors"):
        msg = "; ".join(str(x.get("message", "")) for x in d["errors"])[:200]
        if "authoriz" in msg.lower() or "permission" in msg.lower() or "access" in msg.lower():
            return {"ok": False, "erro": _erro_http(403)}
        return {"ok": False, "erro": "A Cloudflare recusou a consulta: " + msg}
    contas = ((d.get("data") or {}).get("viewer") or {}).get("accounts") or []
    linhas = (contas[0].get("r") if contas else None) or []
    r = _resumir(linhas, dias)
    if usar_cache:
        _cache[chave] = (time.time(), r)
    return r


def _erro_http(codigo: int) -> str:
    if codigo in (401, 403):
        return ("O token não tem permissão de ler análises. Na Cloudflare, edite o token heimdall-news e acrescente Conta > Análises "
                "(Account Analytics) > Leitura; o valor do token não muda.")
    return f"A Cloudflare respondeu com erro {codigo}."


def _resumir(linhas: list, dias: int) -> dict:
    por_modelo, por_dia = {}, {}
    total = {"requisicoes": 0, "tokens_in": 0, "tokens_out": 0, "custo": 0.0, "erros": 0, "cache": 0}
    for l in linhas:
        s, dim, n = l.get("sum") or {}, l.get("dimensions") or {}, int(l.get("count") or 0)
        v = {"requisicoes": n, "tokens_in": int(s.get("tokensIn") or 0), "tokens_out": int(s.get("tokensOut") or 0),
             "custo": float(s.get("cost") or 0), "erros": int(s.get("erroredRequests") or 0), "cache": int(s.get("cachedRequests") or 0)}
        for destino, k in ((por_modelo, dim.get("model") or "(sem modelo)"), (por_dia, dim.get("date") or "(sem data)")):
            a = destino.setdefault(k, {"requisicoes": 0, "tokens_in": 0, "tokens_out": 0, "custo": 0.0, "erros": 0, "cache": 0})
            for c in v:
                a[c] += v[c]
        for c in v:
            total[c] += v[c]
    return {"ok": True, "dias": dias, "linhas": len(linhas), "total": total,
            "por_modelo": [{"modelo": k, **v} for k, v in sorted(por_modelo.items(), key=lambda x: -x[1]["custo"])],
            "por_dia": [{"dia": k, **v} for k, v in sorted(por_dia.items(), reverse=True)]}


def _usd(x: float) -> str:
    return f"US$ {x:.4f}" if x < 0.1 else f"US$ {x:.2f}"


def _n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def texto(r: dict, ligada: bool = None) -> str:
    ligada = nuvem.ativo() if ligada is None else ligada
    cab = f"Nuvem {'LIGADA' if ligada else 'desligada'}. Gateway de IA: {GATEWAY}."
    if not r.get("ok"):
        return cab + "\n" + r.get("erro", "Sem dados.")
    t = r["total"]
    out = [cab, f"Últimos {r['dias']} dias: {_n(t['requisicoes'])} requisições, {_n(t['tokens_in'])} tokens de entrada e {_n(t['tokens_out'])} de saída, "
                f"{t['erros']} com erro, custo estimado {_usd(t['custo'])}.",
           f"Teto do gateway: {_usd(t['custo'])} de US$ {TETO_GATEWAY:.2f} por mês ({t['custo'] / TETO_GATEWAY * 100:.1f}%). Teto combinado da nuvem: US$ {TETO_TOTAL:.2f} por mês."]
    if r["por_modelo"]:
        out.append("Por modelo:")
        out += [f"  {m['modelo']}: {_n(m['requisicoes'])} requisições, {_n(m['tokens_in'] + m['tokens_out'])} tokens, {_usd(m['custo'])}" for m in r["por_modelo"]]
    if r["por_dia"]:
        out.append("Por dia (mais recentes primeiro):")
        out += [f"  {d['dia']}: {_n(d['requisicoes'])} requisições, {_n(d['tokens_in'] + d['tokens_out'])} tokens, {_usd(d['custo'])}" for d in r["por_dia"][:10]]
    if not r["por_modelo"]:
        out.append("Ainda não há uso registrado nesse período.")
    out.append("O custo é uma estimativa da Cloudflare; a fatura é a referência. No plano gratuito, a cota diária da Workers AI para sozinha em vez de cobrar.")
    return "\n".join(out)


def main() -> None:
    dias = 30
    a = sys.argv[1:]
    if a[:1] == ["--dias"]:
        try:
            dias = int(a[1])
        except (IndexError, ValueError):
            sys.exit("Use --dias com um número de 1 a 31.")
    r = consultar(dias)
    print(texto(r))
    if not r.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
