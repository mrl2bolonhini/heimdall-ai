#!/usr/bin/env python3
"""Métricas diárias de saúde (passos, energia, sono, frequência em repouso, HRV, oxigênio...) a partir do corpo do Health Auto Export.

É o equivalente em Python do que o fluxo 15-saude do n8n faz ao receber o webhook, para o caminho da caixa de correio da Cloudflare:
o n8n só recebe o que o iPhone manda direto, e a caixa não passa por ele. Grava em saude_diaria (dia, metrica, valor, unidade) pelo heimdall_banco
(dentro de banco.pessoa(nome), cada pessoa no seu banco).

Métricas somadas (passos, energia...) chegam muitas vezes em partes (o envio de hora em hora traz só as últimas horas). Para não trocar o total do
dia pelo do último envio, cada hora já recebida fica guardada em horas.json, na pasta do banco da pessoa, e o total é a soma das horas (nunca diminui).
"""
import json
import os
import re
from pathlib import Path

import heimdall_banco as banco

SOMA = re.compile(r"^(basal_energy_burned|flights_climbed|walking_running_distance|cycling_distance|swimming_distance|wheelchair_distance|push_count|swimming_stroke_count|"
                  r"apple_exercise_time|apple_move_time|apple_stand_time|apple_stand_hour|time_in_daylight|mindful_minutes|number_of_times_fallen|handwashing|toothbrushing|"
                  r"dietary_.*|carbohydrates|protein|total_fat|saturated_fat|caffeine|fiber|alcohol_consumption|inhaler_usage|insulin_delivery|uv_exposure)$")
UNIDADE = {"passos": "count", "energia": "kcal", "fc_repouso": "bpm", "hrv": "ms", "resp": "rpm", "spo2": "%", "spo2_min": "%", "glicose": "mg/dL", "glicose_min": "mg/dL",
           "sono_total": "min", "sono_profundo": "min", "sono_rem": "min", "sono_cama": "min",
           "x:pressao_sistolica": "mmHg", "x:pressao_diastolica": "mmHg"}
_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v and abs(v) != float("inf") else None
    if isinstance(v, str) and v.strip():
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _val(p):
    for k in ("qty", "Avg", "avg"):
        v = _num(p.get(k))
        if v is not None:
            return v
    return None


def _horas_min(v):
    x = _num(v)
    return None if x is None else (x * 60 if x <= 24 else x)


