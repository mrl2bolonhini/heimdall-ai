#!/usr/bin/env python3
"""Testa a conexão do Library com apps por conta (Microsoft: OneNote, To Do, Calendário e Contatos): escopos pedidos só para os serviços marcados,
conversão de cada item em documento de texto, atualização no lugar (sem duplicar), serviço recusado sem derrubar os outros, isolamento por pessoa,
revogação e as telas /apps, contra uma Microsoft Graph simulada."""
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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="apps_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_LIBRARY_IA": "0",
                   "HEIMDALL_NUVEM_CHAVE": "chave-de-teste", "HEIMDALL_NUVEM_ONEDRIVE_ID": "app-ms-id", "HEIMDALL_LIBRARY_URL": "https://library.exemplo.test"})

ESTADO = {"revogado": False, "recusar": set(), "tokens": 0, "chamadas": []}
NOTAS = {   # id -> (título, html, marca)
    "n1": ("Reunião do condomínio", "<html><head><title>x</title><style>p{}</style></head><body><h1>Reunião do condomínio</h1><p>Ficou decidida a <b>troca do portão</b>.</p><ul><li>orçamento aprovado</li></ul></body></html>", "2026-11-20T10:00:00Z"),
    "n2": ("Receita de pão", "<html><body><p>Farinha, água e fermento biológico.</p></body></html>", "2026-11-21T10:00:00Z"),
    "n3": ("Ideias para o livro", "<html><body><p>Capítulo sobre rescisão contratual.</p></body></html>", "2026-11-22T10:00:00Z"),
}


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
            if f.get("code") != "codigo-bom" or not f.get("code_verifier"):
                return self._j({"error": "invalid_grant"}, 400)
        elif ESTADO["revogado"]:
            return self._j({"error": "invalid_grant"}, 400)
        ESTADO["tokens"] += 1
        self._j({"access_token": f"acesso{ESTADO['tokens']}", "refresh_token": f"renov{ESTADO['tokens']}", "expires_in": 3600})

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if not (self.headers.get("Authorization") or "").startswith("Bearer acesso"):
            return self._j({}, 401)
        ESTADO["chamadas"].append(p.path)
        serv = {"/me/onenote": "notas", "/me/todo": "tarefas", "/me/calendarView": "agenda", "/me/contacts": "contatos"}
        for pref, nome in serv.items():
            if p.path.startswith(pref) and nome in ESTADO["recusar"]:
                return self._j({"error": "Forbidden"}, 403)
        q = urllib.parse.parse_qs(p.query)
        if p.path == "/me/onenote/pages":
            if q.get("pag") == ["2"]:
                return self._j({"value": [{"id": "n3", "title": NOTAS["n3"][0], "lastModifiedDateTime": NOTAS["n3"][2], "parentSection": {"displayName": "Livro"}}]})
            return self._j({"value": [{"id": i, "title": t, "lastModifiedDateTime": m, "parentSection": {"displayName": "Casa"}} for i, (t, h, m) in list(NOTAS.items())[:2]],
                            "@odata.nextLink": f"http://127.0.0.1:{PORTA}/me/onenote/pages?pag=2"})
        m = re.fullmatch(r"/me/onenote/pages/([^/]+)/content", p.path)
        if m:
            b = NOTAS[m.group(1)][1].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if p.path == "/me/todo/lists":
            return self._j({"value": [{"id": "l1", "displayName": "Casa"}]})
        if p.path == "/me/todo/lists/l1/tasks":
            return self._j({"value": [{"id": "t1", "title": "Pagar o IPTU", "status": "notStarted", "importance": "high", "dueDateTime": {"dateTime": "2026-12-10T00:00:00.0000000", "timeZone": "UTC"},
                                       "body": {"content": "Cota única", "contentType": "text"}, "lastModifiedDateTime": "2026-11-23T10:00:00Z"}]})
        if p.path == "/me/calendarView":
            assert "startDateTime" in q and "endDateTime" in q
            return self._j({"value": [{"id": "e1", "subject": "Consulta com o dentista", "start": {"dateTime": "2026-12-03T14:00:00.0000000", "timeZone": "UTC"},
                                       "end": {"dateTime": "2026-12-03T15:00:00.0000000", "timeZone": "UTC"}, "location": {"displayName": "Clínica Sorriso"},
                                       "bodyPreview": "Levar exames", "lastModifiedDateTime": "2026-11-24T10:00:00Z", "isAllDay": False}]})
        if p.path == "/me/contacts":
            return self._j({"value": [{"id": "c1", "displayName": "Maria Souza", "emailAddresses": [{"address": "maria@exemplo.test"}], "mobilePhone": "11 99999-0000", "businessPhones": [],
                                       "homePhones": [], "companyName": "Souza Contabilidade", "jobTitle": "Contadora", "lastModifiedDateTime": "2026-11-19T10:00:00Z"}]})
        self._j({}, 404)


fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORTA = fake.server_address[1]
threading.Thread(target=fake.serve_forever, daemon=True).start()
F = f"http://127.0.0.1:{PORTA}"

import heimdall_conexoes as cx  # noqa: E402
import heimdall_lab as hc  # noqa: E402
import heimdall_library as lib  # noqa: E402
import heimdall_library_apps as ap  # noqa: E402
import heimdall_library_dados as dados  # noqa: E402
import heimdall_servico_web as web  # noqa: E402

dados.PROJECT_DIR = TMP
cx.PERMITE_HTTP = True
cx.PROVEDORES["microsoft"].update({"auth": "https://auth.exemplo.test/ms", "token": F + "/token", "api": F})
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except dados.ErroLibrary as ex:
        return str(ex)
    return ""


def conectar(servicos, codigo="codigo-bom"):
    url = cx.iniciar("microsoft", False, servicos)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return q, cx.concluir(q["state"][0], codigo)


def textos():
    return [d for d in dados.listar(por_pagina=100)[0]]


# --- configuração e escopos
confere("o app Microsoft usa as credenciais do OneDrive e não entra na lista de arquivos", cx.configurados("apps") == ["microsoft"] and "microsoft" not in cx.configurados("arquivos"))
confere("sem serviço marcado a conexão é recusada", "pelo menos um serviço" in erro(cx.iniciar, "microsoft", False, []))
q, (ok, msg) = conectar(["notas", "agenda", "inventado"])
confere("escopos pedidos só para os serviços marcados (serviço inventado é ignorado)", q["scope"] == ["offline_access Notes.Read Calendars.Read"] and q["code_challenge_method"] == ["S256"], q)
confere("conecta e a mensagem lista os serviços", ok and "OneNote" in msg and "Calendário do Outlook" in msg and "Tasks" not in msg, msg)
bruto = (TMP / "library" / "nuvem.bin").read_bytes()
confere("token cifrado em disco", b"renov" not in bruto and b"acesso" not in bruto)
sit = ap.situacao()[0]
confere("situação: conectado e com os serviços escolhidos", sit["conectado"] and sit["servicos"] == ["notas", "agenda"] and sit["nomes"] == ["OneNote", "Calendário do Outlook"], sit)

# --- sincronização
r = ap.sincronizar("microsoft")
docs = textos()
confere("importa as 3 notas (duas páginas) e o evento", r["novos"] == 4 and r["erros"] == 0 and len(docs) == 4, (r, len(docs)))
confere("tarefas e contatos não foram lidos (não foram marcados)", not any(c.startswith(("/me/todo", "/me/contacts")) for c in ESTADO["chamadas"]), ESTADO["chamadas"])
did = [d for d in docs if "condom" in (d["titulo"] or "").lower()][0]["id"]
texto = dados.obter(did)["texto"]
confere("a nota virou texto limpo, sem etiquetas HTML nem estilos", "troca do portão" in texto and "- orçamento aprovado" in texto and "<" not in texto and "p{}" not in texto and "OneNote · Casa" in texto, texto)
confere("a busca acha o conteúdo das notas e do evento", dados.listar(q="rescisao")[1] == 1 and dados.listar(q="dentista")[1] == 1 and dados.listar(q="Clínica Sorriso")[1] == 1)
confere("itens de app já entram como revisados (não vão para A revisar)", all(d.get("revisado") for d in docs), [d.get("revisado") for d in docs])
r = ap.sincronizar("microsoft")
confere("segunda rodada não importa nada", r["novos"] == 0 and r["atualizados"] == 0 and len(textos()) == 4, r)
chamadas_antes = ESTADO["chamadas"].count("/me/onenote/pages/n2/content")
NOTAS["n2"] = ("Receita de pão", "<html><body><p>Farinha, água, fermento e azeite de oliva.</p></body></html>", "2026-11-25T08:00:00Z")
r = ap.sincronizar("microsoft")
confere("nota alterada é atualizada no mesmo documento, sem duplicar", r["atualizados"] == 1 and r["novos"] == 0 and len(textos()) == 4 and dados.listar(q="azeite")[1] == 1 and dados.listar(q="biológico")[1] == 0, r)

# --- trocar serviços (nova autorização) e serviço recusado
q, (ok, msg) = conectar(["notas", "tarefas", "agenda", "contatos"])
confere("alterar serviços pede os escopos novos e mantém o que já foi importado", ok and "Tasks.Read" in q["scope"][0] and "Contacts.Read" in q["scope"][0] and len(textos()) == 4)
ESTADO["recusar"] = {"contatos"}
r = ap.sincronizar("microsoft")
sit = ap.situacao()[0]
confere("serviço recusado vira erro por serviço e os outros seguem", r["erros"] == 1 and r["novos"] == 1 and "Contatos do Outlook" in sit["erro"] and "OneNote" not in sit["erro"] and sit["conectado"], (r, sit))
ESTADO["recusar"] = set()
r = ap.sincronizar("microsoft")
docs = textos()
tarefa = [d for d in docs if "IPTU" in (d["titulo"] or "")]
contato = [d for d in docs if "Maria" in (d["titulo"] or "")]
confere("tarefa e contato viram documentos com os campos principais", r["novos"] == 1 and tarefa and contato
        and "a fazer" in dados.obter(tarefa[0]["id"])["texto"] and "Prazo: 2026-12-10" in dados.obter(tarefa[0]["id"])["texto"] and "maria@exemplo.test" in dados.obter(contato[0]["id"])["texto"], (r, len(docs)))

