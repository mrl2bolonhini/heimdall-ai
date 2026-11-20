#!/usr/bin/env python3
"""Testa no Chrome (Playwright) o terminal do Heimdall Controls: saída no próprio campo, entrada para programas, atalhos de teclado.
Se o Playwright ou o Chrome não existirem, avisa e sai sem falhar (o teste do servidor, teste_controls.py, continua valendo)."""
import os
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="controls_nav_"))
os.environ.update({"HEIMDALL_CONTROLS_SHELL": "/bin/bash", "HEIMDALL_CONTROLS_RC": "0", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright não instalado: teste do navegador pulado.")
    sys.exit(0)
import heimdall_cloud as hc  # noqa: E402
import heimdall_controls as hcx  # noqa: E402

hcx.AUDITORIA = TMP / "logs" / "controls_audit.log"
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + repr(detalhe)[:600])


srv = ThreadingHTTPServer(("127.0.0.1", 0), hcx.Painel)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]
token = hc.nova_sessao()[0]


def espera(f, seg=10):
    fim = time.time() + seg
    while time.time() < fim:
        v = f()
        if v:
            return v
        time.sleep(0.1)
    return False


with sync_playwright() as pw:
    try:
        nav = pw.chromium.launch(executable_path=next((c for c in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(c)), None), args=["--no-sandbox"])
    except Exception as ex:  # noqa: BLE001
        print("Chrome não disponível: teste do navegador pulado.", type(ex).__name__)
        sys.exit(0)
    ctx = nav.new_context(permissions=["clipboard-read", "clipboard-write"])
    ctx.add_cookies([{"name": hc.COOKIE, "value": token, "url": f"http://localhost:{PORTA}"}])
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.goto(f"http://localhost:{PORTA}/terminal")
    ta = pg.locator("#terminal")
    valor = lambda: ta.input_value()  # noqa: E731
    estado = lambda: pg.locator("#estado").inner_text()  # noqa: E731
    confere("campo único começa só com o prompt", valor().endswith("%") and "\n" not in valor().strip(), valor())

    confere("ao abrir a página o foco já está no terminal, com o cursor no fim", espera(lambda: pg.evaluate("document.activeElement.id") == "terminal") and espera(lambda: ta.evaluate("e => e.selectionStart === e.value.length")), pg.evaluate("document.activeElement.id"))
    pg.keyboard.type("echo ola mundo")
    pg.keyboard.press("Enter")
    confere("saída aparece no próprio campo, com o prompt de volta no fim", espera(lambda: "ola mundo\n[concluído em " in valor() and valor().endswith("%")), valor())
    confere("aviso falado traz a saída curta", espera(lambda: "Saída: ola mundo" in estado()), estado())
    confere("o cursor está na linha de digitação", ta.evaluate("e => e.selectionStart === e.value.length"))

    pg.keyboard.type("echo segundo")
    pg.keyboard.press("Enter")
    espera(lambda: "segundo\n[concluído" in valor())
    confere("segundo comando: o campo mostra só ele (a primeira saída saiu do campo)", "ola mundo" not in valor() and "echo segundo" in valor(), valor())
    confere("o histórico (acima) guarda o comando anterior; o último fica só no terminal", espera(lambda: "ola mundo" in pg.locator("#historico").input_value()) and "segundo" not in pg.locator("#historico").input_value(), pg.locator("#historico").input_value())
    confere("verificação de ortografia desligada nos dois campos", ta.evaluate("e => e.spellcheck === false") and pg.locator("#historico").evaluate("e => e.spellcheck === false"))

    # primeira letra, recarregar e voltar ao campo
    pg.reload()
    confere("recarregar a página devolve o foco ao terminal", espera(lambda: pg.evaluate("document.activeElement.id") == "terminal"))
    pg.keyboard.type("echo xyz")
    confere("nenhuma letra se perde: a primeira também entra", valor().endswith("echo xyz"), valor()[-30:])
    pg.keyboard.press("Shift+Tab")
    confere("Shift+Tab vai ao histórico, que fica acima", pg.evaluate("document.activeElement.id") == "historico")
    pg.keyboard.press("Tab")
    confere("voltar ao terminal com Tab deixa o cursor depois da última letra", pg.evaluate("document.activeElement.id") == "terminal" and ta.evaluate("e => e.selectionStart === e.value.length"), ta.evaluate("e => [e.selectionStart, e.value.length]"))
    ta.evaluate("e => e.setSelectionRange(0, 0)")
    pg.keyboard.type("Z")
    confere("com o cursor na saída, a letra digitada vai para o fim (não se perde)", valor().endswith("echo xyzZ"), valor()[-30:])
    for _ in range(9):
        pg.keyboard.press("Backspace")
    # histórico: setas navegam sem perder o foco, e nada se altera
    ant = pg.locator("#historico").input_value()
    pg.keyboard.press("Shift+Tab")
    pg.keyboard.press("ArrowUp")
    pg.keyboard.press("ArrowUp")
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Home")
    pg.keyboard.type("abc")
    pg.keyboard.press("Backspace")
    pg.keyboard.press("Delete")
    confere("histórico: as setas movem o cursor sem perder o foco", pg.evaluate("document.activeElement.id") == "historico")
    confere("histórico: digitar e apagar não alteram nada", pg.locator("#historico").input_value() == ant, pg.locator("#historico").input_value()[:80])
    pg.keyboard.press("Tab")

    # só a última linha é editável
    ta.evaluate("e => e.setSelectionRange(0, 0)")
    pg.keyboard.type("x")
    confere("digitar na saída é bloqueado e o cursor vai ao fim", "x" not in valor().split("\n")[0] and ta.evaluate("e => e.selectionStart === e.value.length"), valor())
    ta.evaluate("e => e.setSelectionRange(e.value.length, e.value.length)")
    for _ in range(40):
        pg.keyboard.press("Backspace")
    confere("Backspace não apaga o prompt nem a saída", valor().endswith("ola mundo\n[") or valor().endswith("%"), valor()[-80:])

    # programa que pergunta: a resposta vai na mesma linha, sem campo separado
    pg.keyboard.type('read -p "nome? " x; echo ola $x')
    pg.keyboard.press("Enter")
    confere("pergunta do programa aparece no campo, sem prompt novo", espera(lambda: valor().endswith("nome? ")), valor()[-60:])
    pg.keyboard.type("Ana")
    pg.keyboard.press("Enter")
    confere("resposta digitada na linha vai ao programa", espera(lambda: "ola Ana" in valor() and valor().endswith("%")), valor()[-100:])

    # saída longa e atalho de ir ao início
    pg.keyboard.type("seq 1 60")
    pg.keyboard.press("Enter")
    espera(lambda: "[concluído" in valor().split("seq 1 60")[-1])
    confere("aviso de saída longa fala a saída inteira", espera(lambda: "Saída: 1" in estado() and estado().replace("\u200b", "").rstrip().endswith("60")), estado()[-40:])
    pg.keyboard.press("Alt+Shift+KeyU")
    pos = ta.evaluate("e => e.value.slice(e.selectionStart, e.selectionStart + 6)")
    confere("Option+Shift+U leva o cursor ao início da última saída", pos.startswith("1\n2\n3"), pos)
    pg.keyboard.press("Alt+Shift+KeyT")
    confere("Option+Shift+T volta à linha de digitação", espera(lambda: ta.evaluate("e => e.selectionStart === e.value.length")))

    # copiar
    pg.keyboard.press("Alt+Shift+KeyC")
    confere("Option+Shift+C copia a última saída e avisa", espera(lambda: "Copiado" in estado()) and "seq 1 60" in pg.evaluate("navigator.clipboard.readText()"), estado())
    pg.keyboard.press("Alt+Shift+Digit2")
    copiado = espera(lambda: "Copiado" in estado() and pg.evaluate("navigator.clipboard.readText()").count("$ ") == 2 and pg.evaluate("navigator.clipboard.readText()"))
    confere("Option+Shift+2 copia as duas últimas saídas", bool(copiado) and "ola Ana" in copiado, copiado)
    pg.locator("#com-comando").uncheck()
    pg.keyboard.press("Alt+Shift+KeyC")
    sem = espera(lambda: pg.evaluate("navigator.clipboard.readText()").startswith("1\n2"))
    confere("sem 'Incluir o comando', a cópia traz só a saída", bool(sem))
    pg.locator("#com-comando").check()

    # histórico
    pg.keyboard.press("Alt+Shift+KeyP")
    confere("Option+Shift+P traz o comando anterior à linha", valor().endswith("seq 1 60"), valor()[-40:])
    pg.keyboard.press("Alt+Shift+KeyN")
    confere("Option+Shift+N volta à linha vazia", valor().endswith("%"), valor()[-40:])

    # interromper com Ctrl+C
    pg.keyboard.type("sleep 30")
    pg.keyboard.press("Enter")
    espera(lambda: ta.evaluate("e => e.value.trimEnd().endsWith('sleep 30')"))
    pg.keyboard.press("Control+KeyC")
    confere("Ctrl+C interrompe o programa em execução", espera(lambda: "[interrompido" in valor() and valor().endswith("%")) and espera(lambda: "nterrompido" in estado()), (valor()[-80:], estado()))

    # Ctrl+C sem programa apaga a linha
    pg.keyboard.type("lixo")
    pg.keyboard.press("Control+KeyC")
    confere("Ctrl+C sem programa apaga a linha digitada", valor().endswith("%") and "lixo" not in valor())

    # limpar e reiniciar
    pg.keyboard.type("export HD_N=7")
    pg.keyboard.press("Enter")
    espera(lambda: valor().count("[concluído") >= 4)
    pg.keyboard.press("Control+KeyL")
    confere("Ctrl+L limpa as saídas: sobra só o prompt", espera(lambda: valor().count("\n") == 0 and valor().endswith("%")) and espera(lambda: "Saídas limpas" in estado()), valor())
    pg.keyboard.type("echo ${HD_N:-vazio}")
    pg.keyboard.press("Enter")
    confere("o shell mantém as variáveis depois de limpar", espera(lambda: "\n7\n" in valor()), valor())
    pg.keyboard.press("Alt+Shift+KeyR")
    espera(lambda: "Shell reiniciado" in estado())
    pg.keyboard.press("Alt+Shift+KeyT")
    pg.keyboard.type("echo ${HD_N:-vazio}")
    pg.keyboard.press("Enter")
    confere("Option+Shift+R reinicia o shell (variável some)", espera(lambda: "\nvazio\n" in valor()), valor())

    # Tab: completar
    pg.keyboard.type("mkdir -p /tmp/hdct && cd /tmp/hdct && touch alfa.txt alfabeto.txt beta.txt")
    pg.keyboard.press("Enter")
    espera(lambda: "[concluído" in valor() and valor().endswith("hdct%"))
    pg.keyboard.type("cat be")
    pg.keyboard.press("Control+KeyI")
    confere("Ctrl+I completa um arquivo único", espera(lambda: valor().endswith("cat beta.txt ")), valor()[-40:])
    ta.evaluate("e => { e.value = e.value.slice(0, e.value.length - 'cat beta.txt '.length); e.setSelectionRange(e.value.length, e.value.length); }")
    pg.keyboard.type("cat alf")
    pg.keyboard.press("Control+KeyI")
    confere("Ctrl+I com vários: completa o comum e fala as opções", espera(lambda: valor().endswith("cat alfa") and "2 opções" in estado() and "alfabeto.txt" in estado()), (valor()[-30:], estado()))
    pg.keyboard.press("Control+KeyC")
    pg.keyboard.press("Control+KeyI")
    confere("Ctrl+I com a linha vazia avisa e fica no campo", espera(lambda: "Nada digitado" in estado()) and pg.evaluate("document.activeElement.id") == "terminal", estado())
    pg.keyboard.press("Tab")
    confere("o Tab é livre: move o foco para fora do campo", espera(lambda: pg.evaluate("document.activeElement.id") != "terminal"), pg.evaluate("document.activeElement.id"))
    pg.keyboard.press("Alt+Shift+KeyT")
    confere("Option+Shift+T volta ao campo", pg.evaluate("document.activeElement.id") == "terminal")

    # nomes dos campos e histórico no fim
    confere("os campos se chamam só Histórico e Terminal", pg.evaluate("[document.querySelector('label[for=historico]').textContent, document.querySelector('label[for=terminal]').textContent]") == ["Histórico", "Terminal"])
    pg.keyboard.press("Shift+Tab")
    confere("histórico: o cursor entra no fim", pg.evaluate("document.activeElement.id") == "historico" and pg.locator("#historico").evaluate("e => e.selectionStart === e.value.length"))
    pg.keyboard.press("Tab")
    pg.keyboard.press("Alt+Shift+KeyT")

    # lista de atalhos
    pg.keyboard.press("Alt+Shift+KeyH")
    confere("Option+Shift+H leva à lista de atalhos", pg.evaluate("document.activeElement.id") == "h-atalhos")
    pg.keyboard.press("Alt+Shift+KeyT")
    confere("sem erros de JavaScript no console", not erros, erros)
    nav.close()

hcx.obter_shell().encerrar()
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
