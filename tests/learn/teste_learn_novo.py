#!/usr/bin/env python3
"""Testa o Novo estudo do Learn (nome, arquivos, categoria e tipo numa tela só) e o Resumo da tela inicial.

    python3 tests/learn/teste_learn_novo.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import heimdall_cloud as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
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
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("*")


def req(metodo, caminho, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def multipart(campos, arquivos):
    b = "----teste"
    partes = []
    for k, v in campos.items():
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for nome, conteudo in arquivos:
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="arquivo"; filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + conteudo + b"\r\n")
    partes.append(f"--{b}--\r\n".encode())
    return b"".join(partes), {"Content-Type": f"multipart/form-data; boundary={b}"}


_, home, _ = req("GET", "/")
csrf = re.search(r'name="csrf" value="([^"]+)"', home).group(1)
confere("sem temas, a tela inicial manda usar Novo estudo", "Nenhum tema cadastrado" in home and "Novo estudo" in home)

c, h = multipart({"csrf": csrf, "nome": "Python", "pai": "", "categoria": "", "tipo": "Programação", "tipo_novo": "", "idioma": ""},
                 [("a.md", b"# A\n\nTexto a"), ("b.txt", b"Texto b"), ("c.exe", b"MZ")])
st, _, r = req("POST", "/criar", c, h)
loc = r.getheader("Location")
pasta = d.obter_pasta("python")
confere("criar com arquivos redireciona para a pasta e cria com o tipo escolhido", st == 303 and loc == "/pasta?c=python" and pasta and pasta["tipo"] == "Programação" and pasta["categoria"] == "sequencial", (st, loc, pasta))
nomes = [x["nome"] for x in d.listar_documentos("python")]
confere("os arquivos aceitos foram importados e o inválido não", "a.md" in nomes and "b.txt" in nomes and "c.exe" not in nomes, nomes)
_, corpo, _ = req("GET", loc)
confere("a página avisa o que entrou e o que não entrou", "2 arquivos importados" in corpo and "c.exe" in corpo, re.sub(r"<[^>]+>", " ", corpo)[:300])

c, h = multipart({"csrf": csrf, "nome": "Sem arquivo", "pai": "", "categoria": "aleatorio", "tipo": "Outro", "tipo_novo": "", "idioma": ""}, [])
st, _, r = req("POST", "/criar", c, h)
confere("criar sem arquivos também funciona", st == 303 and d.obter_pasta("sem-arquivo") is not None)

c, h = multipart({"csrf": csrf, "nome": "Tipo sem nome", "pai": "", "categoria": "", "tipo": "__novo__", "tipo_novo": "", "idioma": ""}, [])
st, _, r = req("POST", "/criar", c, h)
_, corpo, _ = req("GET", r.getheader("Location"))
confere("tipo novo sem nome é recusado e nada é criado", r.getheader("Location") == "/nova" and "nome do tipo novo" in corpo and d.obter_pasta("tipo-sem-nome") is None)
c, h = multipart({"csrf": csrf, "nome": "Cálculo", "pai": "", "categoria": "", "tipo": "__novo__", "tipo_novo": "Cálculo avançado", "idioma": ""}, [])
st, _, r = req("POST", "/criar", c, h)
confere("tipo novo com nome é cadastrado e usado", st == 303 and "Cálculo avançado" in d.listar_tipos() and d.obter_pasta("calculo")["tipo"] == "Cálculo avançado")
st, _, _ = req("POST", "/criar", *multipart({"csrf": "x", "nome": "Zé", "tipo": "Outro"}, []))
confere("criar sem csrf é recusado", st == 403 and d.obter_pasta("ze") is None)
st, _, r = req("POST", "/criar", urlencode({"csrf": csrf, "nome": "Pelo formulário simples", "tipo": "Outro", "categoria": "", "pai": "", "idioma": ""}), {"Content-Type": "application/x-www-form-urlencoded"})
confere("o envio simples (sem arquivos) continua aceito", st == 303 and d.obter_pasta("pelo-formulario-simples") is not None)

con = d.conectar()
con.execute("INSERT INTO estudos (pasta, documento, trecho_idx, trecho, pergunta, estado, criado) VALUES ('python', 'a.md', 0, 't', 'p', 'perguntado', '2026-11-23 10:00:00')")
con.execute("INSERT INTO licoes (pasta, numero, titulo, exercicios, estado, criado) VALUES ('python', 1, 'L', '[]', 'pronta', '2026-11-23 10:00:00')")
con.commit()
_, home, _ = req("GET", "/")
resumo = re.sub(r"<[^>]+>", " ", home)
confere("Resumo em texto: total de temas, documentos, estudos e lições", re.search(r"4 temas cadastrados, com 2 documentos de consulta, 1 estudo e 1 lição no total", resumo) is not None, resumo[resumo.find("Resumo"):][:260])
confere("cada tema mostra categoria e os seus números", re.search(r"Python\s*:\s*Sequencial\.\s*2 documentos de consulta, 1 estudo e 1 lição", resumo) is not None, resumo[resumo.find("Temas"):][:400])
confere("a lista de temas é uma lista numerada com link para o tema", '<ol><li><a href="/tema?t=' in home)
_, nova, _ = req("GET", "/nova")
confere("a explicação de cada tipo está ligada ao botão de opção (acessível)", nova.count('aria-describedby="tipo_') >= 5 and "<legend>Tipo de estudo</legend>" in nova)
print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
