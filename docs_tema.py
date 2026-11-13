"""Tema visual, marca e montagem de páginas do site (usado por gerar_docs.py).

Só biblioteca padrão. Fontes do sistema, sem recursos externos.
Para mudar cores, tipografia ou layout: edite este arquivo e rode `python3 gerar_docs.py`.
"""
import html
import re

DOMINIO = "heimdall-ai.tech"
AUTOR = "Murillo Bolonhini Cita"
REPO = "https://github.com/mrl2bolonhini/heimdall-ai"
EMAIL = "suporte@heimdall-ai.tech"
LINKEDIN = "https://www.linkedin.com/in/murillobolonhinicita"
ACESSOS = {
    "chat": "https://chat.heimdall-ai.tech",
    "n8n": "https://flows.heimdall-ai.tech",
    "status": "https://status.heimdall-ai.tech",
    "cloud": "https://cloud.heimdall-ai.tech",
}
H = lambda s: html.escape(str(s), quote=True)

# ---------------------------------------------------------------------------------------------------------
# Paleta (também alimenta a página Marca)
# ---------------------------------------------------------------------------------------------------------
PALETA = [
    ("Noite", "#080d1f", "Fundo do tema escuro"),
    ("Papel", "#f3f6fc", "Fundo do tema claro"),
    ("Tinta", "#0c1530", "Texto no tema claro"),
    ("Névoa", "#e9effc", "Texto no tema escuro"),
    ("Gelo", "#93d2fa", "Faixa externa da ponte"),
    ("Azul da ponte", "#42a5f5", "Faixa da ponte e camada de ferramentas"),
    ("Azul profundo", "#1e88e5", "Faixa da ponte e camada de modelos"),
    ("Turquesa", "#26c6da", "Faixa da ponte e camada de acesso único"),
    ("Ouro do olhar", "#ffc107", "Íris e camada de automações"),
]
BANDAS = ["#bfe3fb", "#93d2fa", "#42a5f5", "#26c6da", "#1e88e5", "#ffc107"]


def _lum(hexa):
    h = hexa.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------------------------------------------------
# Marca: símbolo (ponte de seis faixas com olho) em três versões
# ---------------------------------------------------------------------------------------------------------
def _arcos(cx, base, raios, larg, cores):
    return "".join(f'<path d="M{cx - r} {base}A{r} {r} 0 0 1 {cx + r} {base}" fill="none" stroke="{c}" stroke-width="{larg}"/>' for r, c in zip(raios, cores))


def simbolo_svg(classe="", titulo=None, olho_claro="var(--sclera, #ffffff)", pupila="var(--pupil, #0c1530)", movel=False):
    """Símbolo completo, para uso em páginas (segue o tema) ou em arquivos (cores padrão)."""
    t = f'<title>{H(titulo)}</title>' if titulo else ""
    aria = ' role="img"' if titulo else ' aria-hidden="true" focusable="false"'
    idr = ' id="iris"' if movel else ""
    ids = ' id="bridge"' if movel else ""
    return (f'<svg{ids} class="{classe}" viewBox="0 -4 100 62" xmlns="http://www.w3.org/2000/svg"{aria}>{t}'
            + _arcos(50, 46, [45, 38.5, 32, 25.5, 19, 12.5], 6, BANDAS)
            + f'<ellipse cx="50" cy="46" rx="17" ry="9" fill="{olho_claro}"/>'
            + f'<g{idr}><circle cx="50" cy="46" r="6.6" fill="#ffc107"/><circle cx="50" cy="46" r="3.1" fill="{pupila}"/><circle cx="52.2" cy="43.8" r="1.1" fill="#fff" opacity=".85"/></g></svg>')


def simbolo_arquivo():
    return simbolo_svg(titulo="Heimdall-ai", olho_claro="#ffffff", pupila="#0c1530")


def simbolo_mono():
    arcos = "".join(f'<path d="M{50 - r} 46A{r} {r} 0 0 1 {50 + r} 46" fill="none" stroke="currentColor" stroke-width="6" opacity="{o}"/>' for r, o in zip([45, 38.5, 32, 25.5, 19, 12.5], [.35, .5, .65, .8, .9, 1]))
    return ('<svg viewBox="0 -4 100 62" xmlns="http://www.w3.org/2000/svg" role="img"><title>Heimdall-ai (uma cor)</title>' + arcos
            + '<ellipse cx="50" cy="46" rx="17" ry="9" fill="none" stroke="currentColor" stroke-width="2.4"/><circle cx="50" cy="46" r="5.2" fill="currentColor"/></svg>')


