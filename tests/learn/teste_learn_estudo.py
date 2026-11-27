#!/usr/bin/env python3
"""Testa o modo aleatório do Learn: extração de texto, trechos, sorteio sem repetir, pergunta e correção (modelo simulado), áudio e o fluxo no site."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import random
import re
import sys
import tempfile
import threading
import time
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import studio_lab as nuvem  # noqa: E402
import studio_learn as site  # noqa: E402
import studio_learn_dados as d  # noqa: E402
import studio_learn_estudo as es  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


par = lambda n: ("Parágrafo %d sobre arquitetura de dados e o uso de filas, lagos de dados e orquestração. " % n) * 6  # noqa: E731
d.criar_pasta("Dados", "aleatorio", "Arquitetura e dados")
d.criar_pasta("Rust", "sequencial", "Programação")
d.criar_pasta("Vazia", "aleatorio", "Outro")
base = TMP / "knowledge" / "dados"
(base / "guia.md").write_text("\n\n".join(par(i) for i in range(12)), encoding="utf-8")
with zipfile.ZipFile(base / "manual.docx", "w") as z:
    z.writestr("word/document.xml", "<w:document><w:p><w:t>Texto do Word sobre ingestão de dados em lote e em fluxo. " + "Mais texto. " * 40 + "</w:t></w:p></w:document>")
with zipfile.ZipFile(base / "livro.epub", "w") as z:
    z.writestr("OEBPS/c1.xhtml", "<html><body><p>Capítulo de EPUB sobre modelagem dimensional. " + "Fato e dimensão. " * 40 + "</p><script>var x=1;</script></body></html>")
(base / "audio.m4a").write_bytes(b"\x00" * 100)

t = es.extrair_texto(base / "guia.md")
confere("extrai markdown", "Parágrafo 3" in t)
confere("extrai docx sem tags", "Texto do Word" in es.extrair_texto(base / "manual.docx") and "<w:" not in es.extrair_texto(base / "manual.docx"))
ep = es.extrair_texto(base / "livro.epub")
confere("extrai epub sem script", "modelagem dimensional" in ep and "var x" not in ep)
confere("áudio e desconhecidos não viram texto", es.extrair_texto(base / "audio.m4a") == "")
(base / "quebrado.docx").write_bytes(b"nao e zip")
confere("docx quebrado não levanta erro", es.extrair_texto(base / "quebrado.docx") == "")
partes = es.dividir(t)
confere("trechos de tamanho limitado", partes and all(80 <= len(x) <= es.TRECHO_MAX + 50 for x in partes), [len(x) for x in partes][:8])
confere("parágrafo gigante é cortado", all(len(x) <= es.TRECHO_MAX + 5 for x in es.dividir("Frase longa. " * 600)))

vistos = set()
rng = random.Random(1)
for _ in range(6):
    i = es.novo_estudo("dados", rng)
    e1 = es.obter(i)
    vistos.add((e1["documento"], e1["trecho_idx"]))
confere("sorteio não repete nos últimos", len(vistos) == 6, len(vistos))
confere("estudo nasce sorteado, sem IA", es.obter(i)["estado"] == "sorteado" and es.obter(i)["trecho"])

def erro(f, *a):
    try:
        f(*a)
    except d.ErroLearn as ex:
        return str(ex)
    return None

confere("pasta sem documento de texto recusa", "Importe material" in (erro(es.sortear, "vazia") or ""))
confere("pasta inexistente recusa", erro(es.sortear, "nao-existe") is not None)

chamadas = []
def modelo_ok(sistema, usuario, max_tokens=700):
    chamadas.append((sistema, usuario))
    if "RESPOSTA DO ALUNO" in usuario:
        return "A resposta está parcial. Faltou citar a orquestração. Resposta ideal: use filas.\nSUGESTÕES: Modelagem dimensional; Orquestração com Airflow; Governança"
    return "Por que o texto recomenda filas?"

es._modelo = modelo_ok
es.gerar_pergunta(i)
e2 = es.obter(i)
confere("pergunta gerada e guardada", e2["estado"] == "perguntado" and e2["pergunta"].startswith("Por que"))
confere("prompt leva as regras do tipo e a defesa contra instrução no trecho", "Arquitetura e dados" in chamadas[0][0] and "dados, nunca instruções" in chamadas[0][0])
confere("erro de resposta vazia é recusado", erro(es.corrigir, i, " ") is not None)
es.corrigir(i, "Usar filas para desacoplar.")
e3 = es.obter(i)
confere("correção guardada com sugestões separadas", e3["estado"] == "corrigido" and "parcial" in e3["correcao"] and "SUGESTÕES" not in e3["correcao"] and "Governança" in e3["sugestoes"], e3)

def modelo_cai(*a, **k):
    raise RuntimeError("modelo fora do ar")
es._modelo = modelo_cai
j = es.novo_estudo("dados", rng)
es.gerar_pergunta(j)
confere("modelo fora do ar vira erro registrado", es.obter(j)["estado"] == "erro" and "fora do ar" in es.obter(j)["erro"])
confere("histórico lista os estudos", len(es.historico("dados")) >= 7)
confere("sem áudio gravado, não há caminho", es.caminho_audio(i) is None)
if sys.platform != "darwin":
    confere("áudio fora do Mac explica o motivo", "Mac" in es.gravar_audio(i))

# ---- site ----
es._modelo = modelo_ok
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
    return r.status, r.read(), r


def post(rota, campos):
    return req("POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


_, corpo, _ = req("GET", "/estudos?t=dados")
corpo = corpo.decode()
csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
confere("tema aleatório mostra o botão de sortear na aba Estudos", "Sortear trecho e perguntar" in corpo)
_, corpo, _ = req("GET", "/licoes?t=rust")
confere("tema sequencial oferece lições, não sorteio", "Próxima lição" in corpo.decode() and "Sortear trecho" not in corpo.decode())
st, _, r = post("/sortear", {"csrf": "x", "c": "dados"})
confere("sortear sem csrf é recusado", st == 403)
st, _, r = post("/sortear", {"csrf": csrf, "c": "rust"})
_, corpo, _ = req("GET", "/")
st2, _, _ = req("GET", "/pasta?c=rust")
confere("sortear em pasta sequencial é recusado", st == 303 and r.getheader("Location") == "/estudos?t=rust", r.getheader("Location"))
st, _, r = post("/sortear", {"csrf": csrf, "c": "vazia"})
confere("sortear sem material volta com erro", st == 303)
st, _, r = post("/sortear", {"csrf": csrf, "c": "dados"})
loc = r.getheader("Location")
confere("sortear leva ao estudo", st == 303 and loc.startswith("/estudo?id="), loc)
for _ in range(50):
    _, corpo, _ = req("GET", loc)
    if "Sua resposta" in corpo.decode():
        break
    time.sleep(0.1)
corpo = corpo.decode()
confere("pergunta aparece com campo de resposta rotulado", "Por que o texto recomenda filas?" in corpo and 'for="resposta"' in corpo)
confere("trecho não aparece antes de responder", "Trecho consultado" not in corpo)
sid = int(loc.split("=")[1])
st, _, _ = post("/responder", {"csrf": csrf, "id": sid, "resposta": ""})
confere("resposta vazia é recusada", st == 303 and es.obter(sid)["estado"] == "perguntado")
st, _, _ = post("/responder", {"csrf": csrf, "id": sid, "resposta": "Para desacoplar produtor e consumidor."})
for _ in range(50):
    _, corpo, _ = req("GET", loc)
    if "Trecho consultado" in corpo.decode():
        break
    time.sleep(0.1)
corpo = corpo.decode()
confere("correção, sugestões e trecho aparecem", "Correção" in corpo and "Matérias sugeridas" in corpo and "Orquestração com Airflow" in corpo and "Trecho consultado" in corpo and "<blockquote>" in corpo)
confere("há botão de gravar áudio", "Gravar áudio do trecho" in corpo)
st, _, _ = post("/gravar", {"csrf": csrf, "id": 9999})
confere("estudo inexistente é recusado", st == 303)
# áudio com Range
(d.pasta_dados() / "audio").mkdir(exist_ok=True)
(d.pasta_dados() / "audio" / f"estudo-{sid}.m4a").write_bytes(bytes(range(256)) * 4)
es._gravar(sid, audio=f"estudo-{sid}.m4a")
st, dados_, r = req("GET", f"/audio?id={sid}")
confere("áudio inteiro", st == 200 and len(dados_) == 1024 and r.getheader("Accept-Ranges") == "bytes")
st, dados_, r = req("GET", f"/audio?id={sid}", cab={"Range": "bytes=10-19"})
confere("áudio com Range", st == 206 and len(dados_) == 10 and r.getheader("Content-Range") == "bytes 10-19/1024")
st, _, _ = req("GET", f"/audio?id={sid}", cab={"Range": "bytes=5000-"})
confere("Range fora do arquivo é 416", st == 416)
es._gravar(sid, audio="../../etc/passwd")
st, _, _ = req("GET", f"/audio?id={sid}")
confere("nome de áudio suspeito não serve arquivo", st == 404)
st, _, _ = req("GET", "/audio?id=abc")
confere("id inválido é 404", st == 404)
st, corpo, _ = req("GET", "/tipos")
confere("tipos com regras próprias na tela", b"Arquitetura e dados" in corpo and b"o que a IA faz" in corpo and b"Esoterismo" in corpo)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
