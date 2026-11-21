#!/usr/bin/env python3
"""Heimdall Account (account.heimdall-ai.tech): a porta de entrada do ecossistema. Mostra, a quem entrou pelo Cloudflare Access, um tour dos serviços
a que a pessoa tem acesso, com link, o que cada um faz e como configurar. Também responde /quem.json, que o site heimdall-ai.tech usa para mostrar
"Entrar" (quando não há login) ou o nome e os serviços (quando há).

Segurança:
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare, com o Access na frente (só e-mails de donos e convidados, com o Authenticator).
  2. No endereço público só atende quem trouxe o documento assinado do Access, conferido aqui (heimdall_cfaccess); sem ele, 403. Pela porta local (localhost)
     atende o dono do Mac: a página só tem nomes e links de serviços, nada guardado.
  3. /quem.json só devolve CORS (com cookies) para os sites listados em HEIMDALL_ACCOUNT_ORIGENS; para os outros, nada.
  4. Só atende os nomes de site permitidos (HEIMDALL_ACCOUNT_HOSTS) e manda cabeçalhos de segurança; a página não usa script.

Variáveis opcionais no .env: HEIMDALL_ACCOUNT_PORT (8018), HEIMDALL_ACCOUNT_HOST (127.0.0.1),
HEIMDALL_ACCOUNT_HOSTS (account.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_ACCOUNT_ORIGENS (https://heimdall-ai.tech,https://www.heimdall-ai.tech).
"""
import html
import json
import os
import secrets
import sys
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis deste servidor (as do Access vêm do ambiente, como nos outros painéis)."""
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
        if not chave.startswith(("HEIMDALL_ACCOUNT_", "HEIMDALL_CFACCESS_")):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_cloud as nuvem  # noqa: E402  (marca, cabeçalho com o menu Conta e a base dos servidores)
import heimdall_conta as conta  # noqa: E402
import heimdall_conta_info as info  # noqa: E402
import heimdall_design as design  # noqa: E402

e = html.escape
PORT = int(os.environ.get("HEIMDALL_ACCOUNT_PORT", "8018"))
HOST = os.environ.get("HEIMDALL_ACCOUNT_HOST", "127.0.0.1")
LOCAIS = {"localhost", "127.0.0.1", "[::1]"}


def _lista(nome: str, padrao: str) -> set:
    return {x.strip().lower().rstrip("/") for x in os.environ.get(nome, padrao).split(",") if x.strip()}


def hosts_ok() -> set:
    return _lista("HEIMDALL_ACCOUNT_HOSTS", "account.heimdall-ai.tech,localhost,127.0.0.1")


def origens_ok() -> set:
    return _lista("HEIMDALL_ACCOUNT_ORIGENS", "https://heimdall-ai.tech,https://www.heimdall-ai.tech")


def dados_quem(p: dict) -> dict:
    """O que /quem.json devolve para quem está logado."""
    return {"logado": True, "nome": p.get("nome") or p.get("email") or "Dono", "email": p.get("email", ""), "papel": p.get("papel", ""),
            "servicos": [{"nome": n, "url": url} for _, n, url in conta.servicos_da(p)]}


def pagina_tour(p: dict, nonce: str) -> bytes:
    """O tour: um bloco por serviço que a pessoa pode abrir."""
    blocos = []
    for chave, nome, url in conta.servicos_da(p):
        d = info.INFO.get(chave)
        if not d:
            continue
        i = f"s-{chave}"
        passos = "".join(f"<li>{e(x)}</li>" for x in d["como"])
        extra = f"<p>{e(d['multiusuario'])}</p>" if d.get("multiusuario") else ""
        aviso = "<p>Este serviço é do dono do Heimdall.</p>" if d.get("so_dono") and p.get("papel") == "dono" else ""
        blocos.append(f'<section aria-labelledby="{i}"><h2 id="{i}">{e(nome)}</h2><p>{e(d["oque"])}</p><p>Como configurar e usar</p><ol>{passos}</ol>{extra}{aviso}'
                      f'<p><a href="{e(url)}">Abrir {e(nome)}</a></p></section>')
    saudacao = e(p.get("nome") or p.get("email") or "Dono")
    corpo = (f'<h1>Seus serviços do Heimdall</h1><p>Olá, {saudacao}. Aqui estão os serviços do Heimdall a que você tem acesso, com um link para cada um, o que ele faz '
             f'e como configurar. O menu Conta, no alto de qualquer página, leva a todos eles.</p>' + ("".join(blocos) or "<p>Nenhum serviço liberado ainda. Fale com o dono.</p>"))
    nav = '<nav aria-label="Principal"><ul><li><a href="#principal">Início</a></li></ul></nav>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>Seus serviços - Heimdall Account</title>{nuvem.ICONE}<style nonce="{nonce}">{design.CSS}</style></head><body><div id="topo" tabindex="-1" role="group" aria-label="Início da página"></div>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Account", nav)}<main id="principal">{corpo}</main>{design.rodape()}</body></html>').encode("utf-8")


class Account(nuvem.ManipuladorBase):
    server_version = "Heimdall"
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} {self.address_string()} {fmt % args}\n")

    def _host(self) -> str:
        return (self.headers.get("Host") or "").split(":")[0].strip().lower() if not (self.headers.get("Host") or "").startswith("[") else "[::1]"

    def _base(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _cors(self) -> None:
        origem = (self.headers.get("Origin") or "").strip().rstrip("/").lower()
        if origem and origem in origens_ok():
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def _responder(self, status: int, corpo: bytes, tipo: str, csp: str = "default-src 'none'", cors: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Content-Security-Policy", csp)
        self._base()
        if cors:
            self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _quem(self) -> dict:
        """Quem pede: pelo Access (endereço público) ou o dono do Mac (porta local). {} se não puder."""
        local = self._host() in LOCAIS and not self.headers.get("Cf-Access-Jwt-Assertion")
        return conta.pessoa(logado_local=local, cabecalhos=self.headers)

    def do_OPTIONS(self):
        if self._host() not in hosts_ok():
            return self._responder(421, b"", "text/plain")
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET")
        self.send_header("Access-Control-Max-Age", "600")
        self._cors()
        self._base()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        host = self._host()
        if host not in hosts_ok():
            return self._responder(421, "Endereço não permitido.".encode(), "text/plain; charset=utf-8")
        caminho = self.path.split("?", 1)[0]
        if caminho == "/saude":
            return self._responder(200, b"ok", "text/plain")
        p = self._quem()
        if caminho == "/quem.json":
            if not p or (host not in LOCAIS and not p.get("access")):
                return self._responder(401, json.dumps({"logado": False}).encode(), "application/json", cors=True)
            return self._responder(200, json.dumps(dados_quem(p), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cors=True)
        if caminho != "/":
            return self._responder(404, "Não encontrado.".encode(), "text/plain; charset=utf-8")
        if not p or (host not in LOCAIS and not p.get("access")):
            return self._responder(403, "Entre pelo Cloudflare Access.".encode(), "text/plain; charset=utf-8")
        nonce = secrets.token_urlsafe(12)
        self._responder(200, pagina_tour(p, nonce), "text/html; charset=utf-8", csp=f"default-src 'none'; img-src data:; style-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'")


def main() -> None:
    srv = ThreadingHTTPServer((HOST, PORT), Account)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Account em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(hosts_ok()))}; origens do site: {', '.join(sorted(origens_ok()))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
