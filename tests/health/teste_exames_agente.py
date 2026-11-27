#!/usr/bin/env python3
"""Testa a rota POST /saude/documento do agente (envio do iPhone) e a leitura automática, com documentos FICTÍCIOS."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-exames-agente-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_EXAMES_DIR": str(TMP / "health"), "STUDIO_EXAMES_LLM": "0",
                   "STUDIO_VAULT_DIR": str(TMP / "cofre"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(RAIZ))
import studio_agente as ag  # noqa: E402
import studio_banco as banco  # noqa: E402
import studio_exames as ex  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


def sql(q, *p):
    con = sqlite3.connect(banco.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(q, p)]
    finally:
        con.close()


def pdf_com_texto(linhas):
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    cont = ("BT /F1 10 Tf 40 800 Td 12 TL\n" + "\n".join(f"({esc(l)}) '" for l in linhas) + "\nET").encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(cont) + cont + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        pos.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % p for p in pos)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


TOKEN, ENVIO = "token-do-agente-123456", "ABCDE-FGHJK-LMNPQ-RSTUV"
ag.TOKEN, ag.TOKEN_UPLOAD = TOKEN, ENVIO
avisos = []
ag.bark.enviar_bark = lambda payload: avisos.append(payload) or True
banco.iniciar()
srv = ag.ThreadingHTTPServer(("127.0.0.1", 0), ag.Handler)
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(caminho, corpo=b"", cab=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
    h = {"Content-Length": str(len(corpo))}
    h.update(cab or {})
    c.request("POST", caminho, body=corpo, headers=h)
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados)
    except ValueError:
        return r.status, dados


DOC = pdf_com_texto(["LABORATORIO TESTE", "Data da coleta: 12/11/2026", "Vitamina D 18,5 ng/mL 30 a 100", "Ferritina 45 ng/mL 30 a 400", "TSH 2,1 uUI/mL 0,4 a 4,5"])

confere("sem token: 401", post("/saude/documento", DOC)[0] == 401)
confere("código de envio errado: 401", post("/saude/documento", DOC, {"X-Heimdall-Upload": "ERRADO-ERRADO-ERRADO-ERRADO"})[0] == 401)
confere("código de envio não vale em outras rotas", post("/banco/consultar", b'{"sql":"SELECT 1"}', {"X-Heimdall-Upload": ENVIO})[0] == 401)
confere("código de envio não abre a gravação no banco", post("/banco/gravar", b'{"tabela":"saude_diaria","registros":[]}', {"X-Heimdall-Upload": ENVIO})[0] == 401)

st, r = post("/saude/documento", DOC, {"X-Heimdall-Upload": ENVIO, "X-Heimdall-Nome": urllib.parse.quote("Exame de sangue ção.pdf")})
confere("código de envio: 200 e mensagem", st == 200 and r.get("ok") and "Recebido" in r.get("mensagem", ""), (st, r))
for _ in range(60):
    if sql("SELECT 1 FROM documentos_saude"):
        break
    time.sleep(0.25)
docs = sql("SELECT * FROM documentos_saude")
confere("o documento foi lido na hora e está pendente", len(docs) == 1 and docs[0]["estado"] == "pendente" and docs[0]["tipo"] == "exame" and docs[0]["dia"] == "2026-11-12", docs)
confere("a origem registrada é o iPhone", docs and docs[0]["origem"] == "iphone", docs)
confere("o nome higienizado não carrega o caminho", docs and "/" not in docs[0]["arquivo"])
time.sleep(0.5)
confere("Bark avisa que há documento, sem número nem nome", avisos and "18,5" not in json.dumps(avisos) and "Vitamina" not in json.dumps(avisos) and "para conferir" in avisos[0]["title"], avisos)

st, _ = post("/saude/documento", DOC, {"X-Heimdall-Token": TOKEN})
confere("o token do agente também serve (e o duplicado não entra de novo)", st == 200)
time.sleep(1.5)
confere("duplicado: continua um só documento", len(sql("SELECT 1 FROM documentos_saude")) == 1)

st, r = post("/saude/documento", b"MZ isto nao e documento", {"X-Heimdall-Upload": ENVIO})
confere("conteúdo que não é documento: 400", st == 400 and "não parece" in r.get("erro", ""), (st, r))
st, r = post("/saude/documento", b"", {"X-Heimdall-Upload": ENVIO})
confere("corpo vazio: 413", st == 413, (st, r))

c = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
c.putrequest("POST", "/saude/documento")
c.putheader("Content-Length", str(40 * 1024 * 1024))
c.putheader("X-Heimdall-Upload", ENVIO)
c.endheaders()
resp = c.getresponse()
confere("acima de 25 MB: 413 sem ler o corpo", resp.status == 413, resp.status)
c.close()

st, r = post("/saude/documento", pdf_com_texto(["Foto sem nada", "x"]), {"X-Heimdall-Upload": ENVIO, "X-Heimdall-Nome": "vazio.pdf"})
time.sleep(3)
confere("documento ilegível: vai para revisar, com motivo e aviso no Bark", any((ex.DIR / "review").glob("vazio*.pdf")) and any((ex.DIR / "review").glob("vazio*.motivo.txt"))
        and any("não lido" in a["title"] for a in avisos), (list((ex.DIR / "review").glob("*")), avisos))

srv.shutdown()
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
