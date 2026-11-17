#!/usr/bin/env python3
"""Heimdall Finance (finance.heimdall-ai.tech): suas finanças em páginas de texto e tabelas, para leitor de tela.

Você importa extratos (OFX ou CSV) do banco e do cartão; o painel classifica os gastos por categoria com regras que você
ajusta, mostra o resumo do mês, os maiores gastos, a evolução mês a mês e avisa quando uma categoria dispara.

Privacidade: nada aqui chama a internet. O banco SQLite fica em dados_financas/ (fora do git) e os dados financeiros nunca vão
para a Cloudflare nem para modelo de fora. O Cloudflare só repassa as páginas, como nos outros painéis.

Segurança (mesmas camadas dos outros painéis):
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada com a senha e o código de 6 dígitos do Heimdall Cloud (ou o Cloudflare Access, se ligado).
  3. Limite de tentativas, sessão em cookie HttpOnly e SameSite=Strict, token CSRF em todo POST.
  4. Só atende os nomes de site permitidos (HEIMDALL_FINANCE_HOSTS) e manda cabeçalhos de segurança.
  5. Sem senha e sem código configurados, o servidor não sobe.

Variáveis opcionais no .env: HEIMDALL_FINANCE_PORT (8016), HEIMDALL_FINANCE_HOST (127.0.0.1),
HEIMDALL_FINANCE_HOSTS (finance.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_FINANCE_DIR (pasta do banco) e HEIMDALL_FINANCE_MAX_MB (8).
"""
import html
import os
import re
import secrets
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis deste servidor."""
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
        if not chave.startswith("HEIMDALL_FINANCE_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import financas_arquivos as fa  # noqa: E402
import financas_nucleo as fn  # noqa: E402
import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)

HOST = os.environ.get("HEIMDALL_FINANCE_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("HEIMDALL_FINANCE_PORT", "8016")))
except ValueError:
    PORT = 8016
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_FINANCE_HOSTS", "finance.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
DIR_DADOS = Path(os.environ.get("HEIMDALL_FINANCE_DIR") or (PROJECT_DIR / "dados_financas"))
try:
    MAX_ENVIO = int(float(os.environ.get("HEIMDALL_FINANCE_MAX_MB", "8")) * 1024 * 1024)
except ValueError:
    MAX_ENVIO = 8 * 1024 * 1024
COOKIE = nuvem.COOKIE
POR_PAGINA = 100
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

_con = None
_trava = threading.RLock()


def banco():
    global _con
    with _trava:
        if _con is None:
            DIR_DADOS.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(DIR_DADOS, 0o700)
            except OSError:
                pass
            caminho = DIR_DADOS / "financas.db"
            _con = fn.conectar(caminho)
            try:
                os.chmod(caminho, 0o600)
            except OSError:
                pass
        return _con


CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.6;max-width:62rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .4rem;font-size:1.25em}
table{border-collapse:collapse;width:100%;margin:.6rem 0}caption{text-align:left;font-weight:bold;padding:.3rem 0}
th,td{border:1px solid var(--linha);padding:.4rem .6rem;text-align:left;vertical-align:top}td.n,th.n{text-align:right;white-space:nowrap}
input[type=text],input[type=search],input[type=file],select{font-size:1em;padding:.5rem;margin:.3rem 0;max-width:28rem;width:100%}
button{margin:.3rem .3rem .3rem 0;padding:.5rem 1rem;font-size:1em}
.aviso{border:1px solid var(--linha);padding:.7rem;margin:1rem 0}.ok{border-left:6px solid #2e7d32}
form.linha{display:inline}.sub{color:inherit;opacity:.85}
"""

NAV = [("/", "Resumo"), ("/transacoes", "Transações"), ("/tendencias", "Tendências"), ("/importar", "Importar extrato"), ("/regras", "Regras")]


def pagina(titulo: str, corpo: str, sess: dict = None) -> bytes:
    nav = ""
    flash = ""
    if sess:
        itens = "".join(f'<li><a href="{u}">{e(t)}</a></li>' for u, t in NAV)
        nav = (f'<nav aria-label="Principal"><ul>{itens}<li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
        f = sess.get("flash")
        if f:
            sess["flash"] = None
            flash = f'<div class="aviso {"ok" if f[0] == "ok" else ""}" role="status">{e(f[1])}</div>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Finance</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Finance", nav)}'
            f'<main id="principal"><h1>{e(titulo)}</h1>{flash}{corpo}</main></body></html>').encode("utf-8")


