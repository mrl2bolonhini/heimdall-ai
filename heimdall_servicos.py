#!/usr/bin/env python3
"""Serviços do Heimdall: o catálogo único, o estado (no ar ou fora), ligar e desligar cada um, e a memória do que você desligou.

Quem usa: o Controls (aba Serviços). Para um serviço novo aparecer lá, acrescente uma linha em CATALOGO e só.

Como liga e desliga:
  - "py": script Python do Heimdall. Desliga encerrando quem escuta na porta; liga com o python do venv, a porta no ambiente e o log em logs/.
  - "docker": contêiner. Desliga com docker stop e liga com docker start (o contêiner precisa existir: a primeira vez é do start_heimdall.sh).
  - "cmd": comando próprio (LiteLLM, Ollama).
  - sem "liga": só desliga aqui; para ligar de novo use heimdall restart.
O que você desligou fica em .heimdall_desligados.json. Um vigia (reconciliar) confere de 30 em 30 segundos e derruba de novo o que
deveria estar desligado, por exemplo depois de um "heimdall update --restart", mas só depois de a subida terminar (3 minutos), para
não atrapalhar a espera do start_heimdall.sh. Ligar um serviço tira ele da lista de desligados.
O Controls não aparece como desligável: desligá-lo cortaria o acesso ao painel.
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ARQUIVO = PROJECT_DIR / ".heimdall_desligados.json"
LOGS_DIR = PROJECT_DIR / "logs"
ESPERA_VIGIA_S = int(os.environ.get("HEIMDALL_SERVICOS_ESPERA_S", "180"))
INTERVALO_VIGIA_S = 30


def _porta(var: str, padrao: int) -> int:
    try:
        return int(os.environ.get(var) or padrao)
    except ValueError:
        return padrao


def catalogo() -> list:
    """Lista de serviços, na ordem em que aparecem. As portas respeitam o .env."""
    py = sys.executable or "python3"
    lit = str(Path(py).parent / "litellm")
    lit_cmd = [lit] if os.path.exists(lit) else [py, "-m", "litellm.proxy.proxy_cli"]
    return [
        {"id": "litellm", "nome": "LiteLLM", "porta": 9000, "tipo": "cmd", "log": "litellm",
         "liga": lit_cmd + ["--config", "litellm_config.yaml", "--host", "0.0.0.0", "--port", "9000"]},
        {"id": "ollama", "nome": "Ollama", "porta": 11434, "tipo": "cmd", "log": "ollama", "liga": ["ollama", "serve"]},
        {"id": "qdrant", "nome": "Qdrant", "porta": 6333, "tipo": "docker", "alvo": ["qdrant"]},
        {"id": "searxng", "nome": "SearXNG", "porta": 8080, "tipo": "docker", "alvo": ["searxng"]},
        {"id": "docling", "nome": "Docling", "porta": 5001, "tipo": "docker", "alvo": ["docling"], "opcional": True},
        {"id": "mcp", "nome": "MCP Mac", "porta": 8000, "tipo": "py", "script": ["heimdall_mcp.py", "--group", "mac"], "log": "mcp_debug"},
        {"id": "mcp_public", "nome": "MCP public", "apelidos": ["mcp publico"], "porta": 8001, "tipo": "py", "script": ["heimdall_mcp.py", "--group", "public"], "log": "mcp_public_debug"},
        {"id": "mcp_dados", "nome": "MCP data", "apelidos": ["mcp dados"], "porta": 8004, "tipo": "py", "script": ["heimdall_mcp.py", "--group", "dados"], "log": "mcp_dados_debug"},
        {"id": "terminal", "nome": "Open Terminal", "porta": 8002, "tipo": "py", "script": None, "log": "open_terminal"},
        {"id": "agente", "nome": "Mac Agent", "apelidos": ["agente"], "porta": _porta("HEIMDALL_AGENTE_PORT", 8003), "tipo": "py", "script": ["heimdall_agente.py"],
         "porta_env": "HEIMDALL_AGENTE_PORT", "log": "agente_debug"},
        {"id": "cloud", "nome": "Cloud", "porta": _porta("HEIMDALL_CLOUD_PORT", 8010), "tipo": "py", "script": ["heimdall_cloud.py"],
         "porta_env": "HEIMDALL_CLOUD_PORT", "log": "cloud_debug"},
        {"id": "notas", "nome": "Notes", "apelidos": ["notas"], "porta": _porta("HEIMDALL_NOTAS_PORT", 8011), "tipo": "py", "script": ["heimdall_notas.py"],
         "porta_env": "HEIMDALL_NOTAS_PORT", "log": "notas_debug"},
        {"id": "news", "nome": "News", "porta": _porta("HEIMDALL_NEWS_PORT", 8012), "tipo": "py", "script": ["heimdall_news.py"],
         "porta_env": "HEIMDALL_NEWS_PORT", "log": "news_debug"},
        {"id": "saude", "nome": "Health", "apelidos": ["saude"], "porta": _porta("HEIMDALL_SAUDE_PAINEL_PORT", 8013), "tipo": "py", "script": ["heimdall_painel_saude.py"],
         "porta_env": "HEIMDALL_SAUDE_PAINEL_PORT", "log": "saude_painel_debug"},
        {"id": "jogos", "nome": "Games", "apelidos": ["jogos"], "porta": _porta("HEIMDALL_JOGOS_PORT", 8014), "tipo": "py", "script": ["heimdall_jogos.py"],
         "porta_env": "HEIMDALL_JOGOS_PORT", "log": "jogos_debug"},
        {"id": "finance", "nome": "Finance", "porta": _porta("HEIMDALL_FINANCE_PORT", 8016), "tipo": "py", "script": ["heimdall_finance.py"],
         "porta_env": "HEIMDALL_FINANCE_PORT", "log": "finance_debug"},
        {"id": "kuma", "nome": "Uptime Kuma", "porta": 3001, "tipo": "docker", "alvo": ["uptime-kuma"], "kuma": False},
        {"id": "dozzle", "nome": "Dozzle", "porta": 8081, "tipo": "docker", "alvo": ["dozzle"]},
        {"id": "n8n", "nome": "n8n", "porta": 5678, "tipo": "docker", "alvo": ["n8n"]},
        {"id": "webui", "nome": "Open WebUI", "porta": 3000, "tipo": "docker", "alvo": ["open-webui"]},
        {"id": "aws", "nome": "AWS Emulator", "apelidos": ["emulador", "aws"], "porta": 4566, "tipo": "docker", "alvo": ["moto", "localstack"]},
    ]


def parar_tudo() -> list:
    """Encerra a subida (start_heimdall.sh) e desliga todos os serviços do catálogo. O Controls fica de pé, para você poder religar (Start).
    Não marca nada como desligado de propósito: o Start sobe tudo de novo."""
    _rodar(["pkill", "-f", "start_heimdall.sh"], 8)
    cat = catalogo()
    resultados = []
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for sv, (ok, msg) in zip(cat, ex.map(desligar, cat)):
            resultados.append((sv["nome"], ok, msg))
    return resultados


def iniciar_tudo() -> tuple:
    """Sobe o Heimdall inteiro como o heimdall up (subir.sh), sem esperar. A saída vai para logs/controls_manutencao.log."""
    script = PROJECT_DIR / "subir.sh"
    if not script.exists():
        return False, "subir.sh não encontrado"
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log = open(LOGS_DIR / "controls_manutencao.log", "ab")
        subprocess.Popen(["/bin/bash", str(script)], cwd=str(PROJECT_DIR), env=_ambiente(), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as ex:
        return False, f"não consegui iniciar: {type(ex).__name__}"
    return True, "subida iniciada"


def por_id(sid: str):
    return next((s for s in catalogo() if s["id"] == sid), None)


def porta_aberta(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.4):
            return True
    except OSError:
        return False


def _rodar(cmd: list, tempo: int = 40) -> tuple:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo, env=_ambiente())
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, f"{type(ex).__name__}: {ex}"


def _ambiente() -> dict:
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"
    return env


# ----------------------------------------------------------------------------------------
# Lista do que está desligado de propósito
# ----------------------------------------------------------------------------------------
_trava = threading.Lock()


def desligados() -> set:
    try:
        d = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        return {str(x) for x in d.get("desligados", [])}
    except (OSError, ValueError, AttributeError):
        return set()


def _gravar(conj: set) -> None:
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"desligados": sorted(conj)}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ARQUIVO)


def marcar(sid: str, desligado: bool) -> None:
    with _trava:
        c = desligados()
        (c.add if desligado else c.discard)(sid)
        _gravar(c)


# ----------------------------------------------------------------------------------------
# Estado, desligar, ligar
# ----------------------------------------------------------------------------------------
def no_ar(s: dict) -> bool:
    return porta_aberta(s["porta"])


def _pids_da_porta(porta: int) -> list:
    rc, out = _rodar(["lsof", "-ti", f"tcp:{porta}", "-sTCP:LISTEN"], 8)
    return [int(x) for x in out.split() if x.isdigit()] if rc == 0 else []


def _parar_porta(porta: int) -> tuple:
    pids = _pids_da_porta(porta)
    if not pids:
        return True, "já estava parado"
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(25):
        if not porta_aberta(porta):
            return True, "parado"
        time.sleep(0.2)
    for p in _pids_da_porta(porta):
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.5)
    return (not porta_aberta(porta)), "parado à força" if not porta_aberta(porta) else "não consegui parar"


def _existentes(alvos: list) -> list:
    rc, out = _rodar(["docker", "ps", "-a", "--format", "{{.Names}}"], 15)
    nomes = set(out.split()) if rc == 0 else set()
    return [a for a in alvos if a in nomes]


def desligar(s: dict) -> tuple:
    """Desliga o serviço. Devolve (deu certo, mensagem curta)."""
    if s["tipo"] == "docker":
        if not shutil.which("docker", path=_ambiente()["PATH"]):
            return False, "o Docker não foi encontrado"
        ex = _existentes(s["alvo"])
        if not ex:
            return True, "o contêiner não existe, nada a parar"
        rc, out = _rodar(["docker", "stop"] + ex, 60)
        return rc == 0, "parado" if rc == 0 else out[-200:]
    return _parar_porta(s["porta"])


def ligar(s: dict) -> tuple:
    if no_ar(s):
        return True, "já estava no ar"
    if s["tipo"] == "docker":
        ex = _existentes(s["alvo"])
        if not ex:
            return False, "o contêiner ainda não foi criado: rode heimdall restart uma vez com este serviço ligado"
        rc, out = _rodar(["docker", "start"] + ex, 60)
        return rc == 0, "ligado" if rc == 0 else out[-200:]
    cmd = s.get("liga")
    if s["tipo"] == "py" and s.get("script"):
        cmd = [sys.executable or "python3"] + s["script"]
    if not cmd:
        return False, "este serviço só liga com: heimdall restart"
    env = _ambiente()
    env["HEIMDALL_DIR"] = str(PROJECT_DIR)
    if s.get("porta_env"):
        env[s["porta_env"]] = str(s["porta"])
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log = open(LOGS_DIR / f"{s.get('log', s['id'])}.log", "ab")
        subprocess.Popen(cmd, cwd=str(PROJECT_DIR), env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as ex:
        return False, f"não consegui iniciar: {type(ex).__name__}"
    for _ in range(40):
        if no_ar(s):
            return True, "ligado"
        time.sleep(0.5)
    return False, f"iniciei, mas a porta {s['porta']} ainda não respondeu: veja o log de {s['nome']}"


def aplicar(sid: str, ligado: bool) -> tuple:
    """Liga ou desliga, lembra a escolha e devolve (deu certo, mensagem)."""
    s = por_id(sid)
    if not s:
        return False, "serviço desconhecido"
    marcar(sid, not ligado)
    ok, msg = (ligar if ligado else desligar)(s)
    if not ok and ligado:
        marcar(sid, True)  # não subiu: continua marcado como desligado
    return ok, f"{s['nome']}: {msg}"


def reconciliar_uma_vez() -> list:
    """Derruba o que está marcado como desligado e voltou ao ar. Devolve o que foi derrubado."""
    feitos = []
    for s in catalogo():
        if s["id"] in desligados() and no_ar(s):
            desligar(s)
            feitos.append(s["id"])
    return feitos


def iniciar_vigia() -> None:
    def laco():
        time.sleep(ESPERA_VIGIA_S)
        while True:
            try:
                reconciliar_uma_vez()
            except Exception as ex:  # o vigia nunca pode cair
                sys.stderr.write(f"vigia de serviços: {type(ex).__name__}\n")
            time.sleep(INTERVALO_VIGIA_S)
    threading.Thread(target=laco, daemon=True, name="vigia-servicos").start()