# --- convidado separado
CONV = "p0123456789ab"
with cx.como(CONV):
    confere("convidado começa sem conexão e sem documentos", not ap.situacao()[0]["conectado"] and dados.listar()[1] == 0)
    conectar(["notas"])
    r = ap.sincronizar("microsoft")
    confere("convidado importa só o que ele marcou, para o acervo dele", r["novos"] == 3 and dados.listar()[1] == 3)
confere("o acervo do dono não mudou", dados.listar()[1] == 6 or dados.listar()[1] == 7, dados.listar()[1])
confere("a rodada de fundo percorre quem tem conexão, nos dois grupos", cx.sincronizar_todos()["pessoas"] == 2)

# --- revogação
todos = cx.carregar()
todos["microsoft"]["expira"] = 0
cx.gravar(todos)
ESTADO["revogado"] = True
confere("autorização revogada pede nova conexão", "Conecte de novo" in erro(ap.sincronizar, "microsoft"))
confere("situação mostra desconectado com a mensagem", not ap.situacao()[0]["conectado"] and "Conecte de novo" in ap.situacao()[0]["erro"])
ESTADO["revogado"] = False

# --- telas
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(lib.CFG, {"localhost"}))
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()


def req(metodo, rota, corpo=None, cookie=""):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
    cab = {"Host": "localhost"}
    if cookie:
        cab["Cookie"] = f"{hc.COOKIE}={cookie}"
    dd = None
    if corpo is not None:
        dd, cab["Content-Type"] = urllib.parse.urlencode(corpo).encode(), "application/x-www-form-urlencoded"
    c.request(metodo, rota, body=dd, headers=cab)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


confere("/apps exige sessão", req("GET", "/apps")[0] == 303)
tk = hc.nova_sessao()[0]
s, h, _ = req("GET", "/apps", cookie=tk)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("tela Apps: seção Microsoft, caixas por serviço com rótulo e botão de conectar", s == 200 and "<h2>Microsoft</h2>" in h and 'name="srv_notas"' in h and 'for="srv-microsoft-notas"' in h
        and "OneNote" in h and "Microsoft To Do" in h and "Conectar Microsoft" in h and "<legend>" in h, h[:300])
s, _, r = req("POST", "/apps/conectar", {"csrf": "errado", "provedor": "microsoft", "srv_notas": "1"}, tk)
confere("conectar sem CSRF: 403", s == 403)
s, _, r = req("POST", "/apps/conectar", {"csrf": csrf, "provedor": "microsoft", "srv_notas": "1", "srv_tarefas": "1"}, tk)
loc = r.getheader("Location") or ""
confere("conectar leva ao provedor (https) com os escopos marcados", s == 303 and loc.startswith("https://auth.exemplo.test/ms?") and "Notes.Read+Tasks.Read" in loc and "Calendars" not in loc, (s, loc))
s, _, r = req("POST", "/apps/conectar", {"csrf": csrf, "provedor": "microsoft"}, tk)
confere("conectar sem marcar serviço não vai ao provedor", s != 303 or "auth.exemplo.test" not in (r.getheader("Location") or ""), (s, r.getheader("Location")))
state = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["state"][0]
s, h, _ = req("GET", f"/nuvem/retorno?state={state}&code=codigo-bom")
confere("retorno sem cookie conclui a conexão com os serviços escolhidos", s == 200 and "OneNote" in h and "Voltar ao Library" in h, h[-300:])
s, h, _ = req("GET", "/apps", cookie=tk)
confere("depois de conectar: serviços, Sincronizar agora, Desconectar e Alterar serviços", "Microsoft conectado: OneNote, Microsoft To Do" in h and "Sincronizar agora" in h and "Desconectar Microsoft" in h and "Alterar serviços" in h, h[:400])
s, _, r = req("POST", "/apps/sincronizar", {"csrf": csrf, "provedor": "microsoft"}, tk)
confere("sincronizar pela tela", s == 303 and r.getheader("Location") == "/apps")
s, _, r = req("POST", "/apps/desconectar", {"csrf": csrf, "provedor": "microsoft"}, tk)
confere("desconectar pela tela apaga o acesso e mantém os documentos", s == 303 and not ap.situacao()[0]["conectado"] and dados.listar()[1] >= 6)
s, h, _ = req("GET", "/enviar", cookie=tk)
confere("a subaba Apps aparece em Adicionar", "/apps" in h and "Apps" in h, re.findall(r"href=\"(/[a-z]+)\"", h))
srv.shutdown()
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