def logo_arquivo(escuro=False):
    tinta = "#e9effc" if escuro else "#0c1530"
    return (f'<svg viewBox="0 -4 330 62" xmlns="http://www.w3.org/2000/svg" role="img"><title>Heimdall-ai</title>'
            + '<g>' + _arcos(50, 46, [45, 38.5, 32, 25.5, 19, 12.5], 6, BANDAS)
            + f'<ellipse cx="50" cy="46" rx="17" ry="9" fill="{"#e9effc" if escuro else "#ffffff"}"/><circle cx="50" cy="46" r="6.6" fill="#ffc107"/><circle cx="50" cy="46" r="3.1" fill="{"#080d1f" if escuro else "#0c1530"}"/></g>'
            + f'<text x="112" y="44" font-family="\'Iowan Old Style\',\'Palatino Linotype\',Palatino,\'Book Antiqua\',Georgia,serif" font-size="40" font-weight="700" letter-spacing="-0.5" fill="{tinta}">Heimdall-ai</text></svg>')


def favicon_svg():
    return ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='14' fill='#080d1f'/>"
            "<path d='M8 44a24 24 0 0 1 48 0' fill='none' stroke='#42a5f5' stroke-width='6'/><path d='M16 44a16 16 0 0 1 32 0' fill='none' stroke='#26c6da' stroke-width='5'/>"
            "<ellipse cx='32' cy='44' rx='11' ry='6' fill='#e9effc'/><circle cx='32' cy='44' r='4.2' fill='#ffc107'/></svg>")


def hero_arco():
    return simbolo_svg(classe="bridge", titulo="Uma ponte em arco de seis faixas, em tons de azul e dourado, com um olho no centro que acompanha o ponteiro.", movel=True).replace('id="iris"', 'id="iris"')


# ---------------------------------------------------------------------------------------------------------
# Diagrama de arquitetura
# ---------------------------------------------------------------------------------------------------------
def _no(x, y, w, h, titulo, sub, cor, h2=None):
    return (f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="nd"/><rect x="{x}" y="{y + 8}" width="5" height="{h - 16}" rx="2.5" fill="{cor}"/>'
            f'<text x="{x + 18}" y="{y + 26}" class="nt">{H(titulo)}</text><text x="{x + 18}" y="{y + 46}" class="ns">{H(sub)}</text></g>')


def diagrama():
    L = {"interface": "#42a5f5", "acesso": "#26c6da", "modelos": "#1e88e5", "ferr": "#93d2fa", "auto": "#ffc107"}
    seta = lambda d: f'<path d="{d}" class="ar" marker-end="url(#ponta)"/>'
    s = ('<svg viewBox="0 0 900 450" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="dg-t dg-d">'
         '<title id="dg-t">Mapa do Heimdall-ai</title>'
         '<desc id="dg-d">Na linha de cima, a conversa: você usa o Open WebUI, que fala com o LiteLLM, que usa os modelos do Ollama, os servidores MCP e as bases de documentos e de busca. '
         'Na linha de baixo, as automações: o n8n usa o LiteLLM, aciona o agente do Mac, que grava nos aplicativos do Mac, e avisa no iPhone pelo Bark.</desc>'
         '<defs><marker id="ponta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="am"/></marker></defs>'
         '<text x="0" y="18" class="ln">Conversa</text>'
         + _no(0, 34, 160, 62, "Você", "navegador ou iPhone", L["interface"])
         + _no(210, 34, 190, 62, "Open WebUI", "interface do chat", L["interface"])
         + _no(450, 34, 190, 62, "LiteLLM", "acesso único, porta 9000", L["acesso"])
         + _no(690, 34, 210, 62, "Ollama", "6 modelos no Mac", L["modelos"])
         + seta("M162 65H208") + seta("M402 65H448") + seta("M642 65H688")
         + _no(450, 134, 190, 62, "Servidores MCP", "portas 8000, 8001 e 8004", L["ferr"])
         + _no(690, 134, 210, 62, "Qdrant e SearXNG", "documentos e busca", L["ferr"])
         + seta("M545 98V132") + seta("M642 165H688")
         + '<text x="0" y="262" class="ln">Automação</text>'
         + _no(210, 278, 190, 62, "n8n", "fluxos, porta 5678", L["auto"])
         + _no(450, 278, 190, 62, "Agente do Mac", "ponte local, porta 8003", L["auto"])
         + _no(690, 278, 210, 62, "Notas, Calendário", "e Lembretes do macOS", L["auto"])
         + seta("M402 309H448") + seta("M642 309H688")
         + seta("M305 278V228H415V80H448")
         + _no(210, 378, 190, 62, "Bark", "avisos no iPhone", L["auto"])
         + seta("M305 342V376")
         + '</svg>')
    legenda = ('<ul class="legenda" aria-label="Cores das camadas"><li><i style="background:#42a5f5"></i>Interface</li><li><i style="background:#26c6da"></i>Acesso único</li>'
               '<li><i style="background:#1e88e5"></i>Modelos</li><li><i style="background:#93d2fa"></i>Ferramentas e dados</li><li><i style="background:#ffc107"></i>Automação</li></ul>')
    return (f'<figure class="diagrama"><div class="rolagem" role="region" aria-label="Mapa do projeto (role para os lados em telas pequenas)" tabindex="0">{s}</div>{legenda}'
            '<figcaption class="muted">As setas mostram quem chama quem. A descrição completa está em texto logo abaixo.</figcaption></figure>')


