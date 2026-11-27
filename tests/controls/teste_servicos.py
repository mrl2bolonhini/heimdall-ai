#!/usr/bin/env python3
"""Teste dos serviços do StudioLibre (studio_servicos.py) e do Kuma (studio_kuma.py): catálogo, memória do que foi desligado,
ligar e desligar de verdade um processo de teste, vigia e leitura da página de status do Kuma."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import studio_kuma as hku  # noqa: E402
import studio_servicos as hsv  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {detalhe}"))
    falhas += 0 if ok else 1


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- catálogo
cat = hsv.catalogo()
ids = [s["id"] for s in cat]
confere("catálogo: ids e portas sem repetição", len(ids) == len(set(ids)) and len({s["porta"] for s in cat}) == len(cat), str(ids))
confere("catálogo: cada serviço tem nome, porta e tipo conhecido", all(s["nome"] and isinstance(s["porta"], int) and s["tipo"] in ("py", "docker", "cmd") for s in cat))
confere("catálogo: os 20 serviços da subida estão lá", len(cat) >= 20, str(len(cat)))
confere("catálogo: o Controls não pode ser desligado por aqui", "controls" not in ids)

# --- memória do que está desligado
tmp = tempfile.mkdtemp()
hsv.ARQUIVO = Path(tmp) / "desligados.json"
confere("começa sem nada desligado", hsv.desligados() == set())
hsv.marcar("news", True)
hsv.marcar("lab", True)
confere("marcar desliga e lembra", hsv.desligados() == {"news", "lab"})
hsv.marcar("news", False)
confere("ligar tira da lista", hsv.desligados() == {"lab"})
hsv.ARQUIVO.write_text("{lixo", encoding="utf-8")
confere("arquivo corrompido vira lista vazia, sem erro", hsv.desligados() == set())

# --- ligar e desligar de verdade, com um servidor de teste
porta = porta_livre()
falso = {"id": "teste", "nome": "Teste", "porta": porta, "tipo": "cmd", "log": "teste_servicos",
         "liga": [sys.executable, "-m", "http.server", str(porta), "--bind", "127.0.0.1"]}
hsv.catalogo = lambda: [falso]
hsv.LOGS_DIR = Path(tmp)
ok, msg = hsv.aplicar("teste", True)
confere("ligar sobe o processo e a porta responde", ok and hsv.no_ar(falso), msg)
confere("ligar de novo diz que já estava no ar", hsv.ligar(falso) == (True, "já estava no ar"))
ok, msg = hsv.aplicar("teste", False)
confere("desligar derruba o processo", ok and not hsv.no_ar(falso) and "teste" in hsv.desligados(), msg)
# vigia: se voltar ao ar enquanto marcado como desligado, é derrubado
hsv.ligar(falso)
confere("de volta ao ar", hsv.no_ar(falso))
confere("o vigia derruba o que deveria estar desligado", hsv.reconciliar_uma_vez() == ["teste"] and not hsv.no_ar(falso))
hsv.marcar("teste", False)
hsv.ligar(falso)
confere("o vigia não mexe no que pode ficar ligado", hsv.reconciliar_uma_vez() == [] and hsv.no_ar(falso))
hsv.desligar(falso)
ok, msg = hsv.aplicar("inexistente", True)
confere("serviço desconhecido é recusado", not ok)
sem_liga = {"id": "x", "nome": "X", "porta": porta_livre(), "tipo": "py", "script": None}
confere("serviço sem como ligar explica o caminho", hsv.ligar(sem_liga)[0] is False and "studio restart" in hsv.ligar(sem_liga)[1])

# --- Kuma: leitura da página de status
PAGINA = {"publicGroupList": [{"monitorList": [{"id": 1, "name": "Lab (8010)"}, {"id": 2, "name": "Notas"}, {"id": 3, "name": "Jogos"}]}]}
BEATS = {"heartbeatList": {"1": [{"status": 0}, {"status": 1}], "2": [{"status": 0}], "3": []}}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        d = BEATS if "heartbeat" in self.path else PAGINA
        b = json.dumps(d).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
hku.URL = f"http://127.0.0.1:{srv.server_port}"
mons, erro = hku.monitores()
confere("Kuma: lê os monitores e o último batimento", not erro and [m["status"] for m in mons] == ["no ar", "fora do ar", "desconhecido"], str(mons))
confere("Kuma: acha o monitor pelo nome do serviço, sem acento nem parênteses", hku.achar(mons, "Lab")["id"] == 1 and hku.achar(mons, "Notes", "Notas")["id"] == 2
        and hku.achar(mons, "Uptime Kuma") is None)
srv.shutdown()
mons, erro = hku.monitores()
confere("Kuma fora do ar: devolve lista vazia e o motivo", mons == [] and "Kuma" in erro, erro)
os.environ.pop("STUDIO_KUMA_USUARIO", None)
# Cliente socketio de mentira: registra o que foi chamado e dispara (ou não) o autoLogin ao conectar.
import types
_chamadas, _cfg = [], {"auto": False, "login_ok": True}


class _Cli:
    def __init__(self, **k):
        self.h = {}

    def on(self, ev, f):
        self.h[ev] = f

    def connect(self, url, wait_timeout=0):
        if _cfg["auto"] and "autoLogin" in self.h:
            self.h["autoLogin"]()

    def call(self, ev, dados=None, timeout=0):
        _chamadas.append((ev, dados))
        return {"ok": _cfg["login_ok"] if ev == "login" else True}

    def disconnect(self):
        pass


sys.modules["socketio"] = types.SimpleNamespace(Client=_Cli)
os.environ.pop("STUDIO_KUMA_USUARIO", None)
os.environ.pop("STUDIO_KUMA_SENHA", None)
_cfg["auto"] = False
r = hku.pausar_ou_retomar(7, True)
confere("pausar sem usuário e senha e com login ligado no Kuma explica o que fazer", "STUDIO_KUMA_USUARIO" in r and "Disable Auth" in r and not _chamadas, r)
_cfg["auto"] = True
_chamadas.clear()
confere("pausar com o login do Kuma desligado funciona sem senha (autoLogin) e não tenta logar", hku.pausar_ou_retomar(7, True) == "" and _chamadas == [("pauseMonitor", 7)], str(_chamadas))
_chamadas.clear()
confere("retomar também", hku.pausar_ou_retomar(7, False) == "" and _chamadas == [("resumeMonitor", 7)])
os.environ["STUDIO_KUMA_USUARIO"], os.environ["STUDIO_KUMA_SENHA"] = "u", "s"
_chamadas.clear()
confere("com usuário e senha entra com eles e depois pausa", hku.pausar_ou_retomar(7, True) == "" and [c[0] for c in _chamadas] == ["login", "pauseMonitor"])
_cfg["login_ok"] = False
confere("senha recusada pelo Kuma é dita", "recusou" in hku.pausar_ou_retomar(7, True))
os.environ.pop("STUDIO_KUMA_USUARIO", None)
os.environ.pop("STUDIO_KUMA_SENHA", None)

print("\nTUDO OK" if not falhas else f"\n{falhas} FALHA(S)")
sys.exit(1 if falhas else 0)
