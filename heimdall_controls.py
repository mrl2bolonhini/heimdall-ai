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
MAX_TRANSCRICAO = 400_000  # caracteres do campo do terminal no total (os comandos mais antigos saem da tela)
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.6;max-width:56rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .3rem;font-size:1.25em}h3{font-size:1.05em;margin:.2rem 0}
.terminal.historico{height:16rem}
.terminal{height:60vh;min-height:16rem;font-size:1em;line-height:1.4;white-space:pre-wrap;overflow-wrap:anywhere}
.linha-acoes{display:flex;flex-wrap:wrap;gap:.2rem 1rem;align-items:flex-end}
.linha-acoes form{margin:0}.aviso{border:1px solid var(--linha);padding:.7rem;margin-top:1.5rem;color:var(--suave)}
.fora{color:var(--erro);font-weight:700}
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


SECOES = [("/", "Visão geral"), ("/terminal", "Terminal"), ("/servicos", "Serviços")]

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
    return f"{seg:.1f} s".replace(".", ",") if seg < 60 else f"{int(seg // 60)} min {int(seg % 60)} s"


def prompt_de(pasta: str) -> str:
    """O prompt mostrado no campo: só o nome da pasta, como o zsh faz (~ para a pasta pessoal)."""
    nome = "~" if pasta == str(Path.home()) else (os.path.basename(pasta.rstrip("/")) or "/")
    return f"{nome} % "


def _situacao(b) -> str:
    if b.estado == "interrompido":
        return f"interrompido, {duracao(b.duracao())}"
    if b.estado == "encerrado":
        return "o shell foi encerrado durante este comando"
    return (f"concluído, código {b.codigo}" if b.codigo == 0 else f"erro, código {b.codigo}") + f", {duracao(b.duracao())}"


def _saida_exibida(sh, b) -> tuple:
    """(texto da saída para a tela, aviso de corte). A cópia sempre leva o texto inteiro."""
    saida = sh.saida_parcial(b)
    if len(saida) > MAX_EXIBIDO:
        return saida[-MAX_EXIBIDO:], "[começo da saída omitido na tela; copiar leva tudo]\n"
    return saida, ""


def _texto_do_bloco(sh, b) -> tuple:
    """(texto do comando com prompt, saída e situação; posição onde a saída começa)."""
    cmd = b.comando if len(b.comando) <= 300 else b.comando[:300] + "..."
    cab = prompt_de(b.pasta) + cmd + "\n"
    saida, corte = _saida_exibida(sh, b)
    corpo = corte + saida
    fim_ = b.estado != "rodando"
    if fim_ and corpo and not corpo.endswith("\n"):
        corpo += "\n"
    return cab + corpo + (f"[{_situacao(b)}]\n\n" if fim_ else ""), len(cab) + len(corte)


def transcricao(sh, completo: bool = True) -> dict:
    """O campo do terminal mostra só o ÚLTIMO comando (o leitor de tela lê só a saída dele, como depois de um clear).
    O histórico de todos os comandos vai num campo à parte, somente leitura. O texto do último comando só cresce no fim."""
    with sh._lock:
        if not sh.blocos:
            return {"texto": "", "inicio_ultima": -1, "ultimo_n": 0, "historico": ""}
        ultimo, inicio = _texto_do_bloco(sh, sh.blocos[-1])
        hist = ""
        if completo:
            partes = [_texto_do_bloco(sh, b)[0] for b in sh.blocos[:-1]] + [ultimo]
            while len(partes) > 1 and sum(len(t) for t in partes) > MAX_TRANSCRICAO:
                partes.pop(0)
            hist = "".join(partes)
        return {"texto": ultimo, "inicio_ultima": inicio, "ultimo_n": sh.blocos[-1].n, "historico": hist}


def aviso_do_bloco(sh, b) -> str:
    """O que o leitor de tela fala quando um comando termina: situação e, se for curta, a própria saída."""
    saida, _ = _saida_exibida(sh, b)
    linhas = saida.strip().splitlines()
    if not linhas:
        resumo = "Sem saída."
    elif len(saida.strip()) <= 600 and len(linhas) <= 12:
        resumo = "Saída: " + saida.strip()
    else:
        resumo = f"Saída com {len(linhas)} linhas. Option+Shift+U leva o cursor ao início dela; Option+Shift+O lê o começo."
    return f"Comando {b.n} {_situacao(b)}. {resumo}"


