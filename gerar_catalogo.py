#!/usr/bin/env python3
"""Gera o catálogo de comandos do dono (guides/catalogo_comandos.html) a partir de guides/studio_ajuda.txt e do studio.zsh.

Página só do dono: não vai para o site público (docs/). Abre com `studio help --doc`, servida em 127.0.0.1.
Acessível: lang pt-BR, pular para o conteúdo, um só h1, índice por grupo, busca com rótulo e contagem falada, tabelas com caption e scope.
"""
import html
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "guides" / "catalogo_comandos.html"

GRUPOS = [
    ("Subir e manter o ecossistema", ["up", "restart", "stop", "status", "logs", "containers", "models", "doctor", "update", "docs", "tests", "dir", "cd", "help"]),
    ("Produtos Studio", ["health", "finance", "news", "learn", "games", "hub", "miner", "trading", "lab"]),
    ("Serviços de apoio", ["account", "controls", "chat", "n8n", "kuma", "dozzle", "urls", "support", "app", "mailbox"]),
    ("Dados, segurança e continuidade", ["db", "backup", "continuity", "access", "mail", "notices", "env", "cloudflare", "usage"]),
    ("Modelos, conhecimento e automações", ["ask", "cloudai", "ingest", "voice", "listen", "mcp", "flows", "hook", "notion"]),
]


def ler_secoes() -> list:
    """Lê guides/studio_ajuda.txt: lista de {nome, resumo, desc, opcoes [(opção, texto)], exemplos}."""
    secoes, atual, modo = [], None, ""
    for linha in (AQUI / "guides/studio_ajuda.txt").read_text(encoding="utf-8").splitlines():
        if linha.startswith("#") or (not linha.strip() and atual is None):
            continue
        if linha.startswith("@ "):
            nome, _, resumo = linha[2:].partition(" | ")
            atual = {"nome": nome.strip(), "resumo": resumo.strip(), "desc": [], "opcoes": [], "exemplos": []}
            secoes.append(atual)
            modo = "desc"
        elif atual is None or not linha.strip():
            continue
        elif linha.strip() == "Opções:":
            modo = "opcoes"
        elif linha.strip() == "Exemplos:":
            modo = "exemplos"
        elif modo == "opcoes":
            if re.match(r"^\s+-", linha):
                partes = re.split(r"\s{2,}", linha.strip(), maxsplit=1)
                atual["opcoes"].append([partes[0], partes[1] if len(partes) > 1 else ""])
            elif atual["opcoes"]:  # linha de continuação do texto da opção anterior
                atual["opcoes"][-1][1] += " " + linha.strip()
        elif modo == "exemplos":
            atual["exemplos"].append(linha.strip())
        else:
            atual["desc"].append(linha.strip())
    return secoes


def programas() -> dict:
    """Programa por trás de cada comando, lido do case do studio.zsh: {comando: [arquivos .py/.sh]}."""
    codigo = (AQUI / "studio.zsh").read_text(encoding="utf-8")
    trecho = codigo.split("studio() {")[1].split("# Completar")[0]
    out = {}
    for m in re.finditer(r"^    ([a-z0-9|]+)\)(.*?)(?=^    [a-z0-9|*]+\)|\Z)", trecho, re.S | re.M):
        arqs = re.findall(r"\b(?:_studio_py|_studio_sh)\s+\"?\$?\{?(?:STUDIO_DIR\}?/)?([A-Za-z0-9_./-]+\.(?:py|sh))", m.group(2))
        for nome in m.group(1).split("|"):
            out[nome] = list(dict.fromkeys(arqs))
    return out


def H(t) -> str:
    return html.escape(str(t), quote=True)


