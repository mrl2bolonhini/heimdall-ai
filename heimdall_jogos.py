#!/usr/bin/env python3
"""Heimdall Jogos (games.heimdall-ai.tech): jogos leves, feitos para leitor de tela, que rodam no navegador.

Cada jogo é HTML comum (botões, campos e listas) mais um arquivo JavaScript da pasta jogos/; o que acontece na partida
é dito em voz alta por uma região aria-live. Nada é gravado: o servidor só entrega as páginas.
Jogos: forca, senha (Mastermind), jogo da velha, número secreto, 2048 e uma aventura de texto.

Segurança (pode ficar acessível de fora, então tem as mesmas camadas dos outros painéis):
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada com a senha e o código de 6 dígitos do Heimdall Cloud (python3 heimdall_acesso.py --tudo).
  3. Limite de tentativas por endereço e global, sessão em cookie HttpOnly e SameSite=Strict.
  4. Só atende os nomes de site permitidos (HEIMDALL_JOGOS_HOSTS) e manda cabeçalhos de segurança.
  5. Só os arquivos .js do catálogo são entregues, e a política de conteúdo só deixa rodar script do próprio site.
  6. Sem senha e sem código configurados, o servidor não sobe.

Variáveis opcionais no .env: HEIMDALL_JOGOS_PORT (8014), HEIMDALL_JOGOS_HOST (127.0.0.1),
HEIMDALL_JOGOS_HOSTS (games.heimdall-ai.tech,localhost,127.0.0.1) e HEIMDALL_JOGOS_EXTRAS: outros jogos que você hospeda
(por exemplo Enigma), no formato "Nome|http://localhost:8015|descrição;Outro|https://exemplo.test|descrição".
"""
import html
import os
import re
import secrets
import sys
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent
JOGOS_DIR = PROJECT_DIR / "jogos"