def pg_inicio(q: dict, sess: dict) -> tuple:
    sh = obter_shell() if _shell is not None else None
    corpo = ("<p>Aqui você administra o Heimdall pelo navegador. Tudo roda no seu Mac, com as suas permissões.</p>"
             "<ol><li><a href=\"/terminal\">Terminal</a>: um shell completo. A pasta e as variáveis continuam de um comando para o outro, "
             "e há botões para copiar a última saída ou as últimas saídas.</li>"
             "<li><a href=\"/servicos\">Serviços</a>: quais estão no ar e botões para atualizar, reiniciar e ver os logs.</li></ol>")
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
        '<p id="estado" role="status" aria-live="polite"></p>'
        f'<input type="hidden" id="csrf" value="{e(sess["csrf"])}">'
        '<p>Digite o comando na última linha do campo e aperte Enter. A saída aparece no próprio campo, logo abaixo do comando. '
        'Se um programa estiver perguntando algo, o que você digitar vai para ele. O campo mostra só o último comando; os anteriores ficam em Histórico, mais abaixo. '
        'Tab completa comandos e nomes de arquivos. Option+Shift+H leva à lista de atalhos.</p>'
        '<label for="terminal">Terminal</label>'
        f'<textarea class="terminal" id="terminal" spellcheck="false" autocomplete="off" autocapitalize="off" autocorrect="off" data-versao="{sh.versao}">{e(inicial)}</textarea>'
        '<section aria-labelledby="h-ac"><h2 id="h-ac">Ações</h2><div class="linha-acoes">'
        '<div><button type="button" id="bt-copiar-ultima">Copiar a última saída (Option+Shift+C)</button></div>'
        '<div><label for="qtd">Quantas últimas saídas</label><input id="qtd" type="number" min="1" max="300" value="3" inputmode="numeric">'
        '<button type="button" id="bt-copiar-n">Copiar as últimas saídas</button></div>'
        '<div><label><input type="checkbox" id="com-comando" checked> Incluir o comando</label></div></div>'
        '<div class="linha-acoes"><button type="button" id="bt-int">Interromper (Ctrl+C)</button>'
        '<button type="button" id="bt-inicio">Ir ao início da última saída (Option+Shift+U)</button>'
        '<button type="button" id="bt-ler">Ler o começo da última saída (Option+Shift+O)</button>'
        '<button type="button" id="bt-limpar">Limpar as saídas (Ctrl+L)</button>'
        '<button type="button" id="bt-reiniciar">Reiniciar o shell (Option+Shift+R)</button></div>'
        '<p>Reiniciar o shell fecha o atual e abre outro limpo, na pasta do Heimdall.</p>'
        '<div id="area-copia" hidden><label for="texto-copia">Se o navegador não deixar copiar sozinho, selecione tudo neste campo (Command+A) e copie (Command+C)</label>'
        '<textarea id="texto-copia" readonly></textarea></div></section>'
        '<section aria-labelledby="h-hist"><h2 id="h-hist">Histórico</h2>'
        '<label for="historico">Todos os comandos e saídas, do mais antigo ao mais recente (somente leitura)</label>'
        f'<textarea class="terminal historico" id="historico" readonly spellcheck="false">{e(hist)}</textarea></section>'
        '<section aria-labelledby="h-atalhos"><h2 id="h-atalhos" tabindex="-1">Atalhos de teclado</h2>'
        '<p>Funcionam em qualquer ponto desta página. Option é a tecla Alt do Mac.</p><ol>'
        '<li>Enter: executa o comando digitado na última linha, ou envia a resposta ao programa que está perguntando. Shift+Enter: nova linha dentro do comando.</li>'
        '<li>Tab: completa o nome de um comando (na primeira palavra) ou de um arquivo ou pasta. Se houver vários, completa o que for igual em todos e o leitor de tela diz as opções. Se nada mudar, o Tab seguinte sai do campo, como de costume. Sem nada digitado, o Tab só passa para o próximo item.</li>'
        '<li>Ctrl+C ou Option+Shift+I: interrompe o programa em execução. Sem programa rodando, Ctrl+C apaga a linha digitada.</li>'
        '<li>Option+Shift+C: copia a última saída. Option+Shift+1 até 9: copia as últimas 1 a 9 saídas. Option+Shift+0: copia todas. A caixa Incluir o comando vale para todas.</li>'
        '<li>Option+Shift+U: leva o cursor ao início da última saída; depois leia com VO+A ou desça com a seta. Option+Shift+O: o leitor de tela lê o começo da última saída.</li>'
        '<li>Option+Shift+P e Option+Shift+N: comando anterior e seguinte do histórico.</li>'
        '<li>Ctrl+L ou Option+Shift+L: limpa as saídas. Option+Shift+R: reinicia o shell.</li>'
        '<li>Option+Shift+T: volta ao campo do terminal. Option+Shift+H: vem para esta lista.</li></ol></section>'
        '<noscript><p class="aviso">Sem JavaScript o terminal não funciona. Use o botão Atualizar a página para ver o resultado.</p></noscript>'
        + design.botao("/terminal", "Atualizar a página"))
    return "Terminal", corpo