def acumular(payload) -> dict:
    """{(dia, metrica): {"modo", "soma", "n", "horas": {hh: valor}, "pts", "min", "un"}} do corpo do HAE, sem gravar nada."""
    d = payload.get("data", payload) if isinstance(payload, dict) else {}
    mets = d.get("metrics") if isinstance(d, dict) else None
    acc, unidades = {}, {}

    def reg(dia, k, v, modo, p=None, un=""):
        if not dia or v is None or not _DIA.match(dia):
            return
        c = acc.setdefault((dia, k), {"modo": modo, "soma": 0.0, "n": 0, "horas": {}, "pts": 0, "min": None, "un": ""})
        c["soma"] += v
        c["n"] += 1
        c["min"] = v if c["min"] is None else min(c["min"], v)
        c["modo"] = modo
        if un:
            c["un"] = un
        if modo == "soma":
            hh = str((p or {}).get("date", ""))[11:13]
            hh = hh if re.fullmatch(r"\d\d", hh) else "00"
            c["horas"][hh] = c["horas"].get(hh, 0.0) + v
            c["pts"] += 1

    def ultimo(dia, k, v):
        if dia and _DIA.match(dia):
            acc[(dia, k)] = {"modo": "ultimo", "soma": v, "n": 1, "horas": {}, "pts": 0, "min": v, "un": ""}

    for m in (mets if isinstance(mets, list) else []):
        if not isinstance(m, dict):
            continue
        nome, un = str(m.get("name") or ""), str(m.get("units") or "")
        for p in (m.get("data") if isinstance(m.get("data"), list) else []):
            if not isinstance(p, dict):
                continue
            dia = str(p.get("date") or p.get("sleepEnd") or p.get("sleepStart") or "")[:10]
            v = _val(p)
            if nome == "step_count":
                reg(dia, "passos", v, "soma", p)
            elif nome == "active_energy":
                reg(dia, "energia", v / 4.184 if v is not None and "kj" in un.lower() else v, "soma", p)
            elif nome == "resting_heart_rate":
                reg(dia, "fc_repouso", v, "media")
            elif nome == "heart_rate_variability":
                reg(dia, "hrv", v, "media")
            elif nome == "respiratory_rate":
                reg(dia, "resp", v, "media")
            elif nome == "blood_oxygen_saturation":
                if v is not None and v <= 1:
                    v *= 100
                reg(dia, "spo2", v, "media")
                mn = _num(p.get("Min", p.get("min")))
                mn = mn * 100 if mn is not None and mn <= 1 else mn
                cand = mn if mn is not None else v
                if cand is not None and _DIA.match(dia):
                    ant = acc.get((dia, "spo2_min"))
                    acc[(dia, "spo2_min")] = {"modo": "minimo", "soma": cand if ant is None else min(ant["soma"], cand), "n": 1, "horas": {}, "pts": 0, "min": None, "un": ""}
            elif nome == "blood_glucose":
                reg(dia, "glicose", v * 18.0182 if v is not None and "mmol" in un.lower() else v, "media")
            elif nome == "sleep_analysis":
                dd = str(p.get("sleepEnd") or p.get("date") or "")[:10]
                tot = _horas_min(p.get("totalSleep"))
                if tot is None:
                    tot = _horas_min(p.get("asleep"))
                deep, rem, core, cama = (_horas_min(p.get(k)) for k in ("deep", "rem", "core", "inBed"))
                if tot is None and any(x is not None for x in (deep, rem, core)):
                    tot = (deep or 0) + (rem or 0) + (core or 0)
                if (tot is None or tot <= 0) and cama and cama > 0:
                    ultimo(dd, "sono_cama", cama)
                if tot is not None and tot > 0:
                    ultimo(dd, "sono_total", tot)
                    if deep is not None:
                        ultimo(dd, "sono_profundo", deep)
                    if rem is not None:
                        ultimo(dd, "sono_rem", rem)
            elif nome == "blood_pressure":
                for chave, k in (("systolic", "x:pressao_sistolica"), ("diastolic", "x:pressao_diastolica")):
                    reg(dia, k, _num(p.get(chave)), "media")
            elif nome and nome != "heart_rate":
                if v is None:
                    continue
                if nome == "body_temperature" and "f" in un.lower() and "c" not in un.lower():
                    v = (v - 32) * 5 / 9
                reg(dia, "x:" + nome, v, "soma" if SOMA.match(nome) else "media", p, "°C" if nome == "body_temperature" else un)
    return acc


def _memoria(arq: Path) -> dict:
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def registros(payload, arq_horas: Path = None) -> list:
    """Registros prontos para saude_diaria. Para métricas somadas, soma as horas guardadas em `arq_horas` (e atualiza esse arquivo)."""
    acc = acumular(payload)
    mem = _memoria(arq_horas) if arq_horas else {}
    saida = []
    for (dia, k), c in sorted(acc.items()):
        if c["modo"] == "soma":
            m = mem.setdefault(f"{dia}|{k}", {"h": {}, "dia": 0.0})
            if c["pts"] == 1 and "00" in c["horas"]:   # um ponto só, à meia-noite: total do dia inteiro (envio agrupado por dia)
                m["dia"] = max(m["dia"], c["horas"]["00"])
            else:
                for hh, v in c["horas"].items():
                    m["h"][hh] = max(m["h"].get(hh, 0.0), v)
            valor = max(m["dia"], sum(m["h"].values()))
        elif c["modo"] in ("ultimo", "minimo"):
            valor = c["soma"]
        else:
            valor = c["soma"] / c["n"]
        un = UNIDADE.get(k) or c["un"] or ""
        saida.append({"dia": dia, "metrica": k, "valor": round(valor, 2 if k.startswith("x:") else 1), "unidade": un})
        if k == "glicose" and c["min"] is not None:
            saida.append({"dia": dia, "metrica": "glicose_min", "valor": float(round(c["min"])), "unidade": "mg/dL"})
    if arq_horas is not None:
        vivos = sorted({r["dia"] for r in saida} | {x.split("|")[0] for x in mem})[-75:]
        mem = {k: v for k, v in mem.items() if k.split("|")[0] in vivos}
        arq_horas.parent.mkdir(parents=True, exist_ok=True)
        arq_horas.write_text(json.dumps(mem), encoding="utf-8")
        os.chmod(arq_horas, 0o600)
    return saida


def gravar(payload) -> int:
    """Grava as métricas diárias no banco em uso (o do dono ou, dentro de banco.pessoa(), o da pessoa). Devolve quantos registros."""
    if not banco.DB_PATH.exists():
        banco.iniciar()
    regs = registros(payload, banco.DB_DIR / "horas.json")
    for i in range(0, len(regs), 4000):
        banco.gravar("saude_diaria", regs[i:i + 4000])
    return len(regs)
