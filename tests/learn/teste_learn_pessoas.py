#!/usr/bin/env python3
"""Testa que o Learn separa os dados por pessoa: dono, Ana e Beto não enxergam as pastas, arquivos, agenda, cards nem ajustes uns dos outros."""
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
os.environ.pop("HEIMDALL_PESSOAS", None)
(TMP / "knowledge").mkdir()

import heimdall_cloud as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_cards as ca  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
import heimdall_pessoas as pe  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


ANA, BETO = pe.id_da("ana@x.com"), pe.id_da("beto@y.com")
srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
tk = {"dono": nuvem.nova_sessao("*")[0], "ana": nuvem.nova_sessao("learn", ANA)[0], "beto": nuvem.nova_sessao("learn", BETO)[0]}
tk_antigo = nuvem.nova_sessao("learn")[0]


def req(quem, metodo, caminho, corpo=None, cab=None, token=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token or tk[quem]}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def post(quem, rota, campos):
    _, corpo, _ = req(quem, "GET", "/ajustes")
    csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
    campos = dict(campos, csrf=csrf)
    return req(quem, "POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


def multipart(quem, rel, nome, conteudo):
    _, corpo, _ = req(quem, "GET", "/ajustes")
    csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
    b = "XBORDAX"
    corpo = (f'--{b}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n--{b}\r\nContent-Disposition: form-data; name="c"\r\n\r\n{rel}\r\n'
             f'--{b}\r\nContent-Disposition: form-data; name="arquivo"; filename="{nome}"\r\nContent-Type: text/markdown\r\n\r\n{conteudo}\r\n--{b}--\r\n').encode()
    return req(quem, "POST", "/importar", corpo, {"Content-Type": f"multipart/form-data; boundary={b}"})


# Ana e o dono criam pastas com o mesmo nome
st, _, _ = post("ana", "/criar", {"nome": "Segredos da Ana", "pai": "", "categoria": "aleatorio", "tipo": "Filosofia", "tipo_novo": "", "idioma": ""})
confere("Ana cria uma pasta", st == 303)
post("dono", "/criar", {"nome": "Estudo do dono", "pai": "", "categoria": "aleatorio", "tipo": "Direito", "tipo_novo": "", "idioma": ""})
post("dono", "/criar", {"nome": "Comum", "pai": "", "categoria": "aleatorio", "tipo": "Direito", "tipo_novo": "", "idioma": ""})
post("ana", "/criar", {"nome": "Comum", "pai": "", "categoria": "sequencial", "tipo": "Programação", "tipo_novo": "", "idioma": ""})
_, pagina_dono, _ = req("dono", "GET", "/")
_, pagina_ana, _ = req("ana", "GET", "/")
_, pagina_beto, _ = req("beto", "GET", "/")
confere("o dono não vê a pasta da Ana", "segredos-da-ana" in pagina_ana and "segredos-da-ana" not in pagina_dono and "estudo-do-dono" in pagina_dono)
confere("a Ana não vê a pasta do dono", "estudo-do-dono" not in pagina_ana)
confere("o Beto não vê nada de ninguém", "segredos" not in pagina_beto and "estudo-do-dono" not in pagina_beto and "Nenhuma pasta" in pagina_beto)
confere("pastas com o mesmo nome são independentes (categoria diferente)", d.obter_pasta("comum")["categoria"] == "aleatorio" and "Sequencial" in pagina_ana)

# arquivos no lugar certo
multipart("ana", "segredos-da-ana", "ana.md", "Texto secreto da Ana")
ka = TMP / "db" / "pessoas" / ANA / "knowledge" / "segredos-da-ana" / "ana.md"
confere("arquivo da Ana fica na pasta dela, fora de knowledge/ do dono", ka.is_file() and not list((TMP / "knowledge").rglob("ana.md")))
confere("a pasta da Ana não está dentro de knowledge/ (a busca do dono não a vê)", not (TMP / "knowledge" / "pessoas").exists() and not (TMP / "knowledge" / "segredos-da-ana").exists())
confere("a Ana tem o banco dela e o dono o dele", (TMP / "db" / "pessoas" / ANA / "learn.db").is_file() and (TMP / "db" / "learn.db").is_file())
confere("permissão da pasta da Ana é só do dono do Mac", oct((TMP / "db" / "pessoas" / ANA).stat().st_mode & 0o777) == "0o700")
_, p, _ = req("ana", "GET", "/pasta?c=segredos-da-ana")
confere("a Ana vê o documento dela", "ana.md" in p)
st, p, _ = req("beto", "GET", "/pasta?c=segredos-da-ana")
confere("o Beto abrindo o caminho da pasta da Ana não vê nada", "ana.md" not in p and "Texto secreto" not in p)
st, p, _ = req("dono", "GET", "/pasta?c=segredos-da-ana")
confere("o dono abrindo o caminho da pasta da Ana não vê nada", "ana.md" not in p)
st, _, r = multipart("beto", "segredos-da-ana", "intruso.md", "x")
confere("o Beto não consegue importar na pasta da Ana", not (TMP / "db" / "pessoas" / ANA / "knowledge" / "segredos-da-ana" / "intruso.md").exists() and not list((TMP / "db").rglob("intruso.md")))
st, _, _ = post("beto", "/ajustes/arquivar", {"c": "segredos-da-ana", "confirmar": "1"})
confere("o Beto não consegue arquivar a pasta da Ana", ka.is_file() and (TMP / "db" / "pessoas" / ANA / "learn.db").is_file())

# ajustes e agenda por pessoa
post("ana", "/ajustes/definir", {"chave": "agenda", "valor": "0"})
_, aj_dono, _ = req("dono", "GET", "/ajustes")
_, aj_ana, _ = req("ana", "GET", "/ajustes")
confere("pausar a agenda da Ana não pausa a do dono", "ligada" in aj_dono and "pausada" in aj_ana)
post("ana", "/agenda", {"c": "comum", "cards_dia": 2, "licao_dia": 0, "horario": "05:00", "volta": "ajustes"})
with pe.definir(ANA):
    ag_ana = ca.obter_agenda("comum")["cards_dia"]
confere("agenda por pessoa", ag_ana == 2 and ca.obter_agenda("comum")["cards_dia"] == 0)

# agenda percorre as pessoas, sem avisos para convidado
confere("a agenda enxerga o dono e as pessoas que já usaram o Learn", pe.existentes(d.pasta_dados_base()) == ["dono", *sorted([ANA, BETO])])
(TMP / "db" / "pessoas" / ANA / "knowledge" / "comum").mkdir(parents=True, exist_ok=True)
(TMP / "db" / "pessoas" / ANA / "knowledge" / "comum" / "m.md").write_text("Texto de estudo da Ana sobre programação e funções. " * 20, encoding="utf-8")
avisos = []
with pe.definir(ANA):
    d.definir_ajuste("agenda", "1")
    saida = ca.executar_agenda(datetime(2026, 11, 23, 10, 0), lambda *a, **k: "Título\n\nCorpo do card da Ana para testar.", None, lambda *a: avisos.append(a))
    cards_ana = len(ca.listar(False, 10))
confere("card da agenda cai nos dados da Ana", cards_ana == 1 and len(ca.listar(False, 10)) == 0, saida)
confere("o dono não ganhou o card da Ana", len(ca.listar(False, 10)) == 0)
_, c_beto, _ = req("beto", "GET", "/cards")
confere("o Beto não vê o card da Ana", "Corpo do card da Ana" not in c_beto)

# sessão antiga de convidado, sem pessoa
st, _, r = req(None, "GET", "/", token=tk_antigo)
confere("sessão de convidado sem pessoa é mandada entrar de novo", st == 303 and r.getheader("Location") == "/entrar")

# interruptor
os.environ["HEIMDALL_PESSOAS"] = "0"
_, p, _ = req("ana", "GET", "/")
confere("HEIMDALL_PESSOAS=0 devolve o comportamento anterior (todos veem os dados do dono)", "estudo-do-dono" in p and "segredos" not in p)
os.environ.pop("HEIMDALL_PESSOAS")

# nenhum módulo do Learn escolhe caminho de dados sozinho
for arq in sorted(RAIZ.glob("heimdall_learn*.py")):
    txt = re.sub(r'""".*?"""', "", arq.read_text(encoding="utf-8"), flags=re.S)
    txt = re.sub(r"#[^\n]*", "", txt)
    if arq.name == "heimdall_learn_dados.py":
        continue
    confere(f"{arq.name} não monta caminho de dados por conta própria", "learn.db" not in txt and "PROJECT_DIR / \"knowledge\"" not in txt and "HEIMDALL_KNOWLEDGE_DIR\", str" not in txt and "heimdall_pastas.db" not in txt)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