SERVICOS = [(8000, "MCP Mac"), (8001, "MCP público"), (8002, "Open Terminal"), (8003, "Agente do Mac"), (8004, "MCP dados"), (8010, "Cloud"), (8011, "Notas"),
            (8012, "News"), (8013, "Saúde"), (8014, "Jogos"), (8016, "Finance"), (9000, "LiteLLM"), (3000, "Open WebUI"), (5678, "n8n"), (11434, "Ollama")]
LOGS_OK = ["mcp", "mcp_public", "mcp_dados", "agente", "cloud", "notas", "news", "saude_painel", "jogos", "finance", "controls", "ingest"]
# ação -> comando. Só estas viram botão; o texto livre vai pelo terminal.
ACOES = {
    "update": ("Atualizar do GitHub (sem reiniciar)", "heimdall update"),
    "update_restart": ("Atualizar e reiniciar tudo", "heimdall update --restart"),
    "restart": ("Reiniciar o Heimdall", "heimdall restart"),
    "status": ("Ver o estado completo", "heimdall status"),
    "doctor": ("Diagnóstico", "heimdall doctor"),
}


def _porta_aberta(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.4):
            return True
    except OSError:
        return False


def pg_servicos(q: dict, sess: dict) -> tuple:
    csrf = e(sess["csrf"])
    linhas = "".join(f'<tr><th scope="row">{e(n)}</th><td>{p}</td><td>' + ("no ar" if _porta_aberta(p) else '<span class="fora">fora do ar</span>') + "</td></tr>" for p, n in SERVICOS)
    tabela = f'<table><caption>Serviços e portas neste Mac</caption><thead><tr><th scope="col">Serviço</th><th scope="col">Porta</th><th scope="col">Situação</th></tr></thead><tbody>{linhas}</tbody></table>'
    botoes = "".join(f'<li><form method="post" action="/servicos/acao"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="acao" value="{k}">'
                     f'<button type="submit">{e(rot)}</button></form></li>' for k, (rot, _) in ACOES.items())
    opcoes = "".join(f'<option value="{s}">{e(s)}</option>' for s in LOGS_OK)
    log = ('<form method="post" action="/servicos/acao"><input type="hidden" name="csrf" value="' + csrf + '"><input type="hidden" name="acao" value="log">'
           '<label for="servico-log">Ver o log de</label><select id="servico-log" name="servico">' + opcoes + '</select><button type="submit">Ver o log</button></form>')
    corpo = ("<p>Cada botão roda o comando no terminal e abre a página dele com o resultado. Reiniciar tudo também reinicia este painel: espere cerca de um minuto "
             "e recarregue a página.</p>"
             f'<h2>Ações</h2><ul>{botoes}</ul>{log}<h2>Estado</h2>{tabela}')
    return "Serviços", corpo


ROTAS = {"/": pg_inicio, "/terminal": pg_terminal, "/servicos": pg_servicos}

