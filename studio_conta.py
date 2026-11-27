#!/usr/bin/env python3
"""Menu Conta compartilhado por todos os serviços do Heimdall: nome (da conta Microsoft) e e-mail de quem entrou, e links para os serviços a que a pessoa tem acesso.

Quem é a pessoa: o Cloudflare Access manda o documento assinado (JWT) em cada pedido; studio_cfaccess confere a assinatura. O nome vem do endereço
/cdn-cgi/access/get-identity da equipe no Cloudflare, chamado com esse mesmo documento; fica só na memória, por 1 hora (10 minutos se falhar).
Sem nome, mostra o e-mail. Quem entra pela porta local (senha e código) é o dono do Mac: aparece com o nome de STUDIO_DONO_NOME no .env (sem ele, "Dono").
Serviços listados: dono vê todos; convidado só os liberados para ele (HEIMDALL_CFACCESS_CONVIDADOS). O endereço de cada um sai de studio_usuarios.
"""
import html
import json
import os
import re
import threading
import time
import urllib.request

contexto = threading.local()  # cabeçalhos do pedido em curso (preenchidos por studio_lab.ManipuladorBase)
_nomes: dict = {}
_trava = threading.Lock()
NOME_TTL, FALHA_TTL = 3600, 600

# nome no cabeçalho de marca -> chave do serviço em studio_usuarios.SERVICOS
CHAVES = {"Studio Lab": "lab", "Studio Learn": "learn", "Studio Trading": "trading", "Studio Miner": "miner", "Studio Hub": "memory", "Studio News": "news", "Studio Health": "saude", "Studio Games": "jogos",
          "Studio Finance": "finance", "Controls": "controls", "Account": "account"}
# Nomes reais, como cada serviço se chama (nunca traduzidos): é o que o menu e a página Account mostram, em vez dos rótulos do catálogo de usuários.
NOMES = {"lab": "Studio Lab", "learn": "Studio Learn", "trading": "Studio Trading", "miner": "Studio Miner", "memory": "Studio Hub", "news": "Studio News", "saude": "Studio Health", "jogos": "Studio Games", "finance": "Studio Finance",
         "controls": "Controls", "chat": "Chat", "flows": "Flows", "status": "Status", "account": "Account"}
ORDEM = sorted(NOMES, key=lambda k: NOMES[k].lower())  # ordem alfabética pelo nome real
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
        import studio_cfaccess as cfa
        jwt = (cab.get(cfa.CABECALHO, "") if cab is not None else "") or ""
        email = cfa.email_validado(jwt) if jwt else None
        if email:
            c = cfa.config()
            papel = "dono" if email in c["donos"] else "convidado"
            return {"email": email, "nome": nome_de(email, jwt, c["equipe"]), "papel": papel, "via": "Cloudflare Access (Microsoft)", "access": True}
    except Exception:  # noqa: BLE001
        pass
    if logado_local:
        return {"email": "", "nome": _limpo(os.environ.get("STUDIO_DONO_NOME")) or "Dono", "papel": "dono", "via": "senha e código", "access": False}
    return {}


def servicos_da(p: dict) -> list:
    """[(chave, nome real, endereço)] dos serviços que a pessoa pode abrir, na ordem de ORDEM. O Account é de todos que entram."""
    try:
        import studio_usuarios as u
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
    lista = f'<p>Serviços do StudioLibre</p><ul aria-label="Serviços do StudioLibre">{itens}</ul>' if itens else ""
    saida = '<p><a href="/cdn-cgi/access/logout">Sair também do Cloudflare Access</a></p>' if p.get("access") else ""
    return (f'<nav aria-label="Conta"><details class="conta"><summary>Conta: {e(nome)}</summary><p>Conectado como {quem}, entrando por {e(p["via"])}.</p>'
            f'{lista}{sair_html}{saida}</details></nav>')


def urls_publicas() -> list:
    """[(nome do serviço, endereço público)] de todos os serviços, com os nomes de studio urls (controls, notes, health...). É o que o app do Mac abre."""
    import studio_usuarios as u
    return [(u.SERVICOS[k][2], url) for k, _, url in servicos_da({"papel": "dono"})]


def main(argv=None) -> int:
    """python3 studio_conta.py --urls-publicas [--verificar]: lista os endereços públicos; com --verificar confere se cada um está atrás do Cloudflare Access."""
    import sys
    a = list(sys.argv[1:] if argv is None else argv)
    if "--urls-publicas" not in a:
        print(main.__doc__)
        return 2
    ruim = 0
    for nome, url in urls_publicas():
        if "--verificar" in a:
            import verificar_access as va
            cod, _ = va.verificar(url)
            estado = {0: "protegido pelo Access", 1: "ABERTO: o Access não está na frente", 2: "sem resposta"}[cod]
            ruim += cod == 1
            print(f"{nome}: {url}  [{estado}]")
        else:
            print(f"{nome}: {url}")
    return 1 if ruim else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
