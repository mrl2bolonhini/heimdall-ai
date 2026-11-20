#!/usr/bin/env python3
"""Heimdall Controls (controls.heimdall-ai.tech): terminal completo e acessível e painel de serviços, para administrar o Heimdall pelo navegador.

O terminal roda no Mac, com as permissões do seu usuário (heimdall_shell.py): a pasta e as variáveis continuam entre os comandos, programas que
perguntam algo recebem a resposta pelo campo "Resposta ao programa", e há botões para interromper e para copiar a última saída ou as últimas N saídas.
Isso é o recurso mais poderoso do Heimdall: quem entra aqui manda no Mac. Por isso as camadas são as dos outros painéis e mais duas:
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada pelo Cloudflare Access (Microsoft Authenticator) ou pela senha e o código de 6 dígitos do Heimdall Cloud.
  3. Só o dono entra: sessão de convidado (escopo de um serviço) é recusada aqui, mesmo que o Access a aceite.
  4. Em endereço público, com o Access ligado, todo pedido precisa trazer o token do Access de um dono (HEIMDALL_CONTROLS_EXIGE_ACCESS=0 desliga).
  5. Token anti-falsificação (CSRF) e conferência de Origin em todo pedido que age; cabeçalhos de segurança; script só com nonce.
  6. Cada comando é anotado em logs/controls_audit.log (data, endereço, comando; nunca a saída), arquivo só seu.
  7. Sem senha e sem código configurados, o painel não sobe.

Variáveis opcionais no .env: HEIMDALL_CONTROLS_PORT (8017), HEIMDALL_CONTROLS_HOST (127.0.0.1), HEIMDALL_CONTROLS_HOSTS
(controls.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_CONTROLS_SHELL (padrão: o seu shell), HEIMDALL_CONTROLS_EXIGE_ACCESS (1).
"""
import concurrent.futures
import html
import json
import os
import re
import secrets
import socket
import sys
import time
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis deste painel (as outras chaves não entram no processo; o shell herda só o que o processo tem)."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if not chave.startswith("HEIMDALL_CONTROLS_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)
import heimdall_design as design  # noqa: E402
import heimdall_kuma as kuma  # noqa: E402
import heimdall_servicos as servicos  # noqa: E402
import heimdall_shell as hshell  # noqa: E402

