#!/usr/bin/env python3
"""Área de Notas do Studio Hub (fase B do plano `guides/hub_plano.txt`, 27/11/2026): as notas e os documentos de estudo, a busca, os áudios e o catálogo
de notas escritas, dentro do Hub. Reaproveita a leitura, o Markdown e a busca de heimdall_notas; só o dono vê esta área (convidados recebem aviso).
Somente leitura nos arquivos; lembrete e evento do catálogo só nascem depois do aceite (heimdall_catalogo)."""
import mimetypes
from datetime import datetime
from urllib.parse import quote

import heimdall_catalogo as catalogo
from heimdall_memory_dados import ErroMemory
import heimdall_design as design
import heimdall_notas as n
import heimdall_paginacao as pag
import heimdall_perguntar as perguntar
import heimdall_pessoas as pessoas
import heimdall_servico_web as web

e = web.e
PREFIXO = "/notas"
GRUPO = ("Notas", [(PREFIXO, "Recentes"), (PREFIXO + "/temas", "Temas"), (PREFIXO + "/busca", "Busca"), (PREFIXO + "/catalogo", "Catálogo")])
PERTENCE = {PREFIXO + "/tema": PREFIXO + "/temas", PREFIXO + "/nota": PREFIXO + "/temas", PREFIXO + "/documento": PREFIXO + "/temas"}
CSS = n.CSS.replace("body{font-size:19px;line-height:1.7;max-width:46rem}", "").replace(n.nuvem.CSS, "").replace(pag.CSS, "")


def _dono() -> bool:
    return pessoas.e_dono()


def _so_dono() -> tuple:
    return "Notas", '<p role="status">Esta área é só do dono do Studio Hub.</p>'


def _item(chave: str, p, titulo: str, mtime: float, audio: bool, tema: str = "") -> str:
    extra = " · com áudio" if audio else ""
    sufixo = f" · {e(tema)}" if tema else ""
    link = f"{PREFIXO}/nota?p={quote(chave)}&amp;n={quote(p.name)}"
    return (f'<li><h3>{e(titulo)}</h3><a href="{link}">Leia mais sobre {e(n.inicio_do_titulo(titulo))}</a>'
            f'<span class="meta">{datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")}{sufixo}{extra}</span></li>')


def pg_recentes(ctx):
    if not _dono():
        return _so_dono()
    ps = n.pastas()
    todas = sorted(((m, k, p, t, a) for k in ps for p, t, m, a in n.notas_da_pasta(k)), reverse=True)
    paginas = pag.total_de_paginas(len(todas), n.POR_PAGINA)
    pagina = pag.limitar(ctx.pagina(), paginas)
    if not todas:
        return "Notas recentes", '<p class="nota">Ainda não há notas aqui. Elas aparecem depois do próximo estudo.</p>'
    fatia = todas[(pagina - 1) * n.POR_PAGINA:pagina * n.POR_PAGINA]
    return "Notas recentes", ('<ul class="lista">' + "".join(_item(k, p, t, m, a, ps[k]["nome"]) for m, k, p, t, a in fatia) + "</ul>"
                              + pag.html_paginacao(PREFIXO, pagina, paginas, {}, n.plural(len(todas), "nota", "notas")))


def pg_temas(ctx):
    if not _dono():
        return _so_dono()
    ps = n.pastas()
    if not ps:
        return "Temas das notas", '<p class="nota">Nenhum tema encontrado.</p>'
    itens = []
    for k, v in sorted(ps.items(), key=lambda kv: n.sem_acento(kv[1]["nome"])):
        nn, nd = len(n.notas_da_pasta(k)), len(n.documentos_da_pasta(k))
        itens.append(f'<li>{design.botao(PREFIXO + "/tema", v["nome"], {"t": k})}<span class="meta">{n.plural(nn, "nota", "notas")} · {n.plural(nd, "documento", "documentos")}</span></li>')
    return "Temas das notas", '<ul class="lista">' + "".join(itens) + "</ul>"


