#!/usr/bin/env python3
"""Testa o painel de saúde: login, páginas, somente leitura, host permitido, escape de HTML e estado dos dados."""
import os
import random
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="painel_saude_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "banco"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_banco as banco  # noqa: E402
import heimdall_cloud as hc  # noqa: E402
import heimdall_painel_saude as ps  # noqa: E402
import heimdall_saude as hs  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


SENHA, SEGREDO = "senha-de-teste-forte", "JBSWY3DPEHPK3PXP"
hc.SENHA_HASH = hc.hash_senha(SENHA, iteracoes=100_000)
hc.TOTP_SEGREDO = SEGREDO

hs._garantir_banco()
con = sqlite3.connect(banco.DB_PATH)
random.seed(3)
agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
for i in range(120):
    d = (datetime.now() - timedelta(days=i + 1)).strftime("%Y-%m-%d")   # o dado mais novo é de ontem
    s = random.gauss(400, 50)
    for m, v in (("sono_total", s), ("hrv", 30 + (s - 400) * .05 + random.gauss(0, 3)), ("fc_repouso", 64 + random.gauss(0, 2)), ("passos", max(500, random.gauss(6500, 2000))),
                 ("x:apple_exercise_time", max(0, random.gauss(25, 10)))):
        con.execute("INSERT OR REPLACE INTO saude_diaria (dia, metrica, valor, unidade, atualizado) VALUES (?,?,?,?,?)", (d, m, v, "", agora))
con.commit()
con.close()

srv = ThreadingHTTPServer(("127.0.0.1", 0), ps.Painel)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]
BASE = f"http://127.0.0.1:{PORTA}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open


def pedir(caminho, cookie="", host=None, dados=None):
    cab = {}
    if cookie:
        cab["Cookie"] = cookie
    if host:
        cab["Host"] = host
    req = urllib.request.Request(BASE + caminho, data=dados, headers=cab)
    try:
        with abre(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


st, _, cab = pedir("/")
confere("sem login vai para /entrar", st == 303 and cab.get("Location") == "/entrar", (st, cab))
st, _, _ = pedir("/", host="outro.exemplo.test")
confere("host fora da lista é recusado", st == 421, st)
st, corpo, _ = pedir("/saude")
confere("/saude responde ok sem login", st == 200 and corpo == "ok", (st, corpo))
st, corpo, _ = pedir("/entrar", dados=urllib.parse.urlencode({"senha": "errada", "codigo": "000000"}).encode())
confere("login errado é recusado", st == 401 and "incorretos" in corpo, (st, corpo[:200]))

token, sess = hc.nova_sessao()
ck = f"{ps.COOKIE}={token}"
for rota, esperado in (("/", "Como você está agora"), ("/semana", "Saúde: semana de"), ("/sono", "noites com dado"), ("/atividade", "Passos"), ("/recuperacao", "Recuperação"),
                       ("/coracao", "Frequência"), ("/treinos", "Treinos"), ("/eventos", "Sintomas"), ("/diario", "Valores por dia"), ("/dados", "Último dia com dado")):
    st, corpo, cab = pedir(rota, ck)
    confere(f"página {rota}", st == 200 and esperado in corpo and "Pular para o conteúdo" in corpo, (st, corpo[:300]))
st, corpo, cab = pedir("/", ck)
confere("cabeçalhos de segurança e sem cache", "frame-ancestors 'none'" in cab.get("Content-Security-Policy", "") and cab.get("Cache-Control") == "no-store", cab)
confere("datas no padrão brasileiro, sem AAAA-MM-DD", not __import__("re").search(r"\d{4}-\d\d-\d\d", pedir("/diario", ck)[1]), "")
st, corpo, _ = pedir("/diario?dias=7", ck)
confere("período selecionável e tabela com cabeçalhos", "7 dias (selecionado)" in corpo and 'scope="row"' in corpo and 'scope="col"' in corpo, corpo[:400])
st, corpo, _ = pedir("/sono?dias=999%3Cscript%3E", ck)
confere("período inválido volta ao padrão sem quebrar nem refletir", st == 200 and "<script>alert" not in corpo, st)
st, corpo, _ = pedir("/dados", ck)
confere("estado dos dados mostra em dia", "em dia" in corpo and "passos" not in corpo.lower().split("<table")[0], corpo[:500])
st, corpo, _ = pedir("/nao-existe", ck)
confere("página inexistente dá 404", st == 404, st)
st, corpo, _ = pedir("/semana", ck, dados=b"x=1")
confere("POST fora de /sair é recusado (somente leitura)", st == 405, st)
st, corpo, _ = pedir("/sair", ck, dados=b"csrf=errado")
confere("sair sem token CSRF é recusado", st == 403, st)
st, corpo, cab = pedir("/sair", ck, dados=("csrf=" + sess["csrf"]).encode())
confere("sair encerra a sessão", st == 303 and "Max-Age=0" in cab.get("Set-Cookie", "") and pedir("/", ck)[0] == 303, (st, cab))

# estado atrasado: dado mais antigo que 2 dias aparece como alerta
con = sqlite3.connect(banco.DB_PATH)
con.execute("DELETE FROM saude_diaria WHERE metrica = 'passos' AND dia >= ?", ((datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),))
con.commit()
con.close()
token, _ = hc.nova_sessao()
st, corpo, _ = pedir("/dados", f"{ps.COOKIE}={token}")
confere("dado parado há dias vira alerta", "dias sem dado novo" in corpo and "Sem dado novo há mais de 2 dias" in corpo and "Passos" in corpo, corpo[:600])

# escape de HTML vindo dos dados
confere("texto das análises é escapado", "&lt;" in ps.texto_html("<img src=x onerror=alert(1)>") and "<img" not in ps.texto_html("<img src=x>"), ps.texto_html("<img>"))
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