# ---------------------------------------------------------------------------------------------------------
# CSS e JS
# ---------------------------------------------------------------------------------------------------------
CSS = """/* Gerado por gerar_docs.py (docs_tema.py): edite o gerador, não este arquivo. */
:root{--bg:#f3f6fc;--bg2:#e9eff9;--surface:#fff;--ink:#0c1530;--muted:#46557a;--line:#cdd8ea;--link:#0a58ad;--on-link:#fff;--code:#e8eef8;--sclera:#fff;--pupil:#0c1530;--halo:rgba(66,165,245,.16);
--serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--r1:16px;--r2:10px;--r3:6px;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#080d1f;--bg2:#0d1530;--surface:#111a38;--ink:#e9effc;--muted:#a6b4d6;--line:#243157;--link:#86c5ff;--on-link:#080d1f;--code:#0b1230;--sclera:#e9effc;--pupil:#080d1f;--halo:rgba(66,165,245,.14);color-scheme:dark}}
:root[data-theme="dark"]{--bg:#080d1f;--bg2:#0d1530;--surface:#111a38;--ink:#e9effc;--muted:#a6b4d6;--line:#243157;--link:#86c5ff;--on-link:#080d1f;--code:#0b1230;--sclera:#e9effc;--pupil:#080d1f;--halo:rgba(66,165,245,.14);color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-padding-top:6rem}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:1.0625rem;line-height:1.65}
.wrap{max-width:72rem;margin:0 auto;padding:0 1.25rem}
@media (min-width:700px){.wrap{padding:0 2rem}}
a{color:var(--link);text-underline-offset:.2em;text-decoration-thickness:1px}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--link);outline-offset:3px;border-radius:4px}
.skip{position:absolute;left:-999px;top:.5rem;background:var(--ink);color:var(--bg);padding:.6rem 1rem;z-index:30;border-radius:var(--r3)}
.skip:focus{left:.5rem}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.muted{color:var(--muted)}
/* topo: a ponte vira o filete que separa o cabeçalho do conteúdo */
header.top{position:sticky;top:0;z-index:20;background:var(--bg);background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:saturate(1.4) blur(10px);-webkit-backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
header.top::after{content:"";display:block;height:3px;background:linear-gradient(90deg,#bfe3fb 0 16.66%,#93d2fa 0 33.33%,#42a5f5 0 50%,#26c6da 0 66.66%,#1e88e5 0 83.33%,#ffc107 0)}
.barra{display:flex;align-items:center;gap:1rem;min-height:3.75rem;flex-wrap:wrap;padding:.5rem 0}
.marca{display:inline-flex;align-items:center;gap:.65rem;color:var(--ink);text-decoration:none;font-family:var(--serif);font-weight:700;font-size:1.35rem;letter-spacing:-.01em;white-space:nowrap;flex-shrink:0}
.marca svg{width:2.9rem;height:auto;display:block;flex-shrink:0}
.barra .gap{flex:1;min-width:0}
.ferram{display:flex;align-items:center;gap:.5rem;white-space:nowrap;flex-shrink:0}
.ferram a,.ferram button{font:inherit;font-size:.95rem;color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:999px;padding:.35rem .9rem;text-decoration:none;cursor:pointer;line-height:1.4}
.ferram a:hover,.ferram button:hover{border-color:var(--link);color:var(--link)}
nav.menu{width:100%}
nav.menu ul{list-style:none;margin:0;padding:0 0 .35rem;display:flex;gap:.15rem 1.35rem;overflow-x:auto;scrollbar-width:thin}
nav.menu a{display:block;padding:.35rem 0;color:var(--muted);text-decoration:none;white-space:nowrap;border-bottom:2px solid transparent;font-size:.98rem}
nav.menu a:hover{color:var(--ink)}
nav.menu a[aria-current="page"]{color:var(--ink);font-weight:600;border-bottom-color:#ffc107}
@media (min-width:720px){nav.menu ul{flex-wrap:wrap;overflow-x:visible}}
/* texto */
h1,h2,h3{font-family:var(--serif);letter-spacing:-.015em;line-height:1.15;margin:0}
h1{font-size:clamp(2.15rem,5.2vw,3.35rem);margin:2.75rem 0 1.25rem}
h2{font-size:1.65rem;margin:0 0 1rem}
h3{font-size:1.2rem;margin:1.75rem 0 .4rem}
p{margin:0 0 1rem;max-width:68ch}
ul,ol{max-width:68ch}
li{margin:.2rem 0}
code{font-family:var(--mono);font-size:.9em;background:var(--code);padding:.12em .38em;border-radius:var(--r3)}
/* páginas de documentação */
.doc{display:block}
@media (min-width:1120px){.doc{display:grid;grid-template-columns:minmax(0,1fr) 14.5rem;gap:3.5rem}}
.doc>div>section{padding:2.25rem 0;border-top:1px solid var(--line)}
.doc>div>section:first-of-type{border-top:0;padding-top:.5rem}
aside.toc{display:none}
@media (min-width:1120px){aside.toc{display:block;position:sticky;top:6.5rem;align-self:start;margin-top:3.25rem;font-size:.95rem}}
aside.toc p{font-family:var(--serif);font-weight:700;font-size:1.05rem;margin:0 0 .6rem}
aside.toc ul{list-style:none;margin:0;padding:0;border-left:2px solid var(--line)}
aside.toc a{display:block;padding:.28rem 0 .28rem .9rem;margin-left:-2px;border-left:2px solid transparent;color:var(--muted);text-decoration:none}
aside.toc a:hover{color:var(--ink);border-left-color:#ffc107}
/* tabelas e comandos */
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r2);margin:0 0 1.5rem;background:var(--surface)}
table{width:100%;border-collapse:collapse;font-size:.96rem}
caption{text-align:left;font-weight:700;padding:.75rem 1rem .25rem;font-family:var(--serif);font-size:1.05rem}
th,td{text-align:left;vertical-align:top;padding:.65rem 1rem;border-top:1px solid var(--line)}
thead th{background:var(--bg2);font-size:.9rem;border-top:0}
tbody th{font-weight:600}
.cmd{margin:0 0 1.25rem}
.cmd p{margin:0 0 .3rem;font-weight:600}
.cmd .box{display:flex;gap:.5rem;align-items:stretch}
pre{flex:1;margin:0;padding:.8rem 1rem;background:var(--code);border:1px solid var(--line);border-radius:var(--r2);overflow-x:auto;font-family:var(--mono);font-size:.92rem;line-height:1.55}
pre code{background:none;padding:0}
button.copy{font:inherit;font-size:.92rem;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:var(--r2);padding:.5rem .9rem;cursor:pointer;white-space:nowrap}
button.copy:hover{border-color:var(--link);color:var(--link)}
details{margin:0 0 .75rem}summary{cursor:pointer;font-weight:600}
ol.etapas{margin:.25rem 0 1rem;padding-left:1.3rem}
.tag{display:inline-block;font-size:.82rem;font-family:var(--sans);font-weight:500;border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:.05rem .7rem;color:var(--muted);margin-left:.5rem;vertical-align:middle;letter-spacing:0}
/* início */
.hero{display:grid;gap:2rem;align-items:center;padding:2.5rem 0 3rem}
@media (min-width:900px){.hero{grid-template-columns:1fr 1.1fr;gap:3.5rem;padding:4rem 0 4.5rem}}
.hero h1{font-size:clamp(3.1rem,9vw,5.6rem);line-height:.98;margin:0 0 1.35rem;letter-spacing:-.025em}
.lead{font-family:var(--serif);font-size:clamp(1.2rem,2.4vw,1.55rem);line-height:1.4;max-width:32ch;margin:0 0 1rem}
.hero .nota{max-width:46ch;margin:0 0 1.75rem}
.acoes{display:flex;flex-wrap:wrap;gap:.75rem}
.btn{display:inline-block;font:inherit;font-weight:600;text-decoration:none;border-radius:999px;padding:.7rem 1.4rem;border:1px solid var(--link);background:var(--link);color:var(--on-link)}
.btn:hover{filter:brightness(1.08);text-decoration:none}
.btn.sec{background:transparent;color:var(--link)}
.btn.sec:hover{background:var(--halo)}
.hero svg.bridge{width:100%;height:auto;display:block;overflow:visible;filter:drop-shadow(0 24px 40px var(--halo))}
.faixa{padding:2.75rem 0;border-top:1px solid var(--line)}
.faixa>h2{margin-bottom:1.35rem}
.portas{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(15.5rem,1fr));list-style:none;margin:0;padding:0;max-width:none}
.porta{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--r1);padding:1.2rem 1.35rem 1.2rem 1.6rem;margin:0}
.porta::before{content:"";position:absolute;left:0;top:1.1rem;bottom:1.1rem;width:4px;border-radius:0 4px 4px 0;background:var(--cor)}
.porta:hover{border-color:var(--link)}
.porta h3{margin:0 0 .3rem;font-size:1.3rem}
.porta h3 a{color:var(--ink);text-decoration:none}
.porta h3 a::after{content:"";position:absolute;inset:0;border-radius:var(--r1)}
.porta h3 a:hover{text-decoration:underline}
.porta p{margin:0 0 .6rem;color:var(--muted);font-size:.98rem}
.porta .quem{font-size:.86rem;margin:0;color:var(--ink);font-weight:600}
.camadas{list-style:none;margin:0;padding:0;max-width:none;border-top:1px solid var(--line)}
.camadas li{display:grid;grid-template-columns:3.6rem 1fr;gap:0 1.25rem;padding:1.15rem 0 1.15rem 1.15rem;margin:0;border-bottom:1px solid var(--line);position:relative}
.camadas li::before{content:"";position:absolute;left:0;top:1.2rem;bottom:1.2rem;width:4px;border-radius:4px;background:var(--cor)}
.camadas .num{font-family:var(--serif);font-weight:700;font-size:2.4rem;line-height:1;letter-spacing:-.03em;text-align:right}
.camadas h3{margin:.1rem 0 .15rem;font-size:1.2rem}
.camadas p{margin:0;color:var(--muted);max-width:60ch}
@media (min-width:860px){.camadas{display:grid;grid-template-columns:1fr 1fr;column-gap:3rem}.camadas li{border-bottom:1px solid var(--line)}}
.dois{display:grid;gap:1.5rem 3.5rem}
@media (min-width:860px){.dois{grid-template-columns:1fr 1.55fr}}
/* diagrama */
.diagrama{margin:0 0 1.5rem}
.rolagem{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r1);background:var(--surface);padding:1.25rem}
.rolagem svg{display:block;min-width:700px;width:100%;height:auto}
.nd{fill:var(--bg);stroke:var(--line);stroke-width:1.2}
.nt{font:600 15.5px var(--sans);fill:var(--ink)}.ns{font:13px var(--sans);fill:var(--muted)}.ln{font:700 15px var(--serif);fill:var(--ink)}
.ar{fill:none;stroke:var(--muted);stroke-width:1.6}.am{fill:var(--muted)}
.legenda{list-style:none;display:flex;flex-wrap:wrap;gap:.35rem 1.25rem;margin:.9rem 0 .3rem;padding:0;font-size:.92rem;color:var(--muted);max-width:none}
.legenda i{display:inline-block;width:.8rem;height:.8rem;border-radius:50%;margin-right:.45rem;vertical-align:-.08rem}
figcaption{font-size:.92rem}
/* marca */
.amostras{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(18rem,1fr));margin:0 0 1.5rem}
.amostra{border:1px solid var(--line);border-radius:var(--r1);padding:2rem 1.5rem;display:flex;align-items:center;justify-content:center;min-height:9rem}
.amostra svg{max-width:100%;height:4.2rem;width:auto}
.amostra.claro{background:#f3f6fc;color:#0c1530}.amostra.escuro{background:#080d1f;color:#e9effc}.amostra.mono{background:var(--surface);color:var(--ink)}
.cor{display:inline-block;width:1.1rem;height:1.1rem;border-radius:50%;border:1px solid var(--line);vertical-align:-.2rem;margin-right:.6rem}
/* rodapé */
footer{margin-top:3rem;padding:2rem 0 3rem;border-top:1px solid var(--line);color:var(--muted);font-size:.95rem}
footer .linha{display:flex;flex-wrap:wrap;gap:.75rem 2rem;align-items:center;justify-content:space-between}
footer ul{list-style:none;display:flex;flex-wrap:wrap;gap:.25rem 1.25rem;margin:0;padding:0;max-width:none}
footer p{margin:0 0 .25rem}
footer .marca{font-size:1.1rem;color:var(--ink)}footer .marca svg{width:2.4rem}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
@media print{header.top,aside.toc,.ferram,.skip{display:none}body{background:#fff;color:#000}}
"""

