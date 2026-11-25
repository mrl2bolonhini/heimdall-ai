#!/usr/bin/env python3
"""Testa no navegador as abas do Games (categorias): troca sem recarregar, jogo abre a categoria certa e trocar de aba num jogo carrega a página inteira."""
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(RAIZ))
import heimdall_lab as hc  # noqa: E402
import heimdall_jogos as hj  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:400])


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não instalado: teste do navegador não rodou.")
    sys.exit(0)

hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
srv = ThreadingHTTPServer(("127.0.0.1", 0), hj.Jogos)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
token, _ = hc.nova_sessao()

with sync_playwright() as p:
    nav = p.chromium.launch()
    ctx = nav.new_context(viewport={"width": 1000, "height": 800})
    ctx.add_cookies([{"name": hc.COOKIE, "value": token, "url": BASE}])
    pg = ctx.new_page()
    erros = []
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.goto(BASE + "/")
    caixas = pg.evaluate("Array.from(document.querySelectorAll('[role=tab]')).map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]})")
    topos = sorted({c[1] for c in caixas})
    confere("4 categorias numa só linha (no máximo 5 abas)", len(caixas) == 4 and len(topos) == 1, caixas)
    pg.evaluate("window.__marca = 1")
    pg.focus("#aba-1")
    pg.keyboard.press("Alt+Shift+Digit3")
    pg.wait_for_function("document.querySelector('h1').textContent === 'Palavras e lógica'", timeout=5000)
    confere("Option+Shift+3 abre a terceira categoria sem recarregar a página", pg.evaluate("window.__marca") == 1 and pg.url.endswith("/categoria/logica"))
    confere("a aba Palavras e lógica fica selecionada e é a única parada do Tab entre as abas", pg.evaluate("document.querySelector('[aria-selected=true]').textContent") == "Palavras e lógica"
            and pg.evaluate("document.querySelectorAll('[role=tab][tabindex=\"0\"]').length") == 1)
    confere("a troca de aba não violou a política de segurança", not [x for x in erros if "Content Security Policy" in x], erros)
    pg.focus("#aba-3")
    pg.keyboard.press("Tab")
    confere("Tab a partir da aba vai para o painel, não para o menu Conta", pg.evaluate("document.activeElement.id") == "painel-aba")
    pg.goto(BASE + "/jogo/vilarejo")
    confere("o jogo abre com a aba da sua categoria (Ação e aventuras) marcada", pg.evaluate("document.querySelector('[aria-selected=true]').textContent") == "Ação e aventuras")
    pg.evaluate("window.__marca = 1")
    pg.click("#aba-3")
    pg.wait_for_url("**/categoria/logica")
    confere("trocar de aba dentro de um jogo carrega a página inteira", pg.evaluate("window.__marca") is None)
    nav.close()

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
