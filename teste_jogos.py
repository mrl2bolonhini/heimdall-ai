#!/usr/bin/env python3
"""Testa o servidor de jogos (login, host, páginas, arquivos servidos, cabeçalhos) e roda os testes de lógica e de interface em Node."""
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(AQUI))
import heimdall_cloud as hc  # noqa: E402
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
confere("início lista os 6 jogos", st == 200 and all(f"/jogo/{j[0]}" in corpo for j in hj.CATALOGO) and len(hj.CATALOGO) == 6, (st, corpo[:300]))
csp = cab.get("Content-Security-Policy", "")
confere("política de conteúdo só deixa script do próprio site", "script-src 'self'" in csp and "default-src 'none'" in csp and "connect-src 'none'" in csp, csp)
confere("sem script embutido no HTML", "<script>" not in corpo and "onclick" not in corpo.lower())
confere("cabeçalhos de segurança", cab.get("X-Frame-Options") == "DENY" and cab.get("Cache-Control") == "no-store" and "noindex" in cab.get("X-Robots-Tag", ""), cab)
confere("a página é pt-BR com link de pular e título", 'lang="pt-BR"' in corpo and "Pular para o conteúdo" in corpo and "<h1>Jogos</h1>" in corpo)

for jid, titulo, arq, resumo, como in hj.CATALOGO:
    st, corpo, _ = pedir(f"/jogo/{jid}", ck)
    ok = (st == 200 and f"<h1>{titulo}</h1>" in corpo and 'id="jogo"' in corpo and 'role="status"' in corpo and 'aria-live="polite"' in corpo
          and '<script src="/js/base.js" defer>' in corpo and f'<script src="/js/{arq}" defer>' in corpo and "Como jogar" in corpo)
    confere(f"página do jogo {jid}", ok, (st, corpo[:300]))
    st, js, cab = pedir(f"/js/{arq}", ck)
    confere(f"arquivo {arq} é servido como JavaScript", st == 200 and "javascript" in cab.get("Content-Type", "") and len(js) > 500, (st, cab.get("Content-Type")))

st, _, _ = pedir("/js/base.js", ck)
confere("base.js é servido", st == 200)
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
os.environ["HEIMDALL_JOGOS_EXTRAS"] = "Enigma|http://localhost:8015|Quebra-cabeças;Mal|javascript:alert(1)|x;Outro|https://exemplo.test/jogo|"
ex = hj.extras()
confere("extras aceitam só http e https", [x[0] for x in ex] == ["Enigma", "Outro"], ex)
token2, _ = hc.nova_sessao()
st, corpo, _ = pedir("/", f"{hc.COOKIE}={token2}")
confere("extras aparecem no início, sem o endereço perigoso", 'href="http://localhost:8015"' in corpo and "javascript:" not in corpo, corpo[-500:])
os.environ.pop("HEIMDALL_JOGOS_EXTRAS")

for arq in ("teste_jogos_logica.js", "teste_jogos_ui.js"):
    r = subprocess.run(["node", str(AQUI / arq)], capture_output=True, text=True, timeout=120)
    confere(f"{arq} (Node)", r.returncode == 0, r.stdout[-600:] + r.stderr[-300:])
    print("\n".join("     " + l for l in r.stdout.splitlines() if l.startswith("FALHOU")))

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
