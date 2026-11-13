#!/usr/bin/env python3
"""Teste do Heimdall News (heimdall_news.py) com feeds e modelo de mentira, sem internet.

    python3 teste_news.py

Confere: leitura de RSS e Atom, tirar repetidas (links com rastreadores), links perigosos e matérias antigas fora, feed que tenta
usar entidades XML recusado sem derrubar as outras fontes, resumo por IA com limite por atualização e fila, tradução dos títulos
em inglês, leitura da matéria só quando o trecho é curto, modelo fora do ar sem gastar tentativas, saída do modelo fora do formato,
guarda contra endereços da rede interna, 30 dias no banco, site com login e código de 6 dígitos, 10 por página, categorias,
HTML escapado, RSS com chave secreta (geral, categoria e OPML), chave fora do log e troca da chave.
"""
import http.client
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

RAIZ = Path(tempfile.mkdtemp(prefix="news_teste_"))
SEGREDO = "JBSWY3DPEHPK3PXP"
SENHA = "senha-de-teste-123"
TOKEN = "chave-secreta-de-teste-0123456789"
CHAVE_LLM = "sk-teste-llm"
UTC = timezone.utc
AGORA = datetime.now(UTC)

ok_n, falhas = 0, []


def confere(nome: str, cond: bool, detalhe: str = "") -> None:
    global ok_n
    if cond:
        ok_n += 1
    else:
        falhas.append(nome)
        print("FALHOU:", nome, detalhe)


# ----------------------------------------------------------------------------------------
# Internet de mentira: feeds, matérias e o modelo
# ----------------------------------------------------------------------------------------
def rss(itens: list) -> str:
    corpo = ""
    for t, link, quando, desc in itens:
        corpo += f"<item><title>{t}</title><link>{link}</link><pubDate>{format_datetime(quando)}</pubDate><description><![CDATA[{desc}]]></description></item>"
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{corpo}</channel></rss>'


def atom(itens: list) -> str:
    corpo = ""
    for t, link, quando, desc in itens:
        corpo += (f'<entry><title>{t}</title><link rel="alternate" href="{link}"/><published>{quando.isoformat()}</published>'
                  f"<summary>{desc}</summary></entry>")
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title>{corpo}</feed>'


def h(minutos: int) -> datetime:
    return AGORA - timedelta(minutes=minutos)


MATERIA = ("<html><body><nav><p>Menu principal do site com muitos links de navegação que não deve entrar</p></nav>"
           "<p>O governo anunciou nesta quinta-feira uma nova medida para reduzir a fila de espera por consultas no sistema público de saúde.</p>"
           "<p>Segundo o ministério, a medida começa a valer no mês que vem e deve atingir três milhões de pessoas em todo o país.</p>"
           "<footer><p>Rodapé com texto longo de direitos autorais e termos de uso que também não deve entrar no resumo</p></footer></body></html>")
LONGO = "Este é um resumo longo que já veio no próprio feed. " * 10   # > 400 caracteres: não precisa abrir a matéria
SERVIDOR = {"feeds": {}, "pedidos": []}
LLM = {"modo": "ok", "pedidos": [], "chaves": []}