def tabela(legenda: str, cabecalhos: list, linhas: list, numericas: set = None) -> str:
    num = numericas or set()

    def attr(i):
        return ' class="n"' if i in num else ""

    cab = "".join(f'<th scope="col"{attr(i)}>{e(c)}</th>' for i, c in enumerate(cabecalhos))
    corpo = "".join("<tr>" + "".join(f"<td{attr(i)}>{c}</td>" for i, c in enumerate(l)) + "</tr>" for l in linhas)
    return f"<table><caption>{e(legenda)}</caption><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>"


def seletor_mes(atual: str, rota: str = "/", extra: str = "") -> str:
    ms = fn.meses(banco())
    if not ms:
        return ""
    op = "".join(f'<option value="{e(m)}"{" selected" if m == atual else ""}>{e(fn.nome_mes(m))}</option>' for m in ms)
    return (f'<form method="get" action="{rota}"><label for="mes">Mês</label><select id="mes" name="mes">{op}</select>{extra}'
            '<button type="submit">Ver</button></form>')


def opcoes_categoria(sel: str = "", incluir_todas: bool = False) -> str:
    tp = fn.tipos(banco())
    nomes = sorted(tp, key=lambda n: (n == fn.SEM_CATEGORIA, tp[n] != "gasto", n))
    o = '<option value="">Todas</option>' if incluir_todas else ""
    return o + "".join(f'<option value="{e(n)}"{" selected" if n == sel else ""}>{e(n)}{" (não entra nas somas)" if tp[n] == "neutra" else ""}</option>' for n in nomes)


def pg_resumo(mes: str) -> tuple:
    ms = fn.meses(banco())
    if not ms:
        return "Resumo", ('<p>Ainda não há lançamentos. Comece importando o extrato do seu banco ou o da fatura do cartão (OFX ou CSV).</p>'
                          '<p><a href="/importar">Importar extrato</a></p>')
    if mes not in ms:
        mes = ms[0]
    r = fn.resumo_mes(banco(), mes)
    dif = ""
    if r["despesas_anterior"]:
        v = round(100 * (r["despesas"] - r["despesas_anterior"]) / r["despesas_anterior"])
        dif = f' Isso é {abs(v)}% {"a mais" if v > 0 else "a menos"} que em {fn.nome_mes(fn.mes_anterior(mes))} ({fn.brl(r["despesas_anterior"])}).' if v else " Igual ao mês anterior."
    corpo = [seletor_mes(mes)]
    corpo.append(f'<p>Em {e(fn.nome_mes(mes))}: receitas de {e(fn.brl(r["receitas"]))}, despesas de {e(fn.brl(r["despesas"]))} e saldo de {e(fn.brl(r["saldo"], True))}.{e(dif)}</p>')
    if r["neutros"]:
        corpo.append(f'<p class="sub">Ficaram fora das somas {e(fn.brl(r["neutros"]))} em pagamento de fatura, investimentos e transferências entre suas contas, para não contar duas vezes.</p>')
    if r["sem_categoria"]:
        corpo.append(f'<div class="aviso" role="status">{r["sem_categoria"]} lançamento(s) sem categoria neste mês. '
                     f'<a href="/transacoes?mes={e(mes)}&amp;cat={e(fn.SEM_CATEGORIA)}">Classificar agora</a></div>')
    linhas = []
    for c in r["categorias"]:
        var = "sem gasto no mês anterior" if c["variacao"] is None else (f'{c["variacao"]:+d}%' if c["variacao"] else "igual")
        linhas.append([f'<a href="/transacoes?mes={e(mes)}&amp;cat={e(c["categoria"])}">{e(c["categoria"])}</a>', e(fn.brl(c["total"])), f'{c["pct"]:.1f}%'.replace(".", ","), e(var)])
    corpo.append("<h2>Gastos por categoria</h2>" + (tabela(f"Gastos por categoria em {fn.nome_mes(mes)}", ["Categoria", "Total", "Parte das despesas", "Variação sobre o mês anterior"], linhas, {1, 2}) if linhas else "<p>Sem despesas neste mês.</p>"))
    mx = [[e(fn.data_br(m["data"])), e(m["descricao"]), e(m["categoria"]), e(fn.brl(-m["valor"])), e(m["conta"])] for m in r["maiores"]]
    corpo.append("<h2>Maiores gastos</h2>" + (tabela(f"Dez maiores gastos de {fn.nome_mes(mes)}", ["Data", "Descrição", "Categoria", "Valor", "Conta"], mx, {3}) if mx else "<p>Sem despesas neste mês.</p>"))
    return "Resumo", "".join(corpo)


