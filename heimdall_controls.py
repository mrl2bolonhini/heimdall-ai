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
MAX_EXIBIDO = 40_000      # caracteres da saída mostrados na página; a cópia traz tudo
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.6;max-width:56rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .3rem;font-size:1.25em}h3{font-size:1.05em;margin:.2rem 0}
.bloco{border:1px solid var(--linha);padding:.7rem;margin:.8rem 0}
.bloco pre{max-height:28rem}
.campo-comando{width:100%;font-family:ui-monospace,Menlo,monospace;font-size:1em;padding:.5rem}
.linha-acoes{display:flex;flex-wrap:wrap;gap:.2rem 1rem;align-items:flex-end}
.linha-acoes form{margin:0}.aviso{border:1px solid var(--linha);padding:.7rem;margin-top:1.5rem;color:var(--suave)}
.fora{color:var(--erro);font-weight:700}
"""

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


def html_bloco(b, curto: bool = True) -> str:
    """Um comando e a sua saída, no formato que o leitor de tela percorre bem: título, situação e a saída."""
    sh = obter_shell()
    saida = sh.saida_parcial(b)
    corte = ""
    if len(saida) > MAX_EXIBIDO:
        saida = "..." + saida[-MAX_EXIBIDO:]
        corte = '<p class="aviso">Mostrei só o final da saída. O botão Copiar esta saída leva o texto inteiro.</p>'
    if b.estado == "rodando":
        sit = "Em execução" + (", interrompendo" if b.interrompido else "") + f" há {duracao(b.duracao())}."
    elif b.estado == "interrompido":
        sit = f"Interrompido após {duracao(b.duracao())}."
    elif b.estado == "encerrado":
        sit = "O shell foi encerrado durante este comando."
    else:
        sit = ("Concluído com sucesso" if b.codigo == 0 else f"Terminou com erro, código {b.codigo}") + f" em {duracao(b.duracao())}."
    cmd = b.comando if len(b.comando) <= 300 else b.comando[:300] + "..."
    vazio = "" if saida.strip() else '<p>Sem saída.</p>'
    return (f'<article class="bloco" id="bloco-{b.n}" aria-labelledby="titulo-{b.n}" data-n="{b.n}" data-estado="{e(b.estado)}" data-codigo="{"" if b.codigo is None else b.codigo}">'
            f'<h3 id="titulo-{b.n}">Comando {b.n}: {e(cmd)}</h3><p>{e(sit)} Pasta: {e(b.pasta)}.</p>'
            + (f'<pre tabindex="0" aria-label="Saída do comando {b.n}">{e(saida)}</pre>' if saida.strip() else vazio) + corte
            + f'<button type="button" class="copiar-bloco" data-n="{b.n}">Copiar a saída do comando {b.n}</button></article>')


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
    csrf = e(sess["csrf"])
    blocos = list(reversed(sh.blocos))
    lista = "".join(html_bloco(b) for b in blocos) or '<p id="vazio">Nenhum comando ainda. Digite um acima.</p>'
    corpo = (
        '<p id="estado" role="status" aria-live="polite"></p>'
        f'<p>Pasta atual: <span id="pasta">{e(sh.pasta)}</span>.</p>'
        '<section aria-labelledby="h-exec"><h2 id="h-exec">Executar um comando</h2>'
        '<form id="form-exec" method="post" action="/terminal/executar">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<label for="comando">Comando</label>'
        '<input class="campo-comando" id="comando" name="comando" type="text" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" required>'
        '<button type="submit">Executar</button></form></section>'
        '<section aria-labelledby="h-ctl"><h2 id="h-ctl">Programa em execução</h2><div class="linha-acoes">'
        '<form id="form-entrada" method="post" action="/terminal/entrada">'
        f'<input type="hidden" name="csrf" value="{csrf}"><label for="resposta">Resposta ao programa (Enter envia)</label>'
        '<input id="resposta" name="texto" type="text" autocomplete="off"><button type="submit">Enviar resposta</button></form>'
        '<form id="form-int" method="post" action="/terminal/interromper">'
        f'<input type="hidden" name="csrf" value="{csrf}"><button type="submit">Interromper (Ctrl+C)</button></form></div></section>'
        '<section aria-labelledby="h-cop"><h2 id="h-cop">Copiar para a área de transferência</h2><div class="linha-acoes">'
        '<div><button type="button" id="copiar-ultima">Copiar a última saída</button></div>'
        '<div><label for="qtd">Quantas últimas saídas</label><input id="qtd" type="number" min="1" max="300" value="3" inputmode="numeric">'
        '<button type="button" id="copiar-n">Copiar as últimas saídas</button></div>'
        '<div><label><input type="checkbox" id="com-comando" checked> Incluir o comando</label></div></div>'
        '<div id="area-copia" hidden><label for="texto-copia">Se o navegador não deixar copiar sozinho, selecione tudo neste campo (Command+A) e copie (Command+C)</label>'
        '<textarea id="texto-copia" readonly></textarea></div></section>'
        '<section aria-labelledby="h-ger"><h2 id="h-ger">Gerenciar o terminal</h2><div class="linha-acoes">'
        '<form method="post" action="/terminal/limpar">' f'<input type="hidden" name="csrf" value="{csrf}"><button type="submit">Limpar a lista de saídas</button></form>'
        '<form method="post" action="/terminal/reiniciar">' f'<input type="hidden" name="csrf" value="{csrf}"><button type="submit">Reiniciar o shell</button></form>'
        '</div><p>Reiniciar o shell fecha o atual e abre outro limpo, na pasta do Heimdall.</p></section>'
        f'<section aria-labelledby="h-saidas"><h2 id="h-saidas">Saídas, da mais recente para a mais antiga</h2><div id="saidas" data-versao="{sh.versao}">{lista}</div></section>'
        '<noscript><p class="aviso">Sem JavaScript os botões de copiar e a atualização automática não funcionam. Use o botão Atualizar a página para ver o resultado.</p></noscript>'
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
var csrf = document.querySelector('input[name=csrf]').value;
var estado = document.getElementById('estado');
var saidas = document.getElementById('saidas');
var cmd = document.getElementById('comando');
var rodando = false, ultimaVersao = parseInt(saidas.dataset.versao || '0', 10), timer = null, vistos = {};
function dizer(t){ estado.textContent = ''; setTimeout(function(){ estado.textContent = t; }, 60); }
function post(url, dados){
  var corpo = new URLSearchParams(dados || {}); corpo.set('csrf', csrf);
  return fetch(url, {method:'POST', credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1','Content-Type':'application/x-www-form-urlencoded'}, body: corpo.toString()}).then(function(r){ return r.json(); });
}
function aplicar(estadoServidor){
  var vazio = document.getElementById('vazio'); if (vazio) vazio.remove();
  document.getElementById('pasta').textContent = estadoServidor.pasta;
  (estadoServidor.blocos || []).forEach(function(b){
    var antigo = document.getElementById('bloco-' + b.n);
    var t = document.createElement('div'); t.innerHTML = b.html; var novo = t.firstChild;
    if (antigo) { antigo.replaceWith(novo); } else { saidas.insertBefore(novo, saidas.firstChild); }
    var anterior = vistos[b.n];
    if (anterior === 'rodando' && b.estado !== 'rodando') {
      dizer('Comando ' + b.n + (b.estado === 'interrompido' ? ' interrompido.' : b.codigo === 0 ? ' concluído com sucesso.' : ' terminou com erro, código ' + b.codigo + '.'));
    }
    vistos[b.n] = b.estado;
  });
  ultimaVersao = estadoServidor.versao; rodando = estadoServidor.rodando;
}
function buscar(){
  fetch('/terminal/estado?desde=' + ultimaVersao, {credentials:'same-origin', headers:{'X-Heimdall-Ajax':'1'}}).then(function(r){ return r.json(); }).then(function(s){
    aplicar(s); if (s.rodando) { timer = setTimeout(buscar, 700); } else { timer = null; }
  }).catch(function(){ timer = setTimeout(buscar, 2000); });
}
function iniciarBusca(){ if (!timer) { timer = setTimeout(buscar, 300); } }
document.getElementById('form-exec').addEventListener('submit', function(ev){
  ev.preventDefault(); var c = cmd.value; if (!c.trim()) return;
  post('/terminal/executar', {comando: c}).then(function(r){
    if (r.erro) { dizer(r.erro); return; }
    cmd.value = ''; dizer('Executando o comando ' + r.n + '.'); vistos[r.n] = 'rodando'; buscarAgora();
  });
});
function buscarAgora(){ if (timer) { clearTimeout(timer); timer = null; } buscar(); }
document.getElementById('form-entrada').addEventListener('submit', function(ev){
  ev.preventDefault(); var campo = document.getElementById('resposta');
  post('/terminal/entrada', {texto: campo.value}).then(function(r){ if (r.erro) { dizer(r.erro); } else { campo.value = ''; dizer('Resposta enviada.'); iniciarBusca(); } });
});
document.getElementById('form-int').addEventListener('submit', function(ev){
  ev.preventDefault(); post('/terminal/interromper', {}).then(function(r){ dizer(r.ok ? 'Interrompendo.' : 'Nada em execução.'); iniciarBusca(); });
});
function copiar(url){
  fetch(url, {credentials:'same-origin'}).then(function(r){ return r.text(); }).then(function(texto){
    if (!texto) { dizer('Não há saída para copiar.'); return; }
    var n = texto.length;
    var ok = function(){ document.getElementById('area-copia').hidden = true; dizer('Copiado: ' + n + ' caracteres.'); };
    var falha = function(){
      var area = document.getElementById('area-copia'); var campo = document.getElementById('texto-copia');
      area.hidden = false; campo.value = texto; campo.focus(); campo.select();
      try { if (document.execCommand('copy')) { ok(); return; } } catch(e) {}
      dizer('O navegador não deixou copiar sozinho. O texto está no campo abaixo, já selecionado: use Command+C.');
    };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(texto).then(ok, falha); } else { falha(); }
  });
}
function qs(){ return '&comando=' + (document.getElementById('com-comando').checked ? '1' : '0'); }
document.getElementById('copiar-ultima').addEventListener('click', function(){ copiar('/terminal/texto?ultimos=1' + qs()); });
document.getElementById('copiar-n').addEventListener('click', function(){
  var n = parseInt(document.getElementById('qtd').value, 10); if (!(n >= 1)) { n = 1; }
  copiar('/terminal/texto?ultimos=' + n + qs());
});
saidas.addEventListener('click', function(ev){
  var b = ev.target.closest('.copiar-bloco'); if (b) { copiar('/terminal/texto?bloco=' + b.dataset.n + qs()); }
});
Array.prototype.forEach.call(saidas.querySelectorAll('.bloco'), function(el){ vistos[el.dataset.n] = el.dataset.estado; if (el.dataset.estado === 'rodando') { rodando = true; } });
if (rodando) { iniciarBusca(); }
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
            dado = {"versao": sh.versao, "rodando": rod, "pasta": sh.pasta,
                    "blocos": [{"n": b.n, "estado": b.estado, "codigo": b.codigo, "html": html_bloco(b)} for b in mudados]}
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