CSS = """
:root{--fundo:#ffffff;--texto:#14181f;--suave:#4a5260;--linha:#c9ced8;--destaque:#0b4fb3;--codigo:#eef1f6}
@media (prefers-color-scheme:dark){:root{--fundo:#0c1020;--texto:#eef1f7;--suave:#aab3c5;--linha:#2f3752;--destaque:#8db8ff;--codigo:#151b31}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);font:1rem/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:var(--fundo);padding:8px;border:2px solid var(--destaque);z-index:9}
main{max-width:62rem;margin:0 auto;padding:1rem 1.25rem 4rem}a{color:var(--destaque)}
a:focus-visible,input:focus-visible,summary:focus-visible,button:focus-visible{outline:3px solid var(--destaque);outline-offset:2px}
h1{font-size:1.9rem;margin:.6rem 0}h2{font-size:1.4rem;margin:2rem 0 .5rem;border-bottom:1px solid var(--linha);padding-bottom:.2rem}h3{font-size:1.15rem;margin:0 0 .3rem}
.muted{color:var(--suave)}code,pre{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.95em}code{background:var(--codigo);padding:.05em .3em;border-radius:4px}
pre{background:var(--codigo);padding:.7rem .9rem;border-radius:6px;overflow-x:auto;margin:.3rem 0}pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:.5rem 0}caption{text-align:left;font-weight:600;padding:.2rem 0}th,td{border:1px solid var(--linha);padding:.4rem .6rem;text-align:left;vertical-align:top}thead th{background:var(--codigo)}
.cmd{border:1px solid var(--linha);border-radius:8px;padding:.9rem 1.1rem;margin:1rem 0}.cmd[hidden],li[hidden],section[hidden]{display:none}
#busca-bloco{margin:1rem 0}#busca{width:100%;max-width:34rem;padding:.55rem .7rem;font:inherit;color:inherit;background:var(--fundo);border:2px solid var(--linha);border-radius:6px}
nav ul{columns:2;column-gap:2rem;padding-left:1.2rem}@media (max-width:640px){nav ul{columns:1}}nav li{break-inside:avoid;margin:.15rem 0}
.sr{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
"""

JS = """
(function(){
  var bloco=document.getElementById('busca-bloco');if(!bloco)return;
  bloco.hidden=false;
  var campo=document.getElementById('busca'),aviso=document.getElementById('aviso-busca');
  var cartoes=[].slice.call(document.querySelectorAll('section.cmd')),itens=[].slice.call(document.querySelectorAll('nav li[data-cmd]'));
  var grupos=[].slice.call(document.querySelectorAll('section.grupo'));
  var textos=cartoes.map(function(c){return c.textContent.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')});
  var timer=null;
  function filtrar(){
    var q=campo.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').trim(),n=0,ids={};
    cartoes.forEach(function(c,i){var ok=!q||textos[i].indexOf(q)>=0;c.hidden=!ok;if(ok){n++;ids[c.id]=1}});
    itens.forEach(function(li){li.hidden=!ids[li.getAttribute('data-cmd')]});
    grupos.forEach(function(g){g.hidden=!g.querySelector('section.cmd:not([hidden])')});
    clearTimeout(timer);
    timer=setTimeout(function(){aviso.textContent=q?(n===0?'Nenhum comando encontrado.':n+(n===1?' comando encontrado.':' comandos encontrados.')):''},500);
  }
  campo.addEventListener('input',filtrar);
  campo.addEventListener('keydown',function(e){if(e.key==='Escape'){campo.value='';filtrar()}});
})();
"""


