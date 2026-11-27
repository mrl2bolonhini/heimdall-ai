#!/usr/bin/env python3
"""Testa o ponto de entrada do contêiner de continuidade sem Docker: /health só fica pronto depois de restaurar a cópia, o site sobe em modo de leitura e uma falha de restauração não sobe nada."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import importlib.util
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(RAIZ))
falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:400])


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pegar(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, dict(ex.headers)
    except Exception:  # noqa: BLE001
        return 0, {}


def espera(cond, seg=20):
    t = time.time()
    while time.time() - t < seg:
        if cond():
            return True
        time.sleep(0.3)
    return False


import urllib.error  # noqa: E402
import studio_continuidade as hc  # noqa: E402

dados = tempfile.mkdtemp()
p_saude, p_fin = porta_livre(), porta_livre()
os.environ.update({"STUDIO_RAIZ": str(RAIZ), "STUDIO_SAUDE_PORTA": str(p_saude), "STUDIO_FINANCE_DIR": dados,
                   "HEIMDALL_CLOUD_SENHA_HASH": "pbkdf2$teste", "HEIMDALL_CLOUD_TOTP_SEGREDO": "JBSWY3DPEHPK3PXP"})
spec = importlib.util.spec_from_file_location("entrada", RAIZ / "cloudflare" / "continuity" / "entrada.py")
entrada = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrada)
entrada.SERVICOS = [("studio_finance.py", "STUDIO_FINANCE_PORT", p_fin)]
confere("a lista de serviços aponta para arquivos que existem", all((RAIZ / m).exists() for m, _, _ in [(x[0], 0, 0) for x in [("studio_finance.py",), ("studio_painel_saude.py",), ("studio_news.py",), ("studio_learn.py",), ("studio_jogos.py",), ("studio_account.py",)]]))

# falha de restauração: sai com erro e não fica pronto
hc.restaurar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("não há cópia de continuidade no R2"))
_dormir = time.sleep
time.sleep = lambda s: None
rc = entrada.main()
confere("restauração com falha encerra com erro e não fica pronto", rc == 1 and entrada.estado["pronto"] is False and "não há cópia" in entrada.estado["erro"], entrada.estado)

# restauração boa: sobe o site em modo de leitura
hc.restaurar = lambda *a, **k: {"ok": True, "quando": "2026-11-23T21:00:00+00:00", "arquivos": ["finance/financas.db"]}
entrada.estado.update({"pronto": False, "erro": ""})
time.sleep = _dormir
t = threading.Thread(target=entrada.main, daemon=True)
t.start()
confere("/health fica pronto e informa a data da cópia", espera(lambda: pegar(f"http://127.0.0.1:{p_saude}/health")[0] == 200), pegar(f"http://127.0.0.1:{p_saude}/health"))
st, cab = pegar(f"http://127.0.0.1:{p_saude}/health")
confere("o cabeçalho X-Heimdall-Copia leva a data da cópia", cab.get("X-Heimdall-Copia") == "2026-11-23T21:00:00+00:00", cab)
confere("o site do Finance responde dentro do contêiner", espera(lambda: pegar(f"http://127.0.0.1:{p_fin}/saude")[0] == 200), pegar(f"http://127.0.0.1:{p_fin}/saude"))
confere("o modo continuidade está ligado nos filhos", os.environ.get("HEIMDALL_CONTINUIDADE_MODO") == "1")
for f in list(entrada.FILHOS.values()):
    f.terminate()
    f.wait(5)
_di = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
_regras = [l.strip() for l in _di if l.strip() and not l.startswith("#")]
confere("imagem: o .dockerignore da raiz é lista de permissão (começa por * e deixa .env, bancos e dados fora)",
        _regras[0] == "*" and "!db" not in _regras and "!finance" not in _regras and "!health" not in _regras and "!brain" not in _regras and "**/.env*" in _regras and "**/*.db" in _regras, _regras)
confere("imagem: a imagem copia só o que o .dockerignore deixa passar (COPY . /app) e não há ignore ao lado do Dockerfile", "COPY . /app" in (RAIZ / "cloudflare/continuity/Dockerfile").read_text(encoding="utf-8")
        and not (RAIZ / "cloudflare/continuity/Dockerfile.dockerignore").exists())
print("\nFALHAS:", falhas)
os._exit(1 if falhas else 0)
