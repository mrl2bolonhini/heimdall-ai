#!/usr/bin/env python3
"""Heimdall Learn: site de estudos. Fase 1: pastas com categoria e tipo, e importação de documentos.

As pastas ficam em knowledge/ (a mesma pasta de documentos do resto do Heimdall) e são cadastradas no banco próprio do Learn
(db/learn.db). Cada pasta tem uma CATEGORIA (aleatório ou sequencial) e um TIPO aberto (idiomas, programação, filosofia, medicina...).
A IA combina categoria, tipo e material para decidir como estudar (fases seguintes: perguntas aleatórias, lições, voz, cards).

Segurança: escuta só em 127.0.0.1; mesmo login do painel Cloud (senha, código de 6 dígitos ou Cloudflare Access); CSRF em todo POST;
sessão em cookie HttpOnly; só nomes de site permitidos; caminhos conferidos contra fuga de pasta; arquivos só com extensão
conhecida, nome simples e limite de tamanho (HEIMDALL_LEARN_MAX_MB, 50); HTML sempre escapado.

Variáveis: HEIMDALL_LEARN (1 liga; padrão 0, o start_heimdall.sh só sobe com 1), HEIMDALL_LEARN_PORT (8019), HEIMDALL_LEARN_HOST (127.0.0.1),
HEIMDALL_LEARN_HOSTS (learn.heimdall-ai.tech,localhost,127.0.0.1).

    python3 heimdall_learn.py

Usa só a biblioteca padrão do Python.
"""
import html
import os
import re
import secrets
import sys
import time
from email import message_from_bytes
from email.policy import HTTP
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
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
        if not (chave.startswith("HEIMDALL_LEARN_") or chave in ("HEIMDALL_KNOWLEDGE_DIR", "HEIMDALL_DB_DIR")):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_cloud as nuvem  # noqa: E402  (login e sessões: o mesmo do painel Cloud)
import heimdall_design as design  # noqa: E402
import heimdall_learn_dados as dados  # noqa: E402
import heimdall_learn_estudo as estudo  # noqa: E402
import heimdall_learn_tipos as tipos  # noqa: E402
import heimdall_perguntar as perguntar  # noqa: E402  (tarefas em segundo plano do modelo)

