#!/usr/bin/env python3
"""Teste do alerta de memória do Mac (fluxo 4 do n8n) e do emulador de AWS sob demanda (studio lab --start/--stop)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:400])


# --- alerta: a regra do nó "Avaliar limites", executada com o Node e métricas de exemplo
fluxo = json.loads((RAIZ / "flows/basic/4-alerta-saude-mac.json").read_text(encoding="utf-8"))
codigo = next(n["parameters"]["jsCode"] for n in fluxo["nodes"] if n["name"] == "Avaliar limites")
confere("o fluxo não usa mais o limite de swap em GB", "__ALERTA_SWAP__" not in codigo and "swapGb" not in codigo)
confere("o fluxo avisa pela memória livre", "mem_livre_percent" in codigo and "__ALERTA_MEM_LIVRE__" in codigo)

instalador = (RAIZ / "scripts/instalar_fluxos_n8n.sh").read_text(encoding="utf-8")
confere("o instalador troca __ALERTA_MEM_LIVRE__ pelo limite (padrão 30)", '"__ALERTA_MEM_LIVRE__"' in instalador and "STUDIO_ALERT_MEM_FREE:-30" in instalador)
confere("o instalador não deixa nenhum marcador de swap", "__ALERTA_SWAP__" not in instalador and "ALERT_SWAP" not in instalador)

node = shutil.which("node")
if not node:
    print("pulado: Node não está instalado (regra do alerta não executada)")
else:
    def avaliar(metricas):
        js = (codigo.replace("__ALERTA_RAM__", "95").replace("__ALERTA_MEM_LIVRE__", "30")
              .replace("__ALERTA_DISCO__", "90").replace("__ALERTA_LIVRE__", "20"))
        prog = ("const dados = %s;\nconst $input = { first: () => ({ json: dados }) };\n"
                "const $getWorkflowStaticData = () => (globalThis.__est = globalThis.__est || {});\n"
                "const f = new Function('$input', '$getWorkflowStaticData', %s);\n"
                "console.log(JSON.stringify(f($input, $getWorkflowStaticData)));") % (json.dumps(metricas), json.dumps(js))
        r = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout.strip() or "null") if r.returncode == 0 else r.stderr

    base = {"cpu_percent": 25, "ram_percent": 60, "ram_used_gb": 9.6, "ram_total_gb": 16, "disk_percent": 40, "disk_free_gb": 300}
    r = avaliar({**base, "mem_livre_percent": 68, "swap_used_gb": 8.4})
    confere("swap alto com memória livre confortável (68%) não gera aviso", r == [], r)
    r = avaliar({**base, "mem_livre_percent": 25, "swap_used_gb": 6.4})
    confere("memória livre abaixo do limite (25% < 30%) gera aviso com o swap na mensagem",
            isinstance(r, list) and len(r) == 1 and "memória livre em 25%" in r[0]["json"]["mensagem"] and "swap em 6.4 GB" in r[0]["json"]["mensagem"], r)
    r = avaliar({**base, "mem_livre_percent": 30, "swap_used_gb": 0})
    confere("exatamente no limite (30%) não avisa", r == [], r)
    r = avaliar({**base, "swap_used_gb": 12})
    confere("sem a métrica de memória livre (MCP antigo), não avisa por swap", r == [], r)
    r = avaliar({**base, "ram_percent": 97, "mem_livre_percent": 50, "swap_used_gb": 0})
    confere("RAM acima do limite continua avisando", isinstance(r, list) and len(r) == 1 and "RAM em 97%" in r[0]["json"]["mensagem"], r)
    r = avaliar({**base, "disk_percent": 95, "mem_livre_percent": 50, "swap_used_gb": 0})
    confere("disco cheio continua avisando", isinstance(r, list) and len(r) == 1 and "disco em 95%" in r[0]["json"]["mensagem"], r)

# --- métricas do MCP trazem mem_livre_percent
mcp = (RAIZ / "studio_mcp.py").read_text(encoding="utf-8")
confere("as métricas do MCP incluem mem_livre_percent (kern.memorystatus_level, com reserva no psutil)",
        '"mem_livre_percent"' in mcp and "kern.memorystatus_level" in mcp and "ram.available / ram.total" in mcp)

# --- ajuda das variáveis
ajuda = (RAIZ / "studio_config_ajuda.py").read_text(encoding="utf-8")
confere("a ajuda do .env descreve STUDIO_ALERT_MEM_FREE e STUDIO_AWS_EMULATOR_INICIO", "STUDIO_ALERT_MEM_FREE" in ajuda and "STUDIO_AWS_EMULATOR_INICIO" in ajuda)
confere("a ajuda do .env não cita mais STUDIO_ALERT_SWAP", "STUDIO_ALERT_SWAP" not in ajuda)

# --- emulador sob demanda: scripts de subida
start = (RAIZ / "start_studio.sh").read_text(encoding="utf-8")
subir = (RAIZ / "subir.sh").read_text(encoding="utf-8")
confere("start_studio.sh tem o modo sob demanda e só o aplica se o contêiner já existe",
        'STUDIO_AWS_EMULATOR_INICIO:-demanda' in start and "AWS_EMU=demanda" in start and "grep -qE '^(localstack|moto)$'" in start)
confere("no modo sob demanda o emulador é parado, não criado", re.search(r"demanda\)\s*\n\s*docker stop moto localstack", start) is not None)
confere("subir.sh não espera o emulador quando ele está sob demanda", "EMU_SOB_DEMANDA" in subir and '[ "$EMU_SOB_DEMANDA" = "1" ] || LISTA+=("Emulador de AWS|tcp|4566")' in subir)

# --- comando studio lab --start / --stop com um docker de mentira
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    bin_ = tmp / "bin"
    bin_.mkdir()
    log = tmp / "docker.log"
    docker = bin_ / "docker"
    docker.write_text('#!/bin/bash\necho "$@" >> "$FAKE_LOG"\n'
                      'if [ "$1" = "ps" ]; then printf "%s\\n" $FAKE_CONTAINERS; fi\nexit 0\n', encoding="utf-8")
    curl = bin_ / "curl"
    curl.write_text('#!/bin/bash\nexit 0\n', encoding="utf-8")
    sleep = bin_ / "sleep"
    sleep.write_text('#!/bin/bash\nexit 0\n', encoding="utf-8")
    for f in (docker, curl, sleep):
        f.chmod(0o755)

    def lab(args, contêineres):
        env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FAKE_LOG": str(log), "FAKE_CONTAINERS": contêineres, "STUDIO_DIR": str(RAIZ)}
        log.write_text("")
        r = subprocess.run(["bash", "-c", f'source "{RAIZ}/studio.zsh"; studio lab {args}'], capture_output=True, text=True, timeout=60, env=env)
        return r.returncode, r.stdout + r.stderr, log.read_text()

    rc, out, dlog = lab("--start", "localstack")
    confere("lab --start liga o contêiner localstack e confirma que respondeu", rc == 0 and "start localstack" in dlog.splitlines() and "no ar" in out, (rc, out, dlog))
    rc, out, dlog = lab("--start", "moto")
    confere("lab --start usa o Moto quando é o que existe", rc == 0 and "start moto" in dlog.splitlines(), (rc, out, dlog))
    rc, out, dlog = lab("--start", "")
    confere("lab --start sem emulador criado avisa e falha, sem docker start", rc != 0 and not any(l.startswith("start") for l in dlog.splitlines()) and "Ainda não existe emulador" in out, (rc, out, dlog))
    rc, out, dlog = lab("--stop", "localstack")
    confere("lab --stop desliga o localstack e o moto", rc == 0 and "stop localstack moto" in dlog.splitlines() and "desligado" in out, (rc, out, dlog))
    rc, out, dlog = lab("-s", "localstack")
    confere("a forma curta -s vale como --start", "start localstack" in dlog.splitlines(), (rc, out, dlog))
    rc, out, dlog = lab("-p", "localstack")
    confere("a forma curta -p vale como --stop", "stop localstack moto" in dlog.splitlines(), (rc, out, dlog))
    rc, out, dlog = lab("--nada", "localstack")
    confere("opção desconhecida mostra o uso", rc != 0 and "studio lab [--local] [--start] [--stop]" in out, (rc, out))

# --- Lab: mensagem quando o emulador está desligado
lab_py = (RAIZ / "studio_lab.py").read_text(encoding="utf-8")
confere("o Lab explica que o emulador é sob demanda e onde ligar, sem comando de terminal na tela", "sob demanda" in lab_py and "aba Serviços" in lab_py and "ligue-o com studio lab --start" not in lab_py)

print("\nFalhas: %d" % falhas)
raise SystemExit(1 if falhas else 0)
