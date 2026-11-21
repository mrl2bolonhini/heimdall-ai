#!/usr/bin/env python3
"""Teste do Heimdall Account: tour por papel, /quem.json com CORS só para os sites do Heimdall, 403/401 sem Access, porta local e cabeçalhos de segurança."""
import http.client
import json
import re
import sys
import threading
from http.server import ThreadingHTTPServer

import heimdall_account as a
import heimdall_cfaccess as cfa
import heimdall_conta as c
import heimdall_usuarios as u

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


cfa.email_validado = lambda jwt: {"tokdono": "dono@x.com", "tokana": "ana@x.com", "tokxss": "xss@x.com"}.get(jwt)
cfa.config = lambda: {"equipe": "eq", "auds": {"a"}, "donos": {"dono@x.com"}, "convidados": {}}
u.situacao = lambda: {"donos": ["dono@x.com"], "convidados": {"ana@x.com": ["jogos", "news", "saude"], "xss@x.com": ["news"]}}
c._buscar_identidade = lambda eq, jwt: {"name": {"tokdono": "Murillo", "tokana": "Ana Souza", "tokxss": "<img src=x onerror=alert(1)>"}[jwt]}
srv = ThreadingHTTPServer(("127.0.0.1", 0), a.Account)
threading.Thread(target=srv.serve_forever, daemon=True).start()
porta = srv.server_address[1]


def pedir(caminho, host="account.heimdall-ai.tech", jwt=None, origem=None, metodo="GET"):
    h = {"Host": host}
    if jwt:
        h[cfa.CABECALHO] = jwt
    if origem:
        h["Origin"] = origem
    k = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    k.request(metodo, caminho, headers=h)
    r = k.getresponse()
    corpo = r.read().decode("utf-8", "replace")
    k.close()
    return r.status, {x.lower(): v for x, v in r.getheaders()}, corpo


s, hd, b = pedir("/saude")
confere("/saude responde ok sem login", s == 200 and b == "ok")
s, hd, b = pedir("/", host="outro.exemplo")
confere("nome de site não permitido: 421", s == 421)
s, hd, b = pedir("/")
confere("endereço público sem Access: 403", s == 403 and "Cloudflare Access" in b)
s, hd, b = pedir("/quem.json", origem="https://heimdall-ai.tech")
confere("quem.json sem Access: 401 com logado=false e CORS para o site", s == 401 and json.loads(b) == {"logado": False} and hd.get("access-control-allow-origin") == "https://heimdall-ai.tech", f"{s} {hd}")

s, hd, b = pedir("/", jwt="tokdono")
confere("dono: página do tour com todos os serviços, nomes reais", s == 200 and all(x in b for x in ("Heimdall Cloud", "Heimdall Notas", "Heimdall Saúde", "Heimdall Jogos", "Heimdall Finance", "Heimdall Controls", "Open WebUI", "n8n", "Uptime Kuma")), b[:300])
confere("dono: Finance e Saúde explicam o multiusuário e o aviso de serviço do dono", "contas bancárias" in b and "serviços de saúde" in b and "Este serviço é do dono" in b)
confere("página: lang pt-BR, um só h1, pular para o conteúdo, voltar ao topo e sem script", 'lang="pt-BR"' in b and b.count("<h1>") == 1 and 'class="pular"' in b and 'href="#topo"' in b and 'id="topo"' in b and "<script" not in b)
confere("página: menu Conta com nome e e-mail", "Conta: Murillo" in b and "Murillo (dono@x.com)" in b)
confere("cabeçalhos: CSP com nonce de estilo, sem cache, nosniff", "style-src 'nonce-" in hd["content-security-policy"] and hd["cache-control"] == "no-store" and hd["x-content-type-options"] == "nosniff", str(hd))
nonce = re.search(r"nonce-([\w-]+)'", hd["content-security-policy"]).group(1)
confere("o nonce do CSP é o da tag de estilo", f'<style nonce="{nonce}">' in b)
s, hd, b = pedir("/", jwt="tokana")
confere("convidado: só os serviços dele; nada de Controls, Finance, n8n, Kuma, Chat", all(x in b for x in ("Heimdall Jogos", "Heimdall News")) and not any(x in b for x in ("Heimdall Controls", "Heimdall Finance", "n8n", "Uptime Kuma", "Open WebUI", "Heimdall Saúde")), b[:200])
s, hd, b = pedir("/", jwt="tokxss")
confere("nome malicioso vindo da Microsoft é escapado", "<img src=x" not in b and "&lt;img" in b)

s, hd, b = pedir("/quem.json", jwt="tokana", origem="https://heimdall-ai.tech")
d = json.loads(b)
confere("quem.json logado: nome, e-mail e serviços, com CORS e cookies", s == 200 and d["logado"] and d["nome"] == "Ana Souza" and d["email"] == "ana@x.com" and [x["nome"] for x in d["servicos"]][:1] == ["Heimdall Account"]
        and hd["access-control-allow-origin"] == "https://heimdall-ai.tech" and hd["access-control-allow-credentials"] == "true" and "origin" in hd["vary"].lower(), f"{s} {hd} {b}")
confere("quem.json: convidado não recebe serviços de dono", not any(x["nome"] in ("Heimdall Controls", "Heimdall Finance", "n8n") for x in d["servicos"]))
s, hd, b = pedir("/quem.json", jwt="tokana", origem="https://mal.exemplo")
confere("quem.json: site de fora não ganha CORS", s == 200 and "access-control-allow-origin" not in hd, str(hd))
s, hd, b = pedir("/quem.json", jwt="tokana")
confere("quem.json sem Origin: sem CORS", "access-control-allow-origin" not in hd)
s, hd, b = pedir("/quem.json", metodo="OPTIONS", origem="https://heimdall-ai.tech")
confere("OPTIONS: 204 com CORS só para o site", s == 204 and hd.get("access-control-allow-origin") == "https://heimdall-ai.tech")

s, hd, b = pedir("/", host="localhost")
confere("porta local: o dono do Mac vê o tour", s == 200 and "Olá, Dono" in b and "Heimdall Controls" in b)
s, hd, b = pedir("/quem.json", host="127.0.0.1")
confere("porta local: quem.json mostra o Dono", s == 200 and json.loads(b)["nome"] == "Dono")
s, hd, b = pedir("/nada", jwt="tokdono")
confere("caminho desconhecido: 404", s == 404)
srv.shutdown()
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