HOST = os.environ.get("HEIMDALL_LEARN_HOST", "127.0.0.1")
PORT = int(os.environ.get("HEIMDALL_LEARN_PORT", "8019"))
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_LEARN_HOSTS", "learn.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
COOKIE = nuvem.COOKIE
NAV = [("/", "Início"), ("/nova", "Nova pasta"), ("/tipos", "Tipos")]
MAX_FORM = 20000
ESTADOS = {"sorteado": "gerando a pergunta", "perguntado": "aguardando a resposta", "corrigindo": "corrigindo", "corrigido": "concluído",
           "erro": "erro na pergunta", "erro_correcao": "erro na correção"}
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.7;max-width:50rem}main{overflow-wrap:anywhere}
.meta{color:var(--suave);font-size:.9em}.lista{list-style:none;padding:0}.lista li{border-bottom:1px solid var(--linha);padding:.6rem 0}
form.campos label{display:block;margin-top:.9rem;font-weight:700}form.campos input[type=text],form.campos select,form.campos input[type=file]{display:block;width:100%;max-width:30rem}
"""


def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def pagina(titulo: str, corpo: str, sess: dict = None, nonce: str = "") -> bytes:
    nav = sair = abas_js = ""
    conteudo = f"<h1>{e(titulo)}</h1>{corpo}"
    if sess:
        atual = urlparse(str(sess.get("atual", "/"))).path
        atual = atual if atual in ("/nova", "/tipos") else "/"
        nav = design.nav_abas(NAV, atual, "Seções do Heimdall Learn")
        sair = f'<form class="linha" method="post" action="/sair"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form>'
        conteudo = design.com_abas(NAV, atual, conteudo)
        abas_js = design.SCRIPT_ABAS + design.SCRIPT_DETALHES
    js = f'<script nonce="{e(nonce)}">{abas_js}</script>' if abas_js and nonce else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Learn</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'{design.topo()}<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Learn", nav, sair_html=sair)}'
            f'<main id="principal">{conteudo}</main>{design.rodape()}{js}</body></html>').encode("utf-8")


def aviso(sess: dict) -> str:
    f = sess.get("flash")
    if not f:
        return ""
    sess["flash"] = None
    tipo, texto = f
    papel = "alert" if tipo == "erro" else "status"
    return f'<p class="{"erro" if tipo == "erro" else "ok"}" role="{papel}">{e(texto)}</p>'


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


def _lista_pastas(itens: list) -> str:
    if not itens:
        return '<p role="status">Nenhuma pasta ainda.</p>'
    linhas = "".join(
        f'<tr><th scope="row"><a href="/pasta?c={quote(p["caminho"])}">{e(p["nome"])}</a></th><td>{e(p["categoria_nome"])}</td>'
        f'<td>{e(p["tipo"] or "sem tipo")}{(" (" + e(p["idioma"]) + ")") if p.get("idioma") else ""}</td>'
        f'<td>{p["documentos"]}</td><td>{p["subpastas"]}</td></tr>' for p in itens)
    return ('<table><caption>Pastas de estudo</caption><thead><tr><th scope="col">Pasta</th><th scope="col">Categoria</th><th scope="col">Tipo</th>'
            f'<th scope="col">Documentos</th><th scope="col">Subpastas</th></tr></thead><tbody>{linhas}</tbody></table>')


def pg_inicio(sess: dict) -> str:
    r = dados.resumo()
    cats = "".join(f"<li><strong>{e(n)}</strong>: {e(d)}</li>" for n, d in dados.CATEGORIAS.values())
    return (aviso(sess) + f'<p role="status">{plural(r["pastas"], "pasta", "pastas")} e {plural(r["documentos"], "documento", "documentos")}.</p>'
            + _lista_pastas(dados.listar_pastas("")) + f'<h2>Categorias</h2><ul>{cats}</ul>'
            '<p class="meta">Fase 1: organizar pastas e importar material. Perguntas, lições, voz e cards vêm nas próximas fases.</p>')


def _opcoes_tipo(atual: str = "") -> str:
    ops = '<option value="">Escolha um tipo</option>' + "".join(
        f'<option value="{e(t)}"{" selected" if t == atual else ""}>{e(t)}</option>' for t in dados.listar_tipos())
    return ops


def _opcoes_categoria(atual: str = "") -> str:
    return "".join(f'<option value="{e(k)}"{" selected" if k == atual else ""}>{e(v[0])}</option>' for k, v in dados.CATEGORIAS.items())


def pg_nova(sess: dict, pai: str = "") -> str:
    csrf = sess["csrf"]
    pais = "".join(f'<option value="{e(p["caminho"])}"{" selected" if p["caminho"] == pai else ""}>{e(p["caminho"])}</option>' for p in dados.arvore_plana())
    return (aviso(sess) +
            f'<form class="campos" method="post" action="/criar"><input type="hidden" name="csrf" value="{e(csrf)}">'
            '<label for="nome">Nome da pasta</label><input id="nome" name="nome" type="text" maxlength="80" required>'
            f'<label for="pai">Dentro de</label><select id="pai" name="pai"><option value="">Raiz do Learn</option>{pais}</select>'
            f'<label for="categoria">Categoria</label><select id="categoria" name="categoria"><option value="">Sugerida pelo tipo</option>{_opcoes_categoria()}</select>'
            f'<label for="tipo">Tipo</label><select id="tipo" name="tipo">{_opcoes_tipo()}</select>'
            '<label for="tipo_novo">Ou um tipo novo</label><input id="tipo_novo" name="tipo_novo" type="text" maxlength="40">'
            '<label for="idioma">Idioma de estudo (só para o tipo Idiomas)</label><input id="idioma" name="idioma" type="text" maxlength="40">'
            '<p class="meta">Em subpasta, categoria, tipo e idioma em branco herdam da pasta de cima.</p>'
            '<button type="submit">Criar pasta</button></form>')


def pg_pasta(sess: dict, rel: str) -> str:
    p = dados.obter_pasta(rel)
    if not p:
        raise dados.ErroLearn("Pasta não encontrada.")
    csrf = sess["csrf"]
    docs = dados.listar_documentos(rel)
    linhas = "".join(f'<tr><th scope="row">{e(d["nome"])}</th><td>{d["bytes"] // 1024 + 1} KB</td><td>{e(d["alterado"])}</td></tr>' for d in docs)
    tabela = (f'<table><caption>Documentos da pasta</caption><thead><tr><th scope="col">Arquivo</th><th scope="col">Tamanho</th><th scope="col">Alterado</th></tr></thead><tbody>{linhas}</tbody></table>'
              if docs else '<p role="status">Nenhum documento nesta pasta.</p>')
    sub = dados.listar_pastas(rel)
    subs = f'<h2>Subpastas</h2>{_lista_pastas(sub)}' if sub else ""
    cab = (f'<p>Categoria: <strong>{e(p["categoria_nome"])}</strong>. Tipo: <strong>{e(p["tipo"] or "sem tipo")}</strong>'
           f'{(". Idioma: <strong>" + e(p["idioma"]) + "</strong>") if p.get("idioma") else ""}.</p>')
    form_imp = (f'<h2>Importar documento</h2><form class="campos" method="post" action="/importar" enctype="multipart/form-data">'
                f'<input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="c" value="{e(rel)}">'
                '<label for="arquivo">Arquivo (PDF, Markdown, texto, Word, EPUB, M4A ou MP3)</label><input id="arquivo" name="arquivo" type="file" required>'
                '<button type="submit">Importar</button></form>')
    form_ed = (f'<h2>Mudar categoria e tipo</h2><form class="campos" method="post" action="/atualizar"><input type="hidden" name="csrf" value="{e(csrf)}">'
               f'<input type="hidden" name="c" value="{e(rel)}">'
               f'<label for="categoria">Categoria</label><select id="categoria" name="categoria">{_opcoes_categoria(p["categoria"])}</select>'
               f'<label for="tipo">Tipo</label><select id="tipo" name="tipo">{_opcoes_tipo(p["tipo"])}</select>'
               f'<label for="idioma">Idioma de estudo</label><input id="idioma" name="idioma" type="text" maxlength="40" value="{e(p.get("idioma") or "")}">'
               '<button type="submit">Salvar</button></form>')
    estudar = ""
    if p["categoria"] == "aleatorio":
        estudar = ('<h2>Estudar</h2><p>O Learn sorteia um trecho do material desta pasta e faz uma pergunta. Depois da sua resposta, corrige com base no trecho, '
                   'mostra o trecho, grava o áudio e sugere matérias.</p>' + design.botao_post("/sortear", "Sortear trecho e perguntar", csrf, {"c": rel}))
        hist = estudo.historico(rel, 10)
        if hist:
            itens = "".join(f'<tr><th scope="row"><a href="/estudo?id={h["id"]}">Estudo {h["id"]}</a></th><td>{e(h["criado"])}</td><td>{e(Path(h["documento"]).name)}</td>'
                            f'<td>{e(ESTADOS.get(h["estado"], h["estado"]))}</td></tr>' for h in hist)
            estudar += ('<table><caption>Últimos estudos desta pasta</caption><thead><tr><th scope="col">Estudo</th><th scope="col">Quando</th><th scope="col">Documento</th>'
                        f'<th scope="col">Situação</th></tr></thead><tbody>{itens}</tbody></table>')
    elif p["categoria"] == "sequencial":
        estudar = '<h2>Estudar</h2><p role="status">As lições em sequência chegam na próxima fase. Por enquanto, esta pasta guarda o material.</p>'
    novo = design.botao("/nova", "Criar subpasta aqui", {"pai": rel})
    voltar = design.botao("/", "Voltar ao início")
    return aviso(sess) + cab + estudar + tabela + subs + novo + form_imp + form_ed + voltar


def pg_tipos(sess: dict) -> str:
    csrf = sess["csrf"]
    linhas = ""
    for t in dados.listar_tipos():
        p = tipos.perfil(t)
        linhas += (f'<tr><th scope="row">{e(t)}</th><td>{e(dados.CATEGORIAS[p["categoria"]][0])}</td><td>{e(p["resumo"])}</td></tr>')
    detalhes = ""
    for t in dados.listar_tipos():
        p = tipos.perfil(t)
        detalhes += (f'<details><summary>{e(t)}: o que a IA faz</summary><p><strong>Faz:</strong></p><ol>' + "".join(f"<li>{e(x)}</li>" for x in p["faz"])
                     + '</ol><p><strong>Evita:</strong></p><ol>' + "".join(f"<li>{e(x)}</li>" for x in p["evita"]) + "</ol>"
                     + (f'<p><strong>Em breve:</strong> {e(p["depois"])}</p>' if p["depois"] else "") + "</details>")
    return (aviso(sess) + '<p>Cada tipo traz regras próprias para a IA. Tipos que você cadastra usam o perfil genérico: a IA estuda o material e, se faltar contexto, pergunta.</p>'
            f'<table><caption>Tipos de estudo</caption><thead><tr><th scope="col">Tipo</th><th scope="col">Categoria sugerida</th><th scope="col">Para quê</th></tr></thead><tbody>{linhas}</tbody></table>{detalhes}'
            f'<form class="campos" method="post" action="/tipo"><input type="hidden" name="csrf" value="{e(csrf)}">'
            '<label for="nome">Novo tipo de estudo</label><input id="nome" name="nome" type="text" maxlength="40" required>'
            '<button type="submit">Cadastrar tipo</button></form>')


def pg_estudo(sess: dict, id_: int) -> tuple:
    est = estudo.obter(id_)
    if not est:
        raise dados.ErroLearn("Estudo não encontrado.")
    csrf, rel = sess["csrf"], est["pasta"]
    pasta = dados.obter_pasta(rel) or {"nome": rel}
    st = est["estado"]
    topo = f'<p>Pasta: <a href="/pasta?c={quote(rel)}">{e(pasta["nome"])}</a>. Documento: {e(Path(est["documento"]).name)}.</p>'
    atualizar = design.botao("/estudo", "Atualizar", {"id": id_})
    repetir = design.botao_post("/repetir", "Tentar de novo", csrf, {"id": id_})
    corpo = aviso(sess) + topo
    if st == "sorteado":
        corpo += '<p role="status">Gerando a pergunta. O modelo local pode levar alguns minutos.</p>' + atualizar + repetir
    elif st == "erro":
        corpo += f'<p class="erro" role="alert">Não consegui gerar a pergunta: {e(est["erro"])}</p>' + repetir
    else:
        corpo += f'<h2>Pergunta</h2><p>{e(est["pergunta"])}</p>'
        if st == "perguntado":
            corpo += (f'<form class="campos" method="post" action="/responder"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="id" value="{id_}">'
                      '<label for="resposta">Sua resposta</label><textarea id="resposta" name="resposta" rows="6" maxlength="4000" required></textarea>'
                      '<button type="submit">Enviar resposta</button></form>')
        else:
            corpo += f'<h2>Sua resposta</h2><p>{e(est["resposta"])}</p>'
        if st == "corrigindo":
            corpo += '<p role="status">Corrigindo a resposta com base no trecho.</p>' + atualizar + repetir
        elif st == "erro_correcao":
            corpo += f'<p class="erro" role="alert">Não consegui corrigir: {e(est["erro"])}</p>' + repetir
        elif st == "corrigido":
            corpo += f'<h2>Correção</h2><p>{e(est["correcao"]).replace(chr(10), "<br>")}</p>'
            if est["sugestoes"]:
                itens = "".join(f"<li>{e(x.strip())}</li>" for x in re.split(r"[;\n]+", est["sugestoes"]) if x.strip())
                corpo += f'<h2>Matérias sugeridas</h2><ol>{itens}</ol>'
            corpo += f'<h2>Trecho consultado</h2><blockquote>{e(est["trecho"]).replace(chr(10), "<br>")}</blockquote>'
            if estudo.caminho_audio(id_):
                corpo += f'<h2>Áudio do trecho</h2><audio controls src="/audio?id={id_}" aria-label="Áudio do trecho consultado"></audio>'
            else:
                corpo += design.botao_post("/gravar", "Gravar áudio do trecho", csrf, {"id": id_})
    corpo += design.botao_post("/sortear", "Sortear outro trecho", csrf, {"c": rel}) + design.botao("/pasta", "Voltar à pasta", {"c": rel})
    return f"Estudo {id_}", corpo


def ler_multipart(tipo_conteudo: str, corpo: bytes) -> tuple:
    """(campos, arquivos) de um formulário multipart/form-data. arquivos: nome do campo -> (nome do arquivo, bytes)."""
    msg = message_from_bytes(b"Content-Type: " + tipo_conteudo.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + corpo, policy=HTTP)
    campos, arquivos = {}, {}
    if not msg.is_multipart():
        return campos, arquivos
    for parte in msg.iter_parts():
        nome = parte.get_param("name", header="content-disposition")
        if not nome:
            continue
        arq = parte.get_filename()
        carga = parte.get_payload(decode=True) or b""
        if arq is not None:
            arquivos[nome] = (arq, carga)
        else:
            campos[nome] = carga.decode("utf-8", "replace")
    return campos, arquivos


class Learn(nuvem.ManipuladorBase):
    server_version = "HeimdallLearn"
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
        self.send_header("Content-Security-Policy", f"default-src 'none'; img-src data:; style-src 'unsafe-inline';{script} media-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _pagina(self, status: int, titulo: str, corpo: str, sess: dict = None) -> None:
        nonce = secrets.token_urlsafe(12) if sess else ""
        self._enviar(status, pagina(titulo, corpo, sess, nonce), nonce=nonce)

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, nuvem.sessao_valida(token, "learn")

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
        url = urlparse(self.path)
        rota, q = url.path, parse_qs(url.query)
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
                self._post(rota, token, sess)
                return
            sess["atual"] = self.path
            self._get(rota, q, sess)
        except dados.ErroLearn as ex:
            self._pagina(400, "Não foi possível", f'<p class="erro" role="alert">{e(ex)}</p><p>{design.botao("/", "Voltar ao início")}</p>', sess)
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._pagina(500, "Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p>', sess)

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            via_access = nuvem.entrada_por_access(self.headers, "learn")
            if via_access:
                self._enviar(200, nuvem.pagina_continuar(), extra=[self._cookie(via_access)])
                return
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
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        self._ir("/", [self._cookie(token)])

    def _get(self, rota: str, q: dict, sess: dict) -> None:
        p = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        if rota == "/":
            dados.sincronizar()
            self._pagina(200, "Início", pg_inicio(sess), sess)
        elif rota == "/pasta":
            reg = dados.obter_pasta(p("c"))
            self._pagina(200, reg["nome"] if reg else "Pasta", pg_pasta(sess, p("c")), sess)
        elif rota == "/estudo":
            titulo, corpo = pg_estudo(sess, int(p("id") or 0))
            self._pagina(200, titulo, corpo, sess)
        elif rota == "/audio":
            arq = estudo.caminho_audio(int(p("id") or 0)) if p("id").isdigit() else None
            if not arq:
                self._pagina(404, "Não encontrei", "<p>Este áudio não existe.</p>", sess)
            else:
                self._servir(arq)
        elif rota == "/nova":
            self._pagina(200, "Nova pasta", pg_nova(sess, p("pai")), sess)
        elif rota == "/tipos":
            self._pagina(200, "Tipos de estudo", pg_tipos(sess), sess)
        else:
            self._pagina(404, "Não encontrei", '<p>Esta página não existe.</p><p><a href="/">Voltar ao início</a></p>', sess)

    def _post(self, rota: str, token: str, sess: dict) -> None:
        if rota not in ("/sair", "/criar", "/atualizar", "/tipo", "/importar", "/sortear", "/responder", "/repetir", "/gravar"):
            self._pagina(405, "Não permitido", "<p>Esta ação não existe.</p>", sess)
            return
        tipo_c = self.headers.get("Content-Type", "")
        limite = dados.max_bytes() + 65536 if rota == "/importar" else MAX_FORM
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > limite:
            self._pagina(413, "Pedido grande demais", f'<p class="erro" role="alert">O arquivo passa do limite de {dados.max_bytes() // (1024 * 1024)} MB.</p>', sess)
            return
        bruto = self.rfile.read(n)
        if rota == "/importar":
            campos, arquivos = ler_multipart(tipo_c, bruto)
        else:
            campos, arquivos = {k: v[0] for k, v in parse_qs(bruto.decode("utf-8", "replace"), keep_blank_values=True).items()}, {}
        if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
            self._pagina(403, "Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess)
            return
        if rota == "/sair":
            nuvem.encerrar_sessao(token)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        destino = "/"
        try:
            if rota == "/criar":
                tipo = campos.get("tipo_novo", "").strip() and dados.criar_tipo(campos["tipo_novo"]) or campos.get("tipo", "")
                r = dados.criar_pasta(campos.get("nome", ""), campos.get("categoria", ""), tipo, campos.get("idioma", ""), campos.get("pai", ""))
                sess["flash"] = ("ok", f"Pasta {r['nome']} criada.")
                destino = "/pasta?c=" + quote(r["caminho"])
            elif rota == "/atualizar":
                rel = campos.get("c", "")
                dados.atualizar_pasta(rel, campos.get("categoria", ""), campos.get("tipo", ""), campos.get("idioma", ""))
                sess["flash"] = ("ok", "Pasta atualizada.")
                destino = "/pasta?c=" + quote(rel)
            elif rota == "/sortear":
                rel = campos.get("c", "")
                if (dados.obter_pasta(rel) or {}).get("categoria") != "aleatorio":
                    raise dados.ErroLearn("Só pastas da categoria aleatório têm estudo por sorteio.")
                id_ = estudo.novo_estudo(rel)
                perguntar.iniciar(sess["csrf"], f"learn-p{id_}", lambda i=id_: estudo.gerar_pergunta(i), f"pergunta {id_}")
                destino = f"/estudo?id={id_}"
            elif rota in ("/responder", "/repetir", "/gravar"):
                id_ = int(campos.get("id", "0") or 0)
                est = estudo.obter(id_)
                if not est:
                    raise dados.ErroLearn("Estudo não encontrado.")
                destino = f"/estudo?id={id_}"
                if rota == "/responder":
                    if est["estado"] != "perguntado":
                        raise dados.ErroLearn("Este estudo não está esperando resposta.")
                    resp = campos.get("resposta", "")
                    if len(" ".join(resp.split())) < 2:
                        raise dados.ErroLearn("Escreva a sua resposta.")
                    perguntar.iniciar(sess["csrf"], f"learn-c{id_}", lambda: estudo.corrigir(id_, resp), f"correção {id_}")
                elif rota == "/repetir":
                    if est["estado"] in ("sorteado", "erro"):
                        perguntar.iniciar(sess["csrf"], f"learn-p{id_}", lambda: estudo.gerar_pergunta(id_), f"pergunta {id_}")
                    elif est["estado"] in ("corrigindo", "erro_correcao") and est["resposta"]:
                        perguntar.iniciar(sess["csrf"], f"learn-c{id_}", lambda: estudo.corrigir(id_, est["resposta"]), f"correção {id_}")
                else:
                    if est["estado"] != "corrigido":
                        raise dados.ErroLearn("O áudio é gravado depois da correção.")
                    motivo = estudo.gravar_audio(id_)
                    sess["flash"] = ("erro", "Áudio não gravado: " + motivo) if motivo else ("ok", "Áudio gravado.")
            elif rota == "/tipo":
                dados.criar_tipo(campos.get("nome", ""))
                sess["flash"] = ("ok", "Tipo cadastrado.")
                destino = "/tipos"
            elif rota == "/importar":
                rel = campos.get("c", "")
                destino = "/pasta?c=" + quote(rel)
                nome, conteudo = arquivos.get("arquivo", ("", b""))
                r = dados.importar_documento(rel, nome, conteudo)
                sess["flash"] = ("ok", f"Arquivo {r['arquivo']} importado.")
        except dados.ErroLearn as ex:
            sess["flash"] = ("erro", str(ex))
            if rota == "/criar":
                destino = "/nova"
            elif rota == "/tipo":
                destino = "/tipos"
        self._ir(destino)


def _servir_audio(self, arq: Path) -> None:
    """Entrega o m4a com suporte a Range (o Safari do iPhone exige para tocar áudio)."""
    total = arq.stat().st_size
    ini, fim, status = 0, total - 1, 200
    m = re.match(r"^bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
    if m and (m.group(1) or m.group(2)) and total > 0:
        if m.group(1):
            ini = int(m.group(1))
            fim = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
        else:
            ini = max(0, total - int(m.group(2)))
        if ini > fim or ini >= total:
            self._enviar(416, b"", extra=[("Content-Range", f"bytes */{total}")])
            return
        status = 206
    tamanho = max(0, fim - ini + 1)
    self.send_response(status)
    self.send_header("Content-Type", "audio/mp4")
    self.send_header("Content-Length", str(tamanho))
    self.send_header("Accept-Ranges", "bytes")
    if status == 206:
        self.send_header("Content-Range", f"bytes {ini}-{fim}/{total}")
    self.send_header("Cache-Control", "private, max-age=600")
    self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
    self.send_header("X-Content-Type-Options", "nosniff")
    self.end_headers()
    if self.command == "HEAD":
        return
    with arq.open("rb") as f:
        f.seek(ini)
        restante = tamanho
        while restante > 0:
            bloco = f.read(min(65536, restante))
            if not bloco:
                break
            try:
                self.wfile.write(bloco)
            except (BrokenPipeError, ConnectionResetError):
                return
            restante -= len(bloco)


Learn._servir = _servir_audio


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o Heimdall Learn não sobe. Rode: python3 heimdall_acesso.py --tudo")
    dados.sincronizar()
    srv = ThreadingHTTPServer((HOST, PORT), Learn)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Learn em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