SCRIPT = r"""
(function(){
'use strict';
var csrf = document.getElementById('csrf').value;
var ta = document.getElementById('terminal');
var estado = document.getElementById('estado');
var base = ta.value;                 // tudo o que o servidor mostra; o que vem depois é o que a pessoa está digitando
var rodando = false, ultimaVersao = parseInt(ta.dataset.versao || '0', 10), timer = null, vistos = {}, primeira = true;
var inicioUltima = -1, historico = [], hi = -1, tabParado = false;
ta.spellcheck = false; ta.setAttribute('autocorrect', 'off'); ta.setAttribute('autocapitalize', 'off');
function dizer(t){ estado.textContent = ''; setTimeout(function(){ estado.textContent = t; }, 60); }
function digitado(){ return ta.value.indexOf(base) === 0 ? ta.value.slice(base.length) : ''; }
function post(url, dados){
  var corpo = new URLSearchParams(dados || {}); corpo.set('csrf', csrf);
  return fetch(url, {method:'POST', credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1','Content-Type':'application/x-www-form-urlencoded'}, body: corpo.toString()}).then(function(r){ return r.json(); });
}
function aplicar(s){
  var novo = s.texto + (s.rodando ? '' : s.prompt);
  if (novo !== base) {
    var resto = digitado(), a = ta.selectionStart, b = ta.selectionEnd, noFim = a >= base.length, desl = ta.scrollTop;
    var comeco = novo.indexOf(base) === 0 && base.length > 0;
    if (comeco) { ta.setRangeText(novo.slice(base.length), base.length, base.length, 'preserve'); } else { ta.value = novo + resto; }
    if (noFim) { ta.setSelectionRange(novo.length + (a - base.length), novo.length + (b - base.length)); ta.scrollTop = ta.scrollHeight; }
    else { var m = ta.value.length; ta.setSelectionRange(Math.min(a, m), Math.min(b, m)); ta.scrollTop = comeco ? desl : ta.scrollHeight; }
    base = novo;
  }
  if (s.historico !== null && s.historico !== undefined) { var h = document.getElementById('historico'); if (h.value !== s.historico) { h.value = s.historico; } }
  inicioUltima = s.inicio_ultima; historico = s.comandos || historico; ultimaVersao = s.versao; rodando = s.rodando;
  (s.blocos || []).forEach(function(bl){
    if (!primeira && vistos[bl.n] === 'rodando' && bl.estado !== 'rodando' && bl.aviso) { dizer(bl.aviso); }
    vistos[bl.n] = bl.estado;
  });
  primeira = false;
}
function buscar(){
  fetch('/terminal/estado?desde=' + ultimaVersao, {credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1'}}).then(function(r){ return r.json(); }).then(function(s){
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
  if (!t.trim()) { return; }
  historico.push(t); hi = -1;
  ta.value = base; ta.setSelectionRange(base.length, base.length);
  post('/terminal/executar', {comando: t}).then(function(r){
    if (r.erro) { dizer(r.erro); ta.value = base + t; ta.setSelectionRange(ta.value.length, ta.value.length); return; }
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
    dizer(t.length > 2000 ? t.slice(0, 2000) + ' ... (continua; copie ou use Option+Shift+U para ler tudo)' : t);
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
  var c = ta.selectionStart - base.length, pre = linha.slice(0, c), pos = linha.slice(c);
  fetch('/terminal/completar?linha=' + encodeURIComponent(pre), {credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1'}}).then(function(r){ return r.json(); }).then(function(r){
    if (digitado() !== linha) { return; }            // a pessoa continuou digitando enquanto a resposta vinha
    var ops = r.opcoes || [], nova = r.palavra_nova === undefined ? pre : pre.slice(0, r.inicio) + r.palavra_nova;
    if (nova !== pre) { ta.value = base + nova + pos; ta.setSelectionRange(base.length + nova.length, base.length + nova.length); tabParado = false; } else { tabParado = true; }
    if (!ops.length) { dizer('Sem opções.'); }
    else if (ops.length === 1) { dizer(ops[0]); }
    else { dizer(ops.length + ' opções: ' + ops.slice(0, 25).join(', ') + (ops.length > 25 ? ' e mais ' + (ops.length - 25) : '') + '.'); }
  }).catch(function(){ tabParado = true; });
}
function irAoCampo(){ ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
// só a última linha pode ser editada: o resto é a saída e fica protegido
ta.addEventListener('beforeinput', function(ev){
  var t = ev.inputType || '', a = ta.selectionStart, b = ta.selectionEnd;
  var apagaParaTras = t.indexOf('Backward') >= 0 && a === b && a <= base.length;
  if (t === 'historyUndo' || t === 'historyRedo' || a < base.length || apagaParaTras) {
    ev.preventDefault();
    if (a < base.length && t.indexOf('delete') !== 0) { ta.setSelectionRange(ta.value.length, ta.value.length); dizer('Só dá para digitar na última linha. O cursor foi para o final.'); }
  }
});
ta.addEventListener('keydown', function(ev){
  if (ev.isComposing) { return; }
  if (ev.key !== 'Tab') { tabParado = false; }
  if (ev.key === 'Tab' && !ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey) {
    var linha = digitado();
    if (rodando || !linha.length || ta.selectionStart < base.length) { return; }   // sem nada a completar, o Tab é o de sempre: passa ao próximo item
    if (tabParado) { tabParado = false; return; }                                    // Tab sem efeito duas vezes seguidas: deixa sair do campo
    ev.preventDefault(); completar(linha); return;
  }
  if (ev.key === 'Enter' && !ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey) { ev.preventDefault(); enviar(); return; }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey && ev.code === 'KeyC') {
    ev.preventDefault();
    if (rodando) { interromper(); } else { ta.value = base; ta.setSelectionRange(base.length, base.length); dizer('Linha apagada.'); }
    return;
  }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && !ev.shiftKey && ev.code === 'KeyL') { ev.preventDefault(); limpar(); }
});
ta.addEventListener('focus', function(){ if (ta.selectionStart === 0 && ta.selectionEnd === 0 && base.length > 0) { ta.setSelectionRange(ta.value.length, ta.value.length); } });
document.addEventListener('keydown', function(ev){
  if (ev.isComposing || !ev.altKey || !ev.shiftKey || ev.ctrlKey || ev.metaKey) { return; }
  var c = ev.code, f = null;
  if (c === 'KeyC') { f = function(){ copiarUltimas(1); }; }
  else if (/^Digit[0-9]$/.test(c)) { var n = parseInt(c.slice(5), 10); f = function(){ copiarUltimas(n === 0 ? 300 : n); }; }
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
buscarAgora();
})();
"""