JS = """/* Gerado por gerar_docs.py (docs_tema.py). Tema, copiar comando e olho do início. */
(function () {
  var live = document.getElementById('aviso');
  var avisar = function (t) { if (live) { live.textContent = ''; setTimeout(function () { live.textContent = t; }, 50); } };
  var raiz = document.documentElement, btn = document.getElementById('tema');
  var escuro = function () { var t = raiz.getAttribute('data-theme'); return t ? t === 'dark' : !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches); };
  var rotulo = function () { if (btn) { btn.textContent = escuro() ? 'Tema claro' : 'Tema escuro'; } };
  rotulo();
  if (btn) btn.addEventListener('click', function () {
    var novo = escuro() ? 'light' : 'dark';
    raiz.setAttribute('data-theme', novo);
    try { localStorage.setItem('tema', novo); } catch (e) {}
    rotulo(); avisar(novo === 'dark' ? 'Tema escuro ativado.' : 'Tema claro ativado.');
  });
  document.querySelectorAll('button.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var alvo = document.getElementById(b.getAttribute('data-alvo'));
      if (!alvo) return;
      var ok = function () { avisar('Comando copiado.'); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(alvo.textContent).then(ok, function () { avisar('Não foi possível copiar. Selecione o texto do comando.'); });
      else { var r = document.createRange(); r.selectNodeContents(alvo); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); try { document.execCommand('copy'); ok(); } catch (e) {} }
    });
  });
  var svg = document.getElementById('bridge'), iris = document.getElementById('iris');
  if (!svg || !iris || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  iris.style.transition = 'transform .12s ease-out';
  window.addEventListener('pointermove', function (e) {
    var r = svg.getBoundingClientRect(), k = r.width / 100, cx = r.left + 50 * k, cy = r.top + (46 + 4) * k;
    var dx = e.clientX - cx, dy = e.clientY - cy, d = Math.sqrt(dx * dx + dy * dy) || 1, f = Math.min(1, d / (r.width * .5));
    var x = dx / d * 6.5 * f, y = (dy < 0 ? dy / d * 2.4 : dy / d * 1) * f;
    iris.setAttribute('transform', 'translate(' + x.toFixed(2) + ' ' + y.toFixed(2) + ')');
  }, { passive: true });
})();
"""

