#!/usr/bin/env python3
"""Teste do menu Conta (heimdall_conta.py): nome e e-mail, serviços por papel, texto escapado, fallback sem nome e sem Access."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys

import heimdall_cfaccess as cfa
import heimdall_conta as c
import heimdall_usuarios as u

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


class Cab(dict):
    pass


DONOS = {"dono@x.com"}
cfa.email_validado = lambda jwt: {"tokdono": "dono@x.com", "tokana": "ana@x.com", "tokxss": "xss@x.com", "toksemnome": "sem@x.com"}.get(jwt)
cfa.config = lambda: {"equipe": "eq", "auds": {"a"}, "donos": DONOS, "convidados": {}}
u.situacao = lambda: {"donos": ["dono@x.com"], "convidados": {"ana@x.com": ["jogos", "news", "saude"]}}
NOMES = {"dono@x.com": "Murillo Bolonhini", "ana@x.com": "Ana Souza", "xss@x.com": "<script>alert(1)</script>", "sem@x.com": ""}
c._buscar_identidade = lambda equipe, jwt: {"name": NOMES[cfa.email_validado(jwt)]}


def h(tok):
    return Cab({cfa.CABECALHO: tok})


m = c.menu("Studio News", cabecalhos=h("tokdono"))
confere("dono: nome e e-mail no resumo e no texto", "Conta: Murillo Bolonhini" in m and "Murillo Bolonhini (dono@x.com)" in m, m)
confere("dono: vê todos os serviços, inclusive Controls, Health, Finance, n8n e Kuma", all(n in m for n in (">Studio Lab<", ">Studio Notes<", ">Studio Games<", ">Studio Controls<", ">Studio Health<", ">Studio Finance<", ">Studio Flows<", ">Studio Status<", ">Studio Chat<", ">Studio Account<")) and "Open WebUI" not in m and "Uptime Kuma" not in m and "Notas" not in m and "Saúde" not in m and "Jogos" not in m, m)
import heimdall_conta as _c
confere("lista em ordem alfabética pelo nome real", [_c.NOMES[k] for k in _c.ORDEM] == sorted(_c.NOMES.values(), key=str.lower))
confere("serviço atual marcado, sem link duplicado", 'aria-current="page">Studio News (você está aqui)' in m and m.count(">Studio News<") == 0, m)
confere("Kuma abre no painel (/dashboard)", "https://status.heimdall-ai.tech/dashboard" in m, m)
g = c.menu("Studio Games", cabecalhos=h("tokana"))
confere("convidado: só o que foi liberado e é convidável (Saúde fica de fora, mesmo na lista)", ">Studio News<" in g and "Studio Games (você está aqui)" in g and ">Studio Account<" in g and "Saúde" not in g and "Controls" not in g and "Finance" not in g and "Uptime" not in g, g)
confere("convidado: nome mostrado", "Conta: Ana Souza" in g)
x = c.menu("", cabecalhos=h("tokxss"))
confere("nome vindo da Microsoft é escapado", "<script>" not in x and "&lt;script&gt;" in x, x)
s = c.menu("", cabecalhos=h("toksemnome"))
confere("sem nome: mostra o e-mail", "Conta: sem@x.com" in s and "Conectado como sem@x.com" in s, s)
confere("sem Access e sem sessão: nada", c.menu("", cabecalhos=Cab()) == "")
confere("token inválido: nada", c.menu("", cabecalhos=h("falso")) == "")
l = c.menu("Studio Lab", logado_local=True, cabecalhos=Cab(), sair_html="<form>SAIR</form>")
import os
os.environ["HEIMDALL_DONO_NOME"] = "Murillo"
l_nome = c.menu("Studio Lab", logado_local=True, cabecalhos=Cab())
confere("porta local com HEIMDALL_DONO_NOME: mostra o nome, não \"Dono\"", "Conta: Murillo" in l_nome and "Conta: Dono" not in l_nome, l_nome)
del os.environ["HEIMDALL_DONO_NOME"]
confere("porta local com sessão: Dono, todos os serviços e o botão Sair do serviço", "Conta: Dono" in l and "senha e código" in l and ">Studio Notes<" in l and "<form>SAIR</form>" in l and "cdn-cgi/access/logout" not in l, l)
confere("pelo Access há o link para sair do Access", "cdn-cgi/access/logout" in m)
chamadas = []
c._nomes.clear()
c._buscar_identidade = lambda equipe, jwt: chamadas.append(1) or {"name": "Fulano"}
c.pessoa(cabecalhos=h("tokdono")); c.pessoa(cabecalhos=h("tokdono"))
confere("o nome é guardado na memória (uma só consulta)", len(chamadas) == 1, str(chamadas))
c._nomes.clear()
def quebra(equipe, jwt):
    chamadas.append(2)
    raise OSError("sem rede")
c._buscar_identidade = quebra
chamadas.clear()
p1 = c.pessoa(cabecalhos=h("tokdono")); c.pessoa(cabecalhos=h("tokdono"))
confere("falha ao buscar o nome: usa o e-mail e não tenta de novo por 10 minutos", p1["nome"] == "" and len(chamadas) == 1, str(p1))
c._nomes.clear()
c._buscar_identidade = lambda equipe, jwt: {"name": "dono@x.com"}
confere("nome igual ao e-mail não repete", c.pessoa(cabecalhos=h("tokdono"))["nome"] == "")
# De ponta a ponta: um servidor com a base ManipuladorBase vê os cabeçalhos do pedido em curso, e um pedido não vaza para o seguinte.
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import heimdall_lab as nuvem


class Eco(nuvem.ManipuladorBase):
    def do_GET(self):
        corpo = nuvem.cabecalho("Studio News", "").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


c._nomes.clear()
c._buscar_identidade = lambda equipe, jwt: {"name": NOMES[cfa.email_validado(jwt)]}
srv = ThreadingHTTPServer(("127.0.0.1", 0), Eco)
threading.Thread(target=srv.serve_forever, daemon=True).start()
porta = srv.server_address[1]
a = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{porta}/", headers={cfa.CABECALHO: "tokana"})).read().decode()
b = urllib.request.urlopen(f"http://127.0.0.1:{porta}/").read().decode()
srv.shutdown()
confere("servidor real: o cabeçalho mostra a conta de quem pediu", "Conta: Ana Souza" in a and "<header>" in a, a[:200])
confere("servidor real: pedido sem Access não herda a conta do anterior", "Conta:" not in b, b[:200])
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
