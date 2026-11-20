#!/usr/bin/env python3
"""Testa que o agente abre Notas, Lembretes e Calendário escondidos (open -g -j) e só fecha o que ele mesmo abriu."""
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_agente as ag  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + repr(detalhe)[:400])


chamadas = []
rodando = set()
na_frente = [""]


def falso(cmd, **kw):
    chamadas.append(list(cmd))
    if cmd[0] == "pgrep":
        return SimpleNamespace(returncode=0 if cmd[-1] in rodando else 1, stdout="", stderr="")
    if cmd[0] == "open":
        rodando.add(cmd[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if cmd[0] == "lsappinfo":
        return SimpleNamespace(returncode=0, stdout=('"LSDisplayName"="%s"' % na_frente[0]) if cmd[1] == "info" else "ASN:0x0-0x1:", stderr="")
    if cmd[0] == "osascript" and len(cmd) > 2 and cmd[1] == "-e" and cmd[2].endswith("to quit"):
        rodando.discard(cmd[2].split('"')[1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if cmd[0] == "osascript":
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


ag.subprocess = SimpleNamespace(run=falso, TimeoutExpired=subprocess.TimeoutExpired)
ag.SOSSEGO_APP = 0.3
ag.FECHAR_APPS = True
ag.ASSENTAR_APP_S = 0
SCRIPT = 'tell application "Notes" to return "x"'

# 1. app fechado: abre escondido, roda o script e fecha depois
saida = ag.osascript(SCRIPT)
confere("roda o script e devolve a saída", saida == "ok")
confere("abre o Notas escondido e em segundo plano", ["open", "-g", "-j", "-a", "Notes"] in chamadas, chamadas)
time.sleep(0.8)
confere("fecha o Notas que o próprio Heimdall abriu", "Notes" not in rodando and ag._apps_nossos == set(), (rodando, ag._apps_nossos))

esconderam = [c for c in chamadas if c[:3] == ["osascript", "-l", "JavaScript"] and "com.apple.Notes" in c[-1]]
confere("esconde o Notas logo depois de abri-lo e de novo no fim da chamada", len(esconderam) == 2, chamadas)

# 2. app que você já deixou aberto: nunca abre nem fecha
chamadas.clear(); rodando.add("Notes")
ag.osascript(SCRIPT)
time.sleep(0.8)
confere("não mexe num Notas que já estava aberto (nem abre, nem esconde, nem fecha)", not any(c[0] == "open" or c[:3] == ["osascript", "-l", "JavaScript"] for c in chamadas) and "Notes" in rodando, chamadas)

# 3. você passou a usar o app (fica na frente): não fecha
rodando.discard("Notes"); chamadas.clear(); na_frente[0] = "Notes"
ag.osascript(SCRIPT)
time.sleep(0.8)
confere("não fecha o app se ele está na frente", "Notes" in rodando and ag._apps_nossos == set(), (rodando, ag._apps_nossos))
na_frente[0] = ""; rodando.discard("Notes")

# 3b. padrão: não fecha o app depois de usar (evita abrir e fechar a cada ciclo)
ag.FECHAR_APPS = False
chamadas.clear(); rodando.discard("Notes"); ag._apps_nossos.clear()
ag.osascript(SCRIPT)
time.sleep(0.8)
confere("por padrão o Notas continua aberto (escondido) e não é fechado", "Notes" in rodando and not any(c[:3] == ["osascript", "-e", 'tell application "Notes" to quit'] for c in chamadas), chamadas)
chamadas.clear()
ag.osascript(SCRIPT)
confere("a chamada seguinte não abre o app de novo", not any(c[0] == "open" for c in chamadas), chamadas)
ag.FECHAR_APPS = True; rodando.discard("Notes"); ag._apps_nossos.clear()

# 4. script que não usa os apps: não abre nada
chamadas.clear()
ag.osascript('return "oi"')
confere("script sem Notas, Lembretes ou Calendário não abre app", not any(c[0] == "open" for c in chamadas), chamadas)

print("\nTUDO OK" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)
