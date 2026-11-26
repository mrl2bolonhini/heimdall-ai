#!/usr/bin/env python3
"""Teste do Account: tour por papel, /quem.json com CORS só para os sites do Heimdall, 403/401 sem Access, porta local e cabeçalhos de segurança."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
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


def pedir(caminho, host="account.heimdall-ai.tech", jwt=None, origem=None, metodo="GET", corpo=None):
    h = {"Host": host}
    if corpo is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    if jwt:
        h[cfa.CABECALHO] = jwt
    if origem:
        h["Origin"] = origem
    k = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    k.request(metodo, caminho, body=corpo, headers=h)
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
confere("dono: página do tour com todos os serviços, nomes reais", s == 200 and all(x in b for x in ("Studio Lab", "Studio Notes", "Studio Health", "Studio Games", "Studio Finance", "Controls", "Open WebUI", "n8n", "Uptime Kuma")), b[:300])
confere("dono: Finance e Saúde explicam o multiusuário e o aviso de serviço do dono", "contas bancárias" in b and "serviços de saúde" in b and "Este serviço é do dono" in b)
confere("página: lang pt-BR, um só h1, pular para o conteúdo, voltar ao topo e sem script", 'lang="pt-BR"' in b and b.count("<h1>") == 1 and 'class="pular"' in b and 'href="#topo"' in b and 'id="topo"' in b and "<script" not in b)
confere("página: menu Conta com nome e e-mail", "Conta: Murillo" in b and "Murillo (dono@x.com)" in b)
confere("cabeçalhos: CSP com nonce de estilo, sem cache, nosniff", "style-src 'nonce-" in hd["content-security-policy"] and hd["cache-control"] == "no-store" and hd["x-content-type-options"] == "nosniff", str(hd))
nonce = re.search(r"nonce-([\w-]+)'", hd["content-security-policy"]).group(1)
confere("o nonce do CSP é o da tag de estilo", f'<style nonce="{nonce}">' in b)
s, hd, b = pedir("/", jwt="tokana")
confere("convidado: só os serviços dele; nada de Controls, Finance, n8n, Kuma, Chat", all(x in b for x in ("Studio Games", "Studio News")) and not any(x in b for x in ("Controls", "Studio Finance", "n8n", "Uptime Kuma", "Open WebUI", "Studio Health")), b[:200])
s, hd, b = pedir("/", jwt="tokxss")
confere("nome malicioso vindo da Microsoft é escapado", "<img src=x" not in b and "&lt;img" in b)

s, hd, b = pedir("/quem.json", jwt="tokana", origem="https://heimdall-ai.tech")
d = json.loads(b)
confere("quem.json logado: nome, e-mail e serviços, com CORS e cookies", s == 200 and d["logado"] and d["nome"] == "Ana Souza" and d["email"] == "ana@x.com" and [x["nome"] for x in d["servicos"]][:1] == ["Account"]
        and hd["access-control-allow-origin"] == "https://heimdall-ai.tech" and hd["access-control-allow-credentials"] == "true" and "origin" in hd["vary"].lower(), f"{s} {hd} {b}")
confere("quem.json: convidado não recebe serviços de dono", not any(x["nome"] in ("Controls", "Studio Finance", "Flows") for x in d["servicos"]))
s, hd, b = pedir("/quem.json", jwt="tokana", origem="https://mal.exemplo")
confere("quem.json: site de fora não ganha CORS", s == 200 and "access-control-allow-origin" not in hd, str(hd))
s, hd, b = pedir("/quem.json", jwt="tokana")
confere("quem.json sem Origin: sem CORS", "access-control-allow-origin" not in hd)
s, hd, b = pedir("/quem.json", metodo="OPTIONS", origem="https://heimdall-ai.tech")
confere("OPTIONS: 204 com CORS só para o site", s == 204 and hd.get("access-control-allow-origin") == "https://heimdall-ai.tech")

s, hd, b = pedir("/", host="localhost")
confere("porta local: o dono do Mac vê o tour", s == 200 and "Olá, Dono" in b and "Controls" in b)
s, hd, b = pedir("/quem.json", host="127.0.0.1")
confere("porta local: quem.json mostra o Dono", s == 200 and json.loads(b)["nome"] == "Dono")
s, hd, b = pedir("/nada", jwt="tokdono")
confere("caminho desconhecido: 404", s == 404)

# ---- Integrações ----
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import heimdall_integracoes as integ  # noqa: E402

integ.ARQUIVO = Path(tempfile.mkdtemp()) / "banco" / "integracoes.json"
chamadas = []
amb = {"HEIMDALL_CAIXA": "1", "HEIMDALL_CAIXA_TOKEN": "hc_dono", "HEIMDALL_CAIXA_MEU_NOME": "murillo"}
integ.caixa._env = lambda: dict(amb)
integ.caixa.revogar_pessoa = lambda nome, env=None, abrir=None: chamadas.append(("revogar", nome)) or 1
integ.caixa.criar_pessoa = lambda nome, env=None, abrir=None: chamadas.append(("criar", nome)) or "hc_tokendeteste1234567890"

s, hd, b = pedir("/integracoes")
confere("integrações sem Access: 403", s == 403)
s, hd, b = pedir("/integracoes", jwt="tokdono")
confere("integrações: página do dono com um h1, botão de ativar (POST) e blocos em preparação",
        s == 200 and b.count("<h1>") == 1 and 'method="post"' in b and "Ativar a Saúde" in b and b.count("em preparação") == 3 and "<script" not in b and 'lang="pt-BR"' in b, b[:400])
confere("integrações: nada de link para ação (só botão)", 'href="/integracoes/saude' not in b)
m = re.search(r'name="csrf" value="([0-9a-f]{32})"', b)
tok_csrf = m.group(1) if m else ""
s, hd, b = pedir("/integracoes", jwt="tokana")
confere("integrações: convidado vê que ainda não está disponível e não recebe botão de ativar", s == 200 and "Ainda não disponível" in b and "Ativar a Saúde" not in b)

s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokdono", metodo="POST", corpo="csrf=" + tok_csrf)
confere("ativar sem Origin: 403", s == 403)
s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokdono", metodo="POST", origem="https://outro.exemplo", corpo="csrf=" + tok_csrf)
confere("ativar com origem de outro site: 403", s == 403)
s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokdono", metodo="POST", origem="https://account.heimdall-ai.tech", corpo="csrf=errado")
confere("ativar com csrf errado: 403 e nada criado", s == 403 and not chamadas)
s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokana", metodo="POST", origem="https://account.heimdall-ai.tech", corpo="csrf=" + integ.csrf({"email": "ana@x.com"}))
confere("convidado não consegue ativar a Saúde (400) e nada é criado", s == 400 and not chamadas, b[:200])
s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokdono", metodo="POST", origem="https://account.heimdall-ai.tech", corpo="csrf=" + tok_csrf)
confere("dono ativa: token novo aparece uma vez, em campo somente leitura, com o endereço /v1/hae e passos",
        s == 200 and "hc_tokendeteste1234567890" in b and "readonly" in b and "/v1/hae" in b and "Authorization" in b and chamadas == [("revogar", "murillo"), ("criar", "murillo")], f"{s} {chamadas} {b[:300]}")
confere("o token não fica no arquivo de estado", "hc_tokendeteste" not in integ.ARQUIVO.read_text(encoding="utf-8") and (integ.ARQUIVO.stat().st_mode & 0o777) == 0o600)
s, hd, b = pedir("/integracoes", jwt="tokdono")
confere("depois de ativar, a página mostra 'Ativa desde' e o token não aparece de novo", "Ativa desde" in b and "hc_tokendeteste" not in b and "Desativar a Saúde" in b)
s, hd, b = pedir("/integracoes/saude/desativar", jwt="tokdono", metodo="POST", origem="https://account.heimdall-ai.tech", corpo="csrf=" + tok_csrf)
confere("desativar revoga o token e limpa o estado", s == 200 and "Saúde desativada" in b and chamadas[-1] == ("revogar", "murillo") and "saude" not in integ._ler().get("murillo", {}))
amb["HEIMDALL_CAIXA"] = "0"
s, hd, b = pedir("/integracoes/saude/ativar", jwt="tokdono", metodo="POST", origem="https://account.heimdall-ai.tech", corpo="csrf=" + tok_csrf)
confere("com a caixa desligada, ativar é recusado com mensagem clara", s == 400 and "desligada" in b)
confere("nome da pessoa na caixa: dono usa o nome combinado; convidado, o e-mail reduzido", integ.usuario_de({"papel": "dono"}, amb) == "murillo" and integ.usuario_de({"papel": "convidado", "email": "Ana.Souza@x.com"}, amb) == "ana-souza-x-com")
confere("nome longo ganha sufixo e cabe em 32 caracteres", len(integ.usuario_de({"papel": "convidado", "email": "a" * 80 + "@x.com"}, amb)) <= 32)

srv.shutdown()
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
