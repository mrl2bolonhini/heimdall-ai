#!/usr/bin/env python3
"""Teste do bloco de conta das páginas do site (docs/index.html + heimdall.js) no navegador, com o account.studiolibre.io de mentira.
Sem login (redirecionamento do Access ou 401): fica o link "Entrar no StudioLibre". Com login: nome, e-mail e links dos serviços, sem executar HTML vindo do servidor."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Sem Playwright instalado: teste do site pulado.")
    sys.exit(0)

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


class Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=str(RAIZ / "docs")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
ORIGEM = f"http://127.0.0.1:{srv.server_address[1]}"
CORS = {"Access-Control-Allow-Origin": ORIGEM, "Access-Control-Allow-Credentials": "true", "Content-Type": "application/json"}
LOGADO = {"logado": True, "nome": "Ana <b>Souza</b>", "email": "ana@x.com", "papel": "convidado",
          "servicos": [{"nome": "Account", "url": "https://account.studiolibre.io/"}, {"nome": "Studio Games", "url": "https://games.studiolibre.io/"},
                       {"nome": "Mal", "url": "javascript:alert(1)"}]}


def rodar(rota):
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.route("https://account.studiolibre.io/quem.json", rota)
        pg.goto(ORIGEM + "/index.html")
        pg.wait_for_timeout(700)
        html = pg.inner_html("#conta-site")
        texto = pg.text_content("#conta-site")
        aviso = pg.inner_text("#aviso")
        links = pg.eval_on_selector_all("#conta-site a", "els => els.map(e => e.href)")
        b_dentro = pg.eval_on_selector_all("#conta-site b", "els => els.length")
        outras = pg.evaluate("document.getElementById('conta-site') !== null")
        pg.goto(ORIGEM + "/arquitetura.html")
        sem_conta = pg.evaluate("document.getElementById('conta-site') !== null")
        nav.close()
        return html, texto, aviso, links, b_dentro, erros, outras, sem_conta


h, t, av, ln, b, er, _, sem = rodar(lambda r: r.fulfill(status=200, headers=CORS, body=json.dumps(LOGADO)))
confere("logado: mostra 'Conta: nome' no resumo", "Conta: Ana <b>Souza</b>" in t, t)
confere("logado: o HTML do nome não é interpretado", b == 0, h)
confere("logado: links dos serviços https; link javascript: ignorado", "https://games.studiolibre.io/" in ln and not any(x.startswith("javascript") for x in ln), str(ln))
confere("logado: e-mail no texto, link para sair e aviso para o leitor de tela", "ana@x.com" in t and any(x.endswith("/cdn-cgi/access/logout") for x in ln) and "conectado como" in av.lower(), av)
confere("logado: sem erro de JavaScript", er == [], str(er))
confere("as outras páginas do site também têm o bloco de conta", sem)

h, t, av, ln, b, er, _, _ = rodar(lambda r: r.fulfill(status=302, headers={"Location": "https://eq.cloudflareaccess.com/cdn-cgi/access/login/x"}))
confere("sem login (redirecionamento do Access): continua o link Entrar", "Entrar no StudioLibre" in t and ln == ["https://account.studiolibre.io/"] and av == "", f"{t} {ln}")
h, t, av, ln, b, er, _, _ = rodar(lambda r: r.fulfill(status=401, headers=CORS, body=json.dumps({"logado": False})))
confere("sem login (401): continua o link Entrar", "Entrar no StudioLibre" in t and "Conta:" not in t)
h, t, av, ln, b, er, _, _ = rodar(lambda r: r.abort())
confere("sem rede: continua o link Entrar e não dá erro", "Entrar no StudioLibre" in t and er == [], str(er))
srv.shutdown()
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
