#!/usr/bin/env python3
"""Testa o menu Mais das abas (mais de 9 itens): marcação, Option+Shift+0 e Esc no navegador."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import heimdall_design as d  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


itens = [(f"/r{i}", f"Nome{i}") for i in range(1, 13)]
h = d.abas(itens, "/r2")
confere("até 9 itens: sem Mais", "<details" not in d.abas(itens[:9], "/r2") and d.abas(itens[:9], "/r2").count('role="tab"') == 9)
confere("12 itens: 9 abas, Mais com 3 links, atalhos de 1 a 9 mais o 0", h.count('role="tab"') == 9 and 'id="mais"' in h and h.count("<li><a") == 3 and "Atalho: Option Shift 0" in h and "Atalho: Option Shift 9" in h and "Option Shift 10" not in h, h)
h2 = d.abas(itens, "/r11")
confere("aba aberta dentro do Mais: resumo diz qual, link marcado, e uma aba continua alcançável pelo Tab", "Mais, aba aberta: Nome11" in h2 and 'aria-current="page"' in h2 and 'tabindex="0"' in h2 and 'aria-selected="true"' not in h2, h2)
confere("o painel da aba do Mais é rotulado pelo link", 'aria-labelledby="aba-11"' in d.painel_da_aba(itens, "/r11", "x"))
confere("o resumo do Mais é um <summary> (funciona sem JavaScript)", "<summary" in h and "<button" not in h)

confere("quantidade por linha: 5 numa linha; 6=3+3, 7=4+3, 8=4+4, 9=5+4; mais de 9 = 5+4+Mais",
        [d.por_linha(n) for n in (3, 5, 6, 7, 8, 9, 12)] == [3, 5, 3, 4, 4, 5, 5])
confere("a lista de abas leva a classe da linha e com-mais só com o menu", 'class="l3"' in d.abas(itens[:6], "/r1") and "com-mais" in h and "com-mais" not in d.abas(itens[:9], "/r1"))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não instalado: parte do navegador não testada.")
else:
    pagina = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title></head><body><nav>' + d.abas(itens, "/r1") + "</nav>"
              + d.painel_da_aba(itens, "/r1", "<p>x</p>") + "<script>" + d.SCRIPT_ABAS + d.SCRIPT_DETALHES + "</script></body></html>")
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.set_content(pagina)
        pg.keyboard.press("Alt+Shift+Digit0")
        aberto = pg.evaluate("document.getElementById('mais').open")
        foco = pg.evaluate("document.activeElement && document.activeElement.textContent")
        confere("Option+Shift+0 abre o Mais e leva o foco ao primeiro item", aberto and foco == "Nome10", (aberto, foco))
        pg.keyboard.press("Escape")
        confere("Esc fecha o Mais e devolve o foco ao resumo", not pg.evaluate("document.getElementById('mais').open") and pg.evaluate("document.activeElement.tagName") == "SUMMARY")
        pg.keyboard.press("Alt+Shift+Digit0")
        pg.keyboard.press("Alt+Shift+Digit0")
        confere("Option+Shift+0 de novo fecha", not pg.evaluate("document.getElementById('mais').open"))
        pg2 = nav.new_page(viewport={"width": 1000, "height": 700})
        pg2.set_content('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title><style>' + d.CSS + '</style></head><body>' + d.abas(itens, "/r1") + "</body></html>")
        caixas = pg2.evaluate("Array.from(document.querySelectorAll('[role=tab],summary')).map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]})")
        topos = sorted({c[1] for c in caixas})
        confere("12 abas: duas linhas, 5 na primeira e 4 na segunda, e o Mais na segunda linha, depois das 4", len(topos) == 2 and sum(1 for c in caixas[:9] if c[1] == topos[0]) == 5 and caixas[9][1] == topos[1] and caixas[9][0] > caixas[8][0], caixas)
        pg2.set_content('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title><style>' + d.CSS + '</style></head><body>' + d.abas(itens[:7], "/r1") + "</body></html>")
        caixas = pg2.evaluate("Array.from(document.querySelectorAll('[role=tab]')).map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]})")
        confere("7 abas: 4 na primeira linha e 3 na segunda", sum(1 for c in caixas if c[1] == caixas[0][1]) == 4 and len({c[1] for c in caixas}) == 2, caixas)
        nav.close()
print("TUDO OK" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
