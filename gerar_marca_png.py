"""Gera og.png e apple-touch-icon.png a partir da marca (precisa de Playwright). Só rode ao mudar a marca."""
import sys
from pathlib import Path
from docs_tema import simbolo_arquivo, H
from playwright.sync_api import sync_playwright
D = Path(__file__).resolve().parent / "docs"
sym = simbolo_arquivo()
og = f"""<html><body style="margin:0;width:1200px;height:630px;background:#080d1f;display:flex;align-items:center;font-family:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;color:#e9effc">
<div style="padding:0 90px;display:flex;align-items:center;gap:70px;width:100%"><div style="flex:1"><div style="font-size:112px;font-weight:700;letter-spacing:-3px;line-height:1">Heimdall-ai</div>
<div style="font-size:36px;line-height:1.35;margin-top:28px;color:#a6b4d6;max-width:520px">IA que roda em casa, com ferramentas e automações.</div></div>
<div style="width:460px">{sym.replace('var(--sclera, #ffffff)','#e9effc')}</div></div>
<div style="position:absolute;left:0;right:0;bottom:0;height:12px;background:linear-gradient(90deg,#bfe3fb 0 16.66%,#93d2fa 0 33.33%,#42a5f5 0 50%,#26c6da 0 66.66%,#1e88e5 0 83.33%,#ffc107 0)"></div></body></html>"""
ap = f"""<html><body style="margin:0;width:180px;height:180px;background:#080d1f;display:flex;align-items:center;justify-content:center"><div style="width:140px">{sym.replace('var(--sclera, #ffffff)','#e9effc')}</div></body></html>"""
with sync_playwright() as p:
    b = p.chromium.launch()
    for html_, nome, w, h in ((og, "og.png", 1200, 630), (ap, "apple-touch-icon.png", 180, 180)):
        pg = b.new_page(viewport={"width": w, "height": h}); pg.set_content(html_); pg.screenshot(path=str(D / nome)); pg.close()
    b.close()
print("ok")
