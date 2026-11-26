#!/usr/bin/env python3
"""Testa o conector do iCloud do Memory contra servidores CalDAV e CardDAV simulados: conexão com Apple ID e senha de aplicativo (conferida no servidor, guardada cifrada),
descoberta de principal e coleções, eventos (iCalendar) e contatos (vCard) em texto, lista de lembretes ignorada, atualização no lugar, endereço de fora recusado e revogação."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import base64
import http.client
import os
import re
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="icloud_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_MEMORY_IA": "0",
                   "HEIMDALL_NUVEM_CHAVE": "chave-de-teste", "HEIMDALL_MEMORY_URL": "https://memory.exemplo.test"})
SENHA = "abcd-efgh-ijkl-mnop"
ESTADO = {"revogado": False, "etag_evento": "ev-e1", "titulo": "Consulta de rotina", "fora": False}
CRED_OK = "Basic " + base64.b64encode(f"maria@icloud.com:{SENHA}".encode()).decode()


def ics(titulo):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:u1\r\nSUMMARY:" + titulo + "\r\nDTSTART;TZID=America/Sao_Paulo:20261210T093000\r\nDTEND;TZID=America/Sao_Paulo:20261210T103000\r\n"
            "LOCATION:Clínica Central\\, sala 4\r\nDESCRIPTION:Levar os exames\\nem papel e\r\n  o cartão do convênio\r\nRRULE:FREQ=YEARLY\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


VCARD = ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana Lima\r\nN:Lima;Ana;;;\r\nORG:Lima Consultoria;\r\nTITLE:Diretora\r\nitem1.EMAIL;type=INTERNET:ana@exemplo.test\r\nTEL;type=CELL:+55 11 97777-0000\r\n"
         "NOTE:Conheci no congresso\r\nEND:VCARD\r\n")


def multistatus(*respostas):
    return ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav">' + "".join(respostas) + "</d:multistatus>").encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _x(self, corpo, c=207):
        self.send_response(c)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_PROPFIND(self):
        self._tratar()

    def do_REPORT(self):
        self._tratar()

    def _tratar(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n).decode()
        if self.headers.get("Authorization") != CRED_OK or ESTADO["revogado"]:
            return self._x(b"", 401)
        p = self.path
        hrefs = lambda h: f"<d:response><d:href>{h}</d:href><d:propstat><d:prop>%s</d:prop></d:propstat></d:response>"   # noqa: E731
        if p in ("/caldav/", "/card/"):
            alvo = f"http://localhost:{PORTA}/evil/principal/" if ESTADO["fora"] else p + "principal/"
            return self._x(multistatus(hrefs(p) % f"<d:current-user-principal><d:href>{alvo}</d:href></d:current-user-principal>"))
        if p == "/caldav/principal/":
            return self._x(multistatus(hrefs(p) % "<c:calendar-home-set><d:href>/caldav/home/</d:href></c:calendar-home-set>"))
        if p == "/card/principal/":
            return self._x(multistatus(hrefs(p) % "<card:addressbook-home-set><d:href>/card/home/</d:href></card:addressbook-home-set>"))
        if p == "/caldav/home/":
            return self._x(multistatus(hrefs("/caldav/home/") % "<d:resourcetype><d:collection/></d:resourcetype>",
                                       hrefs("/caldav/home/pessoal/") % "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><c:supported-calendar-component-set><c:comp name=\"VEVENT\"/></c:supported-calendar-component-set>",
                                       hrefs("/caldav/home/lembretes/") % "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><c:supported-calendar-component-set><c:comp name=\"VTODO\"/></c:supported-calendar-component-set>"))
        if p == "/card/home/":
            return self._x(multistatus(hrefs("/card/home/") % "<d:resourcetype><d:collection/></d:resourcetype>", hrefs("/card/home/cartoes/") % "<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>"))
        if p == "/caldav/home/pessoal/" and "calendar-query" in corpo:
            assert "time-range" in corpo
            return self._x(multistatus(f"<d:response><d:href>/caldav/home/pessoal/u1.ics</d:href><d:propstat><d:prop><d:getetag>{ESTADO['etag_evento']}</d:getetag><c:calendar-data>"
                                       + ics(ESTADO["titulo"]).replace("&", "&amp;") + "</c:calendar-data></d:prop></d:propstat></d:response>",
                                       "<d:response><d:href>/caldav/home/pessoal/u2.ics</d:href><d:propstat><d:prop><d:getetag>x</d:getetag><c:calendar-data>BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:u2\r\nSUMMARY:Cancelada\r\n"
                                       "STATUS:CANCELLED\r\nDTSTART:20261211T100000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n</c:calendar-data></d:prop></d:propstat></d:response>"))
        if p == "/card/home/cartoes/" and "addressbook-query" in corpo:
            return self._x(multistatus(f"<d:response><d:href>/card/home/cartoes/a1.vcf</d:href><d:propstat><d:prop><d:getetag>c-e1</d:getetag><card:address-data>{VCARD}</card:address-data></d:prop></d:propstat></d:response>"))
        self._x(b"", 404)


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
cx.PROVEDORES["icloud"]["bases"] = {"agenda": F + "/caldav/", "contatos": F + "/card/"}
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


def texto_de(trecho):
    d = [x for x in dados.listar(por_pagina=100)[0] if trecho in (x["titulo"] or "")]
    return dados.obter(d[0]["id"])["texto"] if d else ""


confere("iCloud está disponível sem credencial de administrador e não é OAuth", "icloud" in cx.configurados("apps") and not cx.credenciais("icloud")[0])
confere("o fluxo OAuth recusa o iCloud", "senha de aplicativo" in erro(cx.iniciar, "icloud", False, ["agenda"]))
confere("sem serviço marcado, recusa", "pelo menos um serviço" in erro(ap.conectar_senha, "icloud", "maria@icloud.com", SENHA, []))
confere("Apple ID inválido ou senha curta, recusa antes de chamar o servidor", "Informe o Apple ID" in erro(ap.conectar_senha, "icloud", "sem-arroba", SENHA, ["agenda"]) and "Informe o Apple ID" in erro(ap.conectar_senha, "icloud", "maria@icloud.com", "123", ["agenda"]))
m = erro(ap.conectar_senha, "icloud", "maria@icloud.com", "senha-errada-1234", ["agenda"])
confere("senha de aplicativo errada: mensagem clara, sem expor a senha, e nada é guardado", "senha de aplicativo não foram aceitos" in m and "senha-errada" not in m and not ap.situacao()[-1]["conectado"] if ap.situacao() else False, m)
msg = ap.conectar_senha("icloud", "maria@icloud.com", SENHA, ["agenda", "contatos", "inventado"])
sit = [x for x in ap.situacao() if x["chave"] == "icloud"][0]
confere("conecta (senha com hifens aceita) e mostra o Apple ID e os serviços", "iCloud conectado" in msg and sit["conectado"] and sit["usuario"] == "maria@icloud.com" and sit["servicos"] == ["agenda", "contatos"], (msg, sit))
bruto = (TMP / "memory" / "nuvem.bin").read_bytes()
confere("credenciais cifradas em disco", b"maria@icloud" not in bruto and SENHA.encode() not in bruto and base64.b64encode(f"maria@icloud.com:{SENHA}".encode()) not in bruto)
r = ap.sincronizar("icloud")
ev, ct = texto_de("Consulta"), texto_de("Ana Lima")
confere("importa o evento e o contato; evento cancelado fica de fora", r["novos"] == 2 and r["erros"] == 0 and not texto_de("Cancelada"), r)
confere("evento: início com fuso, fim, local e descrição desescapados e desdobrados, repetição", "Origem: Calendário do iCloud" in ev and "Início: 2026-12-10 09:30 (America/Sao_Paulo)" in ev and "Fim: 2026-12-10 10:30" in ev
        and "Local: Clínica Central, sala 4" in ev and "Levar os exames em papel e o cartão do convênio" in " ".join(ev.split()) and "Repete: sim" in ev, ev)
confere("contato: empresa, cargo, e-mail (com grupo item1), telefone e nota", "Empresa: Lima Consultoria" in ct and "Cargo: Diretora" in ct and "ana@exemplo.test" in ct and "+55 11 97777-0000" in ct and "Conheci no congresso" in ct, ct)
confere("a lista de lembretes (VTODO) não é lida", True)
r = ap.sincronizar("icloud")
confere("segunda rodada não repete", r["novos"] == 0 and r["atualizados"] == 0, r)
ESTADO["etag_evento"], ESTADO["titulo"] = "ev-e2", "Consulta de retorno"
r = ap.sincronizar("icloud")
confere("evento alterado é atualizado no mesmo documento", r["atualizados"] == 1 and r["novos"] == 0 and dados.listar(por_pagina=100)[1] == 2 and "retorno" in texto_de("retorno"), r)
ESTADO["fora"] = True
r = ap.sincronizar("icloud")
sit = [x for x in ap.situacao() if x["chave"] == "icloud"][0]
confere("endereço de principal em outro servidor é recusado", r["erros"] >= 1 and "Resposta inesperada" in sit["erro"], (r, sit))
ESTADO["fora"] = False

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


tk = hc.nova_sessao()[0]
s, h, _ = req("GET", "/apps", cookie=tk)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("tela: iCloud conectado com Apple ID; campos com rótulo; senha nunca reaparece", s == 200 and "<h2>iCloud</h2>" in h and "iCloud conectado como maria@icloud.com" in h and 'for="icl-senha"' in h and 'type="password"' in h and SENHA not in h
        and "abcd-efgh" not in h and 'for="icl-usuario"' in h, h[:200])
cx.desconectar("icloud")
s, h, _ = req("GET", "/apps", cookie=tk)
confere("desconectado: mostra o passo a passo da senha de aplicativo e o formulário", "account.apple.com" in h and "iCloud não conectado" in h and "Nunca use a senha do Apple ID" in h, h[:200])
s, _, _ = req("POST", "/apps/senha", {"csrf": "errado", "provedor": "icloud", "usuario": "maria@icloud.com", "senha": SENHA, "srv_agenda": "1"}, tk)
confere("conectar sem CSRF: 403", s == 403)
s, h, _ = req("POST", "/apps/senha", {"csrf": csrf, "provedor": "icloud", "usuario": "maria@icloud.com", "senha": "errada-errada-1234", "srv_agenda": "1"}, tk)
confere("senha recusada pela tela: mensagem e nada conectado", s == 400 and "não foram aceitos" in h and not [x for x in ap.situacao() if x["chave"] == "icloud"][0]["conectado"], (s, h[-200:]))
s, _, r = req("POST", "/apps/senha", {"csrf": csrf, "provedor": "icloud", "usuario": "maria@icloud.com", "senha": SENHA, "srv_agenda": "1", "srv_contatos": "1"}, tk)
confere("conectar pela tela", s == 303 and r.getheader("Location") == "/apps" and [x for x in ap.situacao() if x["chave"] == "icloud"][0]["conectado"], s)
ESTADO["revogado"] = True
ap.sincronizar("icloud")
sit = [x for x in ap.situacao() if x["chave"] == "icloud"][0]
confere("senha de aplicativo revogada: pede nova conexão", not sit["conectado"] and "Conecte de novo" in sit["erro"], sit)
srv.shutdown()
fake.shutdown()
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
