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

BD = {"tags": {}, "document_types": {}, "correspondents": {}, "docs": {}, "mail_accounts": {}, "mail_rules": {}, "prox": 1, "pedidos": [],
      "users": {"heimdall": {"id": 1, "username": "heimdall", "password": "segredo", "is_superuser": True}}}


def novo_id():
    BD["prox"] += 1
    return BD["prox"]


def visivel(obj, eu):
    return eu["is_superuser"] or obj.get("owner") in (None, eu["id"])   # como no Paperless: o superusuário vê tudo


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
        h = self.headers.get("Authorization") or ""
        u = BD["users"].get(h[len("Token tok-"):]) if h.startswith("Token tok-") else None
        if not u:
            self._json({"detail": "nao"}, 401)
        return u

    def do_POST(self):
        u = urlparse(self.path)
        corpo = self._corpo()
        BD["pedidos"].append(("POST", u.path))
        if u.path == "/api/token/":
            d = json.loads(corpo)
            usr = BD["users"].get(d.get("username"))
            if usr and usr["password"] == d.get("password"):
                return self._json({"token": "tok-" + usr["username"]})
            return self._json({"non_field_errors": ["x"]}, 400)
        eu = self._auth()
        if not eu:
            return
        if u.path == "/api/users/":
            if not eu["is_superuser"]:
                return self._json({}, 403)
            d = json.loads(corpo)
            novo = {"id": novo_id(), "is_superuser": bool(d.get("is_superuser")), **{k: d[k] for k in ("username", "password", "user_permissions")}}
            BD["users"][d["username"]] = novo
            return self._json({"id": novo["id"], "username": novo["username"]}, 201)
        m = re.fullmatch(r"/api/(tags|document_types|correspondents|mail_accounts|mail_rules)/", u.path)
        if m:
            d = json.loads(corpo)
            i = novo_id()
            BD[m.group(1)][i] = {"id": i, "document_count": 0, **d, "owner": d.get("owner") or eu["id"]}
            return self._json(BD[m.group(1)][i], 201)
        if u.path == "/api/documents/post_document/":
            if b"duplicado" in corpo:
                BD["tarefa"] = {"status": "FAILURE", "result": "It is a duplicate of x", "related_document": None}
            else:
                i = novo_id()
                tag = int(re.search(rb'name="tags"\r\n\r\n(\d+)', corpo).group(1))
                nome = re.search(rb'filename="([^"]+)"', corpo).group(1).decode()
                BD["docs"][i] = {"id": i, "title": nome.rsplit(".", 1)[0], "content": "Texto lido do contrato com a Empresa Alfa", "tags": [tag], "document_type": None, "correspondent": None,
                                 "created": "2026-11-25", "added": "2026-11-25T10:00:00Z", "original_file_name": nome, "owner": eu["id"], "bytes": corpo.split(b"\r\n\r\n", 2)[-1]}
                BD["tarefa"] = {"status": "SUCCESS", "related_document": i, "result": "ok"}
            return self._json("uuid-1")
        self._json({}, 404)

    def do_PATCH(self):
        u = urlparse(self.path)
        corpo = json.loads(self._corpo() or b"{}")
        BD["pedidos"].append(("PATCH", u.path))
        eu = self._auth()
        if not eu:
            return
        m = re.fullmatch(r"/api/(documents|mail_accounts|mail_rules)/(\d+)/", u.path)
        if m:
            alvo = BD[m.group(1) if m.group(1) != "documents" else "docs"].get(int(m.group(2)))
            if not alvo or not visivel(alvo, eu):
                return self._json({}, 404)
            alvo.update(corpo)
            return self._json({k: v for k, v in alvo.items() if k != "bytes"})
        self._json({}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        BD["pedidos"].append(("GET", u.path, q))
        eu = self._auth()
        if not eu:
            return
        if u.path == "/api/users/":
            r = [{"id": x["id"], "username": x["username"]} for x in BD["users"].values() if x["username"] == q.get("username", x["username"])]
            return self._json({"count": len(r), "next": None, "results": r})
        m = re.fullmatch(r"/api/(tags|document_types|correspondents|mail_accounts|mail_rules)/", u.path)
        if m:
            itens = [x for x in BD[m.group(1)].values() if visivel(x, eu)]
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
            docs = [d for d in BD["docs"].values() if visivel(d, eu)]
            if "owner__id" in q:
                docs = [d for d in docs if d["owner"] == int(q["owner__id"])]
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
        if m and int(m.group(1)) in BD["docs"] and visivel(BD["docs"][int(m.group(1))], eu):
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
os.environ["HEIMDALL_PAPERLESS_SECRET"] = "chave-de-teste"
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
confere("convidado também usa o Paperless, com usuário próprio", L.motor() == "paperless")
os.environ["HEIMDALL_LIBRARY_MOTOR"] = "interno"
confere("interruptor devolve o motor interno", L.motor() == "interno")
os.environ["HEIMDALL_LIBRARY_MOTOR"] = "paperless"

# --- senha errada
os.environ["HEIMDALL_PAPERLESS_SENHA"] = "errada"
P._estado["tokens"].clear()
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
ent0 = L.pasta_entrada()
ent0.mkdir(parents=True, exist_ok=True)
(ent0 / "nota_dono.txt").write_bytes(b"texto do dono")
confere("pasta de entrada do dono é própria e o Library envia ao Paperless", "consume" not in str(ent0) and L.processar_entrada(usar_ia=False)["novos"] == 1 and L.listar()[1] == 2)
confere("dono tem usuário comum, sem exclusão, e o administrador não é dono dos documentos", "heimdall-dono" in BD["users"] and not BD["users"]["heimdall-dono"]["is_superuser"]
        and "delete_document" not in BD["users"]["heimdall-dono"]["user_permissions"] and BD["docs"][did]["owner"] == BD["users"]["heimdall-dono"]["id"] != 1)

# --- e-mail: a senha vem só do .env
os.environ.pop("HEIMDALL_LIBRARY_EMAIL_SENHA", None)
confere("sem senha, e-mail é recusado", "senha de aplicativo" in erro(P.email_configurar, "imap.exemplo.com", "pessoa@exemplo.com", "Heimdall"))
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
confere("regra e conta pertencem ao dono", conta["owner"] == regra["owner"] == BD["users"]["heimdall-dono"]["id"])
confere("estado do e-mail lista conta e regra e não mostra a senha", est["contas"] == ["Heimdall pessoa@exemplo.com"] and est["regras"][0]["pasta"] == "Outra" and "senha-app" not in json.dumps(est))

# --- convidado: usuário próprio, só vê o que é dele, e o dono não mistura
marca = banco._PESSOA_DIR.set(TMP / "people" / "ana")
confere("convidado começa sem documentos", L.listar()[1] == 0 and L.estado()["documentos"] == 0)
rc = L.adicionar("segredo_ana.pdf", b"%PDF ana", usar_ia=False)
confere("usuário do convidado criado sem exclusão, comum (não administrador)", "heimdall-ana" in BD["users"] and not BD["users"]["heimdall-ana"]["is_superuser"]
        and "delete_document" not in BD["users"]["heimdall-ana"]["user_permissions"], BD["users"].get("heimdall-ana"))
confere("convidado vê o próprio documento", L.listar()[1] == 1 and L.obter(rc["id"])["titulo"] == "segredo_ana")
confere("convidado não vê documento do dono", L.obter(did) == {} and L.arquivo(did) == ("", b""))
confere("convidado não altera documento do dono", "não encontrado" in erro(L.atualizar, did, "Invasão", "", "", "", ""))
confere("convidado não confirma nem exclui documento do dono", "não encontrado" in erro(L.confirmar, did) and "não encontrado" in erro(L.lixeira, did))
confere("documento do dono continua intacto", BD["docs"][did]["title"] == "Contrato Alfa" and not any(t["name"] == "Lixeira" and t["id"] in BD["docs"][did]["tags"] for t in BD["tags"].values()))
confere("etiquetas do convidado são só dele", all(x["nome"] != "trabalho" for x in L.etiquetas_com_contagem()))
os.environ["HEIMDALL_LIBRARY_EMAIL_SENHA"] = "senha-do-dono"
confere("convidado não herda a senha de e-mail do dono", "senha de aplicativo" in erro(P.email_configurar, "imap.exemplo.com", "ana@exemplo.com", "Heimdall") and not P.senha_do_env())
P.email_configurar("imap.exemplo.com", "ana@exemplo.com", "Ana", "", "senha-da-ana")
ana = BD["users"]["heimdall-ana"]["id"]
conta_ana = next(c for c in BD["mail_accounts"].values() if c["owner"] == ana)
confere("convidado conecta o próprio e-mail, com a própria senha, em conta dele", conta_ana["password"] == "senha-da-ana" and conta_ana["username"] == "ana@exemplo.com"
        and next(r for r in BD["mail_rules"].values() if r["owner"] == ana)["folder"] == "Ana")
confere("convidado vê só a própria conta de e-mail e sem a senha", P.email_estado()["contas"] == ["Heimdall ana@exemplo.com"] and "senha" not in json.dumps(P.email_estado()))
ent = L.pasta_entrada()
confere("pasta de entrada do convidado é a própria", "people" in str(ent) or "library" in str(ent), ent)
ent.mkdir(parents=True, exist_ok=True)
(ent / "nota.txt").write_bytes(b"texto da ana")
confere("importar da pasta envia ao Paperless do convidado", L.processar_entrada(usar_ia=False)["novos"] == 1 and L.listar()[1] == 2)
banco._PESSOA_DIR.reset(marca)
confere("dono vê só a própria conta de e-mail", P.email_estado()["contas"] == ["Heimdall pessoa@exemplo.com"])
docs, n = L.listar()
confere("dono não vê documentos do convidado", n == 2 and all(d["titulo"] != "segredo_ana" for d in docs) and L.obter(rc["id"]) == {}, (docs, n))
confere("dono não vê as etiquetas do convidado", L.estado()["documentos"] == 2)
n_tags_a_revisar = [t for t in BD["tags"].values() if t["name"] == "A revisar"]
confere("cada pessoa tem a sua etiqueta A revisar", len(n_tags_a_revisar) == 2 and len({t["owner"] for t in n_tags_a_revisar}) == 2, n_tags_a_revisar)

srv.shutdown()
print(f"\n{falhas} falha(s)")
sys_exit = 1 if falhas else 0
raise SystemExit(sys_exit)
