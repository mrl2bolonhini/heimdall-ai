#!/usr/bin/env python3
"""Testa os conectores de tarefas e quadros do Memory contra servidores simulados: Microsoft Planner (conta de trabalho ou escola; conta pessoal recusada),
Todoist (OAuth sem PKCE, token sem expiração, revogação) e Trello (token no fragmento entregue por POST, chave de API no cabeçalho, state de uso único)."""
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

TMP = Path(tempfile.mkdtemp(prefix="apps2_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_MEMORY_IA": "0",
                   "HEIMDALL_NUVEM_CHAVE": "chave-de-teste", "HEIMDALL_NUVEM_ONEDRIVE_ID": "app-ms-id", "HEIMDALL_NUVEM_TODOIST_ID": "todo-id",
                   "HEIMDALL_NUVEM_TODOIST_SEGREDO": "todo-seg", "HEIMDALL_NUVEM_TRELLO_ID": "chave-trello-publica", "HEIMDALL_MEMORY_URL": "https://memory.exemplo.test"})

TOKEN_TRELLO = "ATTA" + "a1b2c3d4" * 8
ESTADO = {"pessoal": False, "todoist_revogado": False, "token_todoist": "tdst-token-1", "detalhes": 0, "form_todoist": None, "marca_plano": '"etag-1"'}


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
        if self.path == "/ms/token":
            return self._j({"access_token": "acesso-ms", "refresh_token": "renov-ms", "expires_in": 3600})
        if self.path == "/todoist/token":
            ESTADO["form_todoist"] = f
            if f.get("code") != "codigo-bom" or f.get("client_secret") != "todo-seg":
                return self._j({"error": "bad_authorization_code"}, 400)
            return self._j({"access_token": ESTADO["token_todoist"], "token_type": "Bearer"})
        self._j({}, 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        aut = self.headers.get("Authorization") or ""
        if p.path.startswith("/ms/"):
            if aut != "Bearer acesso-ms":
                return self._j({}, 401)
            if p.path.startswith("/ms/me/planner") and ESTADO["pessoal"]:
                return self._j({"error": "Forbidden"}, 403)
            if p.path == "/ms/me/planner/plans":
                return self._j({"value": [{"id": "pl1", "title": "Reforma da sede"}]})
            if p.path == "/ms/me/planner/tasks":
                return self._j({"value": [{"id": "pt1", "title": "Contratar pedreiro", "planId": "pl1", "percentComplete": 50, "dueDateTime": "2026-12-05T00:00:00Z",
                                           "@odata.etag": ESTADO["marca_plano"]}]})
            if p.path == "/ms/planner/tasks/pt1/details":
                ESTADO["detalhes"] += 1
                return self._j({"description": "Pedir três orçamentos.", "checklist": {"a": {"title": "Ligar para a obra", "isChecked": True}, "b": {"title": "Comparar preços", "isChecked": False}}})
            return self._j({}, 404)
        if p.path.startswith("/todoist/"):
            if aut != "Bearer " + ESTADO["token_todoist"] or ESTADO["todoist_revogado"]:
                return self._j({}, 401)
            if p.path == "/todoist/projects":
                return self._j({"results": [{"id": "pr1", "name": "Casa"}], "next_cursor": None})
            if p.path == "/todoist/tasks":
                if q.get("cursor") == ["c2"]:
                    return self._j({"results": [{"id": "t3", "content": "Trocar a lâmpada", "description": "", "project_id": "pr1", "labels": [], "priority": 1, "due": None, "checked": False}], "next_cursor": None})
                return self._j({"results": [{"id": "t1", "content": "Renovar o seguro", "description": "Pedir cotação", "project_id": "pr1", "labels": ["urgente"], "priority": 4,
                                             "due": {"date": "2026-12-01", "string": "1 dez"}, "checked": False},
                                            {"id": "t2", "content": "Comprar tinta", "description": "", "project_id": "pr1", "labels": [], "priority": 1, "due": None, "checked": False}], "next_cursor": "c2"})
            return self._j({}, 404)
        if p.path.startswith("/trello/"):
            if aut != f'OAuth oauth_consumer_key="chave-trello-publica", oauth_token="{TOKEN_TRELLO}"' or "token" in q or "key" in q:
                return self._j({}, 401)
            if p.path == "/trello/members/me":
                return self._j({"id": "m1"})
            if p.path == "/trello/members/me/boards":
                return self._j([{"id": "b1", "name": "Escritório"}])
            if p.path == "/trello/boards/b1/lists":
                return self._j([{"id": "li1", "name": "Em andamento"}])
            if p.path == "/trello/boards/b1/cards":
                return self._j([{"id": "c1", "name": "Revisar contrato de locação", "desc": "Conferir reajuste.", "due": "2026-12-09T12:00:00.000Z", "dueComplete": False, "idList": "li1",
                                 "dateLastActivity": "2026-11-24T10:00:00Z", "labels": [{"name": "Contratos", "color": "blue"}]}])
        self._j({}, 404)


fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORTA = fake.server_address[1]
threading.Thread(target=fake.serve_forever, daemon=True).start()
F = f"http://127.0.0.1:{PORTA}"

import heimdall_conexoes as cx  # noqa: E402
import heimdall_lab as hc  # noqa: E402
import heimdall_memory as lib  # noqa: E402
import heimdall_memory_apps as ap  # noqa: E402
import heimdall_memory_dados as dados  # noqa: E402
import heimdall_servico_web as web  # noqa: E402

dados.PROJECT_DIR = TMP
cx.PERMITE_HTTP = True
cx.PROVEDORES["microsoft"].update({"auth": "https://auth.exemplo.test/ms", "token": F + "/ms/token", "api": F + "/ms"})
cx.PROVEDORES["todoist"].update({"token": F + "/todoist/token", "api": F + "/todoist"})
cx.PROVEDORES["trello"].update({"api": F + "/trello"})
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
    except dados.ErroMemory as ex:
        return str(ex)
    return ""


def textos():
    return list(dados.listar(por_pagina=100)[0])


def texto_de(trecho):
    d = [x for x in textos() if trecho in (x["titulo"] or "")]
    return dados.obter(d[0]["id"])["texto"] if d else ""


# --- configuração
confere("Todoist e Trello aparecem como apps configurados e não como nuvem", {"todoist", "trello"} <= set(cx.configurados("apps")) and not {"todoist", "trello"} & set(cx.configurados("arquivos")))

# --- Planner
url = cx.iniciar("microsoft", False, ["tarefas", "planner"])
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
confere("To Do e Planner pedem o escopo Tasks.Read uma só vez", q["scope"] == ["offline_access Tasks.Read"], q["scope"])
ok, msg = cx.concluir(q["state"][0], "x")
confere("conecta o Microsoft com Planner", ok and "Planner" in msg, msg)
r = ap.sincronizar("microsoft")
t = texto_de("Contratar pedreiro")
confere("tarefa do Planner vira documento com plano, situação, prazo e lista de verificação",
        "Microsoft Planner · plano Reforma da sede" in t and "em andamento" in t and "Prazo: 2026-12-05" in t and "- [x] Ligar para a obra" in t and "- [ ] Comparar preços" in t and "Pedir três orçamentos" in t, t)
r = ap.sincronizar("microsoft")
confere("sem mudança (mesma etiqueta) não baixa os detalhes de novo nem duplica", ESTADO["detalhes"] == 1 and r["novos"] == 0 and r["atualizados"] == 0, (ESTADO["detalhes"], r))
ESTADO["pessoal"] = True
r = ap.sincronizar("microsoft")
sit = [x for x in ap.situacao() if x["chave"] == "microsoft"][0]
confere("conta pessoal: mensagem clara sobre o Planner e a conexão continua", "conta Microsoft de trabalho ou escola" in sit["erro"] and sit["conectado"], sit)
ESTADO["pessoal"] = False

# --- Todoist
url = cx.iniciar("todoist", False, ["tarefas"])
u = urllib.parse.urlparse(url)
q = urllib.parse.parse_qs(u.query)
confere("Todoist: endereço, escopo data:read e state, sem PKCE nem redirect_uri", url.startswith("https://app.todoist.com/oauth/authorize?") and q["scope"] == ["data:read"] and "state" in q
        and "code_challenge" not in q and "redirect_uri" not in q and "client_id=todo-id" in url, url)
ok, msg = cx.concluir(q["state"][0], "codigo-bom")
confere("Todoist conecta (token sem renovação)", ok and "Todoist" in msg, msg)
confere("o token enviado ao provedor usa o segredo do administrador e não o verificador PKCE", ESTADO["form_todoist"].get("client_secret") == "todo-seg" and "code_verifier" not in ESTADO["form_todoist"], ESTADO["form_todoist"])
bruto = (TMP / "memory" / "nuvem.bin").read_bytes()
confere("token do Todoist cifrado em disco", b"tdst-token" not in bruto)
r = ap.sincronizar("todoist")
t1, t3 = texto_de("Renovar o seguro"), texto_de("lâmpada")
confere("importa as tarefas das duas páginas", r["novos"] == 3 and r["erros"] == 0 and t3, r)
confere("tarefa com projeto, prazo, prioridade, etiqueta e descrição", "Todoist · projeto Casa" in t1 and "Prazo: 1 dez" in t1 and "Prioridade: urgente" in t1 and "Etiquetas: urgente" in t1 and "Pedir cotação" in t1, t1)
r = ap.sincronizar("todoist")
confere("segunda rodada não repete", r["novos"] == 0 and r["atualizados"] == 0, r)
ESTADO["todoist_revogado"] = True
r = ap.sincronizar("todoist")
sit = [x for x in ap.situacao() if x["chave"] == "todoist"][0]
confere("token revogado no app: pede nova conexão", not sit["conectado"] and "Conecte de novo" in sit["erro"], sit)
ESTADO["todoist_revogado"] = False
confere("state de uso único: repetir o retorno é recusado", not cx.concluir(q["state"][0], "codigo-bom")[0])
ok, msg = cx.concluir(cx.iniciar("todoist", False, ["tarefas"]).split("state=")[1].split("&")[0], "codigo-ruim")
confere("código recusado pelo provedor não conecta", not ok and not [x for x in ap.situacao() if x["chave"] == "todoist"][0]["conectado"], msg)
ok, msg = cx.concluir(cx.iniciar("todoist", False, ["tarefas"]).split("state=")[1].split("&")[0], "codigo-bom")
confere("reconectar funciona", ok and ap.sincronizar("todoist")["erros"] == 0)

# --- Trello
url = cx.iniciar("trello", False, ["quadros"])
u = urllib.parse.urlparse(url)
q = urllib.parse.parse_qs(u.query)
ret = urllib.parse.urlparse(q["return_url"][0])
state = urllib.parse.parse_qs(ret.query)["state"][0]
confere("Trello: endereço com chave, escopo read, token por fragmento e state no retorno", url.startswith("https://trello.com/1/authorize?") and q["key"] == ["chave-trello-publica"] and q["scope"] == ["read"]
        and q["response_type"] == ["token"] and q["callback_method"] == ["fragment"] and ret.path == "/nuvem/retorno" and ret.netloc == "memory.exemplo.test", url)
confere("Trello exige escolher o serviço", "pelo menos um serviço" in erro(cx.iniciar, "trello", False, []))

# telas e retorno com POST público
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


s, h, r = req("GET", f"/nuvem/retorno?state={state}")
csp = r.getheader("Content-Security-Policy") or ""
confere("retorno do Trello: página com formulário para /nuvem/trello e script com nonce (sem sessão)", s == 200 and 'action="/nuvem/trello"' in h and 'name="token"' in h and "location.hash" in h
        and "script-src 'nonce-" in csp and re.search(r'<script nonce="[^"]+">', h) and "<noscript>" in h, (s, csp, h[-400:]))
confere("a página de retorno não repete o token e o state continua válido até o POST", cx.provedor_do_state(state) == "trello")
s, h, _ = req("POST", "/nuvem/trello", {"state": "inventado", "token": TOKEN_TRELLO})
confere("POST público com state desconhecido é recusado", "expirou ou já foi usada" in h and not [x for x in ap.situacao() if x["chave"] == "trello"][0]["conectado"], h[-200:])
s, h, _ = req("POST", "/nuvem/trello", {"state": state, "token": "curto"})
confere("token com formato inválido é recusado e consome o state", "não foi concluída" in h and cx.provedor_do_state(state) == "")
q2 = urllib.parse.parse_qs(urllib.parse.urlparse(cx.iniciar("trello", False, ["quadros"])).query)
state2 = urllib.parse.parse_qs(urllib.parse.urlparse(q2["return_url"][0]).query)["state"][0]
s, h, _ = req("POST", "/nuvem/trello", {"state": state2, "token": "A" * 40})
confere("token que o Trello não confirma não conecta", "não confirmou" in h and not [x for x in ap.situacao() if x["chave"] == "trello"][0]["conectado"], h[-200:])
q3 = urllib.parse.parse_qs(urllib.parse.urlparse(cx.iniciar("trello", False, ["quadros"])).query)
state3 = urllib.parse.parse_qs(urllib.parse.urlparse(q3["return_url"][0]).query)["state"][0]
s, h, _ = req("POST", "/nuvem/trello", {"state": state3, "token": TOKEN_TRELLO})
confere("token confirmado pelo Trello conecta", s == 200 and "Trello conectado" in h and [x for x in ap.situacao() if x["chave"] == "trello"][0]["conectado"], h[-300:])
s, h, _ = req("POST", "/nuvem/trello", {"state": state3, "token": TOKEN_TRELLO})
confere("o mesmo state não vale duas vezes", "expirou ou já foi usada" in h)
confere("token do Trello cifrado em disco", TOKEN_TRELLO.encode() not in (TMP / "memory" / "nuvem.bin").read_bytes())
r = ap.sincronizar("trello")
t = texto_de("Revisar contrato")
confere("cartão vira documento com quadro, lista, prazo, etiqueta e descrição (token só no cabeçalho)",
        r["novos"] == 1 and r["erros"] == 0 and "quadro Escritório · lista Em andamento" in t and "Prazo: 2026-12-09" in t and "Etiquetas: Contratos" in t and "Conferir reajuste" in t, (r, t))
r = ap.sincronizar("trello")
confere("segunda rodada do Trello não repete", r["novos"] == 0 and r["atualizados"] == 0, r)

# --- tela Apps
tk = hc.nova_sessao()[0]
s, h, _ = req("GET", "/apps", cookie=tk)
confere("tela Apps mostra as seções Microsoft, Todoist e Trello; o Planner avisa que exige conta de trabalho ou escola",
        all(f"<h2>{n}</h2>" in h for n in ("Microsoft", "Todoist", "Trello")) and "Microsoft Planner (só conta de trabalho ou escola)" in h and "Cartões do Trello" in h and "Tarefas do Todoist" in h, h[:300])
confere("a rodada de fundo percorre os três provedores", cx.sincronizar_todos()["pessoas"] >= 1)
srv.shutdown()
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
