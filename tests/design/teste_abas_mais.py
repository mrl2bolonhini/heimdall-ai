#!/usr/bin/env python3
"""Testa o menu Mais das abas (mais de 5 itens, o máximo por padrão): marcação, Option+Shift+0 e Esc no navegador."""
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
confere("até 5 itens: sem Mais", "<details" not in d.abas(itens[:5], "/r2") and d.abas(itens[:5], "/r2").count('role="tab"') == 5)
confere("o padrão é no máximo 5 posições", d.MAX_ABAS == 5)
confere("6 itens: 4 abas e o Mais na quinta posição, com 2 links (nunca passa de 5)", d.abas(itens[:6], "/r1").count('role="tab"') == 4 and d.abas(itens[:6], "/r1").count("<li><a") == 2)
confere("12 itens: 4 abas, Mais com 8 links e um só atalho (5), dito para macOS, Windows e Linux", h.count('role="tab"') == 4 and 'id="mais"' in h and h.count("<li><a") == 8
        and "Option Shift 5 no macOS, ou Alt Shift 5 no Windows e no Linux" in h and "ou 0" not in h and "Digit0" not in d.SCRIPT_ABAS, h)
h2 = d.abas(itens, "/r11")
confere("aba aberta dentro do Mais: resumo diz qual, link marcado, e uma aba continua alcançável pelo Tab", "Mais, aba aberta: Nome11" in h2 and 'aria-current="page"' in h2 and 'tabindex="0"' in h2 and 'aria-selected="true"' not in h2, h2)
confere("o painel da aba do Mais é rotulado pelo link", 'aria-labelledby="aba-11"' in d.painel_da_aba(itens, "/r11", "x"))
confere("o resumo do Mais é um <summary> (funciona sem JavaScript)", "<summary" in h and "<button" not in h)

confere("quantidade por linha: até 5 abas; com mais itens, 4 abas e o Mais completa as 5 posições",
        [d.por_linha(n) for n in (3, 4, 5, 6, 12)] == [3, 4, 5, 4, 4] and [d.limite_abas(n) for n in (5, 6)] == [5, 4])
confere("a lista de abas leva a classe da linha e com-mais só com o menu", 'class="l3"' in d.abas(itens[:3], "/r1") and "com-mais" in h and "com-mais" not in d.abas(itens[:5], "/r1"))

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
        pg.keyboard.press("Alt+Shift+Digit5")
        aberto = pg.evaluate("document.getElementById('mais').open")
        foco = pg.evaluate("document.activeElement && document.activeElement.textContent")
        confere("Option+Shift+5 (Alt+Shift+5) abre o Mais e leva o foco ao primeiro item", aberto and foco == "Nome5", (aberto, foco))
        pg.keyboard.press("Escape")
        confere("Esc fecha o Mais e devolve o foco ao resumo", not pg.evaluate("document.getElementById('mais').open") and pg.evaluate("document.activeElement.tagName") == "SUMMARY")
        pg.keyboard.press("Alt+Shift+Digit5")
        pg.keyboard.press("Alt+Shift+Digit5")
        confere("o mesmo atalho de novo fecha", not pg.evaluate("document.getElementById('mais').open"))
        pg.keyboard.press("Alt+Shift+Digit0")
        confere("Option+Shift+0 não faz mais nada (um só atalho para o Mais)", not pg.evaluate("document.getElementById('mais').open"))
        pg2 = nav.new_page(viewport={"width": 1000, "height": 700})
        pg2.set_content('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title><style>' + d.CSS + '</style></head><body>' + d.abas(itens, "/r1") + "</body></html>")
        caixas = pg2.evaluate("Array.from(document.querySelectorAll('[role=tab],summary')).map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]})")
        topos = sorted({c[1] for c in caixas})
        confere("12 itens: as 4 abas e o Mais ficam na mesma linha, o Mais na quinta posição, depois das abas", len(topos) == 1 and caixas[4][0] > caixas[3][0], caixas)
        pg2.set_content('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>t</title><style>' + d.CSS + '</style></head><body>' + d.abas(itens[:5], "/r1") + "</body></html>")
        caixas = pg2.evaluate("Array.from(document.querySelectorAll('[role=tab]')).map(function(x){var r=x.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]})")
        confere("5 abas: todas numa só linha", len({c[1] for c in caixas}) == 1 and len(caixas) == 5, caixas)
        nav.close()
print("TUDO OK" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
