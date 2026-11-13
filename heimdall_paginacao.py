"""Paginação em botões, igual em todos os sites do Heimdall (News, Notas).

Um único formulário GET com um botão por página, bom para leitor de tela e para teclado:

    Página anterior, Página 1, Página 2, Página 3 (atual), Página 4, Página 5, ..., Próxima página, Última página

A página atual leva aria-current="page" e o texto "(atual)". "Página anterior" some na primeira página; "Próxima página" e
"Última página" somem na última. A janela mostra até 5 números de página e reticências quando há mais páginas.
"""
import html

CSS = """
.pags{border-top:1px solid var(--linha);margin-top:1.5rem;padding-top:1rem}
.pags ul{list-style:none;padding:0;margin:.5rem 0;display:flex;flex-wrap:wrap;gap:.5rem}
.pags button{margin:0;min-height:2.75rem}.pags button[aria-current=page]{background:var(--acento);color:var(--fundo);font-weight:700;box-shadow:inset 0 -4px 0 var(--ouro,#ffc107)}
.pags .reticencias{align-self:center;color:var(--suave)}
"""


def janela(atual: int, total: int, tamanho: int = 5) -> list:
    """Números de página mostrados: até `tamanho`, com a atual o mais ao meio possível."""
    inicio = max(1, min(atual - tamanho // 2, total - tamanho + 1))
    return list(range(inicio, min(total, inicio + tamanho - 1) + 1))


def total_de_paginas(itens: int, por_pagina: int) -> int:
    return max(1, -(-int(itens) // int(por_pagina)))


def limitar(pagina, total: int) -> int:
    try:
        p = int(pagina)
    except (TypeError, ValueError):
        p = 1
    return max(1, min(p, total))


def html_paginacao(acao: str, atual: int, total: int, params: dict = None, resumo: str = "", nome: str = "pagina") -> str:
    """HTML da paginação. `acao`: caminho do formulário (ex.: "/tema"); `params`: outros campos a manter (categoria, t, q...)."""
    if total <= 1:
        return ""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    ocultos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (params or {}).items() if v not in (None, "") and k != nome)

    def botao(p: int, rotulo: str, atual_: bool = False) -> str:
        marca = ' aria-current="page"' if atual_ else ""
        return f'<li><button type="submit" name="{e(nome)}" value="{p}"{marca}>{e(rotulo)}</button></li>'

    itens = []
    if atual > 1:
        itens.append(botao(atual - 1, "Página anterior"))
    pags = janela(atual, total)
    if pags[0] > 1:
        itens.append('<li class="reticencias" aria-hidden="true">…</li>')
    for p in pags:
        itens.append(botao(p, f"Página {p} (atual)" if p == atual else f"Página {p}", p == atual))
    if pags[-1] < total:
        itens.append('<li class="reticencias" aria-hidden="true">…</li>')
    if atual < total:
        itens.append(botao(atual + 1, "Próxima página"))
        itens.append(botao(total, "Última página"))
    texto = f'<p class="meta">Página {atual} de {total}{" · " + e(resumo) if resumo else ""}</p>'
    return (f'<nav class="pags" aria-label="Paginação">{texto}<form method="get" action="{e(acao)}">{ocultos}<ul>{"".join(itens)}</ul></form></nav>')