def pg_transacoes(q: dict, sess: dict) -> tuple:
    mes, cat, busca = (q.get("mes") or [""])[0], (q.get("cat") or [""])[0], (q.get("q") or [""])[0][:80]
    conta, produto = (q.get("conta") or [""])[0][:80], (q.get("produto") or [""])[0][:20]
    try:
        pg = max(0, int((q.get("pg") or ["0"])[0]))
    except ValueError:
        pg = 0
    total, linhas = fn.listar(banco(), mes, cat, busca, POR_PAGINA, pg * POR_PAGINA, conta, produto)
    soma = fn.somas_listagem(banco(), mes, cat, busca, conta, produto)
    contas, produtos = fn.contas_e_produtos(banco())
    opconta = '<option value="">Todas</option>' + "".join(f'<option value="{e(c)}"{" selected" if c == conta else ""}>{e(c)} ({n})</option>' for c, n in contas)
    opprod = '<option value="">Todos</option>' + "".join(f'<option value="{e(k)}"{" selected" if k == produto else ""}>{e(fn.PRODUTOS[k])} ({n})</option>' for k, n in produtos)
    ms = fn.meses(banco())
    opmes = '<option value="">Todos</option>' + "".join(f'<option value="{e(m)}"{" selected" if m == mes else ""}>{e(fn.nome_mes(m))}</option>' for m in ms)
    filtro = ('<form method="get" action="/transacoes"><label for="mes">Mês</label><select id="mes" name="mes">' + opmes + '</select>'
              f'<label for="conta">Conta (banco e tipo)</label><select id="conta" name="conta">{opconta}</select>'
              f'<label for="produto">Produto</label><select id="produto" name="produto">{opprod}</select>'
              f'<label for="cat">Categoria</label><select id="cat" name="cat">{opcoes_categoria(cat, True)}</select>'
              f'<label for="q">Buscar na descrição</label><input id="q" name="q" type="search" value="{e(busca)}"><button type="submit">Filtrar</button></form>')
    inline = cat == fn.SEM_CATEGORIA
    rows = []
    for t in linhas:
        if inline:
            acao = (f'<form method="post" action="/transacao/{t["id"]}"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
                    f'<input type="hidden" name="volta" value="{e(mes)}"><label for="c{t["id"]}">Categoria de {e(t["descricao"][:40])}</label>'
                    f'<select id="c{t["id"]}" name="categoria">{opcoes_categoria()}</select><button type="submit">Salvar</button></form>')
        else:
            acao = f'<a href="/transacao/{t["id"]}">Alterar categoria</a>'
        rows.append([e(fn.data_br(t["data"])), e(t["descricao"]), e(fn.brl(t["valor"], True)), e(t["categoria"]) + (" (manual)" if t["manual"] else ""), e(t["conta"]), e(fn.PRODUTOS.get(t["produto"], "")), acao])
    corpo = [filtro, f"<p>{total} lançamento(s) encontrado(s). Entradas: {e(fn.brl(soma['entradas']))}. Saídas: {e(fn.brl(soma['saidas']))}. Saldo do filtro: {e(fn.brl(soma['liquido'], True))}.</p>"]
    if rows:
        corpo.append(tabela("Lançamentos", ["Data", "Descrição", "Valor", "Categoria", "Conta", "Produto", "Ação"], rows, {2}))
    qs = f"mes={e(mes)}&amp;cat={e(cat)}&amp;q={e(busca)}&amp;conta={e(conta)}&amp;produto={e(produto)}"
    nav = []
    if pg > 0:
        nav.append(f'<a href="/transacoes?{qs}&amp;pg={pg - 1}">Página anterior</a>')
    if (pg + 1) * POR_PAGINA < total:
        nav.append(f'<a href="/transacoes?{qs}&amp;pg={pg + 1}">Próxima página</a>')
    corpo.append(f'<p>{" | ".join(nav)}</p>' if nav else "")
    corpo.append('<p><a href="/exportar.csv">Baixar tudo em CSV</a></p>')
    return "Transações", "".join(corpo)


