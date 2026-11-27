#!/usr/bin/env python3
"""Account (account.studiolibre.io): a porta de entrada do ecossistema. Mostra, a quem entrou pelo Cloudflare Access, um tour dos serviços
a que a pessoa tem acesso, com link, o que cada um faz e como configurar. Também responde /quem.json, que o site studiolibre.io usa para mostrar
"Entrar" (quando não há login) ou o nome e os serviços (quando há).

Segurança:
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare, com o Access na frente (só e-mails de donos e convidados, com o Authenticator).
  2. No endereço público só atende quem trouxe o documento assinado do Access, conferido aqui (heimdall_cfaccess); sem ele, 403. Pela porta local (localhost)
     atende o dono do Mac: a página só tem nomes e links de serviços, nada guardado.
  3. /quem.json só devolve CORS (com cookies) para os sites listados em STUDIO_ACCOUNT_ORIGENS; para os outros, nada.
  4. Só atende os nomes de site permitidos (STUDIO_ACCOUNT_HOSTS) e manda cabeçalhos de segurança; a página não usa script.

Variáveis opcionais no .env: STUDIO_ACCOUNT_PORT (8018), STUDIO_ACCOUNT_HOST (127.0.0.1),
STUDIO_ACCOUNT_HOSTS (account.studiolibre.io,localhost,127.0.0.1), STUDIO_ACCOUNT_ORIGENS (https://studiolibre.io,https://www.studiolibre.io).
"""
import html
import json
import os
import secrets
import sys
import time
import urllib.parse
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
        if not chave.startswith(("STUDIO_ACCOUNT_", "HEIMDALL_CFACCESS_")):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_lab as nuvem  # noqa: E402  (marca, cabeçalho com o menu Conta e a base dos servidores)
import heimdall_conta as conta  # noqa: E402
import heimdall_conta_info as info  # noqa: E402
import heimdall_design as design  # noqa: E402
import heimdall_integracoes as integ  # noqa: E402
import heimdall_ajuda as ajuda  # noqa: E402  (perguntas frequentes, suporte e políticas)

e = html.escape
PORT = int(os.environ.get("STUDIO_ACCOUNT_PORT", "8018"))
HOST = os.environ.get("STUDIO_ACCOUNT_HOST", "127.0.0.1")
LOCAIS = {"localhost", "127.0.0.1", "[::1]"}


def _lista(nome: str, padrao: str) -> set:
    return {x.strip().lower().rstrip("/") for x in os.environ.get(nome, padrao).split(",") if x.strip()}


def hosts_ok() -> set:
    import heimdall_links
    return _lista("STUDIO_ACCOUNT_HOSTS", "account.studiolibre.io,localhost,127.0.0.1") | heimdall_links.hosts_padrao("account")


def origens_ok() -> set:
    return _lista("STUDIO_ACCOUNT_ORIGENS", "https://studiolibre.io,https://www.studiolibre.io")


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
        aviso = "<p>Este serviço é do dono do StudioLibre.</p>" if d.get("so_dono") and p.get("papel") == "dono" else ""
        blocos.append(f'<section aria-labelledby="{i}"><h2 id="{i}">{e(nome)}</h2><p>{e(d["oque"])}</p><p>Como configurar e usar</p><ol>{passos}</ol>{extra}{aviso}'
                      f'<p><a href="{e(url)}">Abrir {e(nome)}</a></p></section>')
    saudacao = e(p.get("nome") or p.get("email") or "Dono")
    corpo = (f'<h1>Seus serviços do StudioLibre</h1><p>Olá, {saudacao}. Aqui estão os serviços do StudioLibre a que você tem acesso, com um link para cada um, o que ele faz '
             f'e como configurar. O menu Conta, no alto de qualquer página, leva a todos eles.</p>' + ("".join(blocos) or "<p>Nenhum serviço liberado ainda. Fale com o dono.</p>"))
    return _documento("Seus serviços - Account", corpo, nonce)


NAV = '<nav aria-label="Principal"><ul><li><a href="/">Serviços</a></li><li><a href="/integracoes">Integrações</a></li><li><a href="/ajuda">Ajuda e suporte</a></li></ul></nav>'


