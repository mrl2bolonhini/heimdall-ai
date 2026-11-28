#!/usr/bin/env python3
"""Usuários do Heimdall: quem entra em quais serviços, no .env e no Cloudflare Access (aba Usuários do Controls).

Heimdall: donos em HEIMDALL_CFACCESS_EMAILS (entram em tudo) e convidados em HEIMDALL_CFACCESS_CONVIDADOS ("ana@x.com=jogos+chat;beto@y.com=chat").
Cloudflare: uma política reutilizável "Heimdall: <serviço>" por serviço, com os e-mails que podem entrar, ligada ao aplicativo do endereço público
do serviço (criado se não existir). Só se mexe em política com esse nome; as de outra origem ficam como estão.
Token: STUDIO_CLOUDFLARE_ACCESS_TOKEN (permissão "Access: Apps and Policies" de edição) e CLOUDFLARE_ACCOUNT_ID, no .env.
Sempre há o plano antes (o que vai mudar) e o aplicar. Dono nunca é removido por aqui.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import studio_config as config

BASE = "https://api.cloudflare.com/client/v4"
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
# chave -> (nome, variável com o(s) endereço(s) públicos, subdomínio padrão, pode ser dado a convidado)
SERVICOS = {
    "lab": ("Lab", "STUDIO_LAB_HOSTS", "lab", True),
    "learn": ("Learn", "STUDIO_LEARN_HOSTS", "learn", True),
    "trading": ("Trading", "STUDIO_TRADING_HOSTS", "trading", True),
    "miner": ("Miner", "STUDIO_MINER_HOSTS", "miner", True),
    "memory": ("Hub", "STUDIO_HUB_HOSTS", "hub", True),
    "news": ("News", "STUDIO_NEWS_HOSTS", "news", True),
    "jogos": ("Games", "STUDIO_JOGOS_HOSTS", "games", True),
    "chat": ("Chat (Open WebUI)", "STUDIO_WEBUI_HOST", "chat", True),
    "saude": ("Health", "STUDIO_SAUDE_PAINEL_HOSTS", "health", False),
    "finance": ("Finance", "STUDIO_FINANCE_HOSTS", "finance", False),
    "controls": ("Controls", "STUDIO_CONTROLS_HOSTS", "controls", False),
    "flows": ("n8n", "STUDIO_N8N_HOSTS", "flows", False),
    "status": ("Uptime Kuma", "STUDIO_KUMA_HOSTS", "status", False),
    "account": ("Account", "STUDIO_ACCOUNT_HOSTS", "account", False),  # tour dos serviços: entram todos os e-mails (donos e convidados), sem escolher
}
PREFIXO = "Heimdall: "


def _env() -> dict:
    return {d["nome"]: d["valor"] for d in config.ler()}


def _lista(v: str) -> list:
    return [x.strip().lower() for x in (v or "").split(",") if x.strip()]


def situacao() -> dict:
    """Do .env: {"donos": [e-mails], "convidados": {e-mail: [serviços]}}."""
    env = _env()
    conv = {}
    for item in env.get("HEIMDALL_CFACCESS_CONVIDADOS", "").split(";"):
        if "=" in item:
            e, s = item.split("=", 1)
            sv = sorted({x.strip().lower() for x in s.split("+") if re.fullmatch(r"[a-z0-9]{1,20}", x.strip().lower()) and SERVICOS.get(x.strip().lower(), (0, 0, 0, True))[3]})
            if e.strip() and sv:
                conv[e.strip().lower()] = sv
    return {"donos": _lista(env.get("HEIMDALL_CFACCESS_EMAILS", "")), "convidados": conv}


def _gravar_convidados(conv: dict) -> str:
    texto = ";".join(f"{e}={'+'.join(s)}" for e, s in sorted(conv.items()))
    return config.remover("HEIMDALL_CFACCESS_CONVIDADOS") if not texto else config.salvar("HEIMDALL_CFACCESS_CONVIDADOS", texto)


def definir(email: str, servicos: list) -> str:
    """Põe ou troca um convidado e os serviços dele. Devolve "" ou o motivo de recusar."""
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        return "e-mail inválido"
    s = situacao()
    if email in s["donos"]:
        return "esse e-mail é de dono: já entra em tudo"
    ok = {k for k, v in SERVICOS.items() if v[3]}
    sv = sorted({x for x in servicos if x in ok})
    if not sv:
        return "escolha pelo menos um serviço"
    s["convidados"][email] = sv
    return _gravar_convidados(s["convidados"])


def remover(email: str, quem: str = "") -> str:
    email = (email or "").strip().lower()
    s = situacao()
    if email in s["donos"]:
        return "dono não se remove por aqui (edite HEIMDALL_CFACCESS_EMAILS em Ajustes)"
    if email == (quem or "").strip().lower():
        return "você não pode remover o seu próprio e-mail"
    if email not in s["convidados"]:
        return "esse e-mail não é de convidado"
    del s["convidados"][email]
    return _gravar_convidados(s["convidados"])


# ---------- Cloudflare ----------
class ErroCloudflare(Exception):
    pass


def configurado() -> str:
    """"" se há token e conta; senão o que falta."""
    env = {**_env(), **{k: v for k, v in os.environ.items() if k.startswith(("STUDIO_CLOUDFLARE", "CLOUDFLARE"))}}
    if not env.get("STUDIO_CLOUDFLARE_ACCESS_TOKEN"):
        return "falta STUDIO_CLOUDFLARE_ACCESS_TOKEN no .env (studio env --set STUDIO_CLOUDFLARE_ACCESS_TOKEN)"
    if not re.fullmatch(r"[0-9a-f]{32}", env.get("CLOUDFLARE_ACCOUNT_ID", "")):
        return "falta CLOUDFLARE_ACCOUNT_ID (32 letras e números) em Ajustes"
    return ""


def _api(metodo: str, caminho: str, corpo=None):
    env = {**_env(), **{k: v for k, v in os.environ.items() if k.startswith(("STUDIO_CLOUDFLARE", "CLOUDFLARE"))}}
    conta, tok = env.get("CLOUDFLARE_ACCOUNT_ID", ""), env.get("STUDIO_CLOUDFLARE_ACCESS_TOKEN", "")
    req = urllib.request.Request(f"{BASE}/accounts/{conta}{caminho}", method=metodo, data=None if corpo is None else json.dumps(corpo).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read(2_000_000) or b"{}")
    except urllib.error.HTTPError as ex:
        try:
            msg = "; ".join(x.get("message", "") for x in json.loads(ex.read(100_000)).get("errors", []))
        except (ValueError, AttributeError):
            msg = ""
        raise ErroCloudflare(f"a Cloudflare recusou ({ex.code}){': ' + msg if msg else ''}")
    except (urllib.error.URLError, OSError, ValueError) as ex:
        raise ErroCloudflare(f"não consegui falar com a Cloudflare ({type(ex).__name__})")
    if not d.get("success", True):
        raise ErroCloudflare("; ".join(x.get("message", "") for x in d.get("errors", [])) or "a Cloudflare não aceitou")
    return d.get("result")


def _tudo(caminho: str) -> list:
    out, pag = [], 1
    while pag <= 20:
        r = _api("GET", f"{caminho}{'&' if '?' in caminho else '?'}per_page=100&page={pag}") or []
        out += r
        if len(r) < 100:
            break
        pag += 1
    return out


def _mfa() -> bool:
    return (_env().get("STUDIO_CLOUDFLARE_ACCESS_MFA") or os.environ.get("STUDIO_CLOUDFLARE_ACCESS_MFA", "1")).strip() != "0"


def _idp() -> str:
    """Login permitido nos aplicativos novos: o de STUDIO_CLOUDFLARE_ACCESS_IDP ou, se a conta tem um só login da Microsoft (azureAD), esse."""
    env = {**_env(), **os.environ}
    if env.get("STUDIO_CLOUDFLARE_ACCESS_IDP", "").strip():
        return env["STUDIO_CLOUDFLARE_ACCESS_IDP"].strip()
    try:
        ms = [i["id"] for i in (_api("GET", "/access/identity_providers") or []) if i.get("type") == "azureAD"]
    except (ErroCloudflare, KeyError, TypeError):
        return ""
    return ms[0] if len(ms) == 1 else ""


def _exige_mfa(politica: dict) -> bool:
    return any(isinstance(r, dict) and r.get("auth_method", {}).get("auth_method") == "mfa" for r in politica.get("require", []))


def host_publico(chave: str) -> str:
    env = {**_env(), **os.environ}
    _, var, sub, _ = SERVICOS[chave]
    import studio_config
    for h in _lista(env.get(var, "")):
        sub_, _, resto_ = h.partition(".")
        if sub_ in studio_config.HOSTS_ANTIGOS and resto_:   # endereço de serviço renomeado que ainda está no .env
            h = f"{studio_config.HOSTS_ANTIGOS[sub_]}.{resto_}"
        if h not in ("localhost",) and not h.startswith(("127.", "[")) and not h[:1].isdigit() and not h.endswith(".ts.net"):
            return h
    import studio_links
    return f"{sub}.{studio_links.dominio()}"


def _hosts_do_app(app: dict) -> set:
    """Endereços inteiros (sem caminho) que o aplicativo cobre: o campo domain, os destinos e os domínios extras."""
    brutos = [app.get("domain") or ""] + [d.get("uri", "") for d in app.get("destinations", []) if isinstance(d, dict)] + list(app.get("self_hosted_domains", []) or [])
    return {b.lower() for b in brutos if b and "/" not in b and "*" not in b}


def _emails_de(politica: dict) -> list:
    return sorted(i["email"]["email"].lower() for i in politica.get("include", []) if isinstance(i, dict) and "email" in i)


def desejado() -> dict:
    """{serviço: [e-mails que devem entrar]}: donos em todos; convidados só nos serviços liberados (e só nos que podem ser dados a convidado)."""
    s = situacao()
    todos = set(s["donos"]) | set(s["convidados"])
    return {k: sorted(todos if k == "account" else set(s["donos"]) | {e for e, sv in s["convidados"].items() if k in sv and SERVICOS[k][3]}) for k in SERVICOS}


def plano() -> list:
    """Lê a Cloudflare e diz o que mudaria. Cada item: dict com servico, host, emails (novos), atuais, app, politica, acao, texto."""
    apps = _tudo("/access/apps")
    pols = {p["name"]: p for p in _tudo("/access/policies") if str(p.get("name", "")).startswith(PREFIXO)}
    out = []
    for chave, emails in desejado().items():
        nome = SERVICOS[chave][0]
        host = host_publico(chave)
        app = next((a for a in apps if host in _hosts_do_app(a)), None)
        if app and len(_hosts_do_app(app)) > 1:  # aplicativo que cobre vários endereços: uma política por serviço o abriria para todos eles
            out.append({"servico": chave, "host": host, "emails": emails, "atuais": [], "app": app, "politica": None, "acao": "nada",
                        "texto": f"{nome} ({host}): coberto pelo aplicativo compartilhado \"{app.get('name')}\" ({len(_hosts_do_app(app))} endereços); não mexo. "
                                 "Entra quem a política dele permitir; para dar acesso só a este serviço, separe-o em aplicativo próprio."})
            continue
        pol = pols.get(PREFIXO + nome)
        atuais = _emails_de(pol) if pol else []
        if not emails:
            out.append({"servico": chave, "host": host, "emails": emails, "atuais": atuais, "app": app, "politica": pol, "acao": "nada",
                        "texto": f"{nome}: nenhum e-mail para pôr (cadastre um dono em Ajustes); pulado."})
            continue
        ligada = bool(app and pol and any(p.get("id") == pol["id"] for p in app.get("policies", [])))
        tarefas = []
        if atuais != emails or (pol and _mfa() and not _exige_mfa(pol)):
            tarefas.append("criar a política" if not pol else f"atualizar a política (+{len(set(emails) - set(atuais))} -{len(set(atuais) - set(emails))}{', exigir o Authenticator' if _mfa() and not _exige_mfa(pol) else ''})")
        if not app:
            tarefas.append(f"criar o aplicativo de {host}")
        elif not ligada:
            tarefas.append(f"ligar a política ao aplicativo de {host}")
        out.append({"servico": chave, "host": host, "emails": emails, "atuais": atuais, "app": app, "politica": pol, "acao": "mudar" if tarefas else "nada",
                    "texto": f"{nome} ({host}): " + (", ".join(tarefas) if tarefas else "já está certo") + f". Entram {len(emails)} e-mail(s)."})
    return out


def aplicar(itens: list) -> list:
    """Executa o plano. Devolve linhas de resultado. Remoções revogam as sessões abertas do e-mail tirado."""
    res, tirados, auds = [], set(), set()
    for it in itens:
        if it["acao"] != "mudar":
            res.append(it["texto"])
            if it.get("app") and it["app"].get("aud"):
                auds.add(it["app"]["aud"])
            continue
        nome = SERVICOS[it["servico"]][0]
        try:
            corpo = {"name": PREFIXO + nome, "decision": "allow", "include": [{"email": {"email": e}} for e in it["emails"]],
                     "require": [{"auth_method": {"auth_method": "mfa"}}] if _mfa() else []}  # mfa: a Microsoft só deixa passar com o Authenticator
            pol = it["politica"]
            if pol:
                _api("PUT", f"/access/policies/{pol['id']}", corpo)
                pid = pol["id"]
            else:
                pid = _api("POST", "/access/policies", corpo)["id"]
            app = it["app"]
            if not app:
                novo = {"name": f"Heimdall {nome}", "domain": it["host"], "type": "self_hosted", "session_duration": "8h", "policies": [{"id": pid, "precedence": 1}]}
                idp = _idp()
                if idp:
                    novo.update({"allowed_idps": [idp], "auto_redirect_to_identity": True})  # só o login da Microsoft, direto
                app = _api("POST", "/access/apps", novo) or {}
            elif not any(p.get("id") == pid for p in app.get("policies", [])):
                existentes = [{"id": p["id"], "precedence": p.get("precedence", i + 1)} for i, p in enumerate(app.get("policies", []))]
                prec = max([p["precedence"] for p in existentes] + [0]) + 1
                inteiro = {k: v for k, v in app.items() if k not in ("id", "aud", "uid", "created_at", "updated_at")}  # o PUT troca tudo: manda o que já existe
                _api("PUT", f"/access/apps/{app['id']}", {**inteiro, "policies": existentes + [{"id": pid, "precedence": prec}]})
            tirados |= set(it["atuais"]) - set(it["emails"])
            if app and app.get("aud"):
                auds.add(app["aud"])
            res.append(f"{nome}: feito.")
        except (ErroCloudflare, KeyError, TypeError) as ex:
            res.append(f"{nome}: NÃO deu: {ex}")
    atual = [x.strip() for x in _env().get("HEIMDALL_CFACCESS_AUD", "").split(",") if x.strip()]
    novas = auds - set(atual)
    if novas:  # os painéis do Heimdall só aceitam o documento do Access dos aplicativos listados em HEIMDALL_CFACCESS_AUD
        motivo = config.salvar("HEIMDALL_CFACCESS_AUD", ",".join(atual + sorted(novas)))
        res.append(f"{len(novas)} identificador(es) de aplicativo (AUD) acrescentado(s) a HEIMDALL_CFACCESS_AUD; reinicie para valer." if not motivo else f"Não consegui gravar HEIMDALL_CFACCESS_AUD: {motivo}")
    for e in sorted(tirados - set(desejado_todos())):
        try:
            _api("POST", "/access/organizations/revoke_user", {"email": e})
            res.append(f"Sessões abertas de {e} revogadas.")
        except ErroCloudflare as ex:
            res.append(f"Não consegui revogar as sessões de {e}: {ex}")
    return res


def desejado_todos() -> set:
    return {e for v in desejado().values() for e in v}