def pg_transacao(tid: int, sess: dict):
    r = banco().execute("SELECT * FROM transacoes WHERE id=?", (tid,)).fetchone()
    if not r:
        return None
    corpo = (f'<p>{e(fn.data_br(r["data"]))}, {e(r["descricao"])}, {e(fn.brl(r["valor"], True))}, conta {e(r["conta"])}. Categoria atual: {e(r["categoria"])}.</p>'
             f'<form method="post" action="/transacao/{tid}"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
             f'<label for="categoria">Nova categoria</label><select id="categoria" name="categoria">{opcoes_categoria(r["categoria"])}</select>'
             '<label><input type="checkbox" name="regra" value="1" checked> Criar regra e aplicar aos lançamentos parecidos que você ainda não mexeu</label>'
             '<button type="submit">Salvar</button></form>'
             f'<p class="sub">Trecho que a regra usaria: {e(fn.padrao_da_descricao(r["desc_norm"]) or "(nenhum, só este lançamento muda)")}</p>'
             '<p><a href="/transacoes">Voltar às transações</a></p>')
    return "Alterar categoria", corpo


def pg_tendencias() -> tuple:
    t = fn.tendencias(banco(), 12)
    if not t["meses"]:
        return "Tendências", '<p>Importe pelo menos um extrato para ver a evolução.</p><p><a href="/importar">Importar extrato</a></p>'
    corpo = []
    if t["alertas"]:
        corpo.append('<div class="aviso" role="status"><h2>Atenção</h2><ul>' + "".join(f"<li>{e(a)}</li>" for a in t["alertas"]) + "</ul></div>")
    corpo.append(f'<p>Média de despesas por mês no período: {e(fn.brl(t["media_despesas"]))}.</p>')
    linhas = [[e(fn.nome_mes(l["mes"])), e(fn.brl(l["receitas"])), e(fn.brl(l["despesas"])), e(fn.brl(l["saldo"], True))] for l in reversed(t["linhas"])]
    corpo.append(tabela("Receitas, despesas e saldo por mês (do mais recente ao mais antigo)", ["Mês", "Receitas", "Despesas", "Saldo"], linhas, {1, 2, 3}))
    top = t["categorias"][:8]
    if top:
        cab = ["Mês"] + top
        lin = [[e(fn.nome_mes(l["mes"]))] + [e(fn.brl(l["cats"].get(c, 0))) for c in top] for l in reversed(t["linhas"])]
        corpo.append(tabela("Gasto por categoria em cada mês (as 8 categorias que mais pesam)", cab, lin, set(range(1, len(cab)))))
    return "Tendências", "".join(corpo)


def pg_importar(sess: dict) -> tuple:
    imp = banco().execute("SELECT * FROM importacoes ORDER BY id DESC LIMIT 10").fetchall()
    hist = ""
    if imp:
        hist = "<h2>Últimas importações</h2>" + tabela("Últimas importações", ["Quando", "Arquivo", "Conta", "Formato", "Novas", "Repetidas"],
                                                         [[e(i["quando"]), e(i["arquivo"]), e(i["conta"]), e(i["formato"]), str(i["novas"]), str(i["repetidas"])] for i in imp], {4, 5})
    pend = fa.pendentes(DIR_DADOS)
    if pend:
        hist += "<h2>Arquivos para revisar</h2>" + tabela("Arquivos para revisar", ["Arquivo", "Motivo"], [[e(n), e(m)] for n, m in pend])
    corpo = ('<p>Aceita OFX (a maioria dos bancos oferece em "exportar extrato"), CSV com colunas de data, descrição e valor e PDF de extrato ou de fatura. '
             'O banco e o tipo (conta ou cartão) são identificados pelo conteúdo e pelo nome do arquivo; se você deixar o nome da conta em branco, uso o que eu identificar. '
             'Importar o mesmo arquivo de novo não duplica nada: lançamentos já vistos são pulados.</p>'
             f'<form method="post" action="/importar" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
             '<label for="arquivo">Arquivo do extrato ou da fatura</label><input id="arquivo" name="arquivo" type="file" accept=".ofx,.csv,.txt,.pdf" required>'
             '<label for="conta">Nome da conta ou do cartão (por exemplo: Itaú conta, Nubank cartão). Deixe em branco para eu identificar.</label><input id="conta" name="conta" type="text" maxlength="60">'
             '<label><input type="checkbox" name="inverter" value="1"> Neste CSV os gastos vêm com valor positivo (comum em fatura de cartão)</label>'
             '<label><input type="checkbox" name="forcar" value="1"> Importar o PDF mesmo que o total do documento não confira com os lançamentos (só depois de revisar)</label>'
             '<button type="submit">Importar</button></form>'
             '<p class="sub">Dica: extrato de conta e fatura de cartão devem ser importados com nomes de conta diferentes. O pagamento da fatura na conta vira "Pagamento de fatura" e não conta como despesa, porque os gastos já aparecem na fatura. '
             'Você também pode soltar os arquivos na pasta de entrada (heimdall finance --folder): o Heimdall importa sozinho o que conferir e separa o que deixar dúvida.</p>' + hist)
    return "Importar extrato", corpo