def _documento(titulo: str, corpo: str, nonce: str) -> bytes:
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)}</title>{nuvem.ICONE}<style nonce="{nonce}">{design.CSS}</style></head><body><div id="topo" tabindex="-1" role="group" aria-label="Início da página"></div>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Account", NAV)}<main id="principal">{corpo}</main>{design.rodape(servico="account")}</body></html>').encode("utf-8")


def _passos_hae(url: str) -> str:
    itens = ["Instale o app Health Auto Export no iPhone e conceda o acesso aos dados de Saúde que quiser enviar.",
             "No app, abra Automações e crie uma automação nova do tipo API REST. As automações exigem o plano Premium do app (ou o período de teste).",
             f"No campo de endereço (URL), coloque: {url}",
             "Método: POST. Formato: JSON. Escolha as métricas de saúde e, se quiser, os treinos.",
             "Em cabeçalhos (headers), acrescente o nome Authorization com o valor Bearer, um espaço e o token mostrado nesta página.",
             "Salve e rode a automação uma vez. No Mac, studio mailbox pull importa o que chegou; o StudioLibre também busca sozinho de tempos em tempos."]
    return "<ol>" + "".join(f"<li>{e(x)}</li>" for x in itens) + "</ol>"


def pagina_integracoes(p: dict, nonce: str, token: str = "", aviso: str = "", erro: str = "") -> bytes:
    """A página de Integrações. `token` só vem logo depois de ativar: aparece uma vez, num campo somente leitura."""
    st = integ.estado(p)
    tok = integ.csrf(p)
    url = integ.url_hae()
    topo = ""
    if erro:
        topo = f'<p role="alert">{e(erro)}</p>'
    elif aviso:
        topo = f'<p role="status">{e(aviso)}</p>'
    s = st["itens"]["saude"]
    if token:
        saude = (f'<section aria-labelledby="i-saude"><h2 id="i-saude">Saúde</h2><p>Integração ativada. Copie o token agora: ele não aparece de novo, e ativar outra vez gera um token novo e invalida este.</p>'
                 f'<label for="tk">Token (somente leitura)</label><input id="tk" type="text" readonly value="{e(token)}" autocomplete="off">'
                 f'<p>Como configurar no iPhone</p>{_passos_hae(url)}</section>')
    else:
        if s["ativa"]:
            estado_txt = f'Ativa desde {e(s["desde"])}. Ativar de novo troca o token.'
        elif not st["pode"]:
            estado_txt = "Ainda não disponível para a sua conta: falta o armazenamento por pessoa. Por enquanto só o dono do StudioLibre pode ligar a Saúde."
        elif not st["caixa"]:
            estado_txt = "A caixa de correio está desligada. No terminal do Mac: studio mailbox start, depois studio env --set STUDIO_CAIXA 1."
        else:
            estado_txt = "Ainda não ativada."
        acoes = ""
        if st["pode"] and st["caixa"]:
            acoes = design.botao_post("/integracoes/saude/ativar", "Trocar o token da Saúde" if s["ativa"] else "Ativar a Saúde", tok, None, "Gerar o token da integração de Saúde")
            if s["ativa"]:
                acoes += design.botao_post("/integracoes/saude/desativar", "Desativar a Saúde", tok, None, "Desativar a integração de Saúde e invalidar o token")
        saude = (f'<section aria-labelledby="i-saude"><h2 id="i-saude">Saúde</h2><p>Envia os dados do app Saúde do iPhone para o StudioLibre, pelo app Health Auto Export, '
                 f'passando pela caixa de correio da Cloudflare. Não é criptografia de ponta a ponta: a Cloudflare consegue ler o que está na caixa em trânsito, e o que sobra some em 7 dias.</p>'
                 f'<p>Estado: {estado_txt}</p>{acoes}</section>')
    prep = []
    for chave, texto in (("notas", "Ler as suas notas a partir da conta Apple (iCloud) ou Google. Você poderá escolher as pastas, ou deixar o StudioLibre buscar sozinho."),
                         ("lembretes", "Sincronizar lembretes com a conta Apple ou Google."),
                         ("calendario", "Sincronizar eventos com a conta Apple ou Google.")):
        n = st["itens"][chave]["nome"]
        prep.append(f'<section aria-labelledby="i-{chave}"><h2 id="i-{chave}">{e(n)}</h2><p>{e(texto)}</p><p>Estado: em preparação. Falta o armazenamento por pessoa e a ligação com a conta Apple ou Google. '
                    f'Para o dono, o Mac já lê Notas, Lembretes e Calendário do iCloud pelo agente da Apple.</p></section>')
    corpo = (f'<h1>Integrações da sua conta</h1>{topo}<p>Aqui você liga o StudioLibre aos apps e contas que usa. Cada integração mostra o estado e o que fazer. '
             f'Android: por enquanto só Calendário e Tarefas, pela conta Google, quando essa integração ficar pronta; a Saúde do Android precisa de um app próprio, que ainda não existe.</p>'
             + saude + "".join(prep))
    return _documento("Integrações - Account", corpo, nonce)