def pg_tema(ctx):
    if not _dono():
        return _so_dono()
    chave = ctx.p("t")
    v = n.pastas().get(chave)
    if not v:
        raise ErroMemory("Tema não encontrado.")
    notas, docs = n.notas_da_pasta(chave), n.documentos_da_pasta(chave)
    corpo = ['<h2 id="notas">Notas</h2>']
    if notas:
        paginas = pag.total_de_paginas(len(notas), n.POR_PAGINA)
        pagina = pag.limitar(ctx.pagina(), paginas)
        fatia = notas[(pagina - 1) * n.POR_PAGINA:pagina * n.POR_PAGINA]
        corpo.append('<ul class="lista" aria-labelledby="notas">' + "".join(_item(chave, p, t, m, a) for p, t, m, a in fatia) + "</ul>")
        corpo.append(pag.html_paginacao(PREFIXO + "/tema", pagina, paginas, {"t": chave}, n.plural(len(notas), "nota", "notas")))
    else:
        corpo.append('<p class="nota">Nenhuma nota neste tema ainda.</p>')
    corpo.append('<h2 id="docs">Documentos</h2>')
    if docs:
        itens = []
        for rel, p in docs:
            tam = p.stat().st_size
            kb = f"{tam / 1024 / 1024:.1f} MB" if tam > 1024 * 1024 else f"{max(1, tam // 1024)} KB"
            itens.append(f'<li><a href="{PREFIXO}/documento?t={quote(chave)}&amp;c={quote(rel)}">{e(rel)}</a><span class="meta">{e(p.suffix[1:].upper())} · {kb}</span></li>')
        corpo.append('<ul class="lista" aria-labelledby="docs">' + "".join(itens) + "</ul>")
    else:
        corpo.append('<p class="nota">Nenhum documento neste tema.</p>')
    return v["nome"], "".join(corpo)


def pg_nota(ctx):
    if not _dono():
        return _so_dono()
    chave = ctx.p("p")
    ps = n.pastas()
    base = ps.get(chave, {}).get("cofre")
    p = n.arquivo_seguro(base, ctx.p("n"), n.EXT_NOTA) if base else None
    if not p:
        raise ErroMemory("Nota não encontrada.")
    md = n.ler_texto(p)
    meta, corpo_md = n.separa_frontmatter(md)
    bruto = n.titulo_de(p, md)
    titulo = n.titulo_exibicao(bruto, corpo_md, p)
    a = n.audio_da_nota(chave, p)
    partes = [f'<p class="meta">{e(ps[chave]["nome"])} · {n.data_de(p)}</p>']
    if a:
        partes.append(n.leitor(f"{PREFIXO}/audio?p={quote(chave)}&n={quote(a.name)}", f"{chave}/{p.name}", mimetypes.guess_type(a.name)[0] or "audio/mp4"))
    for k, rot in (("tags", "Tags"), ("conceitos", "Conceitos"), ("entidades", "Entidades")):
        if meta.get(k):
            partes.append(f'<p class="nota"><strong>{rot}:</strong> {e(", ".join(meta[k]))}.</p>')
    partes.append(f'<article aria-label="Texto da nota">{n.markdown_html(corpo_md, bruto)}</article>')
    lista = [x[0].name for x in n.notas_da_pasta(chave)]
    nav = []
    if p.name in lista:
        i = lista.index(p.name)
        if i + 1 < len(lista):
            nav.append(design.botao(PREFIXO + "/nota", "Nota anterior", {"p": chave, "n": lista[i + 1]}))
        if i > 0:
            nav.append(design.botao(PREFIXO + "/nota", "Próxima nota", {"p": chave, "n": lista[i - 1]}))
    nav.append(design.botao(PREFIXO + "/tema", "Todas as notas do tema", {"t": chave}))
    partes.append('<nav class="ant-prox" aria-label="Entre as notas">' + "".join(nav) + "</nav>")
    return titulo, "".join(partes)


def pg_documento(ctx):
    if not _dono():
        return _so_dono()
    chave, rel = ctx.p("t"), ctx.p("c")
    ps = n.pastas()
    p = n.doc_seguro(ps.get(chave, {}).get("docs"), rel)
    if not p:
        raise ErroMemory("Documento não encontrado.")
    if p.suffix.lower() not in n.EXT_NOTA | n.EXT_AUDIO:
        return p.stem, design.botao(PREFIXO + "/arquivo", "Baixar o arquivo original", {"t": chave, "c": rel, "baixar": "1"})
    titulo, corpo, _audio = n.pg_doc(chave, rel, p)
    corpo = (corpo.replace(f'href="/tema?t={quote(chave)}"', f'href="{PREFIXO}/tema?t={quote(chave)}"')
             .replace(f'src="/arquivo?t=', f'src="{PREFIXO}/arquivo?t=').replace('action="/arquivo"', f'action="{PREFIXO}/arquivo"'))
    return titulo, corpo