HOST = os.environ.get("HEIMDALL_CONTROLS_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("HEIMDALL_CONTROLS_PORT", "8017")))
except ValueError:
    PORT = 8017
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_CONTROLS_HOSTS", "controls.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
LOCAIS = {"localhost", "127.0.0.1"}
EXIGE_ACCESS = os.environ.get("HEIMDALL_CONTROLS_EXIGE_ACCESS", "1") != "0"
COOKIE = nuvem.COOKIE
SERVICO = "controls"
AUDITORIA = PROJECT_DIR / "logs" / "controls_audit.log"
MAX_CORPO = 300_000
MAX_EXIBIDO = 40_000      # caracteres da saída de UM comando mostrados na tela; a cópia traz tudo
try:
    # ao voltar ao campo com o cursor no começo (o Safari faz isso), espera este tempo, em ms, antes de levá-lo ao fim, para o VoiceOver
    # terminar de ler o nome do campo sem ser cortado. 0 desliga o salto. Aumente se o nome ainda for cortado; diminua se demorar.
    ATRASO_CURSOR_MS = max(0, int(os.environ.get("HEIMDALL_CONTROLS_ATRASO_CURSOR", "1800")))
except ValueError:
    ATRASO_CURSOR_MS = 1800
MAX_TRANSCRICAO = 400_000  # caracteres do campo do terminal no total (os comandos mais antigos saem da tela)
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

CSS = nuvem.CSS + """
.aviso{border:1px solid var(--linha);padding:.7rem;margin-top:1.5rem;color:var(--suave)}
"""

BUILTINS = ["cd", "pwd", "echo", "export", "unset", "alias", "unalias", "source", "type", "which", "where", "history", "jobs", "fg", "bg", "kill",
            "exit", "read", "set", "setopt", "unsetopt", "typeset", "print", "printf", "test", "true", "false", "eval", "exec", "wait", "umask",
            "ulimit", "pushd", "popd", "dirs", "rehash", "hash", "command", "builtin", "heimdall"]
_EXE = {"em": 0.0, "nomes": []}


def executaveis() -> list:
    """Nomes executáveis do PATH (guardados por 30 s: ler o PATH inteiro a cada Tab seria lento)."""
    if time.time() - _EXE["em"] < 30 and _EXE["nomes"]:
        return _EXE["nomes"]
    dirs = (os.environ.get("PATH", "") + ":/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin").split(":")
    nomes = set()
    for d in dirs:
        try:
            with os.scandir(d) as it:
                for en in it:
                    if not en.name.startswith(".") and os.access(en.path, os.X_OK):
                        nomes.add(en.name)
        except OSError:
            continue
    _EXE["em"], _EXE["nomes"] = time.time(), sorted(nomes)
    return _EXE["nomes"]


_ESCAPAR = re.compile(r"([ \t\\'\"()&;|<>*?$`!#{}\[\]])")


def completar(pasta: str, linha: str) -> dict:
    """Tab: completa a última palavra da linha. Na primeira palavra (ou depois de ; | &), nomes de comandos; nas outras, arquivos e pastas
    a partir da pasta do shell. Devolve a palavra nova, o ponto onde ela começa e as opções (para o leitor de tela dizer)."""
    m = re.search(r"(?:\\.|[^\s;|&()<>])*$", linha)
    palavra, inicio = m.group(0), m.start()
    antes = linha[:inicio].rstrip()
    sem_esc = re.sub(r"\\(.)", r"\1", palavra)
    comando = antes == "" or antes[-1] in ";|&("
    itens = []                      # (nome, é pasta)
    if sem_esc == "~":
        return {"inicio": inicio, "palavra_nova": "~/", "opcoes": ["~/"]}
    if comando and "/" not in sem_esc and not sem_esc.startswith("."):
        itens = [(n, False) for n in sorted(set(executaveis()) | set(BUILTINS)) if n.startswith(sem_esc)]
        resto, d_tipado = sem_esc, ""
    else:
        cut = sem_esc.rfind("/")
        d, resto = (sem_esc[:cut + 1], sem_esc[cut + 1:]) if cut >= 0 else ("", sem_esc)
        d_tipado = palavra[:palavra.rfind("/") + 1] if "/" in palavra else ""
        try:
            with os.scandir(os.path.join(pasta, os.path.expanduser(d) or ".")) as it:
                for en in it:
                    if en.name.startswith(resto) and (resto.startswith(".") or not en.name.startswith(".")):
                        try:
                            itens.append((en.name, en.is_dir()))
                        except OSError:
                            itens.append((en.name, False))
        except OSError:
            itens = []
        itens.sort()
    if not comando and re.match(r"\s*(cd|pushd)\s*$", antes.split(";")[-1].split("|")[-1].split("&")[-1]):
        itens = [(n, d_) for n, d_ in itens if d_]                       # cd só aceita pastas
        if not itens and "/" not in sem_esc:                              # nada na pasta atual: tenta na pasta pessoal
            try:
                with os.scandir(os.path.expanduser("~")) as it:
                    outros = sorted((en.name, True) for en in it if en.name.startswith(sem_esc) and (sem_esc.startswith(".") or not en.name.startswith(".")) and en.is_dir())
            except OSError:
                outros = []
            if outros:
                nomes = [n for n, _ in outros]
                novo = _ESCAPAR.sub(r"\\\1", nomes[0] if len(nomes) == 1 else os.path.commonprefix(nomes))
                return {"inicio": inicio, "palavra_nova": "~/" + novo + ("/" if len(nomes) == 1 else ""), "opcoes": [n + "/" for n in nomes]}
    itens = itens[:500]
    if not itens:
        return {"inicio": inicio, "palavra_nova": palavra, "opcoes": []}
    nomes = [n for n, _ in itens]
    if len(itens) == 1:
        n, eh_dir = itens[0]
        novo = _ESCAPAR.sub(r"\\\1", n) + ("/" if eh_dir else " ")
    else:
        novo = _ESCAPAR.sub(r"\\\1", os.path.commonprefix(nomes))
    return {"inicio": inicio, "palavra_nova": d_tipado + novo, "opcoes": [n + ("/" if e_ else "") for n, e_ in itens]}


SECOES = [("/", "Visão geral"), ("/terminal", "Terminal"), ("/servicos", "Serviços"), ("/manutencao", "Manutenção")]

_shell = None


def obter_shell() -> hshell.Shell:
    """O shell único do painel; abre na primeira vez que alguém usa o terminal."""
    global _shell
    if _shell is None:
        qual = os.environ.get("HEIMDALL_CONTROLS_SHELL") or ("/bin/zsh" if os.path.exists("/bin/zsh") else os.environ.get("SHELL") or "/bin/bash")
        inicio = '[ -n "$ZSH_VERSION" ] && [ -f "$HEIMDALL_DIR/heimdall.zsh" ] && source "$HEIMDALL_DIR/heimdall.zsh"; true'
        _shell = hshell.Shell(pasta=str(PROJECT_DIR), comando_shell=qual, ambiente={"HEIMDALL_DIR": str(PROJECT_DIR)}, inicio=inicio,
                              carregar_rc=os.environ.get("HEIMDALL_CONTROLS_RC", "1") != "0")
    if not _shell.vivo():
        _shell.iniciar()
    return _shell


def auditar(ip: str, acao: str, detalhe: str = "") -> None:
    """Uma linha por ação que muda algo. Nunca grava a saída (pode ter segredo)."""
    try:
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        novo = not AUDITORIA.exists()
        with open(AUDITORIA, "a", encoding="utf-8") as f:
            f.write(json.dumps({"em": datetime.now().isoformat(timespec="seconds"), "ip": ip, "acao": acao, "detalhe": detalhe[:2000]}, ensure_ascii=False) + "\n")
        if novo:
            os.chmod(AUDITORIA, 0o600)
    except OSError as ex:
        sys.stderr.write(f"auditoria falhou: {type(ex).__name__}\n")


# ----------------------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------------------
def duracao(seg: float) -> str:
    seg = max(0.0, seg)
    """Número colado no s, para o leitor de tela ler certo: 0s, 12,3s, 37,21s (até duas casas, sem zeros sobrando; inteiro quando não há fração; minutos: 1min e 5s)."""
    def _s(x: float) -> str:
        return (f"{x:.2f}".rstrip("0").rstrip(".") or "0").replace(".", ",") + "s"
    if seg < 60:
        return _s(seg)
    m, resto = int(seg // 60), seg - int(seg // 60) * 60
    return f"{m}min" + (f" e {_s(resto)}" if round(resto, 2) > 0 else "")


def prompt_de(pasta: str) -> str:
    """O prompt mostrado no campo: só o nome da pasta, como o zsh faz (~ para a pasta pessoal)."""
    nome = "~" if pasta == str(Path.home()) else (os.path.basename(pasta.rstrip("/")) or "/")
    return f"{nome}%"   # sem espaço depois: o leitor de tela não lê "espaço" ao entrar no campo


def _situacao(b) -> str:
    if b.estado == "interrompido":
        return f"interrompido em {duracao(b.duracao())}"
    if b.estado == "encerrado":
        return "o shell foi encerrado durante este comando"
    return f"concluído em {duracao(b.duracao())}" if b.codigo == 0 else f"código {b.codigo}, em {duracao(b.duracao())}"   # o código só aparece quando é erro


def _saida_exibida(sh, b) -> tuple:
    """(texto da saída para a tela, aviso de corte). A cópia sempre leva o texto inteiro."""
    saida = sh.saida_parcial(b)
    if len(saida) > MAX_EXIBIDO:
        return saida[-MAX_EXIBIDO:], "[começo da saída omitido na tela; copiar leva tudo]\n"
    return saida, ""


def _texto_do_bloco(sh, b) -> tuple:
    """(texto do comando com prompt, saída e situação; posição onde a saída começa)."""
    cmd = b.comando if len(b.comando) <= 300 else b.comando[:300] + "..."
    cab = prompt_de(b.pasta) + " " + cmd + "\n"
    saida, corte = _saida_exibida(sh, b)
    corpo = corte + saida
    fim_ = b.estado != "rodando"
    if fim_ and corpo and not corpo.endswith("\n"):
        corpo += "\n"
    return cab + corpo + (f"[{_situacao(b)}]\n\n" if fim_ else ""), len(cab) + len(corte)


def transcricao(sh, com_historico: bool = True) -> dict:
    """O campo do terminal mostra só o ÚLTIMO comando (o leitor de tela lê só a saída dele, como depois de um clear).
    Os comandos anteriores vão num campo de histórico à parte, que fica logo acima. O texto do último comando só cresce no fim."""
    with sh._lock:
        n_hist = max(0, len(sh.blocos) - 1)
        if not sh.blocos:
            return {"texto": "", "inicio_ultima": -1, "ultimo_n": 0, "historico": "", "n_hist": 0}
        ultimo, inicio = _texto_do_bloco(sh, sh.blocos[-1])
        hist = ""
        if com_historico:
            partes = [_texto_do_bloco(sh, b)[0] for b in sh.blocos[:-1]]
            while len(partes) > 1 and sum(len(t) for t in partes) > MAX_TRANSCRICAO:
                partes.pop(0)
            hist = "".join(partes).rstrip("\n")        # sem linha em branco sobrando no fim
        return {"texto": ultimo, "inicio_ultima": inicio, "ultimo_n": sh.blocos[-1].n, "historico": hist, "n_hist": n_hist}


def aviso_do_bloco(sh, b) -> str:
    """O que o leitor de tela fala quando um comando termina: a situação e a saída inteira."""
    saida, _ = _saida_exibida(sh, b)
    linhas = saida.strip().splitlines()
    if not linhas:
        resumo = "Sem saída."
    else:
        resumo = "Saída: " + saida.strip()        # lê tudo, por maior que seja; Control interrompe a fala do VoiceOver
    sit = _situacao(b)
    return f"{sit[0].upper()}{sit[1:]}. {resumo}"


def pg_inicio(q: dict, sess: dict) -> tuple:
    sh = obter_shell() if _shell is not None else None
    corpo = ("<p>Aqui você administra o Heimdall pelo navegador. Tudo roda no seu Mac, com as suas permissões.</p>"
             "<ol><li><a href=\"/terminal\">Terminal</a>: um shell completo. A pasta e as variáveis continuam de um comando para o outro, "
             "e há botões para copiar a última saída ou as últimas saídas.</li>"
             "<li><a href=\"/servicos\">Serviços</a>: todos os serviços do Heimdall, com Ligado e Desligado em cada um.</li>"
             "<li><a href=\"/manutencao\">Manutenção</a>: atualizar, reiniciar, diagnóstico e logs.</li></ol>"
             "<p>As seções são abas. Setas esquerda e direita movem entre elas e Option+Shift+1 a 4 abre cada uma.</p>")
    if sh and sh.vivo():
        corpo += f"<p>O terminal está aberto, na pasta {e(sh.pasta)}.</p>"
    corpo += ('<p class="aviso">Quem entra aqui manda no Mac. Cada comando fica anotado em logs/controls_audit.log, sem a saída. '
              'Programas de tela cheia, como vim e top, não funcionam aqui: use cat, sed e ps.</p>')
    return "Heimdall Controls", corpo


def pg_terminal(q: dict, sess: dict) -> tuple:
    sh = obter_shell()
    t = transcricao(sh)
    inicial = t["texto"] + ("" if sh.rodando() else prompt_de(sh.pasta))
    hist = t["historico"]
    corpo = (
        '<p id="estado" role="alert" aria-live="assertive" aria-atomic="true"></p>'
        f'<input type="hidden" id="csrf" value="{e(sess["csrf"])}">'
        '<p>O foco já vem no campo Terminal. Digite o comando na última linha e aperte Enter. A saída aparece no próprio campo, logo abaixo do comando. '
        'Se um programa estiver perguntando algo, o que você digitar vai para ele. O campo Terminal mostra só o último comando; os anteriores ficam no campo Histórico, logo acima, com o cursor no fim (do mais novo para o mais antigo, subindo com a seta). '
        'Ctrl+I completa comandos e nomes de arquivos. Option+Shift+H leva à lista de atalhos.</p>'
        '<div><label for="historico">Histórico</label>'
        f'<textarea class="terminal historico" id="historico" aria-readonly="true" inputmode="none" spellcheck="false" data-n="{t["n_hist"]}">{e(hist)}</textarea></div>'
        '<div><label for="terminal">Terminal</label>'
        f'<textarea class="terminal" id="terminal" spellcheck="false" autofocus autocomplete="off" autocapitalize="off" autocorrect="off" data-versao="{sh.versao}" data-atraso="{ATRASO_CURSOR_MS}">{e(inicial)}</textarea></div>'
        '<section aria-labelledby="h-ac"><h2 id="h-ac">Ações</h2><div class="linha-acoes">'
        '<div>'+design.botao_js("bt-copiar-ultima","Copiar a última saída (Option+Shift+C)")+'</div>'
        '<div><label for="qtd">Quantas últimas saídas</label><input id="qtd" type="number" min="1" max="300" value="3" inputmode="numeric">'
        ''+design.botao_js("bt-copiar-n","Copiar as últimas saídas")+'</div>'
        '<div><label><input type="checkbox" id="com-comando" checked> Incluir o comando</label></div></div>'
        '<div class="linha-acoes">'+design.botao_js("bt-int","Interromper (Ctrl+C)")+''
        ''+design.botao_js("bt-inicio","Ir ao início da última saída (Option+Shift+U)")+''
        ''+design.botao_js("bt-ler","Ler o começo da última saída (Option+Shift+O)")+''
        ''+design.botao_js("bt-limpar","Limpar as saídas (Ctrl+L)")+''
        ''+design.botao_js("bt-reiniciar","Reiniciar o shell (Option+Shift+R)")+'</div>'
        '<p>Reiniciar o shell fecha o atual e abre outro limpo, na pasta do Heimdall.</p>'
        '<div id="area-copia" hidden><label for="texto-copia">Se o navegador não deixar copiar sozinho, selecione tudo neste campo (Command+A) e copie (Command+C)</label>'
        '<textarea id="texto-copia" readonly></textarea></div></section>'
        '<section aria-labelledby="h-atalhos"><h2 id="h-atalhos" tabindex="-1">Atalhos de teclado</h2>'
        '<p>Funcionam em qualquer ponto desta página. Option é a tecla Alt do Mac.</p><ol>'
        '<li>Enter: executa o comando digitado na última linha, ou envia a resposta ao programa que está perguntando. Shift+Enter: nova linha dentro do comando.</li>'
        '<li>Ctrl+I: completa o nome de um comando (na primeira palavra) ou de um arquivo ou pasta. Se houver vários, completa o que for igual em todos e o leitor de tela diz as opções. Ctrl+I completa (é o Tab do terminal de verdade). O Tab fica livre para mover o foco pela página. Depois de cd ou pushd, completa só pastas e, se não houver na pasta atual, procura na pasta pessoal (cd heim vira cd ~/heimdall-ai/).</li>'
        '<li>Ctrl+C ou Option+Shift+I: interrompe o programa em execução. Sem programa rodando, Ctrl+C apaga a linha digitada.</li>'
        '<li>Option+Shift+C: copia a última saída. Control+Shift+1 até 9: copia as últimas 1 a 9 saídas. Control+Shift+0: copia todas. A caixa Incluir o comando vale para todas.</li>'
        '<li>Option+Shift+U: leva o cursor ao início da última saída; depois leia com VO+A ou desça com a seta. Option+Shift+O: o leitor de tela lê o começo da última saída.</li>'
        '<li>Option+Shift+P e Option+Shift+N: comando anterior e seguinte do histórico.</li>'
        '<li>Ctrl+L ou Option+Shift+L: limpa as saídas. Option+Shift+R: reinicia o shell.</li>'
        '<li>Option+Shift+T: volta ao campo do terminal. Option+Shift+H: vem para esta lista.</li></ol></section>'
        '<noscript><p class="aviso">Sem JavaScript o terminal não funciona. Use o botão Atualizar a página para ver o resultado.</p></noscript>'
        + design.botao("/terminal", "Atualizar a página"))
    return "Terminal", corpo


LOGS_OK = ["mcp", "mcp_public", "mcp_dados", "agente", "cloud", "notas", "news", "saude_painel", "jogos", "finance", "controls", "ingest"]
# ação -> comando. Só estas viram botão; o texto livre vai pelo terminal.
ACOES = {
    "update": ("Atualizar do GitHub (sem reiniciar)", "heimdall update"),
    "update_restart": ("Atualizar e reiniciar tudo", "heimdall update --restart"),
    "restart": ("Reiniciar o Heimdall", "heimdall restart"),
    "status": ("Ver o estado completo", "heimdall status"),
    "doctor": ("Diagnóstico", "heimdall doctor"),
}


def _situacao_servico(sv: dict, ar: bool, off: bool, mon) -> str:
    partes = [f"porta {sv['porta']}", "no ar" if ar else "fora do ar"]
    if off:
        partes.append("desligado de propósito")
    if mon:
        partes.append("Kuma: " + mon["status"])
    return ", ".join(partes)


def pg_servicos(q: dict, sess: dict) -> tuple:
    """Uma chave (botão de alternância, role=switch) por serviço: apertar liga ou desliga na hora."""
    mons, erro_kuma = kuma.monitores()
    off = servicos.desligados()
    itens = []
    for sv in servicos.catalogo():
        ar = servicos.no_ar(sv)
        mon = kuma.achar(mons, sv["nome"]) if sv.get("kuma", True) else None
        sid = sv["id"]
        itens.append(f'<li><button type="button" role="switch" id="sw-{sid}" data-servico="{sid}" aria-checked="{"true" if ar else "false"}" aria-describedby="est-{sid}">{e(sv["nome"])}</button>'
                     f'<span id="est-{sid}">{"Ligado" if ar else "Desligado"}: {e(_situacao_servico(sv, ar, sid in off, mon))}</span></li>')
    if erro_kuma:
        aviso_kuma = f'<p class="nota">Kuma: {e(erro_kuma)}. A situação vem da porta de cada serviço.</p>'
    elif os.environ.get("HEIMDALL_KUMA_USUARIO"):
        aviso_kuma = '<p class="nota">Kuma consultado. Ao desligar ou ligar, o monitor do serviço no Kuma é pausado ou retomado.</p>'
    else:
        aviso_kuma = '<p class="nota">Kuma consultado só para leitura. Para pausar e retomar monitores por aqui, ponha HEIMDALL_KUMA_USUARIO e HEIMDALL_KUMA_SENHA no .env.</p>'
    corpo = ("<p>Cada serviço é uma chave: aperte Espaço ou Enter nela para ligar ou desligar, na hora, sem outro botão. Ligar e desligar pode levar alguns segundos. "
             "O que você desliga fica desligado mesmo depois de atualizar e reiniciar. Este painel não aparece na lista: desligá-lo cortaria o seu acesso.</p>"
             + aviso_kuma + '<p id="resultado-servicos" role="status"></p>'
             + f'<ul class="chaves" id="servicos" data-csrf="{e(sess["csrf"])}">' + "".join(itens) + "</ul>")
    return "Serviços", corpo


def pg_manutencao(q: dict, sess: dict) -> tuple:
    csrf = e(sess["csrf"])
    botoes = "".join(f'<li><form method="post" action="/manutencao/acao"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="acao" value="{k}">'
                     f'<button type="submit">{e(rot)}</button></form></li>' for k, (rot, _) in ACOES.items())
    opcoes = "".join(f'<option value="{s}">{e(s)}</option>' for s in LOGS_OK)
    log = ('<form method="post" action="/manutencao/acao"><input type="hidden" name="csrf" value="' + csrf + '"><input type="hidden" name="acao" value="log">'
           '<label for="servico-log">Ver o log de</label><select id="servico-log" name="servico">' + opcoes + '</select><button type="submit">Ver o log</button></form>')
    corpo = ("<p>Cada botão roda o comando no terminal e abre a aba Terminal com o resultado. Reiniciar tudo também reinicia este painel: espere cerca de um minuto "
             f"e recarregue a página.</p><h2>Ações</h2><ul>{botoes}</ul>{log}")
    return "Manutenção", corpo


ROTAS = {"/": pg_inicio, "/terminal": pg_terminal, "/servicos": pg_servicos, "/manutencao": pg_manutencao}

SCRIPT = r"""
(function(){
'use strict';
var csrf = document.getElementById('csrf').value;
var ta = document.getElementById('terminal');
var estado = document.getElementById('estado');
var base = ta.value;                 // tudo o que o servidor mostra; o que vem depois é o que a pessoa está digitando
var rodando = false, ultimaVersao = parseInt(ta.dataset.versao || '0', 10), timer = null, vistos = {}, primeira = true;
var inicioUltima = -1, historico = [], hi = -1, pendente = false;
var hist = document.getElementById('historico'), nHist = parseInt(hist.dataset.n || '0', 10);
ta.spellcheck = false; ta.setAttribute('autocorrect', 'off'); ta.setAttribute('autocapitalize', 'off');
var alterna = false, enviado = null;
function dizer(t){ estado.textContent = ''; alterna = !alterna; setTimeout(function(){ estado.textContent = t + (alterna ? '\u200b' : ''); }, 120); }
function digitado(){ return ta.value.indexOf(base) === 0 ? ta.value.slice(base.length) : ''; }
function post(url, dados){
  var corpo = new URLSearchParams(dados || {}); corpo.set('csrf', csrf);
  return fetch(url, {method:'POST', credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1','Content-Type':'application/x-www-form-urlencoded'}, body: corpo.toString()}).then(function(r){ return r.json(); });
}
function fimDoCampo(){ ta.setSelectionRange(ta.value.length, ta.value.length); }
// atualiza um campo sem mexer no cursor nem na rolagem de quem está lendo
function atualizarCampo(el, novo){
  var antigo = el.value; if (antigo === novo) { return; }
  var a = el.selectionStart, b = el.selectionEnd, desl = el.scrollTop;
  if (antigo.length > 0 && novo.indexOf(antigo) === 0) { el.setRangeText(novo.slice(antigo.length), antigo.length, antigo.length, 'preserve'); }
  else { el.value = novo; }
  var m = el.value.length; el.setSelectionRange(Math.min(a, m), Math.min(b, m)); el.scrollTop = desl;
  if (el === hist && a >= antigo.length) { histAoFim(); }       // o histórico acompanha o fim, de onde se lê do mais novo para o mais antigo
}
function aplicar(s){
  var novo = s.texto + (s.rodando ? '' : s.prompt);
  if (novo !== base) {
    var resto = digitado(), trocou = false; if (enviado !== null && resto === enviado) { resto = ''; trocou = true; } enviado = null;
    var a = ta.selectionStart, b = ta.selectionEnd, noFim = a >= base.length, desl = ta.scrollTop;
    var comeco = !trocou && novo.indexOf(base) === 0 && base.length > 0;
    if (trocou) { a = b = base.length; }
    if (comeco) { ta.setRangeText(novo.slice(base.length), base.length, base.length, 'preserve'); } else { ta.value = novo + resto; }
    if (noFim) { ta.setSelectionRange(novo.length + (a - base.length), novo.length + (b - base.length)); ta.scrollTop = ta.scrollHeight; }
    else { var m = ta.value.length; ta.setSelectionRange(Math.min(a, m), Math.min(b, m)); ta.scrollTop = comeco ? desl : ta.scrollHeight; }
    base = novo;
  }
  if (document.activeElement !== ta) { fimDoCampo(); }
  if (s.historico !== null && s.historico !== undefined) { atualizarCampo(hist, s.historico); }
  nHist = s.n_hist;
  inicioUltima = s.inicio_ultima; historico = s.comandos || historico; ultimaVersao = s.versao; rodando = s.rodando;
  (s.blocos || []).forEach(function(bl){
    if (!primeira && vistos[bl.n] === 'rodando' && bl.estado !== 'rodando' && bl.aviso) { dizer(bl.aviso); }
    vistos[bl.n] = bl.estado;
  });
  primeira = false;
}
function buscar(){
  fetch('/terminal/estado?desde=' + ultimaVersao + '&h=' + nHist, {credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1'}}).then(function(r){ return r.json(); }).then(function(s){
    aplicar(s); if (s.rodando) { timer = setTimeout(buscar, 700); } else { timer = null; }
  }).catch(function(){ timer = setTimeout(buscar, 2000); });
}
function buscarAgora(){ if (timer) { clearTimeout(timer); timer = null; } buscar(); }
function enviar(){
  var t = digitado();
  if (rodando) {
    ta.value = base; ta.setSelectionRange(base.length, base.length);
    post('/terminal/entrada', {texto: t}).then(function(r){
      if (r.erro) { dizer(r.erro + ' Digite de novo.'); ta.value = base + t; ta.setSelectionRange(ta.value.length, ta.value.length); buscarAgora(); }
      else { dizer('Resposta enviada.'); buscarAgora(); }
    });
    return;
  }
  if (!t.trim() || enviado !== null) { return; }
  historico.push(t); hi = -1;
  enviado = t;                                           // a linha digitada fica até a saída chegar: o campo muda uma vez só, não duas
  post('/terminal/executar', {comando: t}).then(function(r){
    if (r.erro) { enviado = null; dizer(r.erro); return; }
    vistos[r.n] = 'rodando'; rodando = true; buscarAgora();
  });
}
function interromper(){
  post('/terminal/interromper', {}).then(function(r){ dizer(r.ok ? 'Interrompendo.' : 'Nada em execução.'); buscarAgora(); });
}
function limpar(){ post('/terminal/limpar', {}).then(function(){ dizer('Saídas limpas.'); buscarAgora(); }); }
function reiniciar(){ post('/terminal/reiniciar', {}).then(function(r){ dizer(r.erro ? r.erro : 'Shell reiniciado.'); buscarAgora(); }); }
function copiar(url){
  fetch(url, {credentials:'same-origin'}).then(function(r){ return r.text(); }).then(function(texto){
    if (!texto) { dizer('Não há saída para copiar.'); return; }
    var n = texto.length;
    var ok = function(){ document.getElementById('area-copia').hidden = true; dizer('Copiado: ' + n + ' caracteres.'); };
    var falha = function(){
      var area = document.getElementById('area-copia'); var campo = document.getElementById('texto-copia');
      area.hidden = false; campo.value = texto; campo.focus(); campo.select();
      try { if (document.execCommand('copy')) { ok(); return; } } catch(e) {}
      dizer('O navegador não deixou copiar sozinho. O texto está no campo de cópia, já selecionado: use Command+C.');
    };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(texto).then(ok, falha); } else { falha(); }
  });
}
function qs(){ return '&comando=' + (document.getElementById('com-comando').checked ? '1' : '0'); }
function copiarUltimas(n){ copiar('/terminal/texto?ultimos=' + n + qs()); }
function irAoInicio(){
  if (inicioUltima < 0) { dizer('Ainda não há saída.'); return; }
  ta.focus(); ta.setSelectionRange(inicioUltima, inicioUltima);
  var linhas = ta.value.slice(0, inicioUltima).split('\n').length;
  ta.scrollTop = Math.max(0, (linhas - 2) * parseFloat(getComputedStyle(ta).lineHeight || '24'));
  dizer('Cursor no início da última saída. Leia com VO+A ou desça com a seta.');
}
function lerUltima(){
  fetch('/terminal/texto?ultimos=1&comando=0', {credentials:'same-origin'}).then(function(r){ return r.text(); }).then(function(t){
    t = t.trim(); if (!t) { dizer('Não há saída.'); return; }
    dizer(t);
  });
}
function historicoMover(d){
  if (!historico.length) { dizer('O histórico está vazio.'); return; }
  if (hi === -1) { hi = historico.length; }
  hi = Math.max(0, Math.min(historico.length, hi + d));
  var c = hi >= historico.length ? '' : historico[hi];
  if (hi >= historico.length) { hi = -1; }
  ta.value = base + c; ta.setSelectionRange(ta.value.length, ta.value.length); ta.focus();
  dizer(c ? 'Histórico: ' + c : 'Linha vazia.');
}
function completar(linha){
  pendente = true;
  var c = ta.selectionStart - base.length, pre = linha.slice(0, c), pos = linha.slice(c);
  fetch('/terminal/completar?linha=' + encodeURIComponent(pre), {credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1'}}).then(function(r){ return r.json(); }).then(function(r){
    pendente = false;
    if (digitado() !== linha) { return; }            // a pessoa continuou digitando enquanto a resposta vinha
    var ops = r.opcoes || [], nova = r.palavra_nova === undefined ? pre : pre.slice(0, r.inicio) + r.palavra_nova;
    if (nova !== pre) { ta.value = base + nova + pos; ta.setSelectionRange(base.length + nova.length, base.length + nova.length); } 
    if (!ops.length) { dizer('Sem opções.'); }
    else if (ops.length === 1) { dizer(ops[0]); }
    else { dizer(ops.length + ' opções: ' + ops.slice(0, 25).join(', ') + (ops.length > 25 ? ' e mais ' + (ops.length - 25) : '') + '.'); }
  }).catch(function(){ pendente = false; dizer('Não consegui completar.'); });
}
function irAoCampo(){ fimDoCampo(); if (document.activeElement !== ta) { ta.focus(); } }
// só a última linha pode ser editada: o resto é a saída e fica protegido. Se o cursor estiver na saída, o que a pessoa digita vai para o fim, sem perder letra
ta.addEventListener('beforeinput', function(ev){
  var t = ev.inputType || '', a = ta.selectionStart, b = ta.selectionEnd;
  if (t === 'historyUndo' || t === 'historyRedo') { ev.preventDefault(); return; }
  if (a < base.length) {
    ev.preventDefault();
    if (t.indexOf('delete') === 0) { return; }
    var texto = ev.data || (ev.dataTransfer ? ev.dataTransfer.getData('text/plain') : '') || (t === 'insertLineBreak' ? '\n' : '');
    fimDoCampo();
    if (texto) { ta.setRangeText(texto, ta.value.length, ta.value.length, 'end'); }
    return;
  }
  if (t.indexOf('Backward') >= 0 && a === b && a <= base.length) { ev.preventDefault(); }
});
// o histórico é um campo normal (as setas e o cursor funcionam como em qualquer campo), mas nada pode ser alterado nele
hist.addEventListener('beforeinput', function(ev){ ev.preventDefault(); });
hist.spellcheck = false;
var histApontador = false;
function histAoFim(){ hist.setSelectionRange(hist.value.length, hist.value.length); hist.scrollTop = hist.scrollHeight; }
hist.addEventListener('mousedown', function(){ histApontador = true; });
hist.addEventListener('mouseup', function(){ histApontador = false; });
// Sem mexer no cursor na hora em que o campo recebe o foco (isso fazia o VoiceOver ler só o último caractere em vez do nome e da linha):
// fora do foco o cursor fica sempre no fim, então a entrada normal já cai no fim; se o Safari puser o cursor no começo, ele vai ao fim só
// depois do atraso (o mesmo do Terminal), e apenas se você ainda não digitou, clicou nem moveu o cursor.
var atrasoCursor = parseInt(ta.dataset.atraso || '1800', 10), histTocou = false, histEntrada = 0;
['keydown', 'mousedown', 'touchstart'].forEach(function(n){ hist.addEventListener(n, function(){ histTocou = true; }, true); });
function histFimFora(){ if (!histApontador && document.activeElement !== hist) { histAoFim(); } }
hist.addEventListener('blur', function(){ histApontador = false; histEntrada++; histFimFora(); [0, 60, 300].forEach(function(ms){ setTimeout(histFimFora, ms); }); });
hist.addEventListener('focus', function(){
  histTocou = false; var id = ++histEntrada;
  if (!(atrasoCursor > 0)) { return; }
  setTimeout(function(){
    if (id !== histEntrada || histTocou || histApontador || document.activeElement !== hist) { return; }
    if (hist.selectionStart !== 0 || hist.selectionEnd !== 0) { return; }
    histAoFim();
  }, atrasoCursor);
});
histAoFim();
function tentarCompletar(){
  var linha = digitado();
  if (ta.selectionStart < base.length) { fimDoCampo(); }
  if (rodando) { dizer('Há um programa em execução: Ctrl+I não completa.'); return; }
  if (!linha.length) { dizer('Nada digitado para completar.'); return; }
  if (pendente) { return; }                                                          // a resposta do Tab anterior ainda não chegou: espera
  completar(linha);
}
// Ctrl+I completa (no terminal de verdade Ctrl+I é o Tab). O Tab em si fica livre para mover o foco pela página, como em qualquer lugar.
window.addEventListener('keydown', function(ev){
  if (ev.isComposing || document.activeElement !== ta) { return; }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey && ev.code === 'KeyI') { ev.preventDefault(); ev.stopPropagation(); tentarCompletar(); }
}, true);
ta.addEventListener('keydown', function(ev){
  if (ev.isComposing) { return; }
  if (ev.key === 'Enter' && !ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey) { ev.preventDefault(); enviar(); return; }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey && ev.code === 'KeyC') {
    ev.preventDefault();
    if (rodando || enviado !== null) { interromper(); } else { ta.value = base; ta.setSelectionRange(base.length, base.length); dizer('Linha apagada.'); }
    return;
  }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey && ev.code === 'KeyL') { ev.preventDefault(); limpar(); }
});
// Ao voltar ao campo (Tab, Shift+Tab) o Safari põe o cursor no começo. Nada é mexido na hora, para o VoiceOver ler o nome do campo inteiro;
// só depois do atraso (data-atraso, em ms) o cursor vai ao fim, e apenas se você ainda não digitou, clicou nem moveu o cursor.
// Se você digitar antes disso, a letra já vai para o fim (beforeinput). O carregamento da página, a volta à aba e Option+Shift+T põem o cursor no fim antes do foco.
var tocou = false, entrada = 0;
['keydown', 'mousedown', 'touchstart'].forEach(function(n){ ta.addEventListener(n, function(){ tocou = true; }, true); });
ta.addEventListener('blur', function(){ entrada++; });
ta.addEventListener('focus', function(){
  tocou = false; var id = ++entrada;
  if (!(atrasoCursor > 0)) { return; }
  setTimeout(function(){
    if (id !== entrada || tocou || document.activeElement !== ta) { return; }
    if (ta.selectionStart !== 0 || ta.selectionEnd !== 0) { return; }     // já está no fim ou você escolheu outro ponto: não mexe
    fimDoCampo();
  }, atrasoCursor);
});
window.addEventListener('focus', function(){ if (!document.activeElement || document.activeElement === document.body) { irAoCampo(); } });
window.addEventListener('pageshow', function(ev){ if (ev.persisted) { irAoCampo(); } });
document.addEventListener('keydown', function(ev){
  if (ev.isComposing || !ev.shiftKey || ev.metaKey) { return; }
  if (ev.ctrlKey && !ev.altKey && /^Digit[0-9]$/.test(ev.code)) {          // Ctrl+Shift+número: copia as últimas N saídas (Option+Shift+número troca de aba)
    var n = parseInt(ev.code.slice(5), 10); ev.preventDefault(); copiarUltimas(n === 0 ? 300 : n); return;
  }
  if (!ev.altKey || ev.ctrlKey) { return; }
  var c = ev.code, f = null;
  if (c === 'KeyC') { f = function(){ copiarUltimas(1); }; }
  else if (c === 'KeyU') { f = irAoInicio; }
  else if (c === 'KeyO') { f = lerUltima; }
  else if (c === 'KeyP') { f = function(){ historicoMover(-1); }; }
  else if (c === 'KeyN') { f = function(){ historicoMover(1); }; }
  else if (c === 'KeyL') { f = limpar; }
  else if (c === 'KeyR') { f = reiniciar; }
  else if (c === 'KeyI') { f = interromper; }
  else if (c === 'KeyT') { f = irAoCampo; }
  else if (c === 'KeyH') { f = function(){ document.getElementById('h-atalhos').focus(); }; }
  if (f) { ev.preventDefault(); f(); }
});
document.getElementById('bt-copiar-ultima').addEventListener('click', function(){ copiarUltimas(1); });
document.getElementById('bt-copiar-n').addEventListener('click', function(){
  var n = parseInt(document.getElementById('qtd').value, 10); if (!(n >= 1)) { n = 1; } copiarUltimas(n);
});
document.getElementById('bt-int').addEventListener('click', interromper);
document.getElementById('bt-inicio').addEventListener('click', irAoInicio);
document.getElementById('bt-ler').addEventListener('click', lerUltima);
document.getElementById('bt-limpar').addEventListener('click', limpar);
document.getElementById('bt-reiniciar').addEventListener('click', reiniciar);
irAoCampo();
buscarAgora();
})();
"""


# Chaves da aba Serviços. Delegado no documento, para continuar valendo quando a aba é trocada sem recarregar a página.
SCRIPT_SERVICOS = r"""
(function(){
var ocupado = false;
function dizer(t){ var r = document.getElementById('resultado-servicos'); if (r) { r.textContent = ''; setTimeout(function(){ r.textContent = t; }, 50); } }
document.addEventListener('click', function(ev){
  var b = ev.target.closest ? ev.target.closest('button[role=switch][data-servico]') : null; if (!b) { return; }
  ev.preventDefault();
  if (ocupado || b.getAttribute('aria-disabled') === 'true') { return; }
  var lista = document.getElementById('servicos'), nome = b.textContent, quer = b.getAttribute('aria-checked') === 'true' ? 'off' : 'on';
  var est = document.getElementById('est-' + b.getAttribute('data-servico'));
  ocupado = true; b.setAttribute('aria-disabled', 'true'); dizer((quer === 'on' ? 'Ligando ' : 'Desligando ') + nome + '. Pode levar alguns segundos.');
  var corpo = new URLSearchParams({csrf: lista.getAttribute('data-csrf'), id: b.getAttribute('data-servico'), estado: quer});
  fetch('/servicos/alternar', {method: 'POST', credentials: 'same-origin', headers: {'X-Heimdall-Ajax': '1', 'Content-Type': 'application/x-www-form-urlencoded'}, body: corpo})
    .then(function(r){ return r.json().then(function(d){ return {r: r, d: d}; }); })
    .then(function(x){
      if (x.d.erro) { dizer(nome + ': ' + x.d.erro); return; }
      b.setAttribute('aria-checked', x.d.ligado ? 'true' : 'false'); if (est) { est.textContent = x.d.situacao; }
      dizer(nome + ': ' + x.d.mensagem + ' Agora está ' + (x.d.ligado ? 'ligado' : 'desligado') + '.');
    })
    .catch(function(){ dizer(nome + ': não consegui falar com o painel. Recarregue a página.'); })
    .then(function(){ ocupado = false; b.removeAttribute('aria-disabled'); });
});
})();
"""


def pagina(titulo: str, corpo: str, sess: dict = None, atual: str = "", nonce: str = "", script: str = "", flash=None) -> bytes:
    nav = ""
    if sess:
        nav = ('<nav aria-label="Principal">' + design.abas(SECOES, atual, completas=("/terminal",)) + '<form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></nav>')
        corpo = design.painel_da_aba(SECOES, atual, f"<h1>{e(titulo)}</h1>{{aviso}}{corpo}")
    else:
        corpo = f"<h1>{e(titulo)}</h1>{{aviso}}{corpo}"
    aviso = ""
    if flash:
        tipo, texto = flash if isinstance(flash, tuple) else ("erro", flash)
        linhas = [l for l in str(texto).split("\n") if l.strip()]
        lista = f"<ul>{''.join('<li>' + e(l) + '</li>' for l in linhas)}</ul>" if len(linhas) > 1 else e(linhas[0] if linhas else "")
        aviso = (f'<div class="ok" role="status">{lista}</div>' if tipo == "ok" else f'<div class="erro" role="alert">{lista}</div>')
    corpo = corpo.replace("{aviso}", aviso, 1)
    todo = ((design.SCRIPT_ABAS + SCRIPT_SERVICOS) if sess else "") + script
    js = f'<script nonce="{nonce}">{todo}</script>' if todo and nonce else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Controls</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Controls", nav)}'
            f'<main id="principal">{corpo}</main>{js}</body></html>').encode("utf-8")


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


# ----------------------------------------------------------------------------------------
# Servidor
# ----------------------------------------------------------------------------------------
class Painel(BaseHTTPRequestHandler):
    server_version = "HeimdallControls"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None, nonce: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        script = f"script-src 'nonce-{nonce}'; connect-src 'self'; " if nonce else ""
        self.send_header("Content-Security-Policy", f"default-src 'none'; {script}img-src data:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, status: int, dado: dict) -> None:
        self._enviar(status, json.dumps(dado, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        sess = nuvem.sessao_valida(token, SERVICO)
        # Só o dono (sessão de escopo total): convidado do Access, mesmo liberado em "controls", não entra num terminal.
        if sess and nuvem._escopo_do_token(token) != "*":
            return token, None
        return token, sess

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        return nuvem.cabecalho_cookie(token, self.headers.get("Host", ""), self._https(), apagar)

    def _access_ok(self, host: str) -> bool:
        """Endereço público com o Cloudflare Access ligado: todo pedido precisa vir de um dono aprovado no Access."""
        if host in LOCAIS or not EXIGE_ACCESS:
            return True
        try:
            import heimdall_cfaccess as cfa
            if not cfa.ativo():
                return True
            email, papel = cfa.identificar(self.headers, SERVICO)
            return papel == "dono"
        except Exception:  # noqa: BLE001
            return False

    def _origem_ok(self) -> bool:
        for cab in ("Origin", "Referer"):
            v = self.headers.get(cab)
            if v:
                h = (urlparse(v).hostname or "").lower()
                return h in HOSTS_OK
        return True

    def _corpo(self) -> dict:
        n = min(int(self.headers.get("Content-Length") or 0), MAX_CORPO)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}

    def do_GET(self):  # noqa: N802
        self._despachar("GET")

    def do_POST(self):  # noqa: N802
        self._despachar("POST")

    def do_HEAD(self):  # noqa: N802
        self._despachar("GET")

    def _despachar(self, metodo: str) -> None:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in HOSTS_OK:
            self._enviar(421, b"Host nao permitido", "text/plain; charset=utf-8")
            return
        url = urlparse(self.path)
        rota, q = url.path, parse_qs(url.query)
        if rota == "/saude":
            self._enviar(200, b"ok", "text/plain; charset=utf-8")
            return
        if not self._access_ok(host):
            self._enviar(403, pagina("Acesso negado", "<p>Entre pelo Cloudflare Access com a conta de dono.</p>"))
            return
        sess = None
        ajax = self.headers.get("X-Heimdall-Ajax") == "1"
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                if ajax:
                    self._json(401, {"erro": "Sessão expirada. Recarregue a página e entre de novo."})
                else:
                    self._ir("/entrar")
                return
            if metodo == "POST":
                self._acao(rota, sess, token, ajax)
                return
            if rota == "/terminal/estado":
                self._estado(q)
                return
            if rota == "/terminal/texto":
                self._texto(q)
                return
            if rota == "/terminal/completar":
                sh = obter_shell()
                self._json(200, completar(sh.pasta, (q.get("linha") or [""])[0][:4000]) if not sh.rodando() else {"opcoes": []})
                return
            funcao = ROTAS.get(rota)
            if not funcao:
                self._enviar(404, pagina("Não encontrei", '<p>Esta página não existe.</p><p><a href="/">Voltar à visão geral</a></p>', sess))
                return
            titulo, corpo = funcao(q, sess)
            nonce = secrets.token_urlsafe(16)
            flash = sess.get("flash") or None
            sess["flash"] = None
            self._enviar(200, pagina(titulo, corpo, sess, rota, nonce, SCRIPT if rota == "/terminal" else "", flash), nonce=nonce)
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            if ajax:
                self._json(500, {"erro": "Erro interno."})
            else:
                self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    # ---------------------------------------------------------------- ações (POST)
    def _acao(self, rota: str, sess: dict, token: str, ajax: bool) -> None:
        campos = self._corpo()
        origem_ok = self._origem_ok()
        csrf_ok = secrets.compare_digest(campos.get("csrf", ""), sess["csrf"])
        if not origem_ok or not csrf_ok:
            motivo = "origem não permitida" if not origem_ok else "token de segurança não confere (a página pode estar velha)"
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} pedido recusado em {rota}: {motivo}; Origin={self.headers.get('Origin')!r} Referer={self.headers.get('Referer')!r} "
                             f"csrf_enviado={bool(campos.get('csrf'))} campos={sorted(campos)[:6]}\n")
            if ajax:
                self._json(403, {"erro": f"Pedido recusado: {motivo}. Recarregue a página."})
            else:
                self._enviar(403, pagina("Pedido recusado", f"<p>Pedido recusado: {e(motivo)}. Recarregue a página e tente de novo.</p>", sess))
            return
        ip = self._ip()
        if rota == "/sair":
            nuvem.encerrar_sessao(token)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        sh = obter_shell() if rota.startswith(("/terminal", "/manutencao")) else None
        try:
            if rota == "/terminal/executar":
                cmd = campos.get("comando", "")
                b = sh.executar(cmd)
                auditar(ip, "executar", cmd)
                if ajax:
                    self._json(200, {"n": b.n})
                else:
                    sh.esperar(20)
                    self._ir("/terminal")
                return
            if rota == "/terminal/entrada":
                sh.enviar_texto(campos.get("texto", ""))
                auditar(ip, "resposta ao programa", "(texto não gravado)")
            elif rota == "/terminal/interromper":
                ok = sh.interromper()
                auditar(ip, "interromper")
                if ajax:
                    self._json(200, {"ok": ok})
                    return
            elif rota == "/terminal/limpar":
                sh.limpar()
                auditar(ip, "limpar")
            elif rota == "/terminal/reiniciar":
                sh.reiniciar()
                auditar(ip, "reiniciar o shell")
            elif rota == "/servicos/alternar":
                self._json(200, self._alternar_servico(campos, ip))
                return
            elif rota == "/manutencao/acao":
                acao = campos.get("acao", "")
                if acao == "log" and campos.get("servico") in LOGS_OK:
                    cmd = f"./subir.sh --log {campos['servico']}"
                elif acao in ACOES:
                    cmd = ACOES[acao][1]
                else:
                    raise ValueError("ação desconhecida")
                sh.executar(cmd)
                auditar(ip, "manutenção: " + acao, cmd)
                self._ir("/terminal")
                return
            else:
                self._enviar(405, pagina("Não permitido", "<p>Pedido desconhecido.</p>", sess))
                return
        except (RuntimeError, ValueError) as ex:
            if ajax:
                self._json(409, {"erro": str(ex)})
                return
            sess["flash"] = ("erro", str(ex))
            self._ir("/terminal" if rota.startswith("/terminal") else rota.rsplit("/", 1)[0] or "/")
            return
        if ajax:
            self._json(200, {"ok": True})
        else:
            self._ir("/terminal")

    def _alternar_servico(self, campos: dict, ip: str) -> dict:
        """Liga ou desliga um serviço e pausa ou retoma o monitor dele no Kuma. Devolve o estado de verdade depois da mudança."""
        sv = servicos.por_id(campos.get("id", ""))
        if not sv or campos.get("estado") not in ("on", "off"):
            raise ValueError("serviço desconhecido")
        ligar = campos["estado"] == "on"
        ok, msg = servicos.aplicar(sv["id"], ligar)
        extra = ""
        mons, _ = kuma.monitores()
        mon = kuma.achar(mons, sv["nome"]) if sv.get("kuma", True) else None
        if mon and ok:
            motivo = kuma.pausar_ou_retomar(mon["id"], pausar=not ligar)
            extra = (" Monitor do Kuma " + ("retomado." if ligar else "pausado.")) if not motivo else f" Kuma não mexido: {motivo}."
        auditar(ip, "serviços: " + ("ligar" if ligar else "desligar"), sv["id"] + ("" if ok else " (falhou)"))
        ar = servicos.no_ar(sv)
        mons, _ = kuma.monitores()
        mon = kuma.achar(mons, sv["nome"]) if sv.get("kuma", True) else None
        sit = ("Ligado" if ar else "Desligado") + ": " + _situacao_servico(sv, ar, sv["id"] in servicos.desligados(), mon)
        return {"ok": ok, "ligado": ar, "mensagem": ("" if ok else "Não deu. ") + msg + extra, "situacao": sit}

    # ---------------------------------------------------------------- leitura do terminal
    def _estado(self, q: dict) -> None:
        sh = obter_shell()
        try:
            desde = int((q.get("desde") or ["0"])[0])
        except ValueError:
            desde = 0
        with sh._lock:
            mudados = [b for b in sh.blocos if b.versao > desde or b.estado == "rodando"]
            rod = sh.rodando()
            try:
                h_cliente = int((q.get("h") or ["-1"])[0])
            except ValueError:
                h_cliente = -1
            n_hist = max(0, len(sh.blocos) - 1)
            t = transcricao(sh, com_historico=(h_cliente != n_hist))
            blocos = []
            for b in mudados:
                fim_ = b.estado != "rodando"
                blocos.append({"n": b.n, "estado": b.estado, "codigo": b.codigo, "comando": b.comando,
                               "saida": _saida_exibida(sh, b)[0] if fim_ else "", "aviso": aviso_do_bloco(sh, b) if fim_ else ""})
            dado = {"versao": sh.versao, "rodando": rod, "pasta": sh.pasta, "prompt": prompt_de(sh.pasta),
                    "texto": t["texto"], "inicio_ultima": t["inicio_ultima"], "historico": t["historico"] if h_cliente != n_hist else None, "n_hist": n_hist,
                    "comandos": [b.comando for b in sh.blocos][-100:], "blocos": blocos}
        self._json(200, dado)

    def _texto(self, q: dict) -> None:
        sh = obter_shell()
        com = (q.get("comando") or ["1"])[0] != "0"
        try:
            if q.get("bloco"):
                t = sh.texto_para_copiar(so_bloco=int(q["bloco"][0]), com_comando=com)
            else:
                t = sh.texto_para_copiar(ultimos=int((q.get("ultimos") or ["1"])[0]), com_comando=com)
        except ValueError:
            t = ""
        self._enviar(200, t.encode("utf-8"), "text/plain; charset=utf-8")

    # ---------------------------------------------------------------- entrada
    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            via = self._entrada_access()
            if via:
                self._enviar(200, nuvem.pagina_continuar(), extra=[self._cookie(via)])
                return
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if nuvem.login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        campos = self._corpo()
        senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
        passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
            nuvem.registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            auditar(ip, "login recusado")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        auditar(ip, "login aceito (senha e código)")
        self._ir("/", [self._cookie(token)])

    def _entrada_access(self):
        """Sessão nova só se o Access aprovou um DONO (convidado nunca entra aqui)."""
        try:
            import heimdall_cfaccess as cfa
            email, papel = cfa.identificar(self.headers, SERVICO)
        except Exception:  # noqa: BLE001
            return None
        if papel != "dono":
            return None
        token, _ = nuvem.nova_sessao("*")
        auditar(self._ip(), "login aceito (Cloudflare Access)", email)
        return token


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o Heimdall Controls não sobe. Rode: python3 heimdall_acesso.py --tudo")
    servicos.iniciar_vigia()
    srv = ThreadingHTTPServer((HOST, PORT), Painel)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Controls em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _shell is not None:
            _shell.encerrar()


if __name__ == "__main__":
    main()
