#!/usr/bin/env python3
"""Testa o motor Paperless-ngx do Library contra um servidor falso que imita a API REST: token, etiquetas, tipos, emissores, documentos, envio, tarefas, e-mail e a escolha do motor."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TMP = _Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")

BD = {"tags": {}, "document_types": {}, "correspondents": {}, "docs": {}, "mail_accounts": {}, "mail_rules": {}, "prox": 1, "pedidos": []}


def novo_id(tipo):
    BD["prox"] += 1
    return BD["prox"]


def ordem(nome):
    return next((i for i, x in BD[nome].items()), None)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, codigo=200):
        b = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self):
        if self.headers.get("Authorization") != "Token tok123":
            self._json({"detail": "nao"}, 401)
            return False
        return True

    def do_POST(self):
        u = urlparse(self.path)
        corpo = self._corpo()
        BD["pedidos"].append(("POST", u.path))
        if u.path == "/api/token/":
            d = json.loads(corpo)
            if d.get("username") == "heimdall" and d.get("password") == "segredo":
                return self._json({"token": "tok123"})
            return self._json({"non_field_errors": ["x"]}, 400)
        if not self._auth():
            return
        m = re.fullmatch(r"/api/(tags|document_types|correspondents|mail_accounts|mail_rules)/", u.path)
        if m:
            d = json.loads(corpo)
            i = novo_id(m.group(1))
            BD[m.group(1)][i] = {"id": i, "document_count": 0, **d}
            return self._json(BD[m.group(1)][i], 201)
        if u.path == "/api/documents/post_document/":
            if b"duplicado" in corpo:
                BD["tarefa"] = {"status": "FAILURE", "result": "It is a duplicate of x", "related_document": None}
            else:
                i = novo_id("docs")
                tag = int(re.search(rb'name="tags"\r\n\r\n(\d+)', corpo).group(1))
                nome = re.search(rb'filename="([^"]+)"', corpo).group(1).decode()
                BD["docs"][i] = {"id": i, "title": nome.rsplit(".", 1)[0], "content": "Texto lido do contrato com a Empresa Alfa", "tags": [tag], "document_type": None, "correspondent": None,
                                 "created": "2026-11-25", "added": "2026-11-25T10:00:00Z", "original_file_name": nome, "bytes": corpo.split(b"\r\n\r\n", 2)[-1]}
                BD["tarefa"] = {"status": "SUCCESS", "related_document": i, "result": "ok"}
            return self._json("uuid-1")
        self._json({}, 404)

    def do_PATCH(self):
        u = urlparse(self.path)
        corpo = json.loads(self._corpo() or b"{}")
        BD["pedidos"].append(("PATCH", u.path))
        if not self._auth():
            return
        m = re.fullmatch(r"/api/(documents|mail_accounts|mail_rules)/(\d+)/", u.path)
        if m:
            alvo = BD[m.group(1) if m.group(1) != "documents" else "docs"][int(m.group(2))]
            alvo.update(corpo)
            return self._json({k: v for k, v in alvo.items() if k != "bytes"})
        self._json({}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        BD["pedidos"].append(("GET", u.path, q))
        if not self._auth():
            return
        m = re.fullmatch(r"/api/(tags|document_types|correspondents|mail_accounts|mail_rules)/", u.path)
        if m:
            itens = list(BD[m.group(1)].values())
            if m.group(1) == "tags":
                for t in itens:
                    t["document_count"] = sum(1 for d in BD["docs"].values() if t["id"] in d["tags"])
            if m.group(1) == "document_types":
                for t in itens:
                    t["document_count"] = sum(1 for d in BD["docs"].values() if d["document_type"] == t["id"])
            return self._json({"count": len(itens), "next": None, "results": itens})
        if u.path == "/api/tasks/":
            return self._json([BD["tarefa"]])
        if u.path == "/api/documents/":
            docs = list(BD["docs"].values())
            if "tags__id__all" in q:
                tem = [int(x) for x in q["tags__id__all"].split(",")]
                docs = [d for d in docs if all(t in d["tags"] for t in tem)]
            if "tags__id__none" in q:
                docs = [d for d in docs if int(q["tags__id__none"]) not in d["tags"]]
            if "document_type__id" in q:
                docs = [d for d in docs if d["document_type"] == int(q["document_type__id"])]
            if "query" in q:
                termos = [t.rstrip("*").lower() for t in re.split(r" OR | ", q["query"])]
                docs = [d for d in docs if any(t in (d["content"] + d["title"]).lower() for t in termos)]
            ini = (int(q.get("page", 1)) - 1) * int(q.get("page_size", 25))
            pg = docs[ini:ini + int(q.get("page_size", 25))]
            if not pg and ini:
                return self._json({"detail": "x"}, 404)
            return self._json({"count": len(docs), "next": None, "results": [{k: v for k, v in d.items() if k != "bytes"} for d in pg]})
        m = re.fullmatch(r"/api/documents/(\d+)/(download/)?", u.path)
        if m and int(m.group(1)) in BD["docs"]:
            d = BD["docs"][int(m.group(1))]
            if m.group(2):
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(d["bytes"])))
                self.end_headers()
                return self.wfile.write(d["bytes"])
            return self._json({k: v for k, v in d.items() if k != "bytes"})
        self._json({}, 404)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["HEIMDALL_PAPERLESS_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
os.environ["HEIMDALL_PAPERLESS_USER"] = "heimdall"
os.environ["HEIMDALL_PAPERLESS_SENHA"] = "segredo"
os.environ["HEIMDALL_LIBRARY_MOTOR"] = "paperless"

import heimdall_banco as banco  # noqa: E402
import heimdall_library_dados as L  # noqa: E402
import heimdall_library_paperless as P  # noqa: E402

L.PROJECT_DIR = TMP
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except L.ErroLibrary as ex:
        return str(ex)
    return ""


# --- escolha do motor
confere("dono usa o Paperless", L.motor() == "paperless")
marca = banco._PESSOA_DIR.set(TMP / "convidado")
confere("convidado usa o acervo interno", L.motor() == "interno")
banco._PESSOA_DIR.reset(marca)
os.environ["HEIMDALL_LIBRARY_MOTOR"] = "interno"
confere("interruptor devolve o motor interno", L.motor() == "interno")
os.environ["HEIMDALL_LIBRARY_MOTOR"] = "paperless"

# --- senha errada
os.environ["HEIMDALL_PAPERLESS_SENHA"] = "errada"
P._estado["token"] = ""
confere("senha recusada vira mensagem clara", "recusou" in erro(L.estado))
os.environ["HEIMDALL_PAPERLESS_SENHA"] = "segredo"

# --- envio
r = L.adicionar("contrato_alfa.pdf", b"%PDF-1.4 conteudo", usar_ia=False)
confere("envio cria documento e etiqueta A revisar", r["novo"] and r["id"] > 0 and any(t["name"] == "A revisar" for t in BD["tags"].values()), r)
confere("formato não aceito é recusado", "Formato" in erro(L.adicionar, "x.exe", b"abc"))
confere("arquivo vazio é recusado", "vazio" in erro(L.adicionar, "x.pdf", b""))
d2 = L.adicionar("duplicado.pdf", b"duplicado", usar_ia=False)
confere("duplicado não é novo", d2["novo"] is False)
did = r["id"]

# --- consulta
docs, n = L.listar(so_revisar=True)
confere("A revisar lista o novo", n == 1 and docs[0]["revisado"] == 0 and docs[0]["etiquetas"] == [], (docs, n))
docs, n = L.listar(q="contrato")
confere("busca por texto", n == 1)
docs, n = L.listar(q="inexistente")
confere("busca sem resultado", n == 0)
docs, n = L.listar(pagina=9)
confere("página além do fim não quebra", n == 0 and docs == [])
confere("obter devolve o documento", L.obter(did)["titulo"] == "contrato_alfa")
confere("obter com id inválido", L.obter("abc") == {} and L.obter(9999) == {})
nome, conteudo = L.arquivo(did)
confere("download do original", nome == "contrato_alfa.pdf" and conteudo.startswith(b"%PDF"), (nome, conteudo))

# --- correção ensina o Paperless
L.atualizar(did, "Contrato Alfa", "Contrato", "2026-03-12", "Empresa Alfa", "trabalho, 2026")
doc = L.obter(did)
confere("atualizar grava título, tipo, emissor, data e etiquetas", doc["titulo"] == "Contrato Alfa" and doc["tipo"] == "Contrato" and doc["emissor"] == "Empresa Alfa" and doc["data_doc"] == "2026-03-12" and doc["etiquetas"] == ["2026", "trabalho"], doc)
confere("salvar confirma o documento, como no acervo interno", doc["revisado"] == 1)
L.lixeira(did); L.lixeira(did, restaurar=True)
BD["docs"][did]["tags"].append(next(i for i, t in BD["tags"].items() if t["name"] == "A revisar"))
confere("confirmar tira A revisar", L.obter(did)["revisado"] == 0 and (L.confirmar(did) or True) and L.obter(did)["revisado"] == 1)
confere("data inválida é recusada", "AAAA-MM-DD" in erro(L.atualizar, did, "Contrato Alfa", "Contrato", "12/03/2026", "", ""))
confere("título curto é recusado", "título" in erro(L.atualizar, did, "x", "", "", "", ""))
confere("nada em A revisar", L.listar(so_revisar=True)[1] == 0)
docs, n = L.listar(tipo="Contrato")
confere("filtro por tipo", n == 1)
docs, n = L.listar(etiqueta="trabalho")
confere("filtro por etiqueta", n == 1)
confere("contagens de etiquetas e tipos", {"nome": "trabalho", "n": 1} in L.etiquetas_com_contagem() and ("Contrato", 1) in L.tipos_com_contagem() and all(e["nome"] != "A revisar" for e in L.etiquetas_com_contagem()))

# --- lixeira
L.lixeira(did)
confere("excluir manda para a lixeira (nada é apagado)", L.listar()[1] == 0 and L.listar(lixeira=True)[1] == 1 and L.obter(did)["lixeira"] == 1 and not any(p[0] == "DELETE" for p in BD["pedidos"]))
L.atualizar(did, "Contrato Alfa", "Contrato", "", "Empresa Alfa", "trabalho")
confere("editar não tira da lixeira", L.obter(did)["lixeira"] == 1)
L.lixeira(did, restaurar=True)
confere("restaurar", L.listar()[1] == 1 and L.listar(lixeira=True)[1] == 0)

# --- estado e entrada
e = L.estado()
confere("estado mostra o motor", e["motor"] == "Paperless-ngx" and e["documentos"] == 1 and e["lixeira"] == 0, e)
confere("pasta de entrada do Paperless", str(L.pasta_entrada()).endswith("paperless/consume") and L.processar_entrada()["novos"] == 0)

# --- e-mail: a senha vem só do .env
os.environ.pop("HEIMDALL_LIBRARY_EMAIL_SENHA", None)
confere("sem senha no .env, e-mail é recusado", ".env" in erro(P.email_configurar, "imap.exemplo.com", "pessoa@exemplo.com", "Heimdall"))
os.environ["HEIMDALL_LIBRARY_EMAIL_SENHA"] = "senha-app"
confere("servidor inválido é recusado", "Confira" in erro(P.email_configurar, "x y", "pessoa@exemplo.com", "Heimdall"))
msg = P.email_configurar("IMAP.exemplo.com", "pessoa@exemplo.com", "Heimdall", "")
conta = next(iter(BD["mail_accounts"].values()))
regra = next(iter(BD["mail_rules"].values()))
confere("conta IMAP criada", conta["imap_server"] == "imap.exemplo.com" and conta["imap_port"] == 993 and conta["password"] == "senha-app", conta)
confere("regra lê só a pasta e marca A revisar", regra["folder"] == "Heimdall" and regra["account"] == conta["id"] and len(regra["assign_tags"]) == 1 and "A revisar" in msg, regra)
P.email_configurar("imap.exemplo.com", "pessoa@exemplo.com", "Outra", "")
confere("repetir atualiza em vez de duplicar", len(BD["mail_accounts"]) == 1 and len(BD["mail_rules"]) == 1 and next(iter(BD["mail_rules"].values()))["folder"] == "Outra")
est = P.email_estado()
confere("estado do e-mail lista conta e regra e não mostra a senha", est["contas"] == ["Heimdall pessoa@exemplo.com"] and est["regras"][0]["pasta"] == "Outra" and "senha-app" not in json.dumps(est))

srv.shutdown()
print(f"\n{falhas} falha(s)")
sys_exit = 1 if falhas else 0
raise SystemExit(sys_exit)