# ---------------------------------------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------------------------------------
PAGINAS = [
    ("index.html", "Início", "Propósito, acessos e visão geral"),
    ("arquitetura.html", "Arquitetura", "Como as peças se ligam, serviços e portas"),
    ("tecnologias.html", "Tecnologias", "O que foi usado e para quê"),
    ("llms.html", "Modelos", "Modelos de linguagem, usos e testes"),
    ("mcp.html", "Ferramentas", "Servidores MCP e cada ferramenta"),
    ("fluxos.html", "Fluxos", "Fluxos do n8n e scripts"),
    ("notas.html", "Notas", "Heimdall Notas: ler as notas e ouvir os áudios"),
    ("news.html", "News", "Heimdall News: notícias com resumo de IA e feeds RSS"),
    ("cloud.html", "Cloud", "Painel do emulador de AWS: acesso, segurança e roteiro"),
    ("comandos.html", "Comandos", "Subir, testar, instalar e manter"),
    ("novidades.html", "Novidades", "Histórico de recursos"),
    ("roadmap.html", "Roadmap", "Próximos recursos"),
    ("marca.html", "Marca", "Logotipo, cores e tipografia"),
]
SITE = "https://" + DOMINIO + "/"


def _toc(corpo):
    itens = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', corpo, flags=re.S)
    if len(itens) < 2:
        return ""
    lis = "".join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a></li>' for i, t in itens)
    return f'<aside class="toc"><nav aria-label="Nesta página"><p>Nesta página</p><ul>{lis}</ul></nav></aside>'