def carregar_env() -> None:
    """Do .env lê só as variáveis deste servidor (as outras chaves não entram neste processo)."""
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
        if not chave.startswith("HEIMDALL_JOGOS_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)

HOST = os.environ.get("HEIMDALL_JOGOS_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("HEIMDALL_JOGOS_PORT", "8014")))
except ValueError:
    PORT = 8014
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_JOGOS_HOSTS", "games.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
COOKIE = nuvem.COOKIE
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

# id, título, arquivo, resumo, como jogar (uma frase por item)
CATALOGO = [
    ("forca", "Forca", "forca.js", "Descubra a palavra letra por letra, com 7 erros permitidos.",
     ["Digite uma letra e confirme com Enter, ou arrisque a palavra inteira.", "Acentos não importam: digite c para ç.", "A cada tentativa a página diz o que aconteceu e como está a palavra."]),
    ("senha", "Senha", "senha.js", "Mastermind: descubra uma senha de 4 dígitos em até 10 tentativas.",
     ["A senha tem 4 dígitos, cada um de 1 a 6, e pode repetir.", "Para cada palpite você ouve quantos dígitos estão no lugar certo e quantos são certos no lugar errado."]),
    ("velha", "Jogo da velha", "velha.js", "Contra o computador, nos níveis fácil e difícil.",
     ["Você é o X e joga primeiro; cada casa é um botão com o nome da linha e da coluna.", "No nível difícil o computador não perde: o melhor que você consegue é empatar."]),
    ("numero", "Número secreto", "numero.js", "Descubra o número de 1 a 100 com as dicas maior e menor.",
     ["Digite um palpite; a resposta diz se o número é maior ou menor e o intervalo que sobrou."]),
    ("2048", "2048", "g2048.js", "Junte peças iguais até chegar ao 2048, ouvindo cada jogada.",
     ["Mova com os botões ou com as setas do teclado; o jogo descreve o que se moveu e onde surgiu uma peça nova.", "O botão Ler o tabuleiro diz as quatro linhas."]),
    ("aventura", "O Farol Apagado", "aventura.js", "Aventura de texto: acenda a lâmpada do farol da ilha.",
     ["Digite comandos como olhar, ir norte, pegar lanterna, usar chave, inventário e ajuda.", "Dica: explore a casa do guarda antes de ir ao farol."]),
]
POR_ID = {j[0]: j for j in CATALOGO}
ARQUIVOS_OK = {"base.js"} | {j[2] for j in CATALOGO}


def extras() -> list:
    """Outros jogos hospedados por você (HEIMDALL_JOGOS_EXTRAS): só endereços http e https."""
    saida = []
    for item in os.environ.get("HEIMDALL_JOGOS_EXTRAS", "").split(";"):
        p = [x.strip() for x in item.split("|")]
        if len(p) >= 2 and p[0] and re.match(r"^https?://[A-Za-z0-9.:/_~%?#=&-]+$", p[1]):
            saida.append((p[0], p[1], p[2] if len(p) > 2 else ""))
    return saida


CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.7;max-width:50rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .3rem;font-size:1.25em}
.lista-jogos{list-style:none;padding:0}.lista-jogos li{margin:.8rem 0}
#anuncio{border:1px solid var(--linha);padding:.7rem;margin:1rem 0;min-height:2.4rem}
#jogo input[type=text]{font-size:1.1em;padding:.5rem;margin:.3rem 0;max-width:22rem;width:100%}
#jogo button{margin:.3rem .3rem .3rem 0;padding:.6rem 1rem;font-size:1em}
#historico{padding-left:1.4rem}#quadro{list-style:none;padding:0}
"""


def pagina(titulo: str, corpo: str, sess: dict = None, extra_head: str = "", scripts: list = None) -> bytes:
    nav = ""
    if sess:
        nav = ('<nav aria-label="Principal"><ul><li><a href="/">Todos os jogos</a></li><li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
    js = "".join(f'<script src="/js/{e(s)}" defer></script>' for s in (scripts or []))
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">{extra_head}<title>{e(titulo)} - Heimdall Jogos</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Jogos", nav)}'
            f'<main id="principal"><h1>{e(titulo)}</h1>{corpo}</main>{js}</body></html>').encode("utf-8")


def pg_inicio() -> tuple:
    itens = "".join(f'<li><h2><a href="/jogo/{e(j[0])}">{e(j[1])}</a></h2><p>{e(j[3])}</p></li>' for j in CATALOGO)
    ex = extras()
    outros = ""
    if ex:
        outros = ("<h2>Outros jogos hospedados aqui</h2><ul class=\"lista-jogos\">"
                  + "".join(f'<li><a href="{e(u)}">{e(n)}</a>' + (f": {e(d)}" if d else "") + "</li>" for n, u, d in ex) + "</ul>")
    corpo = ("<p>Jogos leves para jogar no navegador, feitos para leitor de tela: tudo é botão, campo de texto ou lista, e cada jogada é lida em voz alta. "
             "Nada é guardado no servidor.</p>" f'<ul class="lista-jogos">{itens}</ul>{outros}')
    return "Jogos", corpo, []


def pg_jogo(jid: str):
    j = POR_ID.get(jid)
    if not j:
        return None
    como = "".join(f"<li>{e(t)}</li>" for t in j[4])
    corpo = (f'<p>{e(j[3])}</p><h2>Como jogar</h2><ol>{como}</ol><h2>Jogo</h2>'
             '<noscript><p class="erro">Este jogo precisa de JavaScript ligado no navegador.</p></noscript>'
             '<div id="jogo"></div><div id="anuncio" role="status" aria-live="polite" aria-atomic="true"></div>'
             '<p><a href="/">Voltar para todos os jogos</a></p>')
    return j[1], corpo, ["base.js", j[2]]


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


CSP_PAGINA = "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; base-uri 'none'; connect-src 'none'; frame-ancestors 'none'"


class Jogos(BaseHTTPRequestHandler):
    server_version = "HeimdallJogos"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP_PAGINA)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

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
        return token, nuvem.sessao_valida(token)

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        return nuvem.cabecalho_cookie(token, self.headers.get("Host", ""), self._https(), apagar)

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
        rota = urlparse(self.path).path
        if rota == "/saude":
            self._enviar(200, b"ok", "text/plain; charset=utf-8")
            return
        sess = None
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                self._ir("/entrar")
                return
            if metodo == "POST":
                if rota != "/sair":
                    self._enviar(405, pagina("Não permitido", "<p>Este servidor só entrega os jogos.</p>", sess))
                    return
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
                if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
                    self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
                    return
                nuvem.encerrar_sessao(token)
                self._ir("/entrar", [self._cookie("", apagar=True)])
                return
            if rota.startswith("/js/"):
                nome = rota[4:]
                if nome not in ARQUIVOS_OK or not (JOGOS_DIR / nome).is_file():
                    self._enviar(404, b"nao encontrado", "text/plain; charset=utf-8")
                    return
                self._enviar(200, (JOGOS_DIR / nome).read_bytes(), "application/javascript; charset=utf-8")
                return
            if rota == "/":
                titulo, corpo, scripts = pg_inicio()
                self._enviar(200, pagina(titulo, corpo, sess, scripts=scripts))
                return
            m = re.fullmatch(r"/jogo/([a-z0-9]+)", rota)
            r = pg_jogo(m.group(1)) if m else None
            if not r:
                self._enviar(404, pagina("Não encontrei", '<p>Este jogo não existe.</p><p><a href="/">Ver todos os jogos</a></p>', sess))
                return
            self._enviar(200, pagina(r[0], r[1], sess, scripts=r[2]))
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if nuvem.login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
        senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
        passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
            nuvem.registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o servidor de jogos não sobe. Rode: python3 heimdall_acesso.py --tudo")
    srv = ThreadingHTTPServer((HOST, PORT), Jogos)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Jogos em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
