#!/usr/bin/env python3
"""Testa o campo Perguntar do Learn: aparece nas abas do tema e na lista de temas, usa só os dados de estudo do tema (com os trechos estudados, sem gabarito de lição em aberto,
sem o livro inteiro), exige CSRF, valida o retorno e responde pelo modelo (de mentira aqui).

    python3 tests/learn/teste_learn_perguntar.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import heimdall_lab as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
import heimdall_learn_painel as painel  # noqa: E402
import heimdall_perguntar as perguntar  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


d.criar_pasta("Dados", "sequencial", "Programação")
d.criar_pasta("Esoterismo", "aleatorio", "Outro")
con = d.conectar()
exs = [{"tipo": "texto", "enunciado": "O que é uma fila?", "gabarito": "GABARITO-SECRETO-ABERTA"}]
con.execute("INSERT INTO licoes (pasta, numero, titulo, explicacao, trecho_estudo, exercicios, estado, criado) VALUES ('dados', 1, 'Filas', 'EXPLICACAO-DA-LICAO', 'TRECHO-DA-LICAO', ?, 'pronta', '2026-11-23 10:00:00')", (json.dumps(exs),))
con.execute("INSERT INTO respostas (licao_id, ex_idx, resposta, correto, correcao, criado) VALUES (1, 0, 'não sei', 0, 'faltou o conceito', '2026-11-23 10:05:00')")
exs2 = [{"tipo": "texto", "enunciado": "O que é cache?", "gabarito": "GABARITO-CONCLUIDA"}]
con.execute("INSERT INTO licoes (pasta, numero, titulo, exercicios, estado, nota, criado) VALUES ('dados', 2, 'Cache', ?, 'concluida', 0.5, '2026-11-23 11:00:00')", (json.dumps(exs2),))
con.execute("INSERT INTO respostas (licao_id, ex_idx, resposta, correto, correcao, criado) VALUES (2, 0, 'guarda dados', 0.5, 'parcial', '2026-11-23 11:05:00')")
con.execute("INSERT INTO estudos (pasta, documento, trecho_idx, trecho, pergunta, resposta, correcao, estado, criado) VALUES ('esoterismo', 'livro.md', 0, 'TRECHO-DO-LIVRO-ENVIAR', 'O que é a tríade?', 'três partes', 'certo', 'corrigido', '2026-11-23 12:00:00')")
con.commit()

ctx = painel.contexto_do_tema("dados")
confere("contexto do tema traz progresso, lições e erros", "Pasta dados" in ctx and "Filas" in ctx and "O que é uma fila?" in ctx and "não sei" in ctx)
confere("o gabarito de lição em aberto não entra; o de lição concluída entra", "GABARITO-SECRETO-ABERTA" not in ctx and "GABARITO-CONCLUIDA" in ctx)
confere("o contexto de um tema não mistura outro tema", "tríade" not in ctx and "TRECHO-DO-LIVRO" not in ctx and "tríade" in painel.contexto_do_tema("esoterismo"))
confere("o trecho estudado entra, para poder perguntar sobre o texto", "TRECHO-DO-LIVRO-ENVIAR" in painel.contexto_do_tema("esoterismo") and "TRECHO-DA-LICAO" in ctx and "EXPLICACAO-DA-LICAO" in ctx)
con.execute("INSERT INTO estudos (pasta, documento, trecho_idx, trecho, estado, criado) VALUES ('esoterismo', 'grande.md', 1, ?, 'sorteado', '2026-11-23 12:30:00')", ("x" * 5000,))
con.commit()
confere("trecho muito longo é cortado e o livro inteiro nunca vai", len(painel.contexto_do_tema("esoterismo")) < 6000 and "x" * 1300 not in painel.contexto_do_tema("esoterismo"))
confere("sem tema, o contexto cobre todos", "tríade" in painel.contexto_do_tema("") and "Filas" in painel.contexto_do_tema(""))
confere("o contexto é limitado", len(painel.contexto_do_tema("", 300)) <= 300)

pedidos = []
perguntar.chamar_local = lambda sistema, usuario, modelo="", max_tokens=700, timeout=240, usar_nuvem=True: (pedidos.append((sistema, usuario)) or "Você errou o conceito de fila. Revise a lição 1.")

srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("*")


def req(metodo, caminho, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def post(rota, campos):
    return req("POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


_, home, _ = req("GET", "/")
csrf = re.search(r'name="csrf" value="([^"]+)"', home).group(1)
confere("a lista de temas tem o campo Perguntar", 'id="pergunta"' in home and "Perguntar sobre os estudos" in home)
for aba in ("estudos", "licoes", "exercicios", "cards", "progresso"):
    _, corpo, _ = req("GET", f"/{aba}?t=dados")
    confere(f"aba {aba} tem o campo Perguntar, com label", 'for="pergunta"' in corpo and "Perguntar sobre este tema" in corpo)
_, aj, _ = req("GET", "/ajustes")
confere("Ajustes não tem o campo Perguntar", 'id="pergunta"' not in aj)

volta = "/licoes?t=dados"
st, _, _ = post("/perguntar", {"csrf": "x", "pergunta": "onde erro?", "volta": volta})
confere("perguntar sem csrf é recusado", st == 403 and not pedidos)
st, _, r = post("/perguntar", {"csrf": csrf, "pergunta": "onde estou errando?", "volta": volta})
confere("perguntar volta para a mesma aba", st == 303 and r.getheader("Location") == volta, r.getheader("Location"))
corpo = ""
for _ in range(60):
    _, corpo, _ = req("GET", volta)
    if "Você errou o conceito de fila" in corpo:
        break
    time.sleep(0.1)
confere("a resposta aparece na aba do tema", "Você errou o conceito de fila" in corpo and "onde estou errando?" in corpo)
confere("o modelo recebeu o contexto do tema e o prompt do Learn", pedidos and "O que é uma fila?" in pedidos[0][1] and "tríade" not in pedidos[0][1] and "Learn" not in pedidos[0][0] and "CONTEXTO" in pedidos[0][0])
confere("o gabarito aberto não foi ao modelo", "GABARITO-SECRETO-ABERTA" not in pedidos[0][1])
_, outro, _ = req("GET", "/estudos?t=esoterismo")
confere("a resposta de um tema não aparece em outro", "Você errou o conceito de fila" not in outro)
st, _, r = post("/perguntar", {"csrf": csrf, "pergunta": "x", "volta": "https://evil.example/"})
confere("retorno fora do site é trocado pela lista de temas", st == 303 and r.getheader("Location") == "/", r.getheader("Location"))
n = len(pedidos)
post("/perguntar", {"csrf": csrf, "pergunta": "oi", "volta": "/"})
time.sleep(0.3)
confere("pergunta curta demais é ignorada", len(pedidos) == n)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