def pagina(arquivo, titulo, descricao, corpo, home=False):
    menu = "".join('<li><a href="%s"%s>%s</a></li>' % (a, ' aria-current="page"' if a == arquivo else "", H(t)) for a, t, _ in PAGINAS)
    nome = "Heimdall-ai: IA que roda em casa" if arquivo == "index.html" else titulo + " · Heimdall-ai"
    url = SITE if arquivo == "index.html" else SITE + arquivo
    if home:
        principal = corpo
    else:
        principal = f'<div class="doc"><div>{corpo}</div>{_toc(corpo)}</div>'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{H(nome)}</title>
<meta name="description" content="{H(descricao)}">
<meta name="theme-color" content="#080d1f">
<link rel="canonical" href="{H(url)}">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:locale" content="pt_BR">
<meta property="og:site_name" content="Heimdall-ai">
<meta property="og:title" content="{H(nome)}">
<meta property="og:description" content="{H(descricao)}">
<meta property="og:url" content="{H(url)}">
<meta property="og:image" content="{SITE}og.png">
<meta property="og:image:alt" content="Heimdall-ai: uma ponte em arco de seis faixas azuis e douradas com um olho no centro.">
<meta name="twitter:card" content="summary_large_image">
<script>try{{var t=localStorage.getItem('tema');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<link rel="stylesheet" href="style.css">
</head>
<body>
<a class="skip" href="#conteudo">Ir para o conteúdo</a>
<header class="top"><div class="wrap"><div class="barra">
<a class="marca" href="index.html" aria-label="Heimdall-ai, página inicial">{simbolo_svg()}<span>Heimdall-ai</span></a>
<span class="gap"></span>
<nav class="menu" aria-label="Páginas do site"><ul>{menu}</ul></nav>
<div class="ferram"><button type="button" id="tema">Tema escuro</button></div>
</div></div></header>
<main id="conteudo" tabindex="-1"><div class="wrap">
{principal}
</div></main>
<footer><div class="wrap"><div class="linha">
<div><a class="marca" href="index.html" aria-label="Heimdall-ai, página inicial">{simbolo_svg()}<span>Heimdall-ai</span></a>
<p>&copy; 2026 {H(AUTOR)}. Todos os direitos reservados.</p><p>Documentação gerada do código do projeto.</p></div>
<div><p><strong>Contato</strong></p><ul aria-label="Contato"><li><a href="mailto:{EMAIL}">{EMAIL}</a></li><li><a href="{LINKEDIN}">LinkedIn de {H(AUTOR)}</a></li></ul></div>
<ul aria-label="Links do rodapé"><li><a href="{REPO}">Código no GitHub</a></li><li><a href="novidades.html">Novidades</a></li><li><a href="roadmap.html">Roadmap</a></li><li><a href="marca.html">Marca</a></li><li><a href="comandos.html">Comandos</a></li></ul>
</div></div></footer>
<p id="aviso" class="sr" role="status" aria-live="polite"></p>
<script src="heimdall.js" defer></script>
</body>
</html>
"""


_contador = [0]


def comando(texto, rotulo):
    _contador[0] += 1
    i = "cmd%d" % _contador[0]
    return (f'<div class="cmd"><p>{H(rotulo)}</p><div class="box"><pre tabindex="0" aria-label="Comando: {H(rotulo)}"><code id="{i}">{H(texto)}</code></pre>'
            f'<button type="button" class="copy" data-alvo="{i}" aria-label="Copiar comando: {H(rotulo)}">Copiar</button></div></div>')


def tabela(legenda, cab, linhas):
    t = '<div class="tablewrap"><table><caption>%s</caption><thead><tr>%s</tr></thead><tbody>' % (H(legenda), "".join('<th scope="col">%s</th>' % H(c) for c in cab))
    for l in linhas:
        t += "<tr>" + "".join(("<th scope=\"row\">%s</th>" if k == 0 else "<td>%s</td>") % c for k, c in enumerate(l)) + "</tr>"
    return t + "</tbody></table></div>"


# ---------------------------------------------------------------------------------------------------------
# Corpo da página inicial e da página Marca
# ---------------------------------------------------------------------------------------------------------
def corpo_inicio(n_modelos, n_ferr, n_pub, n_mac, n_mcp, n_fluxos):
    return f"""
<div class="hero"><div>
<h1>Heimdall-ai</h1>
<p class="lead">Inteligência Artificial que roda em casa: modelos locais, ferramentas que fazem coisas de verdade e automações que avisam no iPhone.</p>
<p class="muted nota">Projeto de {H(AUTOR)}. O chat é privado, por convite; o código e esta documentação são abertos.</p>
<div class="acoes"><a class="btn" href="arquitetura.html">Ver como funciona</a><a class="btn sec" href="{REPO}">Código no GitHub</a></div>
</div>{hero_arco()}</div>
<section class="faixa" aria-labelledby="acessos"><h2 id="acessos">Acessos</h2>
<ul class="portas">
<li class="porta" style="--cor:#42a5f5"><h3><a href="{ACESSOS['chat']}">Chat</a></h3><p>Conversar com os modelos, com busca na web e documentos.</p><p class="quem">Por convite</p></li>
<li class="porta" style="--cor:#ffc107"><h3><a href="{ACESSOS['n8n']}">Automações</a></h3><p>Ver e ajustar os fluxos que rodam sozinhos.</p><p class="quem">Login do administrador</p></li>
<li class="porta" style="--cor:#26c6da"><h3><a href="{ACESSOS['status']}">Status</a></h3><p>Ver se os serviços estão no ar.</p><p class="quem">Acesso restrito</p></li>
<li class="porta" style="--cor:#1e88e5"><h3><a href="{ACESSOS['cloud']}">Cloud</a></h3><p>Painel do emulador de AWS: S3, Lambda, Glue e Athena. <a href="cloud.html">Como funciona</a>.</p><p class="quem">Senha e código de 6 dígitos</p></li>
<li class="porta" style="--cor:#93d2fa"><h3><a href="{REPO}">Código</a></h3><p>Repositório do projeto no GitHub.</p><p class="quem">Público</p></li>
</ul></section>
<section class="faixa" aria-labelledby="proposito"><div class="dois"><h2 id="proposito">Por que existe</h2><div>
<p>Heimdall, na mitologia nórdica, guarda Bifröst, a ponte em arco-íris que liga os mundos. O projeto leva o nome dele: um assistente que vigia e conecta as ferramentas de quem o criou.</p>
<p>Os modelos rodam no próprio Mac, e não em serviços de terceiros. Eles ganham ferramentas reais (busca na web, arquivos, documentos, memória, Notas e Calendário) e rotinas automáticas: resumos, estudo, vigilância de privacidade e avisos no iPhone.</p>
<p>Foi pensado para quem usa leitor de tela: tudo se opera por texto e comandos, e as automações entregam notas e áudio.</p></div></div></section>
<section class="faixa" aria-labelledby="mapa"><h2 id="mapa">Como as peças se ligam</h2>
{diagrama()}
<p><a href="arquitetura.html">Ler a arquitetura completa</a>, com serviços, portas e princípios de privacidade.</p></section>
<section class="faixa" aria-labelledby="dentro"><h2 id="dentro">O que tem dentro</h2>
<ul class="camadas">
<li style="--cor:#1e88e5"><span class="num" aria-hidden="true">{n_modelos}</span><div><h3><a href="llms.html">{n_modelos} modelos de linguagem</a></h3><p>Rodam no Ollama e se alternam conforme a tarefa: conversa, código, imagens.</p></div></li>
<li style="--cor:#93d2fa"><span class="num" aria-hidden="true">{n_ferr}</span><div><h3><a href="mcp.html">{n_ferr} ferramentas em {n_mcp} servidores MCP</a></h3><p>{n_pub} abertas a convidados e {n_mac} restritas ao Mac do administrador.</p></div></li>
<li style="--cor:#ffc107"><span class="num" aria-hidden="true">{n_fluxos}</span><div><h3><a href="fluxos.html">{n_fluxos} fluxos de automação</a></h3><p>Estudo diário, monitor de privacidade, diários oficiais, revisão de código e mais.</p></div></li>
<li style="--cor:#26c6da"><span class="num" aria-hidden="true">0</span><div><h3><a href="arquitetura.html#seg">Dados pessoais fora do código</a></h3><p>Chaves e identificadores ficam só no Mac; notas privadas nunca são lidas.</p></div></li>
</ul></section>
"""


def corpo_marca():
    linhas = []
    for nome, hexa, uso in PALETA:
        c1, c2 = contraste(hexa, "#f3f6fc"), contraste(hexa, "#080d1f")
        linhas.append((f'<span class="cor" style="background:{hexa}" aria-hidden="true"></span>{H(nome)}', f"<code>{hexa}</code>", H(uso), f"{c1:.1f}:1", f"{c2:.1f}:1"))
    return f"""
<h1>Marca</h1>
<section aria-labelledby="simbolo"><h2 id="simbolo">Símbolo e logotipo</h2>
<p>O símbolo é a ponte Bifröst vista de frente: seis faixas em azul e dourado e, no centro, o olho de quem vigia. O olho acompanha o ponteiro na página inicial.</p>
<div class="amostras">
<div class="amostra claro">{logo_arquivo(False)}</div>
<div class="amostra escuro">{logo_arquivo(True)}</div>
<div class="amostra mono">{simbolo_mono()}</div>
</div>
<ul>
<li><a href="logo.svg">logo.svg</a>, para fundos claros</li>
<li><a href="logo-escuro.svg">logo-escuro.svg</a>, para fundos escuros</li>
<li><a href="simbolo.svg">simbolo.svg</a>, só o símbolo</li>
<li><a href="simbolo-uma-cor.svg">simbolo-uma-cor.svg</a>, uma cor (segue a cor do texto)</li>
<li><a href="og.png">og.png</a>, imagem de compartilhamento (1200 por 630)</li>
</ul>
<h3>Uso</h3>
<ul><li>Deixe ao redor do símbolo um espaço livre igual à altura da íris.</li><li>Não estique, não gire e não troque as cores das faixas.</li><li>Em fundo de foto ou de cor viva, use a versão de uma cor.</li></ul></section>
<section aria-labelledby="cores"><h2 id="cores">Cores</h2>
<p>As seis faixas da ponte dão a paleta. Os contrastes abaixo seguem a medida das diretrizes WCAG; para texto comum, o mínimo é 4,5 para 1.</p>
{tabela("Paleta", ["Cor", "Hex", "Uso", "Sobre o Papel", "Sobre a Noite"], linhas)}
<p class="muted">Cores claras servem para formas e destaques, não para texto sobre fundo claro.</p></section>
<section aria-labelledby="tipo"><h2 id="tipo">Tipografia</h2>
<p>O site usa só fontes do sistema, sem baixar nada. Os títulos usam uma serifa de livro (Iowan Old Style, Palatino ou Georgia, o que o aparelho tiver), pelo tom de saga; o texto e a interface usam a fonte do sistema; comandos usam a monoespaçada.</p></section>
<section aria-labelledby="terceiros"><h2 id="terceiros">Marcas de terceiros</h2>
<p>Ollama, LiteLLM, Open WebUI, n8n, Qdrant, SearXNG, Cloudflare, GitHub e as demais tecnologias citadas pertencem aos seus donos. Este site cita só os nomes e leva aos sites oficiais, sem reproduzir os logotipos.</p></section>
"""
