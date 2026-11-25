#!/usr/bin/env python3
"""Testa o servidor de jogos (login, host, páginas, arquivos servidos, cabeçalhos) e roda os testes de lógica e de interface em Node."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = RAIZ
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(AQUI))
import heimdall_lab as hc  # noqa: E402
import heimdall_jogos as hj  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
srv = ThreadingHTTPServer(("127.0.0.1", 0), hj.Jogos)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open


def pedir(caminho, cookie="", host=None, dados=None, metodo=None):
    cab = {}
    if cookie:
        cab["Cookie"] = cookie
    if host:
        cab["Host"] = host
    req = urllib.request.Request(BASE + caminho, data=dados, headers=cab, method=metodo)
    try:
        with abre(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


st, _, cab = pedir("/")
confere("sem login vai para /entrar", st == 303 and cab.get("Location") == "/entrar", (st, cab))
st, _, _ = pedir("/", host="outro.exemplo.test")
confere("host fora da lista é recusado", st == 421, st)
st, corpo, _ = pedir("/saude")
confere("/saude responde ok sem login", st == 200 and corpo == "ok", (st, corpo))
st, corpo, _ = pedir("/js/base.js")
confere("os arquivos .js também exigem login", st == 303, st)
st, corpo, _ = pedir("/entrar", dados=urllib.parse.urlencode({"senha": "errada", "codigo": "000000"}).encode())
confere("login errado é recusado", st == 401 and "incorretos" in corpo, (st, corpo[:200]))

token, sess = hc.nova_sessao()
ck = f"{hc.COOKIE}={token}"
st, corpo, cab = pedir("/", ck)
confere("categorias são abas: uma aba por categoria, numa só linha (no máximo 5), com a primeira aberta no início", st == 200 and len(hj.CATALOGO) == 28 and len(hj.CATEGORIAS) == 5
        and corpo.count('role="tab"') == 5 and 'class="l5"' in corpo and "Mais" not in corpo.split("<main")[0] and all(f'href="/categoria/{c[0]}"' in corpo and c[1] in corpo for c in hj.CATEGORIAS)
        and f'href="/categoria/{hj.CATEGORIAS[0][0]}" aria-selected="true"' in corpo, (st, corpo[:300]))
confere("o início mostra a apresentação e os jogos da primeira categoria", "Cada aba é uma categoria" in corpo and all(f"/jogo/{i}" in corpo for i in hj.CATEGORIAS[0][3]))
for c in hj.CATEGORIAS:
    st_c, corpo_c, _ = pedir(f"/categoria/{c[0]}", ck)
    confere(f"categoria {c[0]} lista os seus jogos, com a própria aba aberta e a troca de aba sem recarregar", st_c == 200 and all(f"/jogo/{i}" in corpo_c for i in c[3])
            and f'href="/categoria/{c[0]}" aria-selected="true"' in corpo_c and corpo_c.count('aria-selected="true"') == 1 and " data-completa>" not in corpo_c
            and f"<h1>{hj.e(c[1])}</h1>" in corpo_c and "Voltar às categorias" not in corpo_c, (st_c, corpo_c[:200]))
confere("jogos de cada categoria em ordem alfabética", all([hj.POR_ID[i][1] for i in c[3]] == sorted((hj.POR_ID[i][1] for i in c[3]), key=hj._chave) for c in hj.CATEGORIAS))
confere("categorias em ordem alfabética", [c[1] for c in hj.CATEGORIAS] == sorted((c[1] for c in hj.CATEGORIAS), key=lambda t: __import__("unicodedata").normalize("NFD", t).encode("ascii", "ignore").decode().lower()), [c[1] for c in hj.CATEGORIAS])
confere("categoria inexistente dá 404", pedir("/categoria/nada", ck)[0] == 404)
confere("todo jogo está em uma só categoria", sorted(i for _, ids in hj.GRUPOS for i in ids) == sorted(j[0] for j in hj.CATALOGO))
csp = cab.get("Content-Security-Policy", "")
import re as _re_n
confere("política de conteúdo só deixa script do próprio site e o das abas (com nonce)", _re_n.search(r"script-src 'nonce-[A-Za-z0-9_-]+' 'self'", csp) and "default-src 'none'" in csp and "connect-src 'self'" in csp and "unsafe-eval" not in csp, csp)
st_j, corpo_j, cab_j = pedir("/jogo/vilarejo", ck)
confere("página de jogo: aba da categoria aberta, trocar de aba carrega a página inteira, volta para a categoria e conexão da página fechada",
        'href="/categoria/acao" aria-selected="true"' in corpo_j and corpo_j.count(" data-completa>") == 5 and 'href="/categoria/acao">Voltar para Ação' in corpo_j
        and "connect-src 'none'" in cab_j.get("Content-Security-Policy", ""), (st_j, cab_j.get("Content-Security-Policy")))
confere("abas, atalho Option+Shift+1, voltar ao topo e tema de rodapé no Games", 'role="tablist"' in corpo and 'id="topo"' in corpo and 'href="#topo"' in corpo and "<nav aria-label=\"Principal\"><ul>" not in corpo)
confere("sem script embutido no HTML", "<script>" not in corpo and "onclick" not in corpo.lower())
confere("cabeçalhos de segurança", cab.get("X-Frame-Options") == "DENY" and cab.get("Cache-Control") == "no-store" and "noindex" in cab.get("X-Robots-Tag", ""), cab)
confere("a página é pt-BR com link de pular e título", 'lang="pt-BR"' in corpo and "Pular para o conteúdo" in corpo and f"<h1>{hj.e(hj.CATEGORIAS[0][1])}</h1>" in corpo)

for jid, titulo, arq, resumo, como in hj.CATALOGO:
    st, corpo, _ = pedir(f"/jogo/{jid}", ck)
    ok = (st == 200 and f"<h1>{hj.e(titulo)}</h1>" in corpo and 'id="jogo"' in corpo and 'role="status"' in corpo and 'aria-live="polite"' in corpo
          and '<script src="/js/base.js" defer>' in corpo and f'<script src="/js/{arq}" defer>' in corpo and "Como jogar" in corpo)
    if jid in hj.HISTORIAS:
        ok = ok and f'data-historia="{jid}"' in corpo and corpo.index(f"/js/{arq}") < corpo.index("/js/motor.js")
    else:
        ok = ok and "data-historia" not in corpo
    confere(f"página do jogo {jid}", ok, (st, corpo[:300]))
    st, js, cab = pedir(f"/js/{arq}", ck)
    confere(f"arquivo {arq} é servido como JavaScript", st == 200 and "javascript" in cab.get("Content-Type", "") and len(js) > 500, (st, cab.get("Content-Type")))

st, _, _ = pedir("/js/base.js", ck)
confere("base.js é servido", st == 200)
st, js, cab = pedir("/js/motor.js", ck)
confere("motor.js é servido", st == 200 and "javascript" in cab.get("Content-Type", "") and "HeimdallMotor" in js)
for ruim in ("/js/../.env", "/js/..%2F.env", "/js/heimdall_jogos.py", "/js/teste.js", "/js/", "/jogo/../x", "/jogo/nao-existe", "/jogo/FORCA"):
    st, corpo, _ = pedir(ruim, ck)
    confere(f"recusa {ruim}", st in (404, 400) and "HEIMDALL" not in corpo and "SENHA_HASH" not in corpo, (st, corpo[:100]))
st, corpo, _ = pedir("/jogo/forca", ck, dados=b"x=1")
confere("POST fora de /sair é recusado", st == 405, st)
st, corpo, _ = pedir("/sair", ck, dados=b"csrf=errado")
confere("sair com token errado é recusado", st == 403, st)
st, corpo, cab = pedir("/sair", ck, dados=urllib.parse.urlencode({"csrf": sess["csrf"]}).encode())
confere("sair com o token certo encerra a sessão", st == 303 and cab.get("Location") == "/entrar", (st, cab))
st, _, _ = pedir("/", ck)
confere("depois de sair a sessão não vale", st == 303, st)

# jogos extras do .env
os.environ["HEIMDALL_JOGOS_EXTRAS"] = "Terceiro|http://localhost:8015|Quebra-cabeças;Mal|javascript:alert(1)|x;Outro|https://exemplo.test/jogo|"
ex = hj.extras()
confere("extras aceitam só http e https", [x[0] for x in ex] == ["Terceiro", "Outro"], ex)
token2, _ = hc.nova_sessao()
st, corpo, _ = pedir("/extras", f"{hc.COOKIE}={token2}")
corpo_cab = corpo.split("<main")[0]
confere("com extras são 6 itens: 4 abas e o menu Mais na quinta posição (Lógica e Outros), nunca mais de 5 posições; sem o endereço perigoso",
        st == 200 and 'href="http://localhost:8015"' in corpo and "javascript:" not in corpo and corpo_cab.count('role="tab"') == 4 and 'id="mais"' in corpo_cab
        and 'href="/categoria/logica"' in corpo_cab.split('id="mais"')[1] and 'href="/extras"' in corpo_cab.split('id="mais"')[1] and "Mais, aba aberta: Extras" in corpo_cab, (st, corpo_cab[-700:]))
os.environ.pop("HEIMDALL_JOGOS_EXTRAS")
for _antigo, _novo, _jogo in (("cartas", "cassino", "poker"), ("acao", "acao", "vilarejo"), ("audio", "acao", "vilarejo"), ("tabuleiro", "estrategia", "xadrez"),
                              ("palavras", "logica", "forca"), ("numeros", "logica", "sudoku")):
    st_c, _, cab_c = pedir(f"/categoria/{_antigo}", f"{hc.COOKIE}={token2}")
    if _antigo == _novo:   # ainda é a rota atual: abre
        confere(f"/categoria/{_antigo} é rota atual e abre", st_c == 200)
        continue
    confere(f"rota antiga /categoria/{_antigo} redireciona (301) para a atual /categoria/{_novo}", st_c == 301 and cab_c.get("Location") == f"/categoria/{_novo}", (st_c, cab_c.get("Location")))
    st_c, corpo_c, _ = pedir(f"/categoria/{_novo}", f"{hc.COOKIE}={token2}")
    confere(f"a rota atual /categoria/{_novo} abre com os jogos dela e a aba marcada", st_c == 200 and f'href="/categoria/{_novo}" aria-selected="true"' in corpo_c and f"/jogo/{_jogo}" in corpo_c)
confere("todas as rotas de categoria listadas nas abas são canônicas", all(hj.rota_canonica(r) == r for r, _ in hj.nav_jogos()) and hj.rota_canonica("/outros") == "/extras")
st_c, corpo_c, _ = pedir("/categoria/cassino", f"{hc.COOKIE}={token2}")
confere("Cassino traz só os jogos de azar e de cartas de aposta; a paciência foi para Lógica", "/jogo/poker" in corpo_c and "/jogo/roleta" in corpo_c and "/jogo/paciencia" not in corpo_c)
confere("nomes das abas com uma palavra só e em ordem alfabética", all(" " not in c[1] for c in hj.CATEGORIAS) and [c[1] for c in hj.CATEGORIAS] == ["Ação", "Aventuras", "Cassino", "Estratégia", "Lógica"])
confere("sem extras, as 5 categorias ocupam as 5 posições", len(hj.nav_jogos()) == 5)
st_o, _, cab_o = pedir("/outros", f"{hc.COOKIE}={token2}")
confere("a rota antiga /outros redireciona (301) para /extras", st_o == 301 and cab_o.get("Location") == "/extras", (st_o, cab_o.get("Location")))
confere("sem extras não há item Extras nem a rota", pedir("/extras", f"{hc.COOKIE}={token2}")[0] == 404 and 'href="/extras"' not in pedir("/", f"{hc.COOKIE}={token2}")[1])
os.environ.pop("HEIMDALL_JOGOS_EXTRAS", None)

for arq in ("tests/games/teste_jogos_logica.js", "tests/games/teste_jogos_ui.js"):
    r = subprocess.run(["node", str(AQUI / arq)], capture_output=True, text=True, timeout=120)
    confere(f"{arq} (Node)", r.returncode == 0, r.stdout[-600:] + r.stderr[-300:])
    print("\n".join("     " + l for l in r.stdout.splitlines() if l.startswith("FALHOU")))

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
