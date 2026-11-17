#!/usr/bin/env python3
"""Teste do Heimdall Design: nos sites do Heimdall, link lê e botão age.

Procura no código dos painéis links (<a>) cujo texto é uma ação (Baixar, Atualizar, Continuar, Alterar, Classificar, Importar,
Salvar, Apagar, Ver ..., Próxima, Anterior, Página ...) e falha se achar. Texto em prosa (inline) em minúsculas não conta.
Exceções: <a role="button"> (necessário quando o destino é um esquema de aplicativo, como shortcuts://) e o texto reserva
dentro de <audio>, que o navegador só mostra quando não toca áudio.

    python3 teste_design.py
"""
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
PAINEIS = ["heimdall_cloud.py", "heimdall_notas.py", "heimdall_news.py", "heimdall_painel_saude.py", "heimdall_jogos.py", "heimdall_finance.py"]
ACAO = re.compile(r"^(Baixar|Atualizar|Continuar|Confirmar|Conferir|Alterar|Classificar|Importar|Salvar|Apagar|Enviar|Ver\b|Pr[óo]xim[ao]|Anterior|P[áa]gina|Nota anterior|Subir)", re.I)
ANCORA = re.compile(r"<a\b([^>]*)>([^<{]*)</a>")

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:400])


for nome in PAINEIS:
    linhas = (AQUI / nome).read_text(encoding="utf-8").splitlines()
    achados = []
    for n, ln in enumerate(linhas, 1):
        if "<audio" in ln:
            continue
        for m in ANCORA.finditer(ln):
            atrib, texto = m.group(1), m.group(2).strip()
            if 'role="button"' in atrib:
                continue
            # Só o início do texto em maiúscula é rótulo de ação; "ver hoje" no meio de uma frase é prosa.
            if texto and texto[0].isupper() and ACAO.match(texto):
                achados.append(f"linha {n}: <a>{texto}</a>")
    confere(f"{nome}: nenhuma ação é link", not achados, "; ".join(achados))

import heimdall_design as design  # noqa: E402

b = design.botao("/x", "Ver tudo", {"a": "1", "vazio": ""}, 'Ver "tudo"')
confere("design.botao gera formulário GET com botão e nome acessível escapado", 'method="get"' in b and "<button" in b and 'aria-label="Ver &quot;tudo&quot;"' in b and 'name="a"' in b and 'name="vazio"' not in b, b)
confere("design.botao marca a opção atual", 'aria-current="true"' in design.botao("/x", "7 dias", None, "", True))

import heimdall_paginacao as pag  # noqa: E402

confere("paginação é toda de botões", "<a " not in pag.html_paginacao("/x", 2, 5, {}, "") and "<button" in pag.html_paginacao("/x", 2, 5, {}, ""))
confere("o pacote de CSS do Heimdall Design chega aos painéis (via heimdall_cloud)", "form.acao" in __import__("heimdall_cloud").CSS)

print()
print("FALHAS: " + str(falhas))
sys.exit(1 if falhas else 0)
