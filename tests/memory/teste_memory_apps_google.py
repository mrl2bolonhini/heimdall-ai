#!/usr/bin/env python3
"""Testa o conector do Google do Memory contra serviços simulados (Agenda, Tarefas e Contatos): escopos de leitura só para os serviços marcados, acesso offline com PKCE,
paginação, eventos cancelados ignorados, atualização no lugar, renovação do token e revogação (invalid_grant)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="google_"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "STUDIO_HUB_IA": "0",
                   "STUDIO_NUVEM_CHAVE": "chave-de-teste", "STUDIO_NUVEM_GOOGLE_ID": "g-id", "STUDIO_NUVEM_GOOGLE_SEGREDO": "g-seg", "STUDIO_HUB_URL": "https://memory.exemplo.test"})
ESTADO = {"tokens": 0, "revogado": False, "chamadas": [], "etag": "e1", "form": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, o, c=200):
        b = json.dumps(o).encode()
        self.send_response(c)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        f = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        if self.path != "/token":
            return self._j({}, 404)
        if f.get("grant_type") == "authorization_code":
            ESTADO["form"] = f
            if f.get("code") != "codigo-bom" or not f.get("code_verifier") or f.get("client_secret") != "g-seg":
                return self._j({"error": "invalid_grant"}, 400)
            ESTADO["tokens"] += 1
            return self._j({"access_token": f"g-acesso{ESTADO['tokens']}", "refresh_token": "g-renov", "expires_in": 1})
        if ESTADO["revogado"] or f.get("refresh_token") != "g-renov":
            return self._j({"error": "invalid_grant"}, 400)
        ESTADO["tokens"] += 1
        self._j({"access_token": f"g-acesso{ESTADO['tokens']}", "expires_in": 3600})

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if not (self.headers.get("Authorization") or "").startswith("Bearer g-acesso"):
            return self._j({}, 401)
        ESTADO["chamadas"].append(p.path)
        if p.path == "/cal/calendars/primary/events":
            assert q["singleEvents"] == ["true"] and "timeMin" in q
            if q.get("pageToken") == ["e2"]:
                return self._j({"items": [{"id": "ev2", "status": "cancelled", "summary": "Cancelado"}]})
            return self._j({"items": [{"id": "ev1", "summary": "Audiência de conciliação", "location": "Fórum Central", "start": {"dateTime": "2026-12-02T14:00:00-03:00"},
                                       "end": {"dateTime": "2026-12-02T15:00:00-03:00"}, "description": "Levar procuração", "updated": "2026-11-23T10:00:00Z", "organizer": {"email": "vara@exemplo.test"}},
                                      {"id": "ev3", "summary": "Feriado", "start": {"date": "2026-12-08"}, "end": {"date": "2026-12-09"}, "updated": "2026-11-01T10:00:00Z"}], "nextPageToken": "e2"})
        if p.path == "/tar/users/@me/lists":
            return self._j({"items": [{"id": "L1", "title": "Pessoal"}]})
        if p.path == "/tar/lists/L1/tasks":
            return self._j({"items": [{"id": "T1", "title": "Pagar o condomínio", "status": "needsAction", "due": "2026-12-05T00:00:00.000Z", "notes": "Boleto no e-mail", "updated": "2026-11-22T10:00:00Z"},
                                      {"id": "T2", "title": "", "status": "needsAction"}]})
        if p.path == "/pes/people/me/connections":
            assert "names" in q["personFields"][0]
            return self._j({"connections": [{"resourceName": "people/c1", "etag": ESTADO["etag"], "names": [{"displayName": "João Pereira"}], "emailAddresses": [{"value": "joao@exemplo.test"}],
                                             "phoneNumbers": [{"value": "11 98888-0000" if ESTADO["etag"] == "e1" else "11 97777-1111"}], "organizations": [{"name": "Pereira Advogados", "title": "Sócio"}]}]})
        self._j({}, 404)


fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORTA = fake.server_address[1]
threading.Thread(target=fake.serve_forever, daemon=True).start()
F = f"http://127.0.0.1:{PORTA}"

import heimdall_conexoes as cx  # noqa: E402
import heimdall_memory_apps as ap  # noqa: E402
import heimdall_memory_dados as dados  # noqa: E402

dados.PROJECT_DIR = TMP
cx.PERMITE_HTTP = True
cx.PROVEDORES["google"].update({"token": F + "/token", "bases": {"agenda": F + "/cal", "tarefas": F + "/tar", "contatos": F + "/pes"}})
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def texto_de(trecho):
    d = [x for x in dados.listar(por_pagina=100)[0] if trecho in (x["titulo"] or "")]
    return dados.obter(d[0]["id"])["texto"] if d else ""


confere("Google aparece como app configurado", "google" in cx.configurados("apps") and "google" not in cx.configurados("arquivos"))
url = cx.iniciar("google", False, ["agenda", "contatos", "inventado"])
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
confere("endereço: acesso offline, consentimento, PKCE e só os escopos marcados",
        url.startswith("https://accounts.google.com/o/oauth2/v2/auth?") and q["access_type"] == ["offline"] and q["prompt"] == ["consent"] and q["code_challenge_method"] == ["S256"]
        and q["scope"] == ["https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/contacts.readonly"], q)
ok, msg = cx.concluir(q["state"][0], "codigo-bom")
confere("conecta e lista os serviços", ok and "Google Agenda" in msg and "Google Contatos" in msg and "Tarefas" not in msg, msg)
confere("o token usa o segredo do administrador e o verificador PKCE", ESTADO["form"].get("client_secret") == "g-seg" and ESTADO["form"].get("code_verifier"), ESTADO["form"])
confere("tokens cifrados em disco", b"g-renov" not in (TMP / "memory" / "nuvem.bin").read_bytes())
time.sleep(1.1)   # o primeiro token vale 1 s: força a renovação
r = ap.sincronizar("google")
ev, ct = texto_de("Audiência"), texto_de("João")
confere("renovou o acesso e importou o evento, o feriado de dia inteiro e o contato; evento cancelado e tarefas ficaram de fora",
        ESTADO["tokens"] == 2 and r["novos"] == 3 and r["erros"] == 0 and not texto_de("Cancelado") and "/tar/users/@me/lists" not in ESTADO["chamadas"], (r, ESTADO["tokens"], ESTADO["chamadas"]))
confere("evento com local, organizador e descrição; dia inteiro identificado", "Google Agenda" in ev and "Local: Fórum Central" in ev and "Levar procuração" in ev and "vara@exemplo.test" in ev and "(dia inteiro)" in texto_de("Feriado"), ev)
confere("contato com empresa, cargo, e-mail e telefone", "Empresa: Pereira Advogados" in ct and "Cargo: Sócio" in ct and "joao@exemplo.test" in ct and "11 98888-0000" in ct, ct)
r = ap.sincronizar("google")
confere("segunda rodada não repete", r["novos"] == 0 and r["atualizados"] == 0, r)
ESTADO["etag"] = "e2"
r = ap.sincronizar("google")
confere("contato alterado (etag nova) é atualizado no mesmo documento", r["atualizados"] == 1 and r["novos"] == 0 and "97777-1111" in texto_de("João") and dados.listar(por_pagina=100)[1] == 3, r)
q = urllib.parse.parse_qs(urllib.parse.urlparse(cx.iniciar("google", False, ["agenda", "tarefas", "contatos"])).query)
cx.concluir(q["state"][0], "codigo-bom")
r = ap.sincronizar("google")
t = texto_de("condomínio")
confere("tarefas: documento com lista, situação, prazo e notas; tarefa vazia ignorada", r["novos"] == 1 and "Google Tarefas · lista Pessoal" in t and "a fazer" in t and "Prazo: 2026-12-05" in t and "Boleto no e-mail" in t, (r, t))
todos = cx.carregar()
todos["google"]["expira"] = 0
cx.gravar(todos)
ESTADO["revogado"] = True
try:
    ap.sincronizar("google")
    erro = ""
except dados.ErroMemory as ex:
    erro = str(ex)
sit = [x for x in ap.situacao() if x["chave"] == "google"][0]
confere("acesso revogado (invalid_grant) pede nova conexão", "Conecte de novo" in erro and not sit["conectado"], (erro, sit))
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
