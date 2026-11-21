#!/usr/bin/env python3
"""Menu Conta compartilhado por todos os serviços do Heimdall: nome (da conta Microsoft) e e-mail de quem entrou, e links para os serviços a que a pessoa tem acesso.

Quem é a pessoa: o Cloudflare Access manda o documento assinado (JWT) em cada pedido; heimdall_cfaccess confere a assinatura. O nome vem do endereço
/cdn-cgi/access/get-identity da equipe no Cloudflare, chamado com esse mesmo documento; fica só na memória, por 1 hora (10 minutos se falhar).
Sem nome, mostra o e-mail. Quem entra pela porta local (senha e código) é o dono do Mac: aparece como "Dono".
Serviços listados: dono vê todos; convidado só os liberados para ele (HEIMDALL_CFACCESS_CONVIDADOS). O endereço de cada um sai de heimdall_usuarios.
"""
import html
import json
import re
import threading
import time
import urllib.request

contexto = threading.local()  # cabeçalhos do pedido em curso (preenchidos por heimdall_cloud.ManipuladorBase)
_nomes: dict = {}
_trava = threading.Lock()
NOME_TTL, FALHA_TTL = 3600, 600

# nome no cabeçalho de marca -> chave do serviço em heimdall_usuarios.SERVICOS
CHAVES = {"Heimdall Cloud": "cloud", "Heimdall Notas": "notas", "Heimdall News": "news", "Heimdall Saúde": "saude", "Heimdall Jogos": "jogos",
          "Heimdall Finance": "finance", "Heimdall Controls": "controls", "Heimdall Account": "account"}
# Nomes reais, como cada serviço se chama (nunca traduzidos): é o que o menu e a página Account mostram, em vez dos rótulos do catálogo de usuários.
NOMES = {"cloud": "Heimdall Cloud", "notas": "Heimdall Notas", "news": "Heimdall News", "saude": "Heimdall Saúde", "jogos": "Heimdall Jogos", "finance": "Heimdall Finance",
         "controls": "Heimdall Controls", "chat": "Open WebUI", "flows": "n8n", "status": "Uptime Kuma", "account": "Heimdall Account"}
ORDEM = ["account", "cloud", "notas", "news", "saude", "jogos", "finance", "controls", "chat", "flows", "status"]
CAMINHOS = {"status": "/dashboard"}  # o Kuma abre no painel, onde há o menu dele e as Configurações


def _limpo(v) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(v or "")).strip()[:120]


def _buscar_identidade(equipe: str, jwt: str) -> dict:
    req = urllib.request.Request(f"https://{equipe}.cloudflareaccess.com/cdn-cgi/access/get-identity", headers={"Cookie": f"CF_Authorization={jwt}", "User-Agent": "heimdall-conta"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read(65536).decode("utf-8", "replace"))


def nome_de(email: str, jwt: str, equipe: str, buscar=None) -> str:
    """Nome da conta Microsoft, ou "" se o Cloudflare não disser. Guardado na memória."""
    agora = time.time()
    with _trava:
        achou = _nomes.get(email)
    if achou and agora - achou[1] < (NOME_TTL if achou[0] else FALHA_TTL):
        return achou[0]
    nome = ""
    try:
        d = (buscar or _buscar_identidade)(equipe, jwt)
        nome = _limpo(d.get("name")) if isinstance(d, dict) else ""
        if nome.lower() == email.lower():
            nome = ""
    except Exception:  # noqa: BLE001
        nome = ""
    with _trava:
        if len(_nomes) > 200:
            _nomes.clear()
        _nomes[email] = (nome, agora)
    return nome


def pessoa(logado_local: bool = False, cabecalhos=None) -> dict:
    """{"email","nome","papel","via"} de quem faz o pedido, ou {} se não for possível dizer."""
    cab = cabecalhos if cabecalhos is not None else getattr(contexto, "cabecalhos", None)
    try:
        import heimdall_cfaccess as cfa
        jwt = (cab.get(cfa.CABECALHO, "") if cab is not None else "") or ""
        email = cfa.email_validado(jwt) if jwt else None
        if email:
            c = cfa.config()
            papel = "dono" if email in c["donos"] else "convidado"
            return {"email": email, "nome": nome_de(email, jwt, c["equipe"]), "papel": papel, "via": "Cloudflare Access (Microsoft)", "access": True}
    except Exception:  # noqa: BLE001
        pass
    if logado_local:
        return {"email": "", "nome": "Dono", "papel": "dono", "via": "senha e código", "access": False}
    return {}


def servicos_da(p: dict) -> list:
    """[(chave, nome real, endereço)] dos serviços que a pessoa pode abrir, na ordem de ORDEM. O Account é de todos que entram."""
    try:
        import heimdall_usuarios as u
        if p.get("papel") == "dono":
            chaves = set(u.SERVICOS)
        else:
            chaves = {k for k in u.situacao()["convidados"].get(p.get("email", ""), []) if k in u.SERVICOS and u.SERVICOS[k][3]} | {"account"}
        return [(k, NOMES.get(k, u.SERVICOS[k][0]), f"https://{u.host_publico(k)}{CAMINHOS.get(k, '/')}") for k in ORDEM if k in chaves]
    except Exception:  # noqa: BLE001
        return []


def menu(atual: str = "", logado_local: bool = False, sair_html: str = "", cabecalhos=None) -> str:
    """O HTML do menu Conta, ou "" quando não dá para saber quem é (página de entrada, por exemplo)."""
    p = pessoa(logado_local, cabecalhos)
    if not p:
        return ""
    e = html.escape
    chave = CHAVES.get(atual, "")
    nome = p["nome"] or p["email"] or "Dono"
    quem = f"{e(p['nome'])} ({e(p['email'])})" if p["nome"] and p["email"] else e(nome)
    itens = ""
    for k, n, url in servicos_da(p):
        itens += (f'<li><a href="{e(url)}" aria-current="page">{e(n)} (você está aqui)</a></li>' if k == chave else f'<li><a href="{e(url)}">{e(n)}</a></li>')
    lista = f'<p>Serviços do Heimdall</p><ul aria-label="Serviços do Heimdall">{itens}</ul>' if itens else ""
    saida = '<p><a href="/cdn-cgi/access/logout">Sair também do Cloudflare Access</a></p>' if p.get("access") else ""
    return (f'<nav aria-label="Conta"><details class="conta"><summary>Conta: {e(nome)}</summary><p>Conectado como {quem}, entrando por {e(p["via"])}.</p>'
            f'{lista}{sair_html}{saida}</details></nav>')