def pg_regras(sess: dict) -> tuple:
    rs = banco().execute("SELECT * FROM regras ORDER BY (origem='usuario') DESC, categoria, padrao").fetchall()
    meu = [[e(r["padrao"]), e(r["categoria"]),
            f'<form method="post" action="/regras/apagar"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><input type="hidden" name="id" value="{r["id"]}">'
            f'<button type="submit" aria-label="Apagar a regra {e(r["padrao"])}">Apagar</button></form>'] for r in rs if r["origem"] == "usuario"]
    padrao = [[e(r["padrao"].strip()), e(r["categoria"])] for r in rs if r["origem"] != "usuario"]
    corpo = [('<p>Uma regra diz: se a descrição do lançamento tem este trecho (no início de uma palavra, sem acento e sem diferenciar maiúsculas), a categoria é esta. '
              'As suas regras vencem as padrão. Lançamentos que você categorizou à mão nunca são mudados por regras.</p>'
              f'<form method="post" action="/regras"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
              '<label for="padrao">Trecho da descrição</label><input id="padrao" name="padrao" type="text" maxlength="60" required>'
              f'<label for="cat">Categoria</label><select id="cat" name="categoria">{opcoes_categoria()}</select><button type="submit">Adicionar regra</button></form>')]
    corpo.append("<h2>Suas regras</h2>" + (tabela("Suas regras", ["Trecho", "Categoria", "Ação"], meu) if meu else "<p>Você ainda não criou regras. Ao alterar a categoria de um lançamento, a regra nasce sozinha.</p>"))
    corpo.append("<h2>Regras padrão</h2>" + tabela("Regras padrão", ["Trecho", "Categoria"], padrao))
    return "Regras de categoria", "".join(corpo)


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


CSP_PAGINA = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"


