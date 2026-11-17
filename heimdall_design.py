"""Heimdall Design: o padrão de interface igual em todos os sites do Heimdall.

Regra de ouro (feita para leitor de tela e teclado):
  - LINK leva a outro lugar para LER: menu, "Voltar", o nome de um item em lista ou tabela, "Leia mais", links dentro de texto.
  - BOTÃO faz uma AÇÃO ou COMANDO, mesmo quando o resultado é abrir outra página: baixar, atualizar, continuar, confirmar,
    alterar, classificar, importar, trocar visão ou período, paginar, "Ver todos...", "Ver resultado".

Um botão de comando que só consulta (GET) é um formulário com um botão, o que funciona sem JavaScript e é lido como botão.
Botões repetidos numa lista levam nome acessível com o item ("Alterar categoria de Mercado"), para o leitor de tela distinguir.
A paginação é do heimdall_paginacao.py (botões), igual no News, Notas e Finance.
"""
import html

CSS = """
form.acao{display:inline;margin:0}
.ant-prox form.acao{margin:0}
"""


def botao(rota: str, rotulo: str, params: dict = None, nome_acessivel: str = "", atual: bool = False) -> str:
    """Ação de consulta como botão (formulário GET com campos ocultos). `atual` marca a opção escolhida num grupo (aria-current)."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    ocultos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (params or {}).items() if v not in (None, ""))
    rot = f' aria-label="{e(nome_acessivel)}"' if nome_acessivel else ""
    marca = ' aria-current="true"' if atual else ""
    return f'<form class="acao" method="get" action="{e(rota)}">{ocultos}<button type="submit"{rot}{marca}>{e(rotulo)}</button></form>'
