#!/usr/bin/env python3
"""Testa o conector do Notion do Library contra um Notion simulado: autorização sem PKCE e sem escopos (owner=user), troca de código com autenticação básica e corpo JSON,
leitura das páginas compartilhadas (busca paginada, blocos aninhados e paginados, tabela, tarefa), conteúdo só baixado quando a página muda e revogação."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import base64
import json
import os
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="notion_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_LIBRARY_IA": "0",
                   "HEIMDALL_NUVEM_CHAVE": "chave-de-teste", "HEIMDALL_NUVEM_NOTION_ID": "nt-id", "HEIMDALL_NUVEM_NOTION_SEGREDO": "nt-seg", "HEIMDALL_LIBRARY_URL": "https://library.exemplo.test"})
ESTADO = {"revogado": False, "blocos": 0, "form": None, "versao": "", "editada": "2026-11-20T10:00:00.000Z"}


def rt(t):
    return [{"plain_text": t}]


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

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        c = self._corpo()
        if self.path == "/v1/oauth/token":
            ESTADO["form"] = (self.headers.get("Authorization"), c)
            esperado = "Basic " + base64.b64encode(b"nt-id:nt-seg").decode()
            if self.headers.get("Authorization") != esperado or c.get("code") != "codigo-bom":
                return self._j({"error": "invalid_grant"}, 400)
            return self._j({"access_token": "ntn_token1", "workspace_name": "Casa", "bot_id": "b1"})
        if self.headers.get("Authorization") != "Bearer ntn_token1" or ESTADO["revogado"]:
            return self._j({"code": "unauthorized"}, 401)
        ESTADO["versao"] = self.headers.get("Notion-Version", "")
        if self.path == "/v1/search":
            assert c["filter"] == {"property": "object", "value": "page"}
            if c.get("start_cursor") == "p2":
                return self._j({"results": [{"id": "pg2", "archived": False, "last_edited_time": "2026-11-21T10:00:00.000Z", "properties": {"Nome": {"type": "title", "title": rt("Linha do banco")}}},
                                            {"id": "pg3", "archived": True, "last_edited_time": "2026-11-21T10:00:00.000Z", "properties": {"title": {"type": "title", "title": rt("Arquivada")}}}], "has_more": False})
            return self._j({"results": [{"id": "pg1", "archived": False, "last_edited_time": ESTADO["editada"], "properties": {"title": {"type": "title", "title": rt("Plano da mudança")}}}],
                            "has_more": True, "next_cursor": "p2"})
        self._j({}, 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if self.headers.get("Authorization") != "Bearer ntn_token1" or ESTADO["revogado"]:
            return self._j({"code": "unauthorized"}, 401)
        if p.path == "/v1/blocks/pg1/children":
            ESTADO["blocos"] += 1
            if q.get("start_cursor") == ["b2"]:
                return self._j({"results": [{"id": "b3", "type": "to_do", "has_children": False, "to_do": {"rich_text": rt("Ligar para a transportadora"), "checked": True}},
                                            {"id": "b4", "type": "table_row", "has_children": False, "table_row": {"cells": [rt("Item"), rt("Valor")]}}], "has_more": False})
            return self._j({"results": [{"id": "b1", "type": "heading_2", "has_children": False, "heading_2": {"rich_text": rt("Prazos")}},
                                        {"id": "b2x", "type": "toggle", "has_children": True, "toggle": {"rich_text": rt("Documentos")}}], "has_more": True, "next_cursor": "b2"})
        if p.path == "/v1/blocks/b2x/children":
            return self._j({"results": [{"id": "b5", "type": "bulleted_list_item", "has_children": False, "bulleted_list_item": {"rich_text": rt("Contrato de aluguel")}}], "has_more": False})
        if p.path == "/v1/blocks/pg2/children":
            return self._j({"results": [{"id": "b6", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": rt("Renovar a apólice até dezembro.")}}], "has_more": False})
        self._j({}, 404)


fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORTA = fake.server_address[1]
threading.Thread(target=fake.serve_forever, daemon=True).start()
F = f"http://127.0.0.1:{PORTA}"

import heimdall_conexoes as cx  # noqa: E402
import heimdall_library_apps as ap  # noqa: E402
import heimdall_library_dados as dados  # noqa: E402

dados.PROJECT_DIR = TMP
cx.PERMITE_HTTP = True
cx.PROVEDORES["notion"].update({"token": F + "/v1/oauth/token", "api": F + "/v1"})
ap.PAUSA_NOTION = 0
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def texto_de(trecho):
    d = [x for x in dados.listar(por_pagina=100)[0] if trecho in (x["titulo"] or "")]
    return dados.obter(d[0]["id"])["texto"] if d else ""


confere("Notion aparece como app configurado", "notion" in cx.configurados("apps") and "notion" not in cx.configurados("arquivos"))
url = cx.iniciar("notion", False, ["paginas"])
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
confere("endereço: authorize do Notion, owner=user, state, sem PKCE e sem escopo", url.startswith("https://api.notion.com/v1/oauth/authorize?") and q["owner"] == ["user"] and q["response_type"] == ["code"]
        and "code_challenge" not in q and "scope" not in q and q["redirect_uri"] == ["https://library.exemplo.test/nuvem/retorno"], url)
ok, msg = cx.concluir(q["state"][0], "codigo-bom")
confere("conecta (autenticação básica, corpo JSON sem segredo)", ok and "Notion" in msg and ESTADO["form"][1] == {"grant_type": "authorization_code", "code": "codigo-bom", "redirect_uri": "https://library.exemplo.test/nuvem/retorno"}, (msg, ESTADO["form"]))
confere("token cifrado em disco", b"ntn_token1" not in (TMP / "library" / "nuvem.bin").read_bytes())
r = ap.sincronizar("notion")
t = texto_de("Plano da mudança")
confere("importa as páginas das duas páginas de busca e ignora a arquivada", r["novos"] == 2 and r["erros"] == 0 and not texto_de("Arquivada") and texto_de("Linha do banco"), r)
confere("versão da API enviada no cabeçalho", ESTADO["versao"] == "2022-06-28", ESTADO["versao"])
confere("conteúdo: título, subtítulo, bloco aninhado, tarefa marcada e tabela, com blocos paginados",
        "## Prazos" in t and "  - Contrato de aluguel" in t and "- [x] Ligar para a transportadora" in t and "Item | Valor" in t and "Origem: Notion" in t, t)
confere("a busca acha o conteúdo", dados.listar(q="transportadora")[1] == 1 and dados.listar(q="apólice")[1] == 1)
blocos = ESTADO["blocos"]
r = ap.sincronizar("notion")
confere("página sem mudança não baixa o conteúdo de novo", r["novos"] == 0 and r["atualizados"] == 0 and ESTADO["blocos"] == blocos, (r, ESTADO["blocos"], blocos))
ESTADO["editada"] = "2026-11-25T08:00:00.000Z"
r = ap.sincronizar("notion")
confere("página editada é atualizada no mesmo documento", r["atualizados"] == 1 and r["novos"] == 0 and ESTADO["blocos"] > blocos and dados.listar(por_pagina=100)[1] == 2, r)
ESTADO["revogado"] = True
ap.sincronizar("notion")
sit = [x for x in ap.situacao() if x["chave"] == "notion"][0]
confere("acesso removido no Notion: pede nova conexão", not sit["conectado"] and "Conecte de novo" in sit["erro"], sit)
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
