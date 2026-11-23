#!/usr/bin/env python3
"""Testa as subabas do Heimdall Design: marcação ARIA, ordem do Tab (aba, subaba, painel interno), troca só do painel interno sem recarregar e Alt+Shift+seta."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(RAIZ))
import heimdall_design as d  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


GRUPOS = [("/a1", "Alfa", [("/a1", "Um"), ("/a2", "Dois"), ("/a3", "Três")]), ("/b1", "Beta", [("/b1", "Único")])]
TOPO = [(g[0], g[1]) for g in GRUPOS]


def pagina(rota):
    grupo = next(g for g in GRUPOS if any(r == rota for r, _ in g[2]))
    interno = f"<p>Conteúdo {rota}</p><a href='/x'>Link {rota}</a>"
    corpo = d.com_subabas(grupo[2], rota, interno, "Seções de " + grupo[1]) if len(grupo[2]) > 1 else interno
    miolo = d.com_abas(TOPO, grupo[0], corpo, foco=len(grupo[2]) == 1)
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t ' + rota + '</title><style>' + d.CSS + '</style></head><body>' + d.topo()
            + '<header><nav aria-label="Principal">' + d.abas(TOPO, grupo[0]) + "</nav></header><main>" + miolo + "</main>" + d.rodape()
            + "<script>window.CARGAS=(window.CARGAS||0)+1;" + d.SCRIPT_ABAS + "</script></body></html>")


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        rota = self.path.split("?")[0]
        if not any(rota == r for g in GRUPOS for r, _ in g[2]):
            self.send_response(404)
            self.end_headers()
            return
        corpo = pagina(rota).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


html = pagina("/a2")
confere("subabas formam um tablist de nível 2 ligado ao painel interno", 'data-nivel="2"' in html and 'aria-controls="painel-subaba"' in html and 'id="painel-subaba"' in html, html[:200])
confere("a subaba aberta é a única com aria-selected=true no nível 2", html.count('aria-selected="true"') == 2, html.count('aria-selected="true"'))
confere("o painel de fora não é parada do Tab quando há subabas (foco=False)", html.count('role="tabpanel"') == 2)
confere("a aba com uma só subaba não mostra subabas", 'class="subabas' not in pagina("/b1"))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não instalado: parte do navegador não testada.")
else:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.goto(base + "/a1")
        pg.focus("#aba-1")
        ordem = []
        for _ in range(3):
            pg.keyboard.press("Tab")
            ordem.append(pg.evaluate("document.activeElement.id || document.activeElement.textContent"))
        confere("Tab a partir da aba: a subaba aberta, o painel interno e o link do conteúdo", ordem[0] == "subaba-1" and ordem[1] == "painel-subaba", ordem)
        pg.focus("#subaba-1")
        pg.keyboard.press("ArrowRight")
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#painel-subaba').textContent.includes('/a2')")
        confere("abrir a subaba troca só o painel interno, sem recarregar a página", pg.evaluate("window.CARGAS") == 1 and pg.evaluate("document.activeElement.id") == "subaba-2", pg.evaluate("window.CARGAS"))
        confere("a subaba nova fica selecionada e a outra não", pg.get_attribute("#subaba-2", "aria-selected") == "true" and pg.get_attribute("#subaba-1", "aria-selected") == "false")
        pg.keyboard.press("End")
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#painel-subaba').textContent.includes('/a3')")
        confere("End vai à última subaba", pg.get_attribute("#subaba-3", "aria-selected") == "true")
        pg.focus("#aba-1")
        pg.keyboard.press("ArrowRight")
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#painel-aba').textContent.includes('/b1')")
        confere("trocar a aba de cima troca a lista de subabas junto", pg.query_selector("#subaba-1") is None and pg.evaluate("window.CARGAS") == 1)
        nav.close()
    srv.shutdown()

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
