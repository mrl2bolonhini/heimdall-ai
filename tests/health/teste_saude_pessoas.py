#!/usr/bin/env python3
"""Teste da saúde por pessoa: banco separado, métricas diárias do Health Auto Export, conversor do Atalho e importação pela caixa. Sem rede."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "banco")

import heimdall_atalhos as at  # noqa: E402
import heimdall_banco as banco  # noqa: E402
import heimdall_caixa as cx  # noqa: E402
import heimdall_saude_diaria as sd  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


def valores(nome=None, dono=""):
    with banco.pessoa(nome or "", dono):
        if not banco.DB_PATH.exists():
            return None
        con = banco.conectar(somente_leitura=True)
        try:
            return {(r[0], r[1]): r[2] for r in con.execute("SELECT dia, metrica, valor FROM saude_diaria")}
        finally:
            con.close()


raiz = banco.DB_PATH
for ruim in ("../x", "A b", "", "x" * 40):
    try:
        banco.pasta_da_pessoa(ruim)
        confere(f"nome inválido recusado: {ruim!r}", False)
    except ValueError:
        confere(f"nome inválido recusado: {ruim!r}", True)
with banco.pessoa("ana"):
    dentro = banco.DB_PATH
confere("banco.pessoa troca o caminho dentro do bloco e restaura depois", dentro == TMP / "banco" / "people" / "ana" / "heimdall.db" and banco.DB_PATH == raiz)
with banco.pessoa("eu", "eu"):
    confere("o dono (nome igual ao padrão) continua no banco de sempre", banco.DB_PATH == raiz)
try:
    with banco.pessoa("ana"):
        raise RuntimeError("x")
except RuntimeError:
    pass
confere("o caminho volta mesmo se der erro dentro do bloco", banco.DB_PATH == raiz)

# --- métricas diárias do HAE ---
hae1 = {"data": {"metrics": [
    {"name": "step_count", "units": "count", "data": [{"date": "2026-11-20 09:00:00 -0300", "qty": 1000}, {"date": "2026-11-20 10:00:00 -0300", "qty": 500}]},
    {"name": "resting_heart_rate", "units": "count/min", "data": [{"date": "2026-11-20 00:00:00 -0300", "qty": 58}]},
    {"name": "blood_oxygen_saturation", "units": "%", "data": [{"date": "2026-11-20 03:00:00 -0300", "qty": 0.97, "Min": 0.93}]},
    {"name": "active_energy", "units": "kJ", "data": [{"date": "2026-11-20 09:00:00 -0300", "qty": 418.4}]},
    {"name": "sleep_analysis", "units": "hr", "data": [{"sleepEnd": "2026-11-20 06:30:00 -0300", "totalSleep": 7.5, "deep": 1.2, "rem": 1.6}]},
    {"name": "body_temperature", "units": "degF", "data": [{"date": "2026-11-20 08:00:00 -0300", "qty": 98.6}]}]}}
horas = TMP / "horas.json"
r = {(x["dia"], x["metrica"]): x for x in sd.registros(hae1, horas)}
confere("passos somam as horas do dia", r[("2026-11-20", "passos")]["valor"] == 1500.0)
confere("energia em kJ vira kcal", abs(r[("2026-11-20", "energia")]["valor"] - 100.0) < 0.1 and r[("2026-11-20", "energia")]["unidade"] == "kcal")
confere("oxigênio em fração vira % e guarda o mínimo", r[("2026-11-20", "spo2")]["valor"] == 97.0 and r[("2026-11-20", "spo2_min")]["valor"] == 93.0)
confere("sono: total, profundo e REM em minutos", r[("2026-11-20", "sono_total")]["valor"] == 450.0 and r[("2026-11-20", "sono_profundo")]["valor"] == 72.0 and r[("2026-11-20", "sono_rem")]["valor"] == 96.0)
confere("temperatura em Fahrenheit vira Celsius", r[("2026-11-20", "x:body_temperature")]["valor"] == 37.0)
hae2 = {"data": {"metrics": [{"name": "step_count", "units": "count", "data": [{"date": "2026-11-20 11:00:00 -0300", "qty": 300}, {"date": "2026-11-20 10:00:00 -0300", "qty": 500}]}]}}
r2 = {(x["dia"], x["metrica"]): x for x in sd.registros(hae2, horas)}
confere("envio de hora em hora acumula: não troca o total do dia pelo do último envio, nem conta a mesma hora duas vezes", r2[("2026-11-20", "passos")]["valor"] == 1800.0, r2)
confere("o arquivo de horas só o dono lê", (horas.stat().st_mode & 0o777) == 0o600)
confere("corpo sem métricas não gera nada", sd.registros({"data": {}}) == [] and sd.registros("lixo") == [])

# --- conversor do Atalho ---
atalho = {"origem": "atalhos", "versao": 1, "amostras": [
    {"tipo": "passos", "inicio": "2026-11-20T09:00:00-03:00", "fim": "2026-11-20T09:30:00-03:00", "valor": 800},
    {"tipo": "passos", "inicio": "2026-11-20T10:00:00-03:00", "fim": "2026-11-20T10:30:00-03:00", "valor": "200"},
    {"tipo": "frequencia_cardiaca", "inicio": "2026-11-20T09:10:00-03:00", "fim": "2026-11-20T09:10:00-03:00", "valor": 70},
    {"tipo": "sono", "inicio": "2026-11-20T01:00:00-03:00", "fim": "2026-11-20T02:00:00-03:00", "valor": "profundo"},
    {"tipo": "sono", "inicio": "2026-11-20T02:00:00-03:00", "fim": "2026-11-20T05:00:00-03:00", "valor": "nucleo"},
    {"tipo": "sono", "inicio": "2026-11-20T05:00:00-03:00", "fim": "2026-11-20T06:00:00-03:00", "valor": "rem"},
    {"tipo": "tipo-inventado", "inicio": "2026-11-20T09:00:00-03:00", "valor": 1}, {"tipo": "passos", "inicio": "ontem", "valor": 5}, "lixo"]}
confere("e_atalho reconhece o formato e recusa o do HAE", at.e_atalho(atalho) and not at.e_atalho(hae1))
conv = at.para_hae(atalho)
confere("conversor: amostras inválidas são contadas e ignoradas", conv["_recusados"] == 3, conv["_recusados"])
r3 = {(x["dia"], x["metrica"]): x for x in sd.registros(conv)}
confere("conversor + métricas diárias: passos somados e sono em minutos", r3[("2026-11-20", "passos")]["valor"] == 1000.0 and r3[("2026-11-20", "sono_total")]["valor"] == 300.0 and r3[("2026-11-20", "sono_profundo")]["valor"] == 60.0 and r3[("2026-11-20", "sono_rem")]["valor"] == 60.0, r3)
fc = [m for m in conv["data"]["metrics"] if m["name"] == "heart_rate"][0]["data"][0]
confere("frequência cardíaca sai com Avg, Min e Max (entra na frequência por hora)", fc["Avg"] == 70 and fc["Min"] == 70 and fc["Max"] == 70)

# --- importação pela caixa, um banco por pessoa ---
a = cx.importar_saude("ana", atalho, "eu")
b = cx.importar_saude("bia", {"data": {"metrics": [{"name": "step_count", "units": "count", "data": [{"date": "2026-11-20 09:00:00 -0300", "qty": 77}]}]}}, "eu")
d = cx.importar_saude("eu", hae1, "eu")
va, vb, vd = valores("ana", "eu"), valores("bia", "eu"), valores("eu", "eu")
confere("cada pessoa no seu banco: Ana, Bia e o dono não se misturam", va[("2026-11-20", "passos")] == 1000.0 and vb == {("2026-11-20", "passos"): 77.0} and vd[("2026-11-20", "passos")] == 1500.0, (va, vb))
confere("o banco do dono continua no caminho de sempre e o de cada pessoa em db/people/<nome>/", raiz.exists() and (TMP / "banco" / "people" / "ana" / "heimdall.db").exists() and (TMP / "banco" / "people" / "bia" / "heimdall.db").exists())
confere("a pasta da pessoa é só do dono (0700)", ((TMP / "banco" / "people" / "ana").stat().st_mode & 0o777) == 0o700)
confere("importar de novo é idempotente (mesmo resultado)", (cx.importar_saude("ana", atalho, "eu"), valores("ana", "eu"))[1] == va)
confere("a importação devolve o resumo (treinos, FC por hora e métricas diárias)", a["diarias"] >= 4 and a["fc_horas"] == 1 and d["diarias"] >= 5, (a, d))
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
