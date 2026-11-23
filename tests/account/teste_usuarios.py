#!/usr/bin/env python3
"""Teste de heimdall_usuarios.py: lista de donos e convidados no .env e a sincronização com uma Cloudflare de mentira (servidor local)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import heimdall_config as hcf
import heimdall_usuarios as u

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


hcf.ARQUIVO = Path(tempfile.mkdtemp()) / ".env"
CONTA = "a" * 32
hcf.ARQUIVO.write_text(f"HEIMDALL_CFACCESS_EMAILS='dono@x.com'\nCLOUDFLARE_ACCOUNT_ID='{CONTA}'\n", encoding="utf-8")
confere("sem token, diz o que falta", "HEIMDALL_CLOUDFLARE_ACCESS_TOKEN" in u.configurado())
hcf.salvar("HEIMDALL_CLOUDFLARE_ACCESS_TOKEN", "tok")
confere("com token e conta, está configurado", u.configurado() == "")

confere("e-mail inválido é recusado", "inválido" in u.definir("ana", ["jogos"]))
confere("dono não vira convidado", "dono" in u.definir("dono@x.com", ["jogos"]))
confere("sem serviço é recusado", "serviço" in u.definir("ana@x.com", []))
confere("serviço que só dono pode (Health) não é dado a convidado", "serviço" in u.definir("ana@x.com", ["saude", "controls"]))
confere("adiciona convidado", u.definir("Ana@X.com", ["jogos", "chat"]) == "" and u.situacao()["convidados"] == {"ana@x.com": ["chat", "jogos"]})
confere("troca os serviços", u.definir("ana@x.com", ["jogos"]) == "" and u.situacao()["convidados"]["ana@x.com"] == ["jogos"])
confere("Notes (triagem, diários, privacidade) não é dado a convidado", "serviço" in u.definir("ana@x.com", ["notas"]))
confere("dono não se remove", "dono" in u.remover("dono@x.com") and "dono@x.com" in u.situacao()["donos"])
confere("não remove a si mesmo", "próprio" in u.remover("ana@x.com", "ana@x.com"))
confere("e-mail que não é convidado", "não é de convidado" in u.remover("zé@x.com"))
u.definir("beto@y.com", ["chat"])
d = u.desejado()
confere("donos entram em tudo; convidados só onde liberados", d["controls"] == ["dono@x.com"] and d["notas"] == ["dono@x.com"] and d["jogos"] == ["ana@x.com", "dono@x.com"] and d["chat"] == ["beto@y.com", "dono@x.com"] and d["saude"] == ["dono@x.com"], str(d))

# Cloudflare de mentira
ESTADO = {"apps": [], "pols": [], "revogados": [], "chamadas": [], "n": 0}


class CF(BaseHTTPRequestHandler):
    def _r(self, resultado, cod=200):
        corpo = json.dumps({"success": cod == 200, "result": resultado, "errors": [] if cod == 200 else [{"message": "não"}]}).encode()
        self.send_response(cod)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

    def _caminho(self):
        return re.sub(r"^/accounts/[0-9a-f]{32}", "", self.path.split("?")[0])

    def do_GET(self):
        assert self.headers["Authorization"] == "Bearer tok"
        c = self._caminho()
        self._r(ESTADO["apps"] if c == "/access/apps" else ESTADO["pols"] if c == "/access/policies"
                else [{"id": "ms1", "type": "azureAD"}, {"id": "otp", "type": "onetimepin"}] if c == "/access/identity_providers" else [])

    def do_POST(self):
        c, b = self._caminho(), self._corpo()
        ESTADO["chamadas"].append(("POST", c))
        ESTADO["n"] += 1
        if c == "/access/policies":
            p = dict(b, id=f"p{ESTADO['n']}")
            ESTADO["pols"].append(p)
            self._r(p)
        elif c == "/access/apps":
            a = dict(b, id=f"a{ESTADO['n']}", aud=f"aud{ESTADO['n']}", policies=[{"id": x["id"], "precedence": x["precedence"]} for x in b["policies"]])
            ESTADO["apps"].append(a)
            self._r(a)
        elif c == "/access/organizations/revoke_user":
            ESTADO["revogados"].append(b["email"])
            self._r({"ok": True})
        else:
            self._r({}, 404)

    def do_PUT(self):
        c, b = self._caminho(), self._corpo()
        ESTADO["chamadas"].append(("PUT", c, b))
        for lista, pre in ((ESTADO["pols"], "/access/policies/"), (ESTADO["apps"], "/access/apps/")):
            if c.startswith(pre):
                for i, x in enumerate(lista):
                    if x["id"] == c[len(pre):]:
                        lista[i] = dict(b, id=x["id"], **({"aud": x.get("aud")} if "aud" in x else {}))
                        return self._r(lista[i])
        self._r({}, 404)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), CF)
threading.Thread(target=srv.serve_forever, daemon=True).start()
u.BASE = f"http://127.0.0.1:{srv.server_port}"

p = u.plano()
confere("plano numa conta vazia: tudo a criar", all(i["acao"] == "mudar" for i in p) and "criar o aplicativo de chat.heimdall-ai.tech" in " ".join(i["texto"] for i in p), str([i["texto"] for i in p]))
confere("plano não muda nada na Cloudflare", ESTADO["apps"] == [] and ESTADO["pols"] == [])
res = u.aplicar(p)
confere("aplicar cria política e aplicativo de cada serviço", len(ESTADO["apps"]) == 12 and len(ESTADO["pols"]) == 12 and all(r.endswith("feito.") for r in res[:12]), str(res))
pn = next(x for x in ESTADO["pols"] if x["name"] == "Heimdall: Games")
confere("a política de Games tem dono e Ana", sorted(i["email"]["email"] for i in pn["include"]) == ["ana@x.com", "dono@x.com"])
confere("toda política exige o Authenticator (MFA) e todo aplicativo novo só aceita o login da Microsoft, direto", all(x["require"] == [{"auth_method": {"auth_method": "mfa"}}] for x in ESTADO["pols"])
        and all(a["allowed_idps"] == ["ms1"] and a["auto_redirect_to_identity"] for a in ESTADO["apps"]))
confere("os AUDs dos aplicativos vão para HEIMDALL_CFACCESS_AUD", len([x for x in {d["nome"]: d["valor"] for d in hcf.ler()}["HEIMDALL_CFACCESS_AUD"].split(",")]) == 12)
confere("de novo: nada a fazer", all(i["acao"] == "nada" for i in u.plano()))

# remover a Ana: política de Notes perde o e-mail e as sessões dela são revogadas
u.remover("ana@x.com")
res = u.aplicar(u.plano())
pn = next(x for x in ESTADO["pols"] if x["name"] == "Heimdall: Games")
confere("remover tira da política e revoga as sessões", [i["email"]["email"] for i in pn["include"]] == ["dono@x.com"] and ESTADO["revogados"] == ["ana@x.com"], str(res))

# aplicativo compartilhado (vários endereços) e aplicativo só de caminho (RSS): o primeiro não é tocado, o segundo não conta
ESTADO.update(apps=[{"id": "pes", "name": "Pessoal", "domain": "cloud.heimdall-ai.tech", "destinations": [{"type": "public", "uri": h} for h in ("cloud.heimdall-ai.tech", "notes.heimdall-ai.tech")], "policies": []},
                    {"id": "rss", "name": "RSS", "domain": "news.heimdall-ai.tech/rss", "policies": []}], pols=[], chamadas=[])
p2 = {i["servico"]: i for i in u.plano()}
confere("aplicativo compartilhado não recebe política de serviço; o de caminho (RSS) não vale como cobertura do host",
        p2["notas"]["acao"] == "nada" and "compartilhado" in p2["notas"]["texto"] and p2["cloud"]["acao"] == "nada" and p2["news"]["acao"] == "mudar", str(p2["news"]["texto"]))
# aplicativo que já existe, sem a nossa política: liga sem apagar o que existe nem as outras políticas
ESTADO.update(apps=[{"id": "ap1", "aud": "z", "name": "Meu Games", "domain": "games.heimdall-ai.tech", "type": "self_hosted", "session_duration": "12h",
                     "allowed_idps": ["idp-ms"], "policies": [{"id": "outra", "precedence": 1}]}], pols=[], chamadas=[])
res = u.aplicar(u.plano())
ap = next(a for a in ESTADO["apps"] if a["id"] == "ap1")
confere("app existente: mantém as outras políticas e configurações e acrescenta a nossa", [x["id"] for x in ap["policies"]][0] == "outra" and len(ap["policies"]) == 2
        and ap["allowed_idps"] == ["idp-ms"] and ap["session_duration"] == "12h", str(ap))
srv.shutdown()
u.BASE = "http://127.0.0.1:9"
try:
    u.plano()
    confere("Cloudflare fora do ar vira erro claro", False)
except u.ErroCloudflare as ex:
    confere("Cloudflare fora do ar vira erro claro", "Cloudflare" in str(ex), str(ex))
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