class Web(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        SERVIDOR["pedidos"].append(self.path)
        if self.path.startswith("/materia/"):
            self._resp(200, MATERIA.encode(), "text/html; charset=utf-8")
        elif self.path == "/img.png":
            self._resp(200, b"\x89PNG", "image/png")
        elif self.path in SERVIDOR["feeds"]:
            v = SERVIDOR["feeds"][self.path]
            if isinstance(v, int):
                self._resp(v, b"erro")
            else:
                self._resp(200, v.encode(), "application/xml")
        else:
            self._resp(404, b"nao")

    def _resp(self, st, corpo, tipo="text/plain"):
        self.send_response(st)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


class Modelo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        pedido = json.loads(self.rfile.read(n))
        LLM["chaves"].append(self.headers.get("Authorization", ""))
        usuario = pedido["messages"][1]["content"]
        LLM["pedidos"].append({"sistema": pedido["messages"][0]["content"], "usuario": usuario, "modelo": pedido["model"]})
        if LLM["modo"] == "fora":
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if LLM["modo"] == "lixo":
            conteudo = "Claro! Aqui está o resumo: a matéria fala de coisas."
        else:
            d = {"resumo": "Resumo de teste feito pelo modelo, com frases suficientes para passar na validação de tamanho mínimo."}
            if '"titulo_pt"' in usuario:
                d["titulo_pt"] = "Título traduzido para o português"
            conteudo = json.dumps(d, ensure_ascii=False)
            if LLM["modo"] == "pensa":
                conteudo = "<think>vou pensar</think>\n```json\n" + conteudo + "\n```"
        corpo = json.dumps({"choices": [{"message": {"content": conteudo}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


def servir(classe):
    s = ThreadingHTTPServer(("127.0.0.1", 0), classe)
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]


_, P_WEB = servir(Web)
_, P_LLM = servir(Modelo)
BASE = f"http://127.0.0.1:{P_WEB}"

# 14 notícias em português nas últimas 24 h (mais de uma página), mais as armadilhas
pt = [(f"Notícia número {i:02d} do dia", f"{BASE}/materia/{i}", h(10 + i), f"<p>Trecho curto {i}.</p> O post Notícia apareceu primeiro em Teste.") for i in range(14)]
pt.append(("Mesma matéria com rastreador", f"{BASE}/materia/0?utm_source=x&amp;utm_medium=y#topo", h(5), "<p>duplicada</p>"))
pt.append(("Link perigoso", "javascript:alert(1)", h(6), "<p>x</p>"))
pt.append(("Matéria velha demais", f"{BASE}/materia/velha", AGORA - timedelta(days=40), "<p>x</p>"))
pt.append(("Matéria de ontem à noite", f"{BASE}/materia/ontem", AGORA - timedelta(hours=30), "<p>fora das 24 horas</p>"))
pt.append(("Teste &amp;lt;b&amp;gt;negrito&amp;lt;/b&amp;gt; &amp;amp; \"aspas\"", f"{BASE}/materia/html", h(2),
           "<p>Texto com <script>alert(1)</script>marcação &lt;img src=x onerror=alert(1)&gt;.</p>"))
pt.append(("Do futuro", f"{BASE}/materia/futuro", AGORA + timedelta(days=3), "<p>data errada no feed</p>"))
en = [("Big news about data lakes", f"{BASE}/materia/en1", h(30), "Short."),
      ("A long English story", f"{BASE}/materia/en2", h(40), LONGO),
      ("Paper about graphs", f"{BASE}/materia/en3", h(50), "arXiv:2611.00001 Announce Type: new Abstract: " + LONGO)]
SERVIDOR["feeds"] = {
    "/pt.xml": rss(pt), "/en.xml": atom(en), "/morto.xml": 500,
    "/bomba.xml": '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title><link>http://x.test/1</link></item></channel></rss>',
}
FONTES = {"fontes": [
    {"categoria": "Brasil", "nome": "Fonte PT", "url": f"{BASE}/pt.xml", "idioma": "pt", "limite": 30},
    {"categoria": "Tecnologia", "nome": "Fonte EN", "url": f"{BASE}/en.xml", "idioma": "en", "limite": 10},
    {"categoria": "Ciência", "nome": "Fonte Morta", "url": f"{BASE}/morto.xml", "idioma": "pt"},
    {"categoria": "Ciência", "nome": "Fonte Bomba", "url": f"{BASE}/bomba.xml", "idioma": "pt"},
    {"categoria": "Mundo", "nome": "Desligada", "url": f"{BASE}/pt.xml", "idioma": "pt", "ativa": False},
    {"categoria": "Mundo", "nome": "Sem endereço", "url": "ftp://x/y", "idioma": "pt"},
]}
(RAIZ / "fontes.json").write_text(json.dumps(FONTES), encoding="utf-8")

os.environ.update({
    "HEIMDALL_DB_DIR": str(RAIZ / "banco"), "HEIMDALL_NEWS_FONTES": str(RAIZ / "fontes.json"), "HEIMDALL_NEWS_RSS_TOKEN": TOKEN,
    "HEIMDALL_NEWS_LLM_URL": f"http://127.0.0.1:{P_LLM}/v1/chat/completions", "LITELLM_MASTER_KEY": CHAVE_LLM,
    "HEIMDALL_NEWS_RESUMOS_POR_CICLO": "6", "HEIMDALL_CLOUD_TOTP_SEGREDO": SEGREDO, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
    "HEIMDALL_NEWS_MODELO": "modelo-de-teste", "HEIMDALL_NEWS_URL": "https://news.exemplo.test", "HEIMDALL_NEWS_FUSO": "America/Sao_Paulo",
})
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_cloud as hc  # noqa: E402

hc.SENHA_HASH = hc.hash_senha(SENHA, iteracoes=100_000)
hc.TOTP_SEGREDO = SEGREDO
import heimdall_banco as banco  # noqa: E402
import heimdall_news as hn  # noqa: E402

banco.iniciar()


def sql(q, *p):
    con = banco.conectar(somente_leitura=True)
    try:
        return [tuple(r) for r in con.execute(q, p)]
    finally:
        con.close()


# ----------------------------------------------------------------------------------------
# Textos e endereços
# ----------------------------------------------------------------------------------------
confere("rastreadores saem do link", hn.normalizar_link("HTTPS://Site.com/a?x=1&utm_source=z&fbclid=9#t") == "https://site.com/a?x=1")
confere("link perigoso vira vazio", hn.normalizar_link("javascript:alert(1)") == "" and hn.normalizar_link("file:///etc/passwd") == "")
confere("Leia mais corta no limite de palavra", hn.inicio_do_titulo("Governo anuncia nova medida para reduzir a fila de espera da saúde") == "Governo anuncia nova medida para reduzir a")
confere("limpa 'apareceu primeiro em'", hn.limpar_trecho("<p>Texto bom.</p> O post Título apareceu primeiro em Tecnoblog.") == "Texto bom.")
confere("limpa prefixo do arXiv", hn.limpar_trecho("arXiv:2611.1 Announce Type: new Abstract: Um estudo.") == "Um estudo.")
confere("Hacker News sem texto útil", hn.limpar_trecho("<p>Article URL: http://a</p><p>Comments URL: http://b</p>") == "")
confere("trecho longo é cortado", len(hn.limpar_trecho("palavra " * 300)) <= 701)
confere("matéria sem menu e sem rodapé", "ministério" in hn.texto_da_materia(MATERIA) and "Menu principal" not in hn.texto_da_materia(MATERIA) and "Rodapé" not in hn.texto_da_materia(MATERIA))
confere("data RFC 822 e ISO", hn.parse_data("Wed, 02 Oct 2024 13:00:00 GMT").year == 2024 and hn.parse_data("2024-10-02T13:00:00Z").hour == 13 and hn.parse_data("lixo") is None)
try:
    hn.analisar_feed(SERVIDOR["feeds"]["/bomba.xml"].encode())
    confere("feed com entidade recusado", False)
except ValueError:
    confere("feed com entidade recusado", True)
confere("Atom lido", len(hn.analisar_feed(atom(en).encode())) == 3 and hn.analisar_feed(atom(en).encode())[0]["link"].endswith("/materia/en1"))

# --- guarda contra a rede interna ---
for alvo in ("http://127.0.0.1:1/", "http://localhost/", "http://10.0.0.5/", "http://192.168.0.1/x", "http://169.254.169.254/latest", "http://[::1]/", "file:///etc/passwd", "ftp://x/y"):
    try:
        hn.checar_url(alvo)
        confere(f"recusa {alvo}", False)
    except ValueError:
        confere(f"recusa {alvo}", True)
for alvo in ("http://127.0.0.1:1/", "http://10.1.1.1/", "file:///etc/passwd"):
    try:
        hn._Redireciona().redirect_request(None, None, 302, "x", {}, alvo)
        confere(f"redirecionamento para {alvo} recusado", False)
    except ValueError:
        confere(f"redirecionamento para {alvo} recusado", True)
confere("lista de fontes: só as válidas e ativas", [f["nome"] for f in hn.carregar_fontes()] == ["Fonte PT", "Fonte EN", "Fonte Morta", "Fonte Bomba"])

hn.PERMITIR_LOCAL = True   # daqui em diante a "internet" de mentira roda nesta máquina

# ----------------------------------------------------------------------------------------
# Primeira atualização: coleta, repetidas, limite de resumos
# ----------------------------------------------------------------------------------------
r = hn.ciclo()
linhas = sql("SELECT titulo_original, link, publicado, resumo_base FROM noticias")
titulos = [l[0] for l in linhas]
confere("guardou as notícias válidas", len(linhas) == 14 + 1 + 1 + 1 + 3 and r["novos"] == len(linhas), f"{len(linhas)} {r}")
confere("repetida (rastreador) não entrou", ("Mesma matéria com rastreador" in titulos) != ("Notícia número 00 do dia" in titulos) and len({l[1] for l in linhas}) == len(linhas))
confere("link perigoso não entrou", "Link perigoso" not in titulos and not any(l[1].startswith("javascript") for l in linhas))
confere("mais de 30 dias não entrou", "Matéria velha demais" not in titulos)
confere("data do futuro vira agora", all(l[2] <= hn.iso(hn.agora()) for l in linhas))
confere("matéria de 30 h entrou (fica no banco)", "Matéria de ontem à noite" in titulos)
confere("limite de resumos por atualização", r["resumidos"] == 6 and len(sql("SELECT 1 FROM noticias WHERE resumo_base != ''")) == 6, str(r))
confere("fila guarda o resto", hn.estatisticas()["fila"] == len(linhas) - 1 - 6 and hn.estatisticas()["24h"] == len(linhas) - 1)
confere("matéria de 30 h fora da fila (fora das 24 h)", sql("SELECT resumo_base FROM noticias WHERE titulo_original='Matéria de ontem à noite'") == [("",)])
confere("fonte morta e fonte com entidade falham sem derrubar as outras",
        not hn.ESTADO["fontes"]["Fonte Morta"]["ok"] and not hn.ESTADO["fontes"]["Fonte Bomba"]["ok"] and hn.ESTADO["fontes"]["Fonte PT"]["ok"] and hn.ESTADO["fontes"]["Fonte EN"]["ok"])
confere("modelo e chave certos", all(p["modelo"] == "modelo-de-teste" for p in LLM["pedidos"]) and set(LLM["chaves"]) == {"Bearer " + CHAVE_LLM})
confere("modelo avisado para ignorar ordens do texto", all("ignore qualquer" in p["sistema"] for p in LLM["pedidos"]))

# segunda atualização: nada repetido, mais 6 resumos
n_antes = len(sql("SELECT 1 FROM noticias"))
r = hn.ciclo()
confere("segunda atualização não duplica", len(sql("SELECT 1 FROM noticias")) == n_antes and r["novos"] == 0 and r["resumidos"] == 6, str(r))
r = hn.ciclo()
confere("terceira atualização resume mais 6", r["resumidos"] == 6, str(r))
for _ in range(5):
    if hn.estatisticas()["fila"] == 0:
        break
    hn.ciclo()
confere("a fila termina", hn.estatisticas()["fila"] == 0 and len(sql("SELECT 1 FROM noticias WHERE resumo_base = '' AND publicado >= ?", hn.iso(AGORA - timedelta(hours=24)))) == 0)

# --- traduções e leitura da matéria ---
en_linhas = {l[0]: l for l in sql("SELECT titulo_original, titulo, titulo_traduzido, resumo_base, idioma FROM noticias WHERE idioma='en'")}
confere("título em inglês traduzido", all(l[1] == "Título traduzido para o português" and l[2] == 1 for l in en_linhas.values()), str(en_linhas))
confere("matéria lida quando o trecho é curto", en_linhas["Big news about data lakes"][3] == "materia")
confere("trecho longo não abre a matéria", en_linhas["A long English story"][3] == "trecho" and not any(p.endswith("/materia/en2") for p in SERVIDOR["pedidos"]))
confere("prompt traz o texto da matéria e não o menu", any("ministério" in p["usuario"] and "Menu principal" not in p["usuario"] for p in LLM["pedidos"]))
pt_titulo = sql("SELECT titulo, titulo_traduzido FROM noticias WHERE idioma='pt' LIMIT 1")[0]
confere("título em português fica como veio", pt_titulo[1] == 0 and pt_titulo[0].startswith("Notícia") or "Teste" in pt_titulo[0] or "Do futuro" in pt_titulo[0])

# --- modelo com problemas ---
SERVIDOR["feeds"]["/pt.xml"] = rss(pt + [("Notícia nova A", f"{BASE}/materia/a", h(1), "<p>trecho A</p>"), ("Notícia nova B", f"{BASE}/materia/b", h(1), "<p>trecho B</p>")])
LLM["modo"] = "fora"
r = hn.ciclo()
confere("modelo fora do ar: não gasta tentativa", r["resumidos"] == 0 and sql("SELECT tentativas, resumo_base FROM noticias WHERE titulo_original='Notícia nova A'") == [(0, "")] and "indisponível" in hn.ESTADO["erro_ia"], str(r))
LLM["modo"] = "lixo"
for _ in range(3):
    hn.ciclo()
confere("saída fora do formato: desiste após 3 tentativas", sql("SELECT tentativas, resumo_base FROM noticias WHERE titulo_original='Notícia nova A'") == [(3, "sem")])
SERVIDOR["feeds"]["/pt.xml"] = rss(pt + [("Notícia nova C", f"{BASE}/materia/c", h(1), "<p>trecho C</p>")])
LLM["modo"] = "pensa"
hn.ciclo()
confere("aceita <think> e cerca de código", sql("SELECT resumo_base, resumo FROM noticias WHERE titulo_original='Notícia nova C'")[0][0] == "materia")
confere("erro da IA some quando volta", hn.ESTADO["erro_ia"] == "")
LLM["modo"] = "ok"

# --- 30 dias no banco ---
con = banco.conectar()
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado) VALUES ('velha','Velha','http://x.test/v',?,?)", (hn.iso(AGORA - timedelta(days=31)), hn.iso(AGORA - timedelta(days=31))))
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado) VALUES ('quase','Quase','http://x.test/q',?,?)", (hn.iso(AGORA - timedelta(days=29)), hn.iso(AGORA - timedelta(days=29))))
con.commit()
con.close()
confere("apaga com mais de 30 dias e mantém 29", hn.limpar_antigas() == 1 and sql("SELECT id FROM noticias WHERE id IN ('velha','quase')") == [("quase",)])

# --- pausa ---
h_ = datetime.now(hn.FUSO).hour
hn.PAUSA = f"{h_}-{(h_ + 1) % 24}"
confere("pausa de resumos na hora marcada", hn.em_pausa() and hn.fazer_resumos(time.time()) == (0, 0))
hn.PAUSA = f"{(h_ + 2) % 24}-{(h_ + 3) % 24}"
confere("fora da pausa", not hn.em_pausa())
hn.PAUSA = ""

# ----------------------------------------------------------------------------------------
# Site
# ----------------------------------------------------------------------------------------
srv, porta = servir(hn.News)


def req(metodo, caminho, corpo=None, cookie="", host="localhost"):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = cookie
    if corpo is not None:
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    c.request(metodo, caminho, body=corpo, headers=cab)
    resp = c.getresponse()
    dados = resp.read()
    heads = {k.lower(): v for k, v in resp.getheaders()}
    c.close()
    return resp.status, heads, dados


def txt(b):
    return b.decode("utf-8", "replace")


def codigo(passo):
    return hc._hotp(hc._chave_totp(SEGREDO), passo)


passo = int(time.time() // 30)
s, hd, _ = req("GET", "/")
confere("sem login vai para /entrar", s == 303 and hd["location"] == "/entrar")
s, _, _ = req("GET", "/", host="outro.exemplo")
confere("site não permitido: 421", s == 421)
s, _, c = req("GET", "/saude")
confere("saúde", s == 200 and c == b"ok")
s, _, _ = req("POST", "/entrar", urlencode({"senha": "errada", "codigo": codigo(passo)}))
confere("senha errada recusada", s == 401)
s, hd, _ = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(passo)}))
confere("login correto", s == 303 and "hnews=" in hd.get("set-cookie", "") and "HttpOnly" in hd["set-cookie"] and "SameSite=Strict" in hd["set-cookie"])
ck = hd["set-cookie"].split(";")[0]
s, _, _ = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(passo)}))
confere("código não reaproveitável", s == 401)