def pg_busca(ctx):
    if not _dono():
        return _so_dono()
    q = ctx.p("q")
    form = (f'<form class="busca" method="get" action="{PREFIXO}/busca" role="search"><div><label for="q">Buscar nas notas e documentos de texto</label>'
            f'<input id="q" name="q" type="text" value="{e(q)}" autocomplete="off"></div><button type="submit">Buscar</button></form>')
    if len(q.strip()) < 2:
        return "Buscar nas notas", form + ('<p class="nota">Escreva pelo menos duas letras. A busca ignora acentos e maiúsculas.</p>' if q.strip() else "")
    r = n.busca(q)
    if not r:
        return "Buscar nas notas", form + '<p role="status">Nada encontrado.</p>'
    paginas = pag.total_de_paginas(len(r), n.POR_PAGINA)
    pagina = pag.limitar(ctx.pagina(), paginas)
    itens = "".join(f'<li><a href="{PREFIXO}{e(l)}">{e(t)}</a><span class="meta">{e(tema)}</span><span class="meta">{e(tr)}</span></li>'
                    for l, t, tema, tr in r[(pagina - 1) * n.POR_PAGINA:pagina * n.POR_PAGINA])
    return "Buscar nas notas", (form + f'<p role="status">{n.plural(len(r), "resultado", "resultados")}.</p><ul class="lista">{itens}</ul>'
                                + pag.html_paginacao(PREFIXO + "/busca", pagina, paginas, {"q": q}, n.plural(len(r), "resultado", "resultados")))


def pg_catalogo(ctx):
    if not _dono():
        return _so_dono()
    csrf = ctx.csrf
    form = (f'<section aria-labelledby="escrever-t"><h2 id="escrever-t">Salvar nota</h2>'
            '<p class="sub">Escreva uma nota e o Studio Hub a cataloga: ideias, contatos e endereços vão para o Notion; lembretes e eventos com data ficam pendentes '
            'e só vão para o Lembretes e o Calendário depois do seu aceite. Assuntos de saúde e finanças nunca vão para o Notion.</p>'
            f'<form method="post" action="{PREFIXO}/salvar"><input type="hidden" name="csrf" value="{e(csrf)}">'
            '<p><label for="texto">Nota</label><br><textarea id="texto" name="texto" maxlength="8000" rows="5"></textarea></p>'
            '<button type="submit">Salvar nota</button></form></section>')
    return "Catálogo de notas", form + catalogo.bloco_html(csrf, csrf, PREFIXO + "/catalogo", PREFIXO)


def audio(ctx):
    if not _dono():
        return None
    base = n.pastas().get(ctx.p("p"), {}).get("cofre")
    return n.arquivo_seguro(base / "audio", ctx.p("n"), n.EXT_AUDIO) if base else None


def arquivo(ctx):
    if not _dono():
        return None
    return n.doc_seguro(n.pastas().get(ctx.p("t"), {}).get("docs"), ctx.p("c"))


def post_salvar(ctx, campos, arquivos):
    texto = campos.get("texto", "").strip()[:8000]
    if len(texto) >= 3 and _dono():
        dono = ctx.csrf
        perguntar.iniciar(dono, "catalogo", lambda: catalogo.processar(dono, texto), texto[:80])
    return PREFIXO + "/catalogo"


def _id(campos) -> str:
    return "".join(c for c in campos.get("id", "") if c in "0123456789abcdef")[:10]


def post_confirmar(ctx, campos, arquivos):
    if _dono():
        catalogo.confirmar(ctx.csrf, _id(campos), campos.get("data", ""), campos.get("hora", ""))
    return PREFIXO + "/catalogo"


def post_descartar(ctx, campos, arquivos):
    if _dono():
        catalogo.descartar(ctx.csrf, _id(campos))
    return PREFIXO + "/catalogo"


def post_desfazer(ctx, campos, arquivos):
    if _dono():
        catalogo.desfazer(ctx.csrf, _id(campos))
    return PREFIXO + "/catalogo"


def contexto(ctx) -> str:
    """Perguntar nas telas de Notas: só trechos das notas que combinam com a pergunta (o modelo responde só com isto)."""
    return "Notas do usuário (cada trecho traz o título da nota e o tema):\n" + n.contexto_notas(ctx.p("pergunta"))


def script(rota: str) -> str:
    return n.SCRIPT_LEITOR if rota in (PREFIXO + "/nota", PREFIXO + "/documento") else ""


GET = {PREFIXO: pg_recentes, PREFIXO + "/temas": pg_temas, PREFIXO + "/tema": pg_tema, PREFIXO + "/nota": pg_nota, PREFIXO + "/documento": pg_documento,
       PREFIXO + "/busca": pg_busca, PREFIXO + "/catalogo": pg_catalogo}
ARQUIVOS = {PREFIXO + "/audio": audio, PREFIXO + "/arquivo": arquivo}
POST = {PREFIXO + "/salvar": post_salvar, PREFIXO + "/confirmar": post_confirmar, PREFIXO + "/descartar": post_descartar, PREFIXO + "/desfazer": post_desfazer}
