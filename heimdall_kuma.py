#!/usr/bin/env python3
"""Uptime Kuma (status.heimdall-ai.tech) visto pelo Controls: ler a situação de cada monitor e pausar/retomar o monitor de um serviço.

Ler: a página de status pública do Kuma, pelo endereço local (HEIMDALL_KUMA_URL, padrão http://127.0.0.1:3001) e o nome da página
(HEIMDALL_KUMA_SLUG, padrão heimdall). Não precisa de senha.
Pausar e retomar: o Kuma só oferece isso pela API autenticada (socket.io). Precisa de HEIMDALL_KUMA_USUARIO e HEIMDALL_KUMA_SENHA no .env
e do pacote python-socketio. Sem eles o Controls continua ligando e desligando o serviço de verdade e avisa que o Kuma não foi mexido.
O monitor de um serviço é achado pelo nome: o primeiro monitor cujo nome contém o nome do serviço (sem acento, sem maiúsculas).
"""
import json
import os
import unicodedata
import urllib.request

URL = os.environ.get("HEIMDALL_KUMA_URL", "http://127.0.0.1:3001").rstrip("/")
SLUG = os.environ.get("HEIMDALL_KUMA_SLUG", "heimdall")


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def _get(caminho: str) -> dict:
    req = urllib.request.Request(URL + caminho, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.loads(r.read().decode("utf-8"))


def monitores() -> tuple:
    """(lista, erro). Cada item: {id, nome, status} com status "no ar", "fora do ar", "pendente" ou "desconhecido"."""
    try:
        pagina = _get(f"/api/status-page/{SLUG}")
        beats = _get(f"/api/status-page/heartbeat/{SLUG}").get("heartbeatList", {})
    except (OSError, ValueError) as ex:
        return [], f"Kuma não respondeu ({type(ex).__name__})"
    nomes = {"1": "no ar", "0": "fora do ar", "2": "pendente", "3": "manutenção"}
    saida = []
    for g in pagina.get("publicGroupList", []):
        for m in g.get("monitorList", []):
            lista = beats.get(str(m.get("id")), [])
            st = nomes.get(str(lista[-1].get("status"))) if lista else None
            saida.append({"id": m.get("id"), "nome": m.get("name", ""), "status": st or "desconhecido"})
    return saida, ""


def achar(mons: list, nome_servico: str):
    alvo = _norm(nome_servico).split(" (")[0].strip()
    return next((m for m in mons if alvo and alvo in _norm(m["nome"])), None)


def pausar_ou_retomar(monitor_id: int, pausar: bool) -> str:
    """Devolve "" se deu certo ou o motivo de não ter dado."""
    usuario, senha = os.environ.get("HEIMDALL_KUMA_USUARIO", ""), os.environ.get("HEIMDALL_KUMA_SENHA", "")
    if not usuario or not senha:
        return "sem HEIMDALL_KUMA_USUARIO e HEIMDALL_KUMA_SENHA no .env"
    try:
        import socketio  # python-socketio
    except ImportError:
        return "pacote python-socketio não instalado"
    cli = socketio.Client(reconnection=False)
    try:
        cli.connect(URL, wait_timeout=6)
        r = cli.call("login", {"username": usuario, "password": senha, "token": ""}, timeout=8)
        if not (isinstance(r, dict) and r.get("ok")):
            return "o Kuma recusou o usuário ou a senha"
        r = cli.call("pauseMonitor" if pausar else "resumeMonitor", monitor_id, timeout=8)
        return "" if isinstance(r, dict) and r.get("ok") else "o Kuma não aceitou o pedido"
    except Exception as ex:  # noqa: BLE001 - qualquer falha de rede vira aviso
        return f"falha ao falar com o Kuma ({type(ex).__name__})"
    finally:
        try:
            cli.disconnect()
        except Exception:  # noqa: BLE001
            pass
