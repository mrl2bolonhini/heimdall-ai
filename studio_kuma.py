#!/usr/bin/env python3
"""Uptime Kuma (status.studiolibre.io) visto pelo Controls: ler a situação de cada monitor e pausar/retomar o monitor de um serviço.

Ler: a página de status pública do Kuma, pelo endereço local (STUDIO_KUMA_URL, padrão http://127.0.0.1:3001) e o nome da página
(STUDIO_KUMA_SLUG, padrão heimdall). Não precisa de senha.
Pausar e retomar: o Kuma só oferece isso pela API autenticada (socket.io). Precisa de STUDIO_KUMA_USUARIO e STUDIO_KUMA_SENHA no .env
e do pacote python-socketio. Sem eles o Controls continua ligando e desligando o serviço de verdade e avisa que o Kuma não foi mexido.
O monitor de um serviço é achado pelo nome: o primeiro monitor cujo nome contém o nome do serviço (sem acento, sem maiúsculas).
"""
import json
import os
import time
import unicodedata
import urllib.request

URL = os.environ.get("STUDIO_KUMA_URL", "http://127.0.0.1:3001").rstrip("/")
SLUG = os.environ.get("STUDIO_KUMA_SLUG", "heimdall")


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


_ABRIR = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # o Kuma é local: nunca passa por proxy


def _get(caminho: str) -> dict:
    req = urllib.request.Request(URL + caminho, headers={"Accept": "application/json"})
    with _ABRIR(req, timeout=2.5) as r:
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


def achar(mons: list, *nomes: str):
    """Primeiro monitor cujo nome contém um dos nomes dados (o nome do serviço e os apelidos)."""
    for nome in nomes:
        alvo = _norm(nome).split(" (")[0].strip()
        m = next((m for m in mons if alvo and alvo in _norm(m["nome"])), None)
        if m:
            return m
    return None


def pausar_ou_retomar(monitor_id: int, pausar: bool) -> str:
    """Devolve "" se deu certo ou o motivo de não ter dado. Com STUDIO_KUMA_USUARIO e STUDIO_KUMA_SENHA entra com elas; sem elas, só
    funciona se o login do Kuma estiver desligado (Settings, Security, Disable Auth): nesse caso o Kuma avisa "autoLogin" ao conectar."""
    usuario, senha = os.environ.get("STUDIO_KUMA_USUARIO", ""), os.environ.get("STUDIO_KUMA_SENHA", "")
    try:
        import socketio  # python-socketio
    except ImportError:
        return "pacote python-socketio não instalado"
    cli = socketio.Client(reconnection=False)
    entrou = []
    cli.on("autoLogin", lambda *a: entrou.append(True))
    try:
        cli.connect(URL, wait_timeout=6)
        if usuario and senha:
            r = cli.call("login", {"username": usuario, "password": senha, "token": ""}, timeout=8)
            if not (isinstance(r, dict) and r.get("ok")):
                return "o Kuma recusou o usuário ou a senha"
        else:
            for _ in range(30):  # até 3 s esperando o Kuma dizer que entrou sozinho
                if entrou:
                    break
                time.sleep(0.1)
            if not entrou:
                return "sem STUDIO_KUMA_USUARIO e STUDIO_KUMA_SENHA no .env e o Kuma ainda exige login (desligue em Settings, Security, Disable Auth)"
        r = cli.call("pauseMonitor" if pausar else "resumeMonitor", monitor_id, timeout=8)
        return "" if isinstance(r, dict) and r.get("ok") else "o Kuma não aceitou o pedido"
    except Exception as ex:  # noqa: BLE001 - qualquer falha de rede vira aviso
        return f"falha ao falar com o Kuma ({type(ex).__name__})"
    finally:
        try:
            cli.disconnect()
        except Exception:  # noqa: BLE001
            pass