s, hd, c = req("GET", "/", cookie=ck)
t = txt(c)
confere("página abre", s == 200 and "Notícias das últimas 24 horas" in t)
confere("10 por página", len(re.findall(r"<li><h2>", t)) == 10, str(len(re.findall(r"<li><h2>", t))))
confere("título como cabeçalho", "<h2>Notícia número 00 do dia</h2>" in t or "<h2>Teste" in t)
confere("resumo marcado como IA", t.count("Resumo feito por IA") >= 5 and "podem conter erros" in t)
confere("Leia mais com o início do título", 'Leia mais sobre Notícia número 00 do dia...' in t or "Leia mais sobre Notícia número 01 do dia..." in t)
confere("link da matéria abre a original", f'href="{BASE}/materia/' in t and 'target="_blank" rel="noopener noreferrer"' in t and "(abre em nova aba)" in t)
confere("matéria de 30 h não aparece", "ontem à noite" not in t)
confere("categorias com contagem", "Brasil (" in t and "Tecnologia (3)" in t and "Ciência (0)" in t)
total = hn.estatisticas()["24h"]
paginas = -(-total // 10)
confere("há mais de uma página no teste", paginas >= 2, str(total))
confere("paginação", f"Página 1 de {paginas}" in t and '<button type="submit">Próxima</button>' in t and ">Anterior<" not in t and 'name="pagina" value="2"' in t)
s, _, c = req("GET", "/?pagina=2", cookie=ck)
t2 = txt(c)
confere("segunda página", f"Página 2 de {paginas}" in t2 and '<button type="submit">Anterior</button>' in t2 and 'name="pagina" value="1"' in t2 and len(re.findall(r"<li><h2>", t2)) == min(10, total - 10))
confere("páginas não se repetem", not (set(re.findall(r'href="(http[^"]+)" target="_blank" rel="noopener', t)) & set(re.findall(r'href="(http[^"]+)" target="_blank" rel="noopener', t2))))
todos = []
for n_ in range(1, paginas + 1):
    todos += re.findall(r'href="(http[^"]+)" target="_blank" rel="noopener', txt(req("GET", f"/?pagina={n_}", cookie=ck)[2]))
confere("juntas, as páginas somam as notícias das 24 h, sem repetir", len(todos) == total and len(set(todos)) == total, f"{len(todos)} {len(set(todos))} {total}")
s, _, c = req("GET", "/?pagina=999", cookie=ck)
confere("página fora do limite vai para a última", s == 200 and f"Página {paginas} de {paginas}" in txt(c))
s, _, c = req("GET", "/?pagina=abc", cookie=ck)
confere("página inválida vale 1", s == 200 and f"Página 1 de {paginas}" in txt(c))
# o botão leva à página certa, mantendo a categoria
with_cat = txt(req("GET", "/?categoria=brasil", cookie=ck)[2])
confere("botão Próxima mantém a categoria", 'name="categoria" value="brasil"' in with_cat and 'name="pagina" value="2"' in with_cat)
s, _, c = req("GET", "/?categoria=brasil&pagina=2", cookie=ck)
confere("o botão chega na segunda página da categoria", s == 200 and "Página 2 de" in txt(c))
s, _, c = req("GET", "/?categoria=tecnologia", cookie=ck)
confere("filtro por categoria", s == 200 and "Notícias: Tecnologia" in txt(c) and "Título traduzido para o português" in txt(c) and "Notícia número" not in txt(c))
confere("título traduzido é sinalizado", "título traduzido por IA do inglês" in txt(c))
s, _, c = req("GET", "/?categoria=nao-existe", cookie=ck)
confere("categoria inexistente: 404", s == 404)
s, _, c = req("GET", "/?categoria=ciencia", cookie=ck)
confere("categoria vazia avisa", s == 200 and "Nenhuma notícia" in txt(c))
pagina_toda = "".join(txt(req("GET", f"/?pagina={n_}", cookie=ck)[2]) for n_ in range(1, paginas + 1))
confere("sem resumo da IA o site avisa e mostra o trecho original", "Não consegui resumir. Trecho original da fonte:</strong> trecho A" in pagina_toda)
html_inj = txt(req("GET", "/?pagina=1", cookie=ck)[2]) + txt(req("GET", "/?pagina=2", cookie=ck)[2])
confere("HTML do feed escapado", "&lt;b&gt;negrito&lt;/b&gt;" in html_inj and "<b>negrito" not in html_inj and "<script>alert" not in html_inj and "<img src=x" not in html_inj)
s, _, c = req("GET", "/estado", cookie=ck)
t = txt(c)
confere("estado das fontes", s == 200 and "Fonte PT" in t and "Fonte Morta" in t and "falhou desde" in t and "Fonte Bomba" in t and "modelo-de-teste" in t)
s, _, _ = req("GET", "/estado")
confere("estado exige login", s == 303)
s, _, _ = req("POST", "/", "x=1", cookie=ck)
confere("site é só de leitura", s == 405)
s, hd, c = req("GET", "/", cookie=ck)
confere("cabeçalhos de segurança", "no-store" in hd["cache-control"] and "frame-ancestors 'none'" in hd["content-security-policy"] and hd["x-robots-tag"].startswith("noindex"))

# ----------------------------------------------------------------------------------------
# RSS
# ----------------------------------------------------------------------------------------
antigo_stderr = sys.stderr
sys.stderr = io.StringIO()
s, hd, c = req("GET", f"/rss/{TOKEN}/geral.xml")
log_rss = sys.stderr.getvalue()
sys.stderr = antigo_stderr
confere("RSS geral abre sem login", s == 200 and hd["content-type"].startswith("application/rss+xml"))
raiz = ET.fromstring(c)
itens = raiz.findall("./channel/item")
confere("RSS é XML válido com itens", len(itens) > 10 and raiz.find("./channel/title").text == "Heimdall News")
confere("RSS traz data, link, guid e categoria", all(i.find("pubDate") is not None and i.find("link").text.startswith("http") and i.find("guid") is not None and i.find("category") is not None for i in itens))
confere("RSS marca o resumo como IA", any("Resumo feito por IA" in (i.find("description").text or "") for i in itens))
con = banco.conectar()
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado, categoria, fonte, resumo, resumo_base) VALUES ('r30','Com 30 horas','http://x.test/r30',?,?,'Brasil','Fonte PT','Resumo x que é suficientemente comprido para o teste.','trecho')",
            (hn.iso(AGORA - timedelta(hours=30)), hn.iso(AGORA - timedelta(hours=30))))
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado, categoria, fonte, resumo, resumo_base) VALUES ('r80','Com 80 horas','http://x.test/r80',?,?,'Brasil','Fonte PT','Resumo y que é suficientemente comprido para o teste.','trecho')",
            (hn.iso(AGORA - timedelta(hours=80)), hn.iso(AGORA - timedelta(hours=80))))
