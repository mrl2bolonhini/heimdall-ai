#!/usr/bin/env python3
"""Testa a aba Ajustes do Learn: pausar agenda e avisos, agenda por pasta, arquivar pasta sem apagar nada e as telas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import sys
import tempfile
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
os.environ["HEIMDALL_AVISOS_MAC"] = "0"
(TMP / "knowledge").mkdir()

import heimdall_cloud as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_cards as ca  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


d.criar_pasta("Direito civil", "", "Direito")
d.criar_pasta("Contratos", "", "Direito", "", "direito-civil")
d.criar_pasta("Direito civil 2", "", "Direito")
d.criar_pasta("Python", "", "Programação")
K = TMP / "knowledge"
(K / "direito-civil" / "a.md").write_text("Texto A", encoding="utf-8")
(K / "direito-civil" / "contratos" / "b.md").write_text("Texto B", encoding="utf-8")
(K / "direito-civil-2" / "c.md").write_text("Texto C", encoding="utf-8")

# ajustes gerais
confere("padrões: agenda e avisos ligados", d.ajuste("agenda") == "1" and d.ajuste("avisos") == "1")
d.definir_ajuste("agenda", "0")
confere("ajuste salvo", d.ajuste("agenda") == "0")
try:
    d.definir_ajuste("agenda", "x")
    confere("valor inválido é recusado", False)
except d.ErroLearn:
    confere("valor inválido é recusado", True)
try:
    d.definir_ajuste("lixo", "1")
    confere("chave inválida é recusada", False)
except d.ErroLearn:
    confere("chave inválida é recusada", True)
ca.configurar("python", 3, 0, "00:00")
confere("agenda pausada nos Ajustes não gera nada", ca.executar_agenda(datetime(2026, 11, 23, 10, 0), lambda *a, **k: "Título\n\nCorpo do card de teste aqui.", None, lambda *a: None) == [])
d.definir_ajuste("agenda", "1")
confere("agenda ligada de novo gera", ca.executar_agenda(datetime(2026, 11, 23, 10, 0), lambda *a, **k: "Título\n\nCorpo do card de teste aqui.", None, lambda *a: None) != [])
chamadas = []
import heimdall_avisos_mac as mac  # noqa: E402
mac.publicar = lambda x: chamadas.append(x)
d.definir_ajuste("avisos", "0")
ca.notificar_padrao("t", "c")
confere("avisos desligados não notificam", chamadas == [])
d.definir_ajuste("avisos", "1")

# arquivar
r = d.arquivar_pasta("direito-civil")
confere("arquivar devolve onde guardou", r["guardada_em"] == ".arquivo/direito-civil", r)
confere("nada foi apagado: arquivos estão no arquivo, com a subpasta", (K / ".arquivo" / "direito-civil" / "a.md").read_text(encoding="utf-8") == "Texto A" and (K / ".arquivo" / "direito-civil" / "contratos" / "b.md").is_file())
confere("a pasta saiu do lugar de origem", not (K / "direito-civil").exists())
confere("cadastro da pasta e da subpasta saíram do banco, as outras ficam", d.obter_pasta("direito-civil") is None and d.obter_pasta("direito-civil/contratos") is None and d.obter_pasta("direito-civil-2") is not None and d.obter_pasta("python") is not None)
d.sincronizar()
confere("o sync não recadastra o que foi arquivado", d.obter_pasta("direito-civil") is None and not any(p["caminho"].startswith(".") for p in d.listar_pastas("")))
d.criar_pasta("Direito civil", "", "Direito")
(K / "direito-civil" / "novo.md").write_text("Outro", encoding="utf-8")
r2 = d.arquivar_pasta("direito-civil")
confere("arquivar de novo com o mesmo nome não sobrescreve", r2["guardada_em"] == ".arquivo/direito-civil (2)" and (K / ".arquivo" / "direito-civil" / "a.md").is_file() and (K / ".arquivo" / "direito-civil (2)" / "novo.md").is_file(), r2)
confere("arquivar não mexe em pasta de nome parecido", (K / "direito-civil-2" / "c.md").is_file() and d.obter_pasta("direito-civil-2") is not None)
for ruim in ("", "../fora", "nao-existe"):
    try:
        d.arquivar_pasta(ruim)
        confere(f"arquivar recusa {ruim!r}", False)
    except d.ErroLearn:
        confere(f"arquivar recusa {ruim!r}", True)

# site
srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("learn")


def req(metodo, caminho, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def post(rota, campos):
    return req("POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


st, corpo, _ = req("GET", "/ajustes")
csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
confere("aba Ajustes existe e mostra o estado e as pastas com formulário de agenda", st == 200 and "Agenda de cards e lições: ligada" in corpo and "Direito civil 2" in corpo and "Salvar agenda" in corpo and 'name="volta" value="ajustes"' in corpo)
ids = re.findall(r'<(?:select|input) id="([^"]+)"', corpo)
confere("ids dos campos são únicos na página", len(ids) == len(set(ids)) and all(f'for="{i}"' in corpo for i in ids if i.startswith(("cards_dia", "horario", "licao_dia"))))
confere("Ajustes está entre as abas e Nova pasta continua fora delas", ">Ajustes<" in corpo and 'href="/nova"' not in corpo)
st, _, _ = post("/ajustes/definir", {"csrf": "x", "chave": "agenda", "valor": "0"})
confere("ajuste sem csrf é recusado", st == 403)
st, _, r = post("/ajustes/definir", {"csrf": csrf, "chave": "agenda", "valor": "0"})
_, corpo, _ = req("GET", "/ajustes")
confere("pausar pela tela", st == 303 and "Agenda de cards e lições: pausada" in corpo and "Ligar a agenda" in corpo)
post("/ajustes/definir", {"csrf": csrf, "chave": "agenda", "valor": "1"})
st, _, r = post("/agenda", {"csrf": csrf, "c": "python", "cards_dia": 1, "licao_dia": 0, "horario": "07:45", "volta": "ajustes"})
confere("agenda salva nos Ajustes volta para os Ajustes", st == 303 and r.getheader("Location") == "/ajustes" and ca.obter_agenda("python")["horario"] == "07:45")
st, _, r = post("/agenda", {"csrf": csrf, "c": "python", "cards_dia": 9, "licao_dia": 0, "horario": "07:45", "volta": "ajustes"})
_, corpo, _ = req("GET", r.getheader("Location"))
confere("agenda inválida nos Ajustes mostra o erro lá mesmo", r.getheader("Location") == "/ajustes" and "No máximo 3" in corpo)
_, corpo, _ = req("GET", "/ajustes/arquivar?c=python")
confere("arquivar pede confirmação e explica que nada é apagado", "Sim, arquivar a pasta" in corpo and "Nada é apagado" in corpo and d.obter_pasta("python") is not None)
st, _, r = post("/ajustes/arquivar", {"csrf": csrf, "c": "python"})
confere("sem confirmar não arquiva", d.obter_pasta("python") is not None)
st, _, r = post("/ajustes/arquivar", {"csrf": "x", "c": "python", "confirmar": "1"})
confere("arquivar sem csrf é recusado", st == 403 and d.obter_pasta("python") is not None)
st, _, r = post("/ajustes/arquivar", {"csrf": csrf, "c": "python", "confirmar": "1"})
_, corpo, _ = req("GET", "/ajustes")
confere("arquivar confirmado", st == 303 and d.obter_pasta("python") is None and "arquivada" in corpo and (K / ".arquivo" / "python").is_dir() and not (K / "python").exists())

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
