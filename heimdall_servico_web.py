#!/usr/bin/env python3
"""Base web dos serviços novos do Heimdall (Trading, Memory): login, sessão, CSRF, páginas no Heimdall Design, Ajustes, Perguntar e multipart.

Cada serviço descreve a si mesmo com `Config` (abas e subabas, Ajustes, rotas GET e POST, rotas antigas com 301, texto do Perguntar) e chama `servir(cfg)`.
Segurança: só 127.0.0.1 (HEIMDALL_<X>_HOST), só nomes de site permitidos, login por senha e código de 6 dígitos ou Cloudflare Access, CSRF em todo POST,
cookie HttpOnly, HTML sempre escapado, limite de tamanho do pedido, dados separados por pessoa (`pessoas.definir`).
"""
import html
import os
import secrets
import sys
import time
from email import message_from_bytes
from email.policy import HTTP
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from collections import namedtuple
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import contextlib

import heimdall_ajuda as ajuda
import heimdall_banco as banco
import heimdall_design as design
import heimdall_lab as nuvem
import heimdall_perguntar as perguntar
import heimdall_pessoas as pessoas

PROJECT_DIR = Path(__file__).resolve().parent
COOKIE = nuvem.COOKIE
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731


def carregar_env(prefixo: str, legado: str = "") -> None:
    """Lê do .env só as variáveis do serviço (HEIMDALL_<X>_*) e as de pasta de dados.

    legado: prefixo antigo do serviço renomeado (HEIMDALL_LIBRARY_ para o Memory). As variáveis com o prefixo antigo valem como as novas;
    se as duas existirem, a nova manda. Assim o .env de quem atualiza continua funcionando sem edição."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    novas, antigas = {}, {}
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        if chave.startswith(prefixo) or chave in ("HEIMDALL_DB_DIR",):
            novas[chave] = valor
        elif legado and chave.startswith(legado):
            antigas[prefixo + chave[len(legado):]] = valor
    for chave, valor in {**antigas, **novas}.items():
        os.environ.setdefault(chave, valor)


def ler_multipart(tipo_conteudo: str, corpo: bytes) -> tuple:
    """(campos, arquivos) de multipart/form-data. arquivos: lista de (nome do arquivo, bytes), na ordem."""
    msg = message_from_bytes(b"Content-Type: " + tipo_conteudo.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + corpo, policy=HTTP)
    campos, arquivos = {}, []
    if not msg.is_multipart():
        return campos, arquivos
    for parte in msg.iter_parts():
        nome = parte.get_param("name", header="content-disposition")
        if not nome:
            continue
        arq = parte.get_filename()
        carga = parte.get_payload(decode=True) or b""
        if arq is not None:
            if arq and carga:
                arquivos.append((arq, carga))
        else:
            campos[nome] = carga.decode("utf-8", "replace")
    return campos, arquivos


Redirecionar = namedtuple("Redirecionar", "url")   # resposta de uma ação: leva a um endereço https externo (ex.: autorização OAuth); só o código do serviço a cria
Arquivo = namedtuple("Arquivo", "nome tipo dados")   # resposta de download: a tela devolve isto no lugar de (titulo, corpo)


class Config:
    """Descrição de um serviço.
    abas: [(rotulo_da_aba, [(rota, rotulo_da_subaba), ...])]; grupo com uma só rota não mostra subabas. Máximo de 5 abas (design.MAX_ABAS).
    ajustes: [(rota, rotulo)] sob /ajustes; a última é sempre Ajuda (/ajustes/ajuda, gerada pela base).
    get: {rota: func(ctx) -> (titulo, corpo_html)}; post: {rota: func(ctx, campos, arquivos) -> destino}; ctx é `Ctx`.
    aliases: {rota_antiga: rota_nova} (301). contexto_perguntar: func(ctx) -> texto com os dados da tela, ou None se o serviço não tem Perguntar."""

    def __init__(self, chave: str, nome: str, porta_env: str, porta: int, hosts: str, abas: list, ajustes: list, get: dict, post: dict,
                 aliases: dict = None, sistema_perguntar: str = "", contexto_perguntar=None, dica_perguntar: str = "", max_post: int = 20000, ao_iniciar=None,
                 css: str = "", script_pagina=None, erro=ValueError, pertence: dict = None, publicas: dict = None, publicas_post: dict = None,
                 hosts_legados: str = ""):
        self.chave, self.nome, self.porta_env, self.porta, self.hosts = chave, nome, porta_env, porta, hosts
        self.abas, self.ajustes, self.get, self.post = abas, ajustes, get, post
        self.aliases = aliases or {}
        self.sistema_perguntar, self.contexto_perguntar, self.dica_perguntar = sistema_perguntar, contexto_perguntar, dica_perguntar
        self.max_post, self.ao_iniciar, self.css, self.script_pagina, self.erro = max_post, ao_iniciar, css, script_pagina, erro
        self.publicas = publicas or {}   # {rota GET sem sessão: func(q) -> (titulo, corpo) ou (titulo, corpo, script)}; só para retornos de terceiros (OAuth), que chegam sem o cookie
        self.publicas_post = publicas_post or {}   # {rota POST sem sessão: func(campos) -> (titulo, corpo)}; só para o passo final de um retorno de terceiros (o state de uso único vale como credencial)
        self.hosts_legados = {h.strip().lower() for h in hosts_legados.split(",") if h.strip()}   # endereços de antes de uma troca de nome: continuam respondendo e, com <PREFIXO>URL no .env, redirecionam (301) para o novo
        self.pertence = pertence or {}   # {rota que não é aba: rota da aba a destacar}, como /documento dentro de Documentos
        assert len(abas) <= design.MAX_ABAS, "mais abas do que o Heimdall Design permite"
        self.prefixo = f"HEIMDALL_{chave.upper()}_"

    def rotas_abas(self) -> list:
        return [r for _, subs in self.abas for r, _ in subs]


class Ctx:
    """Dados do pedido entregues às telas: parâmetros da URL, sessão e o token CSRF."""

    def __init__(self, q: dict, sess: dict, rota: str):
        self.q, self.sess, self.rota = q, sess, rota
        self.csrf = sess["csrf"]

    def p(self, k: str, padrao: str = "") -> str:
        return (self.q.get(k) or [padrao])[0]

    def pagina(self) -> int:
        try:
            return max(1, int(self.p("pagina", "1")))
        except ValueError:
            return 1

    def aviso(self) -> str:
        f = self.sess.get("flash")
        if not f:
            return ""
        self.sess["flash"] = None
        tipo, texto = f
        return f'<p class="{"erro" if tipo == "erro" else "ok"}" role="{"alert" if tipo == "erro" else "status"}">{e(texto)}</p>'

    def flash(self, tipo: str, texto: str) -> None:
        self.sess["flash"] = (tipo, texto)


def _grupo_da_rota(cfg: Config, rota: str):
    for i, (_, subs) in enumerate(cfg.abas):
        if any(r == rota for r, _ in subs):
            return i, subs
    return None, None


def pagina(cfg: Config, titulo: str, corpo: str, sess: dict = None, rota: str = "", nonce: str = "", script_publico: str = "") -> bytes:
    """Página no Heimdall Design: abas de cima (grupos), subabas do grupo, botão Ajustes (tela sem abas de cima) e rodapé."""
    nav = sair = abas_js = ajustes_html = ""
    conteudo = f"<h1>{e(titulo)}</h1>{corpo}"
    if sess:
        em_ajustes = rota == "/ajustes" or rota.startswith("/ajustes/")
        if em_ajustes:
            nav = f'<div class="acoes-topo">{design.botao(cfg.abas[0][1][0][0], "Voltar")}</div>'
            ajustes_html = design.botao("/ajustes", "Ajustes", atual=True)
            itens = [(r, rot) for r, rot in cfg.ajustes] + [("/ajustes/ajuda", "Ajuda")]
            conteudo = design.com_subabas(itens, rota if rota != "/ajustes" else itens[0][0], conteudo, "Seções dos Ajustes")
        else:
            ajustes_html = design.botao("/ajustes", "Ajustes")
            rota_nav = cfg.pertence.get(rota, rota)
            idx, subs = _grupo_da_rota(cfg, rota_nav)
            itens = [(g[1][0][0], g[0]) for g in cfg.abas]
            if idx is not None:
                atual = itens[idx][0]
                nav = design.nav_abas(itens, atual, f"Seções do {cfg.nome}")
                if len(subs) > 1:
                    conteudo = design.com_abas(itens, atual, design.com_subabas(subs, rota_nav, conteudo, f"Subseções de {cfg.abas[idx][0]}"), foco=False)
                else:
                    conteudo = design.com_abas(itens, atual, conteudo)
        sair = (f'<form class="linha" method="post" action="/sair"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
                '<button type="submit">Sair</button></form>')
        abas_js = design.SCRIPT_ABAS + design.SCRIPT_DETALHES + design.SCRIPT_PERGUNTAR
    extra = cfg.script_pagina(rota) if (cfg.script_pagina and sess) else script_publico
    js = f'<script nonce="{e(nonce)}">{abas_js}{extra}</script>' if (abas_js or extra) and nonce else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall {e(cfg.nome)}</title>{nuvem.ICONE}<style>{nuvem.CSS}{cfg.css}</style></head>'
            f'<body{(" data-csrf=" + chr(34) + e(sess["csrf"]) + chr(34)) if sess else ""}>'
            f'{design.topo()}<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall " + cfg.nome, nav, sair_html=sair, ajustes_html=ajustes_html)}'
            f'<main id="principal">{conteudo}</main>{design.rodape(servico=cfg.chave)}{js}</body></html>').encode("utf-8")


def pg_entrar(cfg: Config, erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina(cfg, "Entrar", corpo)


def com_perguntar(cfg: Config, ctx: Ctx, corpo: str) -> str:
    if not cfg.contexto_perguntar:
        return corpo
    volta = ctx.sess.get("atual", "") or cfg.abas[0][1][0][0]
    if volta.split("?")[0] not in cfg.rotas_abas():
        volta = cfg.abas[0][1][0][0]
    return corpo + perguntar.bloco_html(ctx.csrf, ctx.csrf, volta, f"Perguntar sobre {cfg.nome}", cfg.dica_perguntar)


def criar_manipulador(cfg: Config, hosts_ok: set):
    """Classe de manipulador HTTP do serviço (separada de `servir` para os testes subirem o servidor numa porta livre)."""
    rotas_perguntar = set(cfg.rotas_abas())

    class Manipulador(nuvem.ManipuladorBase):
        server_version = "Heimdall" + cfg.nome
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
            script = f" script-src 'nonce-{nonce}';" if nonce else ""
            self.send_header("Content-Security-Policy", f"default-src 'none'; img-src data:; style-src 'unsafe-inline';{script} connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or []):
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _ir(self, destino: str, extra: list = None, status: int = 303) -> None:
            self._enviar(status, b"", extra=[("Location", destino)] + (extra or []))

        def _pagina(self, status: int, titulo: str, corpo: str, sess: dict = None, rota: str = "", script_publico: str = "") -> None:
            nonce = secrets.token_urlsafe(12) if (sess or script_publico) else ""
            self._enviar(status, pagina(cfg, titulo, corpo, sess, rota, nonce, script_publico), nonce=nonce)

        def _sessao(self):
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie", ""))
            except Exception:  # noqa: BLE001
                return None, None
            m = c.get(COOKIE)
            token = m.value if m else ""
            sess = nuvem.sessao_valida(token, cfg.chave)
            if sess and pessoas.ativo() and not pessoas.valido(sess.get("pessoa", "")):
                return token, None
            return token, sess

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
            if host not in hosts_ok:
                self._enviar(421, b"Host nao permitido", "text/plain; charset=utf-8")
                return
            url = urlparse(self.path)
            rota, q = url.path, parse_qs(url.query)
            if rota == "/saude":
                self._enviar(200, b"ok", "text/plain; charset=utf-8")
                return
            base_nova = os.environ.get(cfg.prefixo + "URL", "").strip().rstrip("/")
            if host in cfg.hosts_legados and metodo in ("GET", "HEAD") and base_nova.startswith("https://") and (urlparse(base_nova).hostname or "") not in cfg.hosts_legados:
                self._ir(base_nova + self.path, status=301)   # endereço antigo: 301 para o novo (só quando o novo está configurado em <PREFIXO>URL)
                return
            sess = None
            try:
                if rota == "/entrar":
                    self._entrar(metodo)
                    return
                if metodo == "GET" and rota in cfg.publicas:
                    r_p = cfg.publicas[rota](q)
                    self._pagina(200, r_p[0], r_p[1], None, rota, r_p[2] if len(r_p) > 2 else "")
                    return
                if metodo == "POST" and rota in cfg.publicas_post:
                    n_p = min(int(self.headers.get("Content-Length") or 0), 8192)
                    campos_p = {k: v[0] for k, v in parse_qs(self.rfile.read(n_p).decode("utf-8", "replace"), keep_blank_values=True).items()}
                    titulo_p, corpo_p = cfg.publicas_post[rota](campos_p)
                    self._pagina(200, titulo_p, corpo_p, None, rota)
                    return
                token, sess = self._sessao()
                if not sess:
                    self._ir("/entrar")
                    return
                if metodo == "GET" and rota in cfg.aliases:   # rota antiga: 301 para a canônica, mantendo os parâmetros
                    self._ir(cfg.aliases[rota] + (("?" + url.query) if url.query else ""), status=301)
                    return
                quem = sess.get("pessoa") or pessoas.DONO
                # Os dados (heimdall_banco) e a pessoa (heimdall_pessoas) mudam juntos: convidado nunca enxerga os dados do dono.
                with pessoas.definir(quem), (contextlib.nullcontext() if pessoas.e_dono(quem) else banco.da_pessoa(quem)):
                    if metodo == "POST":
                        self._post(rota, token, sess)
                    else:
                        sess["atual"] = self.path
                        self._get(rota, q, sess)
            except cfg.erro as ex:
                self._pagina(400, "Não foi possível", f'<p class="erro" role="alert">{e(ex)}</p><p>{design.botao(cfg.abas[0][1][0][0], "Voltar ao início")}</p>', sess)
            except Exception as ex:  # noqa: BLE001
                sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
                self._pagina(500, "Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p>', sess)

        def _entrar(self, metodo: str) -> None:
            if metodo == "GET":
                via_access = nuvem.entrada_por_access(self.headers, cfg.chave)
                if via_access:
                    self._enviar(200, nuvem.pagina_continuar(), extra=[self._cookie(via_access)])
                    return
                self._enviar(200, pg_entrar(cfg))
                return
            ip = self._ip()
            if nuvem.login_bloqueado(ip):
                self._enviar(429, pg_entrar(cfg, "Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
                return
            n = min(int(self.headers.get("Content-Length") or 0), 4096)
            campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
            senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
            passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
            if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
                nuvem.registrar_falha(ip)
                self._enviar(401, pg_entrar(cfg, "Senha ou código incorretos."))
                return
            token, _ = nuvem.nova_sessao()
            self._ir("/", [self._cookie(token)])

        def _get(self, rota: str, q: dict, sess: dict) -> None:
            ctx = Ctx(q, sess, rota)
            if rota == "/":
                self._ir(cfg.abas[0][1][0][0])
                return
            if rota == "/ajustes" and cfg.ajustes:
                self._ir(cfg.ajustes[0][0])
                return
            if rota == "/ajustes/ajuda":
                self._pagina(200, "Ajuda", ajuda.ajuda_do_servico(cfg.chave, design.base_ajuda()), sess, rota)
                return
            func = cfg.get.get(rota)
            if not func:
                self._pagina(404, "Página não encontrada", f'<p>Esta página não existe.</p><p>{design.botao(cfg.abas[0][1][0][0], "Voltar ao início")}</p>', sess, rota)
                return
            r = func(ctx)
            if isinstance(r, Arquivo):
                seguro = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in r.nome)[:100] or "arquivo"
                self._enviar(200, r.dados, r.tipo, [("Content-Disposition", f'attachment; filename="{seguro}"')])
                return
            titulo, corpo = r
            if rota in rotas_perguntar:
                corpo = com_perguntar(cfg, ctx, ctx.aviso() + corpo)
            else:
                corpo = ctx.aviso() + corpo
            self._pagina(200, titulo, corpo, sess, rota)

        def _post(self, rota: str, token: str, sess: dict) -> None:
            if rota not in cfg.post and rota not in ("/sair", "/perguntar"):
                self._pagina(405, "Não permitido", "<p>Esta ação não existe.</p>", sess)
                return
            tipo_c = self.headers.get("Content-Type", "")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            limite = cfg.max_post if not tipo_c.startswith("multipart/form-data") else int(os.environ.get(cfg.prefixo + "MAX_MB", "40")) * 1024 * 1024 + 65536
            if n < 0 or n > limite:
                self._pagina(413, "Pedido grande demais", '<p class="erro" role="alert">O envio passa do limite de tamanho.</p>', sess)
                return
            bruto = self.rfile.read(n)
            if tipo_c.startswith("multipart/form-data"):
                campos, arquivos = ler_multipart(tipo_c, bruto)
            else:
                campos, arquivos = {k: v[0] for k, v in parse_qs(bruto.decode("utf-8", "replace"), keep_blank_values=True).items()}, []
            if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
                self._pagina(403, "Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess)
                return
            ctx = Ctx({}, sess, rota)
            if rota == "/sair":
                nuvem.encerrar_sessao(token)
                self._ir("/entrar", [self._cookie("", apagar=True)])
                return
            if rota == "/perguntar":   # só consulta o modelo sobre os dados da tela; nada é alterado
                destino = campos.get("volta", "")
                if destino.split("?")[0] not in rotas_perguntar:
                    destino = cfg.abas[0][1][0][0]
                q_ = " ".join(campos.get("pergunta", "").split())[:300]
                if len(q_) >= 3 and cfg.contexto_perguntar:
                    dono = sess["csrf"]
                    ctx = Ctx({**parse_qs(urlparse(destino).query), "pergunta": [q_]}, sess, destino.split("?")[0])
                    contexto = cfg.contexto_perguntar(ctx)
                    perguntar.iniciar(dono, "pergunta", lambda: perguntar.guardar_resposta(dono, q_, perguntar.responder(contexto, q_, cfg.sistema_perguntar)), q_)
                self._ir(destino)
                return
            destino = cfg.post[rota](ctx, campos, arquivos) or cfg.abas[0][1][0][0]
            if isinstance(destino, Redirecionar):
                if destino.url.startswith("https://") and not any(c in destino.url for c in "\r\n"):
                    self._ir(destino.url)
                    return
                destino = "/"
            if not destino.startswith("/") or destino.startswith("//"):
                destino = "/"
            self._ir(destino)

    return Manipulador


def servir(cfg: Config) -> None:
    host_env = os.environ.get(cfg.prefixo + "HOST", "127.0.0.1")
    port = int(os.environ.get(cfg.porta_env, str(cfg.porta)))
    hosts_ok = {h.strip().lower() for h in os.environ.get(cfg.prefixo + "HOSTS", cfg.hosts).split(",") if h.strip()} | set(cfg.hosts_legados)
    if not (nuvem.SENHA_HASH and nuvem.TOTP_SEGREDO):
        sys.exit(f"Sem senha e código configurados o Heimdall {cfg.nome} não sobe. Rode: python3 heimdall_acesso.py --tudo")
    if cfg.ao_iniciar:
        cfg.ao_iniciar()
    srv = ThreadingHTTPServer((host_env, port), criar_manipulador(cfg, hosts_ok))
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall {cfg.nome} em http://{host_env}:{port} (sites permitidos: {', '.join(sorted(hosts_ok))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
