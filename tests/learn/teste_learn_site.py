#!/usr/bin/env python3
"""Testa o site do Heimdall Learn: login exigido, host permitido, CSRF, criação de pasta, tipo, importação multipart, acessibilidade."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import sys
import os
import re
import tempfile
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
os.environ["HEIMDALL_LEARN_MAX_MB"] = "1"
(TMP / "knowledge" / "aws").mkdir(parents=True)

import heimdall_cloud as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, sess = nuvem.nova_sessao("learn")
cookie = f"{nuvem.COOKIE}={token}"


def req(metodo, caminho, corpo=None, cab=None, host="localhost", com_cookie=True):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    h = {"Host": host}
    if com_cookie:
        h["Cookie"] = cookie
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def form(campos):
    from urllib.parse import urlencode
    return urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"}


def multipart(campos, arquivo=None):
    b = uuid.uuid4().hex
    partes = b""
    for k, v in campos.items():
        partes += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    if arquivo:
        partes += f'--{b}\r\nContent-Disposition: form-data; name="arquivo"; filename="{arquivo[0]}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + arquivo[1] + b"\r\n"
    partes += f"--{b}--\r\n".encode()
    return partes, {"Content-Type": f"multipart/form-data; boundary={b}"}


st, _, _ = req("GET", "/saude", com_cookie=False)
confere("saúde responde sem login", st == 200)
st, _, _ = req("GET", "/", host="evil.example", com_cookie=False)
confere("host não permitido é recusado", st == 421, st)
st, _, r = req("GET", "/", com_cookie=False)
confere("sem login vai para entrar", st == 303 and r.getheader("Location") == "/entrar", st)
st, _, _ = req("GET", "/pasta?c=aws", com_cookie=False)
confere("pasta exige login", st == 303)

st, corpo, r = req("GET", "/")
confere("início abre", st == 200 and "Pastas de estudo" in corpo, st)
confere("início cadastra pasta existente (aws)", "aws" in corpo.lower())
confere("lang pt-BR, um h1, pular para o conteúdo", 'lang="pt-BR"' in corpo and corpo.count("<h1>") == 1 and "Pular para o conteúdo" in corpo)
confere("tabela com caption e scope", "<caption>" in corpo and 'scope="col"' in corpo and 'scope="row"' in corpo)
confere("CSP sem unsafe-inline de script", "script-src 'nonce-" in r.getheader("Content-Security-Policy") and "script-src 'unsafe" not in r.getheader("Content-Security-Policy"))

st, corpo, _ = req("GET", "/nova")
csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
confere("formulário tem labels", all(f'for="{i}"' in corpo for i in ("nome", "categoria", "tipo", "idioma")))

c, h = form({"nome": "Inglês", "categoria": "sequencial", "tipo": "Idiomas", "idioma": "inglês"})
st, _, _ = req("POST", "/criar", c, h)
confere("POST sem csrf é recusado", st == 403, st)
c, h = form({"csrf": csrf, "nome": "Inglês", "categoria": "sequencial", "tipo": "Idiomas", "idioma": "inglês"})
st, _, r = req("POST", "/criar", c, h)
confere("criar pasta redireciona para ela", st == 303 and "/pasta?c=" in r.getheader("Location"), (st, r.getheader("Location")))
destino = r.getheader("Location")
st, corpo, _ = req("GET", destino)
confere("página da pasta mostra categoria e tipo", st == 200 and "Sequencial" in corpo and "Idiomas" in corpo and "criada." in corpo, re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", corpo, flags=re.S)[:900])
confere("aviso de sucesso usa role status", 'role="status"' in corpo)

c, h = form({"csrf": csrf, "nome": "Inglês", "categoria": "sequencial", "tipo": "Idiomas", "idioma": "inglês"})
st, _, r = req("POST", "/criar", c, h)
st2, corpo, _ = req("GET", r.getheader("Location"))
confere("pasta repetida dá erro com role alert", "alert" in corpo, corpo[-300:])

c, h = form({"csrf": csrf, "nome": "Grego", "categoria": "sequencial", "tipo": "Idiomas", "idioma": ""})
st, _, r = req("POST", "/criar", c, h)
_, corpo, _ = req("GET", r.getheader("Location"))
confere("idiomas sem idioma é recusado", "alert" in corpo and r.getheader("Location") == "/nova")

c, h = form({"csrf": csrf, "nome": "Cálculo", "categoria": "aleatorio", "tipo": "", "tipo_novo": "Cálculo avançado"})
st, _, r = req("POST", "/criar", c, h)
_, corpo, _ = req("GET", "/tipos")
confere("tipo novo vira cadastrado", "Cálculo avançado" in corpo)

c, h = form({"csrf": csrf, "nome": "Alemão"})
st, _, r = req("POST", "/tipo", c, h)
_, corpo, _ = req("GET", "/tipos")
confere("cadastro de tipo", "Alemão" in corpo)

rel = "ingles"
p = multipart({"csrf": csrf, "c": rel}, ("licao1.txt", b"hello world"))
st, _, r = req("POST", "/importar", p[0], p[1])
confere("importar documento", st == 303 and (TMP / "knowledge" / rel / "licao1.txt").is_file(), (st, list((TMP / "knowledge").rglob("*"))))
_, corpo, _ = req("GET", "/pasta?c=" + rel)
confere("documento aparece na tabela", "licao1.txt" in corpo and "importado" in corpo)
modo = (TMP / "knowledge" / rel / "licao1.txt").stat().st_mode & 0o777
confere("arquivo importado 0600", modo == 0o600, oct(modo))

p = multipart({"csrf": "errado", "c": rel}, ("x.txt", b"x"))
st, _, _ = req("POST", "/importar", p[0], p[1])
confere("importar sem csrf válido é recusado", st == 403 and not (TMP / "knowledge" / rel / "x.txt").exists())
p = multipart({"csrf": csrf, "c": rel}, ("programa.exe", b"MZ"))
st, _, r = req("POST", "/importar", p[0], p[1])
_, corpo, _ = req("GET", "/pasta?c=" + rel)
confere("extensão perigosa não entra", not (TMP / "knowledge" / rel / "programa.exe").exists() and "alert" in corpo)
p = multipart({"csrf": csrf, "c": "../../etc"}, ("a.txt", b"x"))
st, _, r = req("POST", "/importar", p[0], p[1])
confere("fuga de pasta não grava", not (TMP / "etc").exists() and not list(TMP.rglob("a.txt")))
p = multipart({"csrf": csrf, "c": rel}, ("grande.txt", b"x" * (2 * 1024 * 1024)))
st, corpo, _ = req("POST", "/importar", p[0], p[1])
confere("arquivo acima do limite é recusado", st == 413 and not (TMP / "knowledge" / rel / "grande.txt").exists(), st)

c, h = form({"csrf": csrf, "c": rel, "categoria": "aleatorio", "tipo": "Filosofia", "idioma": ""})
st, _, r = req("POST", "/atualizar", c, h)
_, corpo, _ = req("GET", "/pasta?c=" + rel)
confere("atualizar categoria e tipo", "Aleatório" in corpo and "Filosofia" in corpo)

st, corpo, _ = req("GET", "/pasta?c=../../etc")
confere("GET com caminho suspeito não vaza", st in (200, 400, 404) and "root:" not in corpo)
st, _, _ = req("POST", "/inexistente", *form({"csrf": csrf}))
confere("rota POST desconhecida é 405", st == 405)
st, _, r = req("POST", "/sair", *form({"csrf": csrf}))
confere("sair encerra a sessão", st == 303 and r.getheader("Location") == "/entrar")

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
