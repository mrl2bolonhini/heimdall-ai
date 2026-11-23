#!/usr/bin/env python3
"""Teste do Heimdall Design: nos sites do Heimdall, link lê e botão age.

Procura no código dos painéis links (<a>) cujo texto é uma ação (Baixar, Atualizar, Continuar, Alterar, Classificar, Importar,
Salvar, Apagar, Ver ..., Próxima, Anterior, Página ...) e falha se achar. Texto em prosa (inline) em minúsculas não conta.
Exceções: <a role="button"> (necessário quando o destino é um esquema de aplicativo, como shortcuts://) e o texto reserva
dentro de <audio>, que o navegador só mostra quando não toca áudio.

    python3 tests/design/teste_design.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import re
import sys
from pathlib import Path

AQUI = RAIZ
sys.path.insert(0, str(AQUI))
PAINEIS = ["heimdall_lab.py", "heimdall_notas.py", "heimdall_news.py", "heimdall_painel_saude.py", "heimdall_jogos.py", "heimdall_finance.py", "heimdall_controls.py"]
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

bp = design.botao_post("/y", "Ativar", "tok", {"a": "1", "vazio": ""}, 'Ativar "x"')
confere("design.botao_post gera formulário POST com csrf oculto, botão e nome acessível escapado", 'method="post"' in bp and 'name="csrf" value="tok"' in bp and "<button" in bp and 'aria-label="Ativar &quot;x&quot;"' in bp and 'name="vazio"' not in bp, bp)

import heimdall_paginacao as pag  # noqa: E402

confere("paginação é toda de botões", "<a " not in pag.html_paginacao("/x", 2, 5, {}, "") and "<button" in pag.html_paginacao("/x", 2, 5, {}, ""))
confere("o pacote de CSS do Heimdall Design chega aos painéis (via heimdall_lab)", "form.acao" in __import__("heimdall_lab").CSS)

# ---- cores, tipografia e foco: fonte única em heimdall_design.py
for tema, cores in (("claro", design.CORES_CLARO), ("escuro", design.CORES_ESCURO)):
    ruins = [f"{a} sobre {b}: {design.contraste(cores[a], cores[b]):.2f} < {m}" for a, b, m in design.PARES_DE_CONTRASTE if design.contraste(cores[a], cores[b]) < m]
    confere(f"tema {tema}: todo contraste atinge o mínimo", not ruins, "; ".join(ruins))
confere("claro e escuro definem as mesmas variáveis", set(design.CORES_CLARO) == set(design.CORES_ESCURO) == set(design.PAPEL_DAS_CORES))
confere("o CSS traz os dois temas, o foco visível e o salto para o conteúdo", "prefers-color-scheme:dark" in design.CSS and "outline:3px" in design.CSS and ".pular" in design.CSS)
confere("o corpo do texto tem 18 px ou mais", design.TAMANHO_BASE_PX >= 18 and "font:18px/1.5" in design.CSS)
confere("a paginação usa o alvo mínimo de toque", design.ALTURA_MINIMA_ALVO in open(AQUI / "heimdall_paginacao.py", encoding="utf-8").read())
arqs = PAINEIS + ["heimdall_paginacao.py", "heimdall_design.py"]
for nome in arqs:
    src = (AQUI / nome).read_text(encoding="utf-8")
    confere(f"{nome}: não remove o contorno do foco", not re.search(r"outline\s*:\s*(none|0)\b", src))
for nome in PAINEIS:
    src = (AQUI / nome).read_text(encoding="utf-8")
    soltas = [m for m in re.findall(r"(?<![\w&])#[0-9a-fA-F]{6}\b", src) if True]
    confere(f"{nome}: sem cor solta fora do Heimdall Design (use var(--...))", not soltas or nome == "heimdall_lab.py", soltas[:5])  # o Lab guarda o desenho da marca
    confere(f"{nome}: páginas em pt-BR e com viewport", "pt-BR" in src and "viewport" in src, "")
claude_md = (AQUI / "CLAUDE.md")
confere("CLAUDE.md manda seguir o Heimdall Design em toda atualização", claude_md.is_file() and "Heimdall Design" in claude_md.read_text(encoding="utf-8"))

print()
print("FALHAS: " + str(falhas))
sys.exit(1 if falhas else 0)