con.commit()
con.close()
tit72 = [i.find("title").text for i in ET.fromstring(req("GET", f"/rss/{TOKEN}/geral.xml")[2]).findall("./channel/item")]
confere("RSS guarda 72 horas: 30 h entra, 80 h não", "Com 30 horas" in tit72 and "Com 80 horas" not in tit72)
confere("site mostra só 24 horas: 30 h fica fora", "Com 30 horas" not in txt(req("GET", "/", cookie=ck)[2]) + txt(req("GET", "/?pagina=2", cookie=ck)[2]) + txt(req("GET", "/?pagina=3", cookie=ck)[2]))
confere("RSS escapa HTML", "<script" not in txt(c) and "<img src=x" not in txt(c))
confere("chave não vai para o log", TOKEN not in log_rss and "/rss/***/geral.xml" in log_rss, log_rss[:200])
s, _, c = req("GET", f"/rss/{TOKEN}/tecnologia.xml")
confere("RSS por categoria", s == 200 and len(ET.fromstring(c).findall("./channel/item")) == 3 and "Tecnologia" in ET.fromstring(c).find("./channel/title").text)
s, hd, c = req("GET", f"/rss/{TOKEN}/feeds.opml")
op = ET.fromstring(c)
urls = [o.get("xmlUrl") for o in op.iter("outline")]
confere("OPML traz todos os feeds", s == 200 and len(urls) == 1 + 3 and f"https://news.exemplo.test/rss/{TOKEN}/geral.xml" in urls and f"https://news.exemplo.test/rss/{TOKEN}/tecnologia.xml" in urls, str(urls))
s, _, _ = req("GET", f"/rss/{TOKEN}/nao-existe.xml")
confere("feed inexistente: 404", s == 404)
s, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml", host="outro.exemplo")
confere("RSS também confere o site", s == 421)
s, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml", cookie="")
s2, _, _ = req("POST", f"/rss/{TOKEN}/geral.xml", "x=1")
confere("RSS só aceita GET", s2 in (303, 405))
# item recém-coletado e sem resumo espera antes de entrar no RSS
con = banco.conectar()
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado, categoria, fonte) VALUES ('fresca','Matéria fresquinha','http://x.test/f',?,?,'Brasil','Fonte PT')", (hn.iso(AGORA), hn.iso(AGORA)))
con.execute("INSERT INTO noticias (id, titulo, link, publicado, coletado, categoria, fonte) VALUES ('antiga','Matéria que ficou sem resumo','http://x.test/a',?,?,'Brasil','Fonte PT')",
            (hn.iso(AGORA - timedelta(hours=5)), hn.iso(AGORA - timedelta(hours=4))))