class Finance(BaseHTTPRequestHandler):
    server_version = "HeimdallFinance"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # nunca registra parâmetros nem corpo
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
        return token, nuvem.sessao_valida(token, "finance")

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        return nuvem.cabecalho_cookie(token, self.headers.get("Host", ""), self._https(), apagar)

    def _corpo(self, limite: int) -> bytes:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > limite:
            raise OverflowError
        return self.rfile.read(n)

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
        u = urlparse(self.path)
        rota, q = u.path, parse_qs(u.query)
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
            with _trava:
                if metodo == "POST":
                    self._post(rota, token, sess)
                else:
                    self._get(rota, q, sess)
        except OverflowError:
            self._enviar(413, pagina("Arquivo grande demais", f"<p>O limite é de {MAX_ENVIO // (1024 * 1024)} MB por arquivo.</p>", sess))
        except fn.ErroFinance as ex:
            if sess:
                sess["flash"] = ("erro", str(ex))
            self._ir("/importar" if rota == "/importar" else "/regras" if rota.startswith("/regras") else "/transacoes")
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    def _get(self, rota: str, q: dict, sess: dict) -> None:
        if rota == "/":
            titulo, corpo = pg_resumo((q.get("mes") or [""])[0])
        elif rota == "/transacoes":
            titulo, corpo = pg_transacoes(q, sess)
        elif rota == "/tendencias":
            titulo, corpo = pg_tendencias()
        elif rota == "/importar":
            titulo, corpo = pg_importar(sess)
        elif rota == "/regras":
            titulo, corpo = pg_regras(sess)
        elif rota == "/exportar.csv":
            self._enviar(200, fn.exportar_csv(banco()).encode("utf-8-sig"), "text/csv; charset=utf-8",
                         [("Content-Disposition", 'attachment; filename="heimdall-finance.csv"')])
            return
        else:
            m = re.fullmatch(r"/transacao/(\d{1,9})", rota)
            r = pg_transacao(int(m.group(1)), sess) if m else None
            if not r:
                self._enviar(404, pagina("Não encontrei", '<p><a href="/">Voltar ao resumo</a></p>', sess))
                return
            titulo, corpo = r
        self._enviar(200, pagina(titulo, corpo, sess))

    def _post(self, rota: str, token: str, sess: dict) -> None:
        tipo = self.headers.get("Content-Type", "")
        campos, arquivos = nuvem._formulario(self._corpo(MAX_ENVIO + 65536 if rota == "/importar" else 16384), tipo)
        if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
            self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
            return
        if rota == "/sair":
            nuvem.encerrar_sessao(token)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        if rota == "/importar":
            arq = arquivos.get("arquivo")
            if not arq or not arq[1]:
                raise fn.ErroFinance("Escolha o arquivo do extrato.")
            if len(arq[1]) > MAX_ENVIO:
                raise OverflowError
            r = fa.importar_arquivo(banco(), arq[1], arq[0], campos.get("conta", ""), campos.get("forcar") == "1",
                                    True if campos.get("inverter") == "1" else None)
            sess["flash"] = ("ok", f"Importado ({r['formato']}) na conta {r['conta']}: {r['lidas']} lançamentos lidos, {r['novas']} novos e {r['repetidas']} já existentes.")
            self._ir("/")
            return
        m = re.fullmatch(r"/transacao/(\d{1,9})", rota)
        if m:
            veio_da_lista = "volta" in campos
            n = fn.definir_categoria(banco(), int(m.group(1)), campos.get("categoria", ""), veio_da_lista or campos.get("regra") == "1")
            sess["flash"] = ("ok", f"Categoria salva. {n} lançamento(s) atualizado(s).")
            if veio_da_lista:
                mes = campos["volta"] if re.fullmatch(r"\d{4}-\d{2}", campos["volta"]) else ""
                self._ir("/transacoes?cat=Sem%20categoria" + (f"&mes={mes}" if mes else ""))
            else:
                self._ir("/transacoes")
            return
        if rota == "/regras":
            n = fn.adicionar_regra(banco(), campos.get("padrao", ""), campos.get("categoria", ""))
            sess["flash"] = ("ok", f"Regra salva. {n} lançamento(s) reclassificado(s).")
            self._ir("/regras")
            return
        if rota == "/regras/apagar":
            try:
                ok = fn.apagar_regra(banco(), int(campos.get("id", "0")))
            except ValueError:
                ok = False
            if ok:
                n = fn.reaplicar_regras(banco())
                sess["flash"] = ("ok", f"Regra apagada. {n} lançamento(s) reclassificado(s).")
            self._ir("/regras")
            return
        self._enviar(405, pagina("Não permitido", "<p>Pedido não reconhecido.</p>", sess))

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            via_access = nuvem.entrada_por_access(self.headers, "finance")  # aprovado no Cloudflare Access (Microsoft Authenticator), se ligado
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
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])


def _vigiar_entrada() -> None:
    """A cada minuto importa o que foi solto em dados_financas/entrada. Só registra o nome do arquivo, nunca os valores."""
    fa.preparar_pasta(DIR_DADOS)
    while True:
        try:
            with _trava:
                for r in fa.processar_entrada(banco(), DIR_DADOS):
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} entrada: {r['arquivo']} -> " + (f"{r['conta']} ({r['novas']} novos)" if r["ok"] else "para revisar") + "\n")
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} entrada: erro {type(ex).__name__}\n")
        time.sleep(60)


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o Heimdall Finance não sobe. Rode: python3 heimdall_acesso.py --tudo")
    banco()
    threading.Thread(target=_vigiar_entrada, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Finance)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Finance em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))}; dados em {DIR_DADOS})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