def gerar() -> str:
    secoes = {s["nome"]: s for s in ler_secoes()}
    prog = programas()
    nomes_em_grupo = [n for _, g in GRUPOS for n in g]
    soltos = [n for n in secoes if n not in nomes_em_grupo]
    grupos = list(GRUPOS) + ([("Outros", soltos)] if soltos else [])
    corpo = []
    for titulo, nomes in grupos:
        nomes = [n for n in nomes if n in secoes]
        if not nomes:
            continue
        gid = "g-" + re.sub(r"[^a-z0-9]+", "-", titulo.lower())
        blocos = []
        for n in nomes:
            s = secoes[n]
            opcoes = ""
            if s["opcoes"]:
                linhas = ""
                for o, t in s["opcoes"]:
                    m = re.match(r"^(-\w),\s+(--[\w-]+)\s*(.*)$", o)
                    curta, longa, arg = (m.group(1), m.group(2), m.group(3)) if m else ("", o, "")
                    linhas += (f'<tr><th scope="row"><code>{H(longa)}</code>' + (f" <code>{H(arg)}</code>" if arg else "")
                               + f'</th><td>{(H(curta) if curta else "-")}</td><td>{H(t)}</td></tr>')
                opcoes = f'<table><caption>Opções de studio {H(n)}</caption><thead><tr><th scope="col">Opção (e argumento)</th><th scope="col">Forma curta</th><th scope="col">O que faz</th></tr></thead><tbody>{linhas}</tbody></table>'
            exemplos = "".join(f"<pre><code>{H(e)}</code></pre>" for e in s["exemplos"])
            arqs = prog.get(n) or []
            por_tras = ""
            if arqs:
                lista = ", ".join(f"<code>{H(a)}</code>" for a in arqs)
                por_tras = f'<p class="muted">Programa por trás: {lista}. Em Windows e Linux sem zsh, rode o programa direto (<code>py {H(arqs[0])}</code> no PowerShell, <code>python3 {H(arqs[0])}</code> no Linux); as opções dele são em português e aparecem com <code>--help</code> do programa.</p>' if arqs[0].endswith(".py") else f'<p class="muted">Script por trás: {lista} (shell; no Windows, use o WSL).</p>'
            blocos.append(f'<section class="cmd" id="c-{H(n)}" aria-labelledby="t-{H(n)}"><h3 id="t-{H(n)}"><code>studio {H(n)}</code></h3>'
                          f'<p><strong>{H(s["resumo"])}.</strong> {H(" ".join(s["desc"]))}</p>{opcoes}'
                          + (f"<p>Exemplos:</p>{exemplos}" if exemplos else "") + por_tras + "</section>")
        corpo.append(f'<section class="grupo" aria-labelledby="{gid}"><h2 id="{gid}">{H(titulo)}</h2>{"".join(blocos)}</section>')
    nav_grupos = "".join(
        f'<li><a href="#g-{re.sub(r"[^a-z0-9]+", "-", t.lower())}">{H(t)}</a><ul>'
        + "".join(f'<li data-cmd="c-{n}"><a href="#c-{n}"><code>studio {H(n)}</code></a>: {H(secoes[n]["resumo"])}</li>' for n in ns if n in secoes) + "</ul></li>"
        for t, ns in grupos if any(n in secoes for n in ns))
    total = len(secoes)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Catálogo de comandos - StudioLibre</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip" href="#conteudo">Ir para o conteúdo</a>
<main id="conteudo" tabindex="-1">
<h1>Catálogo de comandos do studio</h1>
<p>Referência do dono, com os {total} comandos do terminal. Toda opção tem a forma longa (dois hífens) e a curta (uma letra); <code>studio COMANDO --help</code> mostra a ajuda de um comando. O comando é do zsh (macOS e Linux). Esta página fica só no Mac e é gerada de <code>guides/studio_ajuda.txt</code> por <code>python3 gerar_docs.py</code>; abre com <code>studio help --doc</code>.</p>
<div id="busca-bloco" role="search" hidden><label for="busca">Buscar por comando, opção ou texto</label><br><input id="busca" type="search" autocomplete="off" aria-describedby="dica-busca"><p id="dica-busca" class="muted">A lista abaixo filtra enquanto você digita. Esc limpa a busca.</p><p id="aviso-busca" class="sr" role="status" aria-live="polite"></p></div>
<nav aria-label="Índice de comandos"><h2 id="indice">Índice</h2><ul>{nav_grupos}</ul></nav>
{"".join(corpo)}
</main>
<script>{JS}</script>
</body>
</html>
"""


def main(so_checar: bool = False) -> bool:
    novo = gerar()
    atual = SAIDA.read_text(encoding="utf-8") if SAIDA.exists() else ""
    if atual == novo:
        return True
    if not so_checar:
        SAIDA.write_text(novo, encoding="utf-8")
    return False


if __name__ == "__main__":
    main()
    print("Gerado:", SAIDA)