con.commit()
con.close()
s, _, c = req("GET", f"/rss/{TOKEN}/geral.xml")
tit = [i.find("title").text for i in ET.fromstring(c).findall("./channel/item")]
confere("sem resumo ainda: espera para entrar no RSS", "Matéria fresquinha" not in tit and "Matéria que ficou sem resumo" in tit)
# chave errada, sem chave e limite
for caminho in ("/rss/errada/geral.xml", "/rss/geral.xml", f"/rss/{TOKEN}/a/b.xml", "/rss/", f"/rss/{TOKEN}"):
    s, _, _ = req("GET", caminho)
    confere(f"RSS recusa {caminho}", s == 404)
s, _, c = req("GET", "/", cookie=ck)
confere("chave errada não trava o login nem o site", s == 200)
bloqueou = False
for i in range(hn.RSS_MAX_FALHAS + 2):
    s, _, _ = req("GET", f"/rss/chute{i}/geral.xml")
    if s == 429:
        bloqueou = True
        break
confere("muitas chaves erradas: 429", bloqueou)
s, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml")
confere("depois do bloqueio nem a chave certa passa (mesmo endereço)", s == 429)
s, _, c = req("GET", "/", cookie=ck)
confere("o login continua valendo", s == 200)
hn._rss_falhas.clear()
s, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml")
confere("liberado de novo", s == 200)