class Account(nuvem.ManipuladorBase):
    server_version = "StudioLibre"
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
        if caminho not in ("/", "/integracoes", "/ajuda", "/termos-de-uso", "/politica-de-privacidade", "/suporte/mensagens"):
            return self._responder(404, "Não encontrado.".encode(), "text/plain; charset=utf-8")
        if not p or (host not in LOCAIS and not p.get("access")):
            return self._responder(403, "Entre pelo Cloudflare Access.".encode(), "text/plain; charset=utf-8")
        nonce = secrets.token_urlsafe(12)
        if caminho == "/suporte/mensagens":
            if p.get("papel") != "dono":
                return self._responder(404, "Não encontrado.".encode(), "text/plain; charset=utf-8")
            titulo, corpo = ajuda.pagina_mensagens(integ.csrf(p))
            return self._html(_documento(titulo, corpo, nonce), nonce)
        if caminho in ("/ajuda", "/termos-de-uso", "/politica-de-privacidade"):
            if caminho == "/ajuda":
                q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                titulo, corpo = ajuda.pagina_ajuda(integ.csrf(p), (q.get("servico") or [""])[0], dono=p.get("papel") == "dono")
            else:
                titulo, corpo = ajuda.pagina_termos_de_uso() if caminho == "/termos-de-uso" else ajuda.pagina_privacidade()
            return self._html(_documento(titulo, corpo, nonce), nonce)
        pagina = pagina_tour(p, nonce) if caminho == "/" else pagina_integracoes(p, nonce)
        self._html(pagina, nonce)

    def _html(self, pagina: bytes, nonce: str, status: int = 200) -> None:
        self._responder(status, pagina, "text/html; charset=utf-8", csp=f"default-src 'none'; img-src data:; style-src 'nonce-{nonce}'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

    def do_POST(self):
        """Ações das Integrações. Exigem quem entrou (Access ou porta local), origem do próprio site e o token csrf do formulário."""
        host = self._host()
        if host not in hosts_ok():
            return self._responder(421, "Endereço não permitido.".encode(), "text/plain; charset=utf-8")
        caminho = self.path.split("?", 1)[0]
        acoes = {"/integracoes/saude/ativar": integ.ativar_saude, "/integracoes/saude/desativar": integ.desativar_saude}
        if caminho == "/suporte":
            return self._suporte(host)
        if caminho == "/suporte/responder":
            return self._suporte_responder(host)
        if caminho not in acoes:
            return self._responder(404, "Não encontrado.".encode(), "text/plain; charset=utf-8")
        p = self._quem()
        if not p or (host not in LOCAIS and not p.get("access")):
            return self._responder(403, "Entre pelo Cloudflare Access.".encode(), "text/plain; charset=utf-8")
        origem = urllib.parse.urlparse(self.headers.get("Origin") or "").hostname or ""
        if origem.lower() != host:
            return self._responder(403, "Origem não permitida.".encode(), "text/plain; charset=utf-8")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= 2048:
            return self._responder(413, "Pedido grande demais.".encode(), "text/plain; charset=utf-8")
        campos = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        if not integ.csrf_ok(p, (campos.get("csrf") or [""])[0]):
            return self._responder(403, "Formulário vencido ou inválido: abra a página de novo.".encode(), "text/plain; charset=utf-8")
        nonce = secrets.token_urlsafe(12)
        try:
            if caminho.endswith("/ativar"):
                token = acoes[caminho](p)
                return self._html(pagina_integracoes(p, nonce, token=token), nonce)
            acoes[caminho](p)
            self._html(pagina_integracoes(p, nonce, aviso="Saúde desativada. O token foi invalidado."), nonce)
        except RuntimeError as err:
            self._html(pagina_integracoes(p, nonce, erro=f"Não foi possível: {err}."), nonce, 400)


def _suporte_post(self, host: str) -> None:
    """POST /suporte: grava a mensagem com protocolo e a envia ao suporte. Mesmas exigências das Integrações: quem entrou, origem do próprio site e csrf."""
    p = self._quem()
    if not p or (host not in LOCAIS and not p.get("access")):
        return self._responder(403, "Entre pelo Cloudflare Access.".encode(), "text/plain; charset=utf-8")
    origem = urllib.parse.urlparse(self.headers.get("Origin") or "").hostname or ""
    if origem.lower() != host:
        return self._responder(403, "Origem não permitida.".encode(), "text/plain; charset=utf-8")
    try:
        n = int(self.headers.get("Content-Length") or 0)
    except ValueError:
        n = -1
    if not 0 <= n <= 16384:
        return self._responder(413, "Pedido grande demais.".encode(), "text/plain; charset=utf-8")
    campos = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
    campo = lambda k: (campos.get(k) or [""])[0]  # noqa: E731
    if not integ.csrf_ok(p, campo("csrf")):
        return self._responder(403, "Formulário vencido ou inválido: abra a página de novo.".encode(), "text/plain; charset=utf-8")
    nonce = secrets.token_urlsafe(12)
    try:
        reg, enviado = ajuda.enviar(p, campo("assunto"), campo("servico"), campo("mensagem"))
    except ajuda.ErroSuporte as err:
        titulo, corpo = ajuda.pagina_ajuda(integ.csrf(p), campo("servico"), erro=str(err), valores={"assunto": campo("assunto"), "servico": campo("servico"), "mensagem": campo("mensagem")})
        return self._html(_documento(titulo, corpo, nonce), nonce, 400)
    titulo, corpo = ajuda.pagina_ajuda(integ.csrf(p), campo("servico"), aviso=ajuda.mensagem_de_confirmacao(reg, enviado))
    self._html(_documento(titulo, corpo, nonce), nonce)


def _suporte_responder_post(self, host: str) -> None:
    """POST /suporte/responder: só o dono; responde de suporte@ a quem escreveu. Mesmas exigências: Access ou porta local, origem do próprio site e csrf."""
    p = self._quem()
    if not p or (host not in LOCAIS and not p.get("access")):
        return self._responder(403, "Entre pelo Cloudflare Access.".encode(), "text/plain; charset=utf-8")
    if p.get("papel") != "dono":
        return self._responder(404, "Não encontrado.".encode(), "text/plain; charset=utf-8")
    origem = urllib.parse.urlparse(self.headers.get("Origin") or "").hostname or ""
    if origem.lower() != host:
        return self._responder(403, "Origem não permitida.".encode(), "text/plain; charset=utf-8")
    try:
        n = int(self.headers.get("Content-Length") or 0)
    except ValueError:
        n = -1
    if not 0 <= n <= 16384:
        return self._responder(413, "Pedido grande demais.".encode(), "text/plain; charset=utf-8")
    campos = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
    campo = lambda k: (campos.get(k) or [""])[0]  # noqa: E731
    if not integ.csrf_ok(p, campo("csrf")):
        return self._responder(403, "Formulário vencido ou inválido: abra a página de novo.".encode(), "text/plain; charset=utf-8")
    nonce = secrets.token_urlsafe(12)
    ok, msg = ajuda.responder(campo("protocolo"), campo("texto"))
    titulo, corpo = ajuda.pagina_mensagens(integ.csrf(p), aviso=msg if ok else "", erro="" if ok else msg)
    self._html(_documento(titulo, corpo, nonce), nonce, 200 if ok else 400)


Account._suporte = _suporte_post
Account._suporte_responder = _suporte_responder_post


def main() -> None:
    srv = ThreadingHTTPServer((HOST, PORT), Account)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Account em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(hosts_ok()))}; origens do site: {', '.join(sorted(origens_ok()))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
