#!/usr/bin/env python3
"""Testa a conexão do Memory com Dropbox e OneDrive: OAuth (state, PKCE, uso único), tokens cifrados por pessoa, renovação, sincronização só de leitura,
isolamento entre pessoas e as telas /nuvem, contra provedores falsos."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import sys
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="nuvem_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_MEMORY_IA": "0",
                   "HEIMDALL_NUVEM_CHAVE": "chave-de-teste", "HEIMDALL_NUVEM_DROPBOX_ID": "dbx-id", "HEIMDALL_NUVEM_DROPBOX_SEGREDO": "dbx-seg",
                   "HEIMDALL_NUVEM_ONEDRIVE_ID": "od-id", "HEIMDALL_MEMORY_URL": "https://memory.exemplo.test"})

ESTADO = {"tokens": 0, "revogado": False, "auth_no_download": [], "baixados": [], "refresh_usado": [], "escopo": "", "movidos": [], "pastas_criadas": [], "patch": [], "pastas_lidas": []}
EXTRA = {   # itens que só aparecem na listagem com subpastas
    "id:5": ("nota_sub.txt", b"Nota dentro da subpasta numero 555", "h5"),
    "id:6": ("velho.txt", b"Arquivo na pasta de importados numero 666", "h6"),
    "id:7": ("fundo.txt", b"Arquivo fundo demais numero 777", "h7"),
}
ARQUIVOS = {   # id -> (nome, conteudo, marca)
    "id:1": ("recibo_alfa.txt", b"Recibo de pagamento alfa numero 111", "h1"),
    "id:2": ("contrato_beta.txt", b"Contrato beta clausula de rescisao numero 222", "h2"),
    "id:3": ("programa.exe", b"MZ", "h3"),
    "id:4": ("vazio.txt", b"", "h4"),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, o, c=200, extra=None):
        b = json.dumps(o).encode()
        self.send_response(c)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_POST(self):
        u = urllib.parse.urlparse(self.path).path
        corpo = self._corpo()
        if u == "/token":
            f = {k: v[0] for k, v in urllib.parse.parse_qs(corpo.decode()).items()}
            if f.get("grant_type") == "authorization_code":
                if f.get("code") != "codigo-bom" or not f.get("code_verifier"):
                    return self._j({"error": "invalid_grant"}, 400)
                ESTADO["tokens"] += 1
                return self._j({"access_token": f"acesso{ESTADO['tokens']}", "refresh_token": "renov1", "expires_in": 3600, **({"scope": ESTADO["escopo"]} if ESTADO["escopo"] else {})})
            ESTADO["refresh_usado"].append(f.get("refresh_token"))
            if ESTADO["revogado"]:
                return self._j({"error": "invalid_grant"}, 400)
            ESTADO["tokens"] += 1
            return self._j({"access_token": f"acesso{ESTADO['tokens']}", "refresh_token": "renov-" + str(ESTADO["tokens"]), "expires_in": 3600})
        if not (self.headers.get("Authorization") or "").startswith("Bearer acesso"):
            return self._j({}, 401)
        if u == "/2/files/list_folder":
            d = json.loads(corpo)
            if d["path"] not in ("", "/Docs"):
                return self._j({"error": "path"}, 409)
            extras = [{".tag": "file", "id": i, "name": n, "size": len(c), "content_hash": m, "path_lower": pl} for (i, (n, c, m)), pl in zip(EXTRA.items(), (
                "/docs/sub/nota_sub.txt", "/docs/importados pelo heimdall/velho.txt", "/docs/a/b/c/d/e/f/fundo.txt"))] if d.get("recursive") else []
            return self._j({"entries": [{".tag": "file", "id": i, "name": n, "size": len(c), "content_hash": m} for i, (n, c, m) in list(ARQUIVOS.items())[:2]] + extras, "has_more": True, "cursor": "c1"})
        if u == "/2/files/create_folder_v2":
            ESTADO["pastas_criadas"].append(json.loads(corpo)["path"])
            return self._j({}, 200 if len(ESTADO["pastas_criadas"]) == 1 else 409)
        if u == "/2/files/move_v2":
            ESTADO["movidos"].append(json.loads(corpo))
            return self._j({"metadata": {}})
        if u.startswith("/me/drive/root") and u.endswith("/children"):
            ESTADO["pastas_criadas"].append(json.loads(corpo)["name"])
            return self._j({"id": "destino-od"}, 201)
        if u == "/2/files/list_folder/continue":
            return self._j({"entries": [{".tag": "folder", "id": "id:9", "name": "sub"}] + [{".tag": "file", "id": i, "name": n, "size": len(c), "content_hash": m} for i, (n, c, m) in list(ARQUIVOS.items())[2:]], "has_more": False})
        if u == "/2/files/download":
            arg = json.loads(self.headers["Dropbox-API-Arg"])
            ESTADO["baixados"].append(arg["path"])
            c = {**ARQUIVOS, **EXTRA}[arg["path"]][1]
            self.send_response(200)
            self.send_header("Content-Length", str(len(c)))
            self.end_headers()
            return self.wfile.write(c)
        self._j({}, 404)

    def do_PATCH(self):
        corpo = self._corpo()
        if not (self.headers.get("Authorization") or "").startswith("Bearer acesso"):
            return self._j({}, 401)
        ESTADO["patch"].append((urllib.parse.unquote(urllib.parse.urlparse(self.path).path), json.loads(corpo)))
        self._j({"id": "x"})

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path.startswith("/dl/"):
            ESTADO["auth_no_download"].append(self.headers.get("Authorization"))
            c = {**ARQUIVOS, **EXTRA}[urllib.parse.unquote(p.path[4:])][1]
            self.send_response(200)
            self.send_header("Content-Length", str(len(c)))
            self.end_headers()
            return self.wfile.write(c)
        if not (self.headers.get("Authorization") or "").startswith("Bearer acesso"):
            return self._j({}, 401)
        if p.path.startswith("/me/drive/root") and "children" in p.path:
            pg = urllib.parse.parse_qs(p.query).get("pagina", ["1"])[0]
            itens = [{"id": i, "name": n, "size": len(c), "eTag": m, "file": {}} for i, (n, c, m) in ARQUIVOS.items()]
            if pg == "1":
                return self._j({"value": itens[:2], "@odata.nextLink": f"http://127.0.0.1:{PORTA_F}{p.path}?pagina=2"})
            return self._j({"value": itens[2:] + [{"id": "pasta", "name": "sub", "folder": {}}, {"id": "imp", "name": "Importados pelo Heimdall", "folder": {}}]})
        m = re.fullmatch(r"/me/drive/items/([^/]+)/children", p.path)
        if m:
            ESTADO["pastas_lidas"].append(m.group(1))
            return self._j({"value": [{"id": "id:5", "name": EXTRA["id:5"][0], "size": len(EXTRA["id:5"][1]), "eTag": "h5", "file": {}}, {"id": "imp", "name": "Importados pelo Heimdall", "folder": {}}]})
        m = re.fullmatch(r"/me/drive/items/(.+)/content", p.path)
        if m:
            return self._j({}, 302, {"Location": f"http://127.0.0.1:{PORTA_F}/dl/{m.group(1)}"})
        self._j({}, 404)


fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORTA_F = fake.server_address[1]
threading.Thread(target=fake.serve_forever, daemon=True).start()
F = f"http://127.0.0.1:{PORTA_F}"

import heimdall_lab as hc  # noqa: E402
import heimdall_memory as lib  # noqa: E402
import heimdall_memory_dados as dados  # noqa: E402
import heimdall_conexoes as cx  # noqa: E402
import heimdall_memory_nuvem as nv  # noqa: E402
import heimdall_servico_web as web  # noqa: E402

dados.PROJECT_DIR = TMP
cx.PERMITE_HTTP = True
nv.PROVEDORES["dropbox"].update({"auth": "https://auth.exemplo.test/dropbox", "token": F + "/token", "api": F, "conteudo": F})
nv.PROVEDORES["onedrive"].update({"auth": "https://auth.exemplo.test/onedrive", "token": F + "/token", "api": F})
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


def conectar(chave="dropbox", codigo="codigo-bom", escrita=False):
    url = nv.iniciar(chave, escrita)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    return url, nv.concluir(state, codigo)


def conectar_escrita(chave="dropbox"):
    return conectar(chave, escrita=True)


# --- configuração e OAuth
confere("só provedores com credencial aparecem", nv.configurados() == ["dropbox", "onedrive"])
url = nv.iniciar("dropbox")
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
confere("autorização: cliente, retorno, PKCE S256, escopo de leitura e token de renovação", q["client_id"] == ["dbx-id"] and q["redirect_uri"] == ["https://memory.exemplo.test/nuvem/retorno"]
        and q["code_challenge_method"] == ["S256"] and len(q["code_challenge"][0]) >= 43 and q["token_access_type"] == ["offline"] and "files.content.read" in q["scope"][0]
        and "write" not in q["scope"][0], q)
confere("OneDrive pede offline_access e Files.Read", "Files.Read offline_access" == urllib.parse.parse_qs(urllib.parse.urlparse(nv.iniciar("onedrive")).query)["scope"][0])
confere("provedor desconhecido é recusado", "configurado" in erro(nv.iniciar, "box"))
confere("state errado é recusado", nv.concluir("inventado", "codigo-bom")[0] is False)
st = q["state"][0]
confere("erro do provedor é recusado", nv.concluir(st, "x", "access_denied")[0] is False)
confere("state é de uso único", nv.concluir(st, "codigo-bom")[0] is False)
url, (ok, msg) = conectar("dropbox", "codigo-ruim")
confere("código recusado pelo provedor não conecta", not ok and not nv.situacao()[0]["conectado"], msg)
url, (ok, msg) = conectar("dropbox")
confere("conecta", ok and nv.situacao()[0]["conectado"], msg)
bruto = (TMP / "memory" / "nuvem.bin").read_bytes()
confere("tokens cifrados em disco, com permissão 600", b"renov1" not in bruto and b"acesso" not in bruto and oct((TMP / "memory" / "nuvem.bin").stat().st_mode)[-3:] == "600")
estado_ant = dict(cx.PENDENTES)
s2 = nv.iniciar("dropbox")
st2 = urllib.parse.parse_qs(urllib.parse.urlparse(s2).query)["state"][0]
cx.PENDENTES[st2]["expira"] = time.time() - 1
confere("state expirado é recusado", nv.concluir(st2, "codigo-bom")[0] is False)

# --- sincronização (Dropbox)
confere("pasta inválida é recusada", "inválido" in erro(nv.definir_pasta, "dropbox", "../segredo"))
nv.definir_pasta("dropbox", "/Docs")
r = nv.sincronizar("dropbox", usar_ia=False)
docs, n = dados.listar()
confere("importa só arquivos aceitos, em páginas, sem subpasta", r["novos"] == 2 and n == 2 and r["ignorados"] == 2 and r["erros"] == 0, (r, n))
confere("a busca acha o conteúdo importado", dados.listar(q="rescisao")[1] == 1)
r = nv.sincronizar("dropbox", usar_ia=False)
confere("segunda rodada não baixa de novo", r["novos"] == 0 and ESTADO["baixados"].count("id:1") == 1, (r, ESTADO["baixados"]))
confere("situação resume a última rodada", "novos" in nv.situacao()[0]["resumo"] and nv.situacao()[0]["ultimo"])
ARQUIVOS["id:1"] = ("recibo_alfa.txt", b"Recibo de pagamento alfa numero 111", "h1-novo")
r = nv.sincronizar("dropbox", usar_ia=False)
confere("arquivo alterado é baixado de novo, e o mesmo conteúdo conta como repetido", ESTADO["baixados"].count("id:1") == 2 and r["repetidos"] == 1 and dados.listar()[1] == 2, r)
nv.definir_pasta("dropbox", "/Outra")
r = nv.sincronizar("dropbox", usar_ia=False)
confere("pasta inexistente vira mensagem na situação, sem derrubar nem importar", r["erros"] == 1 and r["novos"] == 0 and "Dropbox" in nv.situacao()[0]["erro"] and nv.situacao()[0]["conectado"], (r, nv.situacao()[0]))
nv.definir_pasta("dropbox", "/Docs")

# --- renovação do token e rotação
todos = cx.carregar()
todos["dropbox"]["expira"] = time.time() - 10
cx.gravar(todos)
nv.sincronizar("dropbox", usar_ia=False)
todos = cx.carregar()
confere("token vencido é renovado e o novo token de renovação é guardado", ESTADO["refresh_usado"] == ["renov1"] and todos["dropbox"]["renovacao"].startswith("renov-"), (ESTADO, todos["dropbox"]["renovacao"]))

# --- autorização revogada
todos["dropbox"]["expira"] = time.time() - 10
cx.gravar(todos)
ESTADO["revogado"] = True
confere("autorização revogada pede nova conexão", "Conecte de novo" in erro(nv.sincronizar, "dropbox", usar_ia=False))
sit = nv.situacao()[0]
confere("situação mostra o erro e desconectado, mantendo a pasta", not sit["conectado"] and "Conecte de novo" in sit["erro"] and sit["pasta"] == "/Docs", sit)
ESTADO["revogado"] = False
conectar("dropbox")
confere("reconectar mantém a pasta", nv.situacao()[0]["conectado"] and nv.situacao()[0]["pasta"] == "/Docs")

# --- OneDrive: paginação e download por redirecionamento sem o token
conectar("onedrive")
nv.definir_pasta("onedrive", "Documentos/Scans")
r = nv.sincronizar("onedrive", usar_ia=False)
confere("OneDrive: páginas e redirecionamento de download", r["repetidos"] == 2 and r["erros"] == 0 and r["novos"] == 0, r)
confere("download pré-autorizado não leva o token do OneDrive", ESTADO["auth_no_download"] and all(a is None for a in ESTADO["auth_no_download"]), ESTADO["auth_no_download"])

# --- convidado: conexão e acervo separados
CONV = "p0123456789ab"
with cx.como(CONV):
    confere("convidado começa sem conexão e sem documentos", not nv.situacao()[0]["conectado"] and dados.listar()[1] == 0)
    conectar("dropbox")
    nv.definir_pasta("dropbox", "")
    nv.sincronizar("dropbox", usar_ia=False)
    confere("convidado importa para o acervo dele", dados.listar()[1] == 2)
    confere("conexão do convidado fica na pasta dele", any((TMP / "db").rglob(f"{CONV}/memory/nuvem.bin")))
confere("a conexão e a pasta do dono não mudaram", nv.situacao()[0]["pasta"] == "/Docs")
confere("rodada de fundo percorre quem tem conexão", cx.sincronizar_todos()["pessoas"] == 2)

# --- desconectar
nv.desconectar("onedrive")
confere("desconectar apaga o token e mantém os documentos", not [s for s in nv.situacao() if s["chave"] == "onedrive"][0]["conectado"] and dados.listar()[1] == 2)

# --- subpastas e escrita opcional (convidado separado para não mexer nas contagens acima)
confere("até aqui nada foi movido: a conexão padrão só lê", ESTADO["movidos"] == [] and ESTADO["patch"] == [] and ESTADO["pastas_criadas"] == [])
confere("provedor sem escopo de escrita no pedido padrão", "write" not in urllib.parse.parse_qs(urllib.parse.urlparse(nv.iniciar("dropbox")).query)["scope"][0])
q = urllib.parse.parse_qs(urllib.parse.urlparse(nv.iniciar("dropbox", escrita=True)).query)
confere("pedido com organização inclui o escopo de escrita", "files.content.write" in q["scope"][0], q["scope"])
confere("OneDrive com organização pede Files.ReadWrite", urllib.parse.parse_qs(urllib.parse.urlparse(nv.iniciar("onedrive", escrita=True)).query)["scope"][0] == "Files.ReadWrite offline_access")
CONV2 = "pabcdef012345"
with cx.como(CONV2):
    conectar("dropbox")
    confere("mover sem permissão de escrita é recusado", "organização" in erro(nv.definir_pasta, "dropbox", "/Docs", True, True))
    ESTADO["escopo"] = "files.content.read"
    url, (ok, msg) = conectar_escrita("dropbox")
    confere("se o provedor não concedeu a escrita, a conexão fica só de leitura", ok and "somente para leitura" in msg and not nv.situacao()[0]["escrita"], msg)
    ESTADO["escopo"] = ""
    url, (ok, msg) = conectar_escrita("dropbox")
    confere("conecta com organização", ok and "mover arquivos" in msg and nv.situacao()[0]["escrita"], msg)
    nv.definir_pasta("dropbox", "/Docs", True, True)
    sit = nv.situacao()[0]
    confere("situação guarda subpastas e mover", sit["subpastas"] and sit["mover"] and sit["escrita"], sit)
    r = nv.sincronizar("dropbox", usar_ia=False)
    confere("Dropbox: importa a subpasta, ignora Importados e o que passa do limite de níveis", r["novos"] == 3 and r["erros"] == 0 and "id:5" in ESTADO["baixados"]
            and "id:6" not in ESTADO["baixados"] and "id:7" not in ESTADO["baixados"], (r, ESTADO["baixados"]))
    confere("Dropbox: cada arquivo importado vai para a pasta de importados", r["movidos"] == 3 and [m["from_path"] for m in ESTADO["movidos"]] == ["id:1", "id:2", "id:5"]
            and all(m["to_path"].startswith("/Docs/Importados pelo Heimdall/") and m["autorename"] for m in ESTADO["movidos"]) and ESTADO["pastas_criadas"] == ["/Docs/Importados pelo Heimdall"], (r, ESTADO))
    r = nv.sincronizar("dropbox", usar_ia=False)
    confere("segunda rodada não repete nem move de novo", r["novos"] == 0 and r["movidos"] == 0 and len(ESTADO["movidos"]) == 3, (r, ESTADO["movidos"]))
    confere("o resumo informa os movidos", "movidos" in nv.situacao()[0]["resumo"])
    confere("nada é apagado: só há chamadas de mover", ESTADO["patch"] == [])
    conectar_escrita("onedrive")
    nv.definir_pasta("onedrive", "Scans", True, True)
    r = nv.sincronizar("onedrive", usar_ia=False)
    confere("OneDrive: percorre a subpasta, pula Importados e move com o id da pasta criada", r["novos"] + r["repetidos"] == 3 and r["movidos"] == 3 and r["erros"] == 0
            and ESTADO["pastas_lidas"] == ["pasta"] and len(ESTADO["patch"]) == 3 and all(b["parentReference"] == {"id": "destino-od"} for _, b in ESTADO["patch"])
            and ESTADO["pastas_criadas"][-1] == "Importados pelo Heimdall", (r, ESTADO["pastas_lidas"], ESTADO["patch"]))
    confere("o acervo do convidado tem os três documentos", dados.listar()[1] == 3)
confere("o dono não foi afetado: continua só leitura e sem mover", nv.situacao()[0]["escrita"] is False and nv.situacao()[0]["mover"] is False and dados.listar()[1] == 2)

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


s, h, r = req("GET", "/nuvem/retorno?state=inventado&code=x")
confere("retorno é público (sem cookie) e recusa state inventado", s == 200 and "expirou" in h and "<h1" in h)
confere("outras rotas continuam exigindo sessão", req("GET", "/nuvem")[0] == 303 and req("POST", "/nuvem/conectar", {"provedor": "dropbox"})[0] in (303, 405))
tk = hc.nova_sessao()[0]
s, h, _ = req("GET", "/nuvem", cookie=tk)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("tela Nuvem: seções por provedor, botões POST e foco no Studio Design", s == 200 and "<h2>Dropbox</h2>" in h and "<h2>OneDrive</h2>" in h and "Conectar OneDrive" in h
        and "Sincronizar agora" in h and "Desconectar Dropbox" in h and 'for="pasta-dropbox"' in h and "Nuvem" in h, h[:300])
s, _, r = req("POST", "/nuvem/conectar", {"csrf": "errado", "provedor": "onedrive"}, tk)
confere("conectar sem CSRF: 403", s == 403)
confere("tela do dono: Dropbox somente leitura, com a opção de subpastas e o botão para permitir organização", "somente para leitura" in h and 'name="subpastas"' in h and "Permitir organização" in h
        and 'name="mover"' not in h and "Conectar OneDrive com organização" in h, h[:200])
s, _, r = req("POST", "/nuvem/conectar", {"csrf": csrf, "provedor": "onedrive", "escrita": "1"}, tk)
confere("conectar com organização pede o escopo de escrita", s == 303 and "Files.ReadWrite" in (r.getheader("Location") or ""))
s, _, r = req("POST", "/nuvem/conectar", {"csrf": csrf, "provedor": "onedrive"}, tk)
loc = r.getheader("Location") or ""
confere("conectar leva ao provedor (https)", s == 303 and loc.startswith("https://auth.exemplo.test/onedrive?") and "state=" in loc, (s, loc))
state = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["state"][0]
s, h, _ = req("GET", f"/nuvem/retorno?state={state}&code=codigo-bom")
confere("retorno sem cookie conclui a conexão", s == 200 and "conectado" in h and "Voltar ao Hub" in h, h[-300:])
confere("a conexão foi gravada para o dono", [x for x in nv.situacao() if x["chave"] == "onedrive"][0]["conectado"])
s, _, r = req("POST", "/nuvem/pasta", {"csrf": csrf, "provedor": "onedrive", "pasta": "Scans"}, tk)
confere("salvar pasta", s == 303 and r.getheader("Location") == "/nuvem")
s, _, r = req("POST", "/nuvem/sincronizar", {"csrf": csrf, "provedor": "onedrive"}, tk)
confere("sincronizar pela tela", s == 303)
s, _, r = req("POST", "/nuvem/desconectar", {"csrf": csrf, "provedor": "onedrive"}, tk)
confere("desconectar pela tela", s == 303 and not [x for x in nv.situacao() if x["chave"] == "onedrive"][0]["conectado"])
tg = hc.nova_sessao("memory", CONV)[0]
s, h, _ = req("GET", "/nuvem", cookie=tg)
confere("a tela do convidado mostra a conexão dele (Dropbox conectado, OneDrive não)", s == 200 and "Dropbox conectado" in h and "OneDrive não conectado" in h)
tg2 = hc.nova_sessao("memory", CONV2)[0]
s, h, _ = req("GET", "/nuvem", cookie=tg2)
csrf2 = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("tela do convidado com organização: subpastas e mover marcados, sem botão de permitir", "com organização" in h and re.search(r'name="subpastas"[^>]*checked', h) and re.search(r'name="mover"[^>]*checked', h)
        and "Importados pelo Heimdall" in h and 'for="sub-dropbox"' in h and "Permitir organização" not in h, h[:300])
s, _, r = req("POST", "/nuvem/pasta", {"csrf": csrf2, "provedor": "dropbox", "pasta": "/Docs"}, tg2)
with cx.como(CONV2):
    sit = nv.situacao()[0]
confere("desmarcar as caixas e salvar desliga subpastas e mover", s == 303 and not sit["subpastas"] and not sit["mover"] and sit["escrita"], sit)
srv.shutdown()
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