# --- sem chave configurada, o RSS some ---
chave_certa = hn.RSS_TOKEN
hn.RSS_TOKEN = ""
s, _, _ = req("GET", "/rss//geral.xml")
s2, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml")
confere("sem chave no .env o RSS fica desligado", s2 == 404)
hn.RSS_TOKEN = chave_certa
hn._rss_falhas.clear()

# --- sair ---
csrf = re.search(r'name="csrf" value="([^"]+)"', txt(req("GET", "/", cookie=ck)[2])).group(1)
s, _, _ = req("POST", "/sair", urlencode({"csrf": "errado"}), cookie=ck)
confere("sair sem token CSRF é recusado", s == 403)
s, hd, _ = req("POST", "/sair", urlencode({"csrf": csrf}), cookie=ck)
s2, _, _ = req("GET", "/", cookie=ck)
confere("sair encerra a sessão", s == 303 and s2 == 303)

# ----------------------------------------------------------------------------------------
# Linha de comando: chave dos feeds
# ----------------------------------------------------------------------------------------
saida = io.StringIO()
antigo, sys.stdout = sys.stdout, saida
hn.mostrar_urls()
sys.stdout = antigo
confere("--urls mostra os endereços e o OPML", f"https://news.exemplo.test/rss/{TOKEN}/geral.xml" in saida.getvalue() and f"/rss/{TOKEN}/feeds.opml" in saida.getvalue())
confere("endereços por categoria", f"/rss/{TOKEN}/tecnologia.xml" in saida.getvalue())
con = banco.conectar()
con.execute("DROP TABLE noticias")
con.commit()
con.close()
saida = io.StringIO()
antigo, sys.stdout = sys.stdout, saida
sys.argv = ["heimdall_news.py", "--urls"]
hn.main()
sys.stdout = antigo
confere("--urls funciona antes da primeira subida (tabela criada na hora)", "/geral.xml" in saida.getvalue() and sql("SELECT COUNT(*) FROM noticias") == [(0,)])
hc.PROJECT_DIR = hn.PROJECT_DIR = RAIZ
(RAIZ / ".env").write_text("OUTRA='coisa'\nHEIMDALL_NEWS_RSS_TOKEN='antiga'\n", encoding="utf-8")
sys.argv = ["heimdall_news.py", "--token"]
saida = io.StringIO()
antigo, sys.stdout = sys.stdout, saida
hn.main()
sys.stdout = antigo
env = (RAIZ / ".env").read_text(encoding="utf-8")
novo = re.search(r"HEIMDALL_NEWS_RSS_TOKEN='([^']+)'", env).group(1)
confere("--token troca a chave no .env e preserva o resto", novo not in ("antiga", TOKEN) and len(novo) >= 30 and "OUTRA='coisa'" in env and env.count("HEIMDALL_NEWS_RSS_TOKEN") == 1)
confere("--token mostra os endereços novos e como reiniciar", f"/rss/{novo}/geral.xml" in saida.getvalue() and "./subir.sh --reiniciar" in saida.getvalue())
confere("--token cria o .env com permissão 600", oct((RAIZ / ".env").stat().st_mode & 0o777) == "0o600")
s, _, _ = req("GET", f"/rss/{TOKEN}/geral.xml")
s2, _, _ = req("GET", f"/rss/{novo}/geral.xml")
confere("chave nova vale e a antiga deixa de valer", s == 404 and s2 == 200)
saida = io.StringIO()
antigo, sys.stdout = sys.stdout, saida
sys.argv = ["heimdall_news.py", "--opml", str(RAIZ / "feeds.opml")]
hn.main()
sys.stdout = antigo
op2 = ET.fromstring((RAIZ / "feeds.opml").read_bytes())
confere("--opml grava o arquivo com todos os feeds e a chave nova", len(list(op2.iter("outline"))) == 4 and f"/rss/{novo}/geral.xml" in (RAIZ / "feeds.opml").read_text(encoding="utf-8") and oct((RAIZ / "feeds.opml").stat().st_mode & 0o777) == "0o600" and "Atenção" in saida.getvalue())
saida = io.StringIO()
antigo, sys.stdout = sys.stdout, saida
sys.argv = ["heimdall_news.py", "--copiar", "ciencia"]
try:
    hn.main()
except SystemExit:
    pass
sys.stdout = antigo
confere("--copiar acha o feed da categoria", "ciencia" in saida.getvalue() and ("copiado" in saida.getvalue() or f"/rss/{novo}/ciencia.xml" in saida.getvalue()))
sys.argv = ["heimdall_news.py", "--copiar", "inexistente"]
try:
    hn.main()
    confere("--copiar com nome errado avisa", False)
except SystemExit as ex:
    confere("--copiar com nome errado avisa", "Não achei" in str(ex))

print(f"\n{ok_n} conferências ok, {len(falhas)} falha(s).")
if falhas:
    sys.exit(1)
print("Tudo certo.")
