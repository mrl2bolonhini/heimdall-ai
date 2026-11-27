#!/usr/bin/env python3
"""Testa o percurso do Tab pelas abas: da aba o foco vai para o painel de conteúdo e termina no link Voltar para o topo, sem cair de volta no menu Conta."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys

sys.path.insert(0, str(RAIZ))
import heimdall_design as d  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


itens = [("/a", "Alfa"), ("/b", "Beta"), ("/c", "Gama")]
painel = d.painel_da_aba(itens, "/b", "<p>Texto</p><ul><li><a href='/x'>Item</a></li></ul>")
confere("o painel da aba é uma parada do Tab (tabindex=0) e leva o nome da aba", 'role="tabpanel"' in painel and 'tabindex="0"' in painel and 'aria-labelledby="aba-2"' in painel, painel)
confere("o link Voltar para o topo é parada do Tab mesmo onde o navegador pula links", 'href="#topo" tabindex="0"' in d.rodape())
confere("foco visível na aba, no painel e no resumo do menu", all(x in d.CSS for x in ("[role=tab]:focus", "[role=tabpanel]:focus", "summary:focus")))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não instalado: parte do navegador não testada.")
else:
    pagina = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title><style>' + d.CSS + '</style></head><body>' + d.topo()
              + '<nav aria-label="Conta"><details class="conta"><summary id="conta">Conta: Dono</summary><p>Conectado.</p></details></nav>'
              + '<header><nav aria-label="Principal">' + d.abas(itens, "/b") + "</nav></header><main>"
              + painel + "</main>" + d.rodape() + "<script>" + d.SCRIPT_ABAS + d.SCRIPT_DETALHES + "</script></body></html>")
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.set_content(pagina)
        pg.focus("#aba-2")
        ordem = []
        for _ in range(8):
            pg.keyboard.press("Tab")
            ordem.append(pg.evaluate("(document.activeElement === document.body ? 'FORA' : (document.activeElement.id || document.activeElement.textContent))"))
        confere("Tab a partir da aba: painel, o link do item, os links de Ajuda e políticas, Voltar para o topo, o fim da página e só então o menu Conta", ordem == ["painel-aba", "Item", "Ajuda e suporte", "Termos de Uso", "Privacidade", "Voltar para o topo", "FORA", "conta"], ordem)
        pg.focus("#aba-2")
        pg.keyboard.press("Tab")
        outline = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        confere("o painel em foco mostra contorno", outline != "none", outline)
        # modo "Safari": links fora do percurso (só tabindex explícito e controles). Simula tirando os links sem tabindex do percurso.
        pg.evaluate("document.querySelectorAll('a:not([tabindex])').forEach(function(a){ a.tabIndex = -1; })")
        pg.focus("#aba-2")
        ordem = []
        for _ in range(4):
            pg.keyboard.press("Tab")
            ordem.append(pg.evaluate("(document.activeElement === document.body ? 'FORA' : (document.activeElement.id || document.activeElement.textContent))"))
        confere("sem links no Tab (como no Safari): painel, os links do conteúdo (têm tabindex), Voltar para o topo, o fim da página e só depois o menu Conta", ordem == ["painel-aba", "Item", "Voltar para o topo", "FORA"], ordem)
        nav.close()

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
