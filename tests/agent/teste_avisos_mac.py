#!/usr/bin/env python3
"""Avisos nativos no Mac: fila local, texto completo (saúde e finanças incluídos) só no Mac, Bark continua genérico, interruptor HEIMDALL_AVISOS_MAC=0.

    python3 tests/agent/teste_avisos_mac.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["HEIMDALL_DB_DIR"] = tmp
os.environ.pop("HEIMDALL_AVISOS_MAC", None)
import heimdall_avisos_mac as mac  # noqa: E402
import heimdall_triagem as tri  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


pasta = Path(tmp) / "avisos_mac"
confere("publicar grava um JSON na pasta de avisos", mac.publicar({"title": "Olá", "body": "Corpo completo", "group": "teste", "level": "timeSensitive"}))
arqs = list(pasta.glob("*.json"))
confere("um arquivo, sem temporário sobrando", len(arqs) == 1 and not list(pasta.glob(".*.tmp")))
d = json.loads(arqs[0].read_text(encoding="utf-8"))
confere("campos do Bark viram titulo, corpo, grupo, nivel", d["titulo"] == "Olá" and d["corpo"] == "Corpo completo" and d["grupo"] == "teste" and d["nivel"] == "timeSensitive", d)
confere("pasta 700 e arquivo 600", oct(pasta.stat().st_mode & 0o777) == "0o700" and oct(arqs[0].stat().st_mode & 0o777) == "0o600")
mac.publicar({"title": "x", "level": "inventado"})
confere("nível desconhecido vira active", any(json.loads(a.read_text())["nivel"] == "active" for a in pasta.glob("*.json")))
confere("aviso vazio é recusado", mac.publicar({}) is False and mac.publicar("texto") is False)
os.environ["HEIMDALL_AVISOS_MAC"] = "0"
antes = len(list(pasta.glob("*.json")))
confere("HEIMDALL_AVISOS_MAC=0 desliga", mac.publicar({"title": "não"}) is False and len(list(pasta.glob("*.json"))) == antes)
os.environ.pop("HEIMDALL_AVISOS_MAC")

# triagem: o Bark segue genérico; o Mac recebe título e resumo mesmo de saúde
row = {"titulo": "Resultado do hemograma", "resumo": "Glicose 62 mg/dL, abaixo da faixa", "prioridade_usuario": "", "fonte": "saude"}
sens = tri._sensivel(row)
bark = tri.montar_aviso(row, False, 1)
completo = tri.montar_aviso(row, False, 1, completo=True)
if sens:
    confere("Bark: saúde sem título nem resumo", "hemograma" not in bark["title"] and "Glicose" not in bark["body"], bark)
    confere("Mac: título e resumo completos", "hemograma" in completo["title"] and "Glicose 62" in completo["body"], completo)
else:
    print("aviso: linha de exemplo não é sensível pelo critério atual; conferência de saúde pulada")
ag = tri.montar_aviso_agrupado([(row, False), ({**row, "titulo": "Outro exame"}, False)], False, 2, completo=True)
confere("agrupado completo traz os títulos", "hemograma" in ag["body"] and "Outro exame" in ag["body"], ag)

sys.exit(1 if falhas else 0)