def pagina(titulo: str, corpo: str, sess: dict = None, atual: str = "", nonce: str = "", script: str = "", flash: str = "") -> bytes:
    nav = ""
    if sess:
        itens = "".join(f'<li><a href="{e(r)}"' + (' aria-current="page"' if r == atual else "") + f">{e(n)}</a></li>" for r, n in SECOES)
        nav = ('<nav aria-label="Principal"><ul>' + itens + '<li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
    aviso = f'<p class="erro" role="alert">{e(flash)}</p>' if flash else ""
    js = f'<script nonce="{nonce}">{script}</script>' if script else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Controls</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Controls", nav)}'
            f'<main id="principal"><h1>{e(titulo)}</h1>{aviso}{corpo}</main>{js}</body></html>').encode("utf-8")


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
            nonce = secrets.token_urlsafe(16) if rota == "/terminal" else ""
            flash = (sess.get("flash") or [None, ""])[1] if sess.get("flash") else ""
            sess["flash"] = None
            self._enviar(200, pagina(titulo, corpo, sess, rota, nonce, SCRIPT if nonce else "", flash), nonce=nonce)
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            if ajax:
                self._json(500, {"erro": "Erro interno."})
            else:
                self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    # ---------------------------------------------------------------- ações (POST)
    def _acao(self, rota: str, sess: dict, token: str, ajax: bool) -> None:
        campos = self._corpo()
        if not self._origem_ok() or not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
            if ajax:
                self._json(403, {"erro": "Pedido recusado: token de segurança inválido. Recarregue a página."})
            else:
                self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
            return
        ip = self._ip()
        if rota == "/sair":
            nuvem.encerrar_sessao(token)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        sh = obter_shell() if rota.startswith(("/terminal", "/servicos")) else None
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
            elif rota == "/servicos/acao":
                acao = campos.get("acao", "")
                if acao == "log" and campos.get("servico") in LOGS_OK:
                    cmd = f"./subir.sh --log {campos['servico']}"
                elif acao in ACOES:
                    cmd = ACOES[acao][1]
                else:
                    raise ValueError("ação desconhecida")
                sh.executar(cmd)
                auditar(ip, "serviços: " + acao, cmd)
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
            self._ir("/terminal" if rota.startswith("/terminal") else "/servicos")
            return
        if ajax:
            self._json(200, {"ok": True})
        else:
            self._ir("/terminal")

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
            t = transcricao(sh, completo=not rod)
            blocos = []
            for b in mudados:
                fim_ = b.estado != "rodando"
                blocos.append({"n": b.n, "estado": b.estado, "codigo": b.codigo, "comando": b.comando,
                               "saida": _saida_exibida(sh, b)[0] if fim_ else "", "aviso": aviso_do_bloco(sh, b) if fim_ else ""})
            dado = {"versao": sh.versao, "rodando": rod, "pasta": sh.pasta, "prompt": prompt_de(sh.pasta),
                    "texto": t["texto"], "inicio_ultima": t["inicio_ultima"], "historico": None if rod else t["historico"],
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
