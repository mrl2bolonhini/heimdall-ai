#!/usr/bin/env python3
"""Conversor do que o Atalho do iPhone envia (saúde) para o formato do Health Auto Export, que o resto do StudioLibre já entende.

Formato do Atalho, versão 1 (corpo "dados" do item de saúde na caixa):
    {"origem": "atalhos", "versao": 1, "amostras": [{"tipo": "passos", "inicio": "2026-11-21T08:00:00-03:00", "fim": "...", "valor": 120, "unidade": "count"}, ...]}
Tipos aceitos: passos, frequencia_cardiaca, frequencia_repouso, hrv, oxigenio, respiracao, energia_ativa, sono, peso, glicose.
No sono, "valor" é a fase: nucleo (ou core), profundo, rem, acordado, na_cama; o tempo vem de inicio e fim.
O Atalho deve mandar sempre dias inteiros (do início de ontem até agora): os totais do dia são refeitos a cada envio e não dependem de quantas vezes o mesmo
dado chegou. Tipos desconhecidos são contados em "recusados" e ignorados.
"""
from datetime import datetime

TIPOS = {   # tipo do Atalho: (nome no HAE, unidade)
    "passos": ("step_count", "count"), "frequencia_cardiaca": ("heart_rate", "count/min"), "frequencia_repouso": ("resting_heart_rate", "count/min"),
    "hrv": ("heart_rate_variability", "ms"), "oxigenio": ("blood_oxygen_saturation", "%"), "respiracao": ("respiratory_rate", "count/min"),
    "energia_ativa": ("active_energy", "kcal"), "peso": ("weight_body_mass", "kg"), "glicose": ("blood_glucose", "mg/dL"),
}
FASES = {"nucleo": "core", "núcleo": "core", "core": "core", "profundo": "deep", "deep": "deep", "rem": "rem", "acordado": "awake", "awake": "awake",
         "na_cama": "inBed", "inbed": "inBed", "cama": "inBed"}


def e_atalho(dados) -> bool:
    return isinstance(dados, dict) and dados.get("origem") == "atalhos" and isinstance(dados.get("amostras"), list)


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(v):
    try:
        x = float(str(v).replace(",", "."))
        return x if x == x and abs(x) != float("inf") else None
    except ValueError:
        return None


def para_hae(dados: dict) -> dict:
    """{"data": {"metrics": [...]}, "_recusados": n} no formato do Health Auto Export. Pontos de frequência cardíaca levam Avg, Min e Max (uma leitura cada)."""
    series, sono, recusados = {}, {}, 0
    for a in dados.get("amostras", []):
        if not isinstance(a, dict):
            recusados += 1
            continue
        tipo, ini, fim = str(a.get("tipo") or "").lower(), _dt(a.get("inicio")), _dt(a.get("fim"))
        if tipo == "sono":
            fase = FASES.get(str(a.get("valor") or "").lower())
            if not (fase and ini and fim and fim > ini):
                recusados += 1
                continue
            dia = fim.strftime("%Y-%m-%d")
            h = (fim - ini).total_seconds() / 3600
            o = sono.setdefault(dia, {"deep": 0.0, "rem": 0.0, "core": 0.0, "inBed": 0.0, "fim": fim})
            if fase in o:
                o[fase] += h
            o["fim"] = max(o["fim"], fim)
            continue
        if tipo not in TIPOS or ini is None:
            recusados += 1
            continue
        v = _num(a.get("valor"))
        if v is None:
            recusados += 1
            continue
        nome, un = TIPOS[tipo]
        ponto = {"date": ini.strftime("%Y-%m-%d %H:%M:%S"), "qty": v}
        if nome == "heart_rate":
            ponto.update({"Avg": v, "Min": v, "Max": v})
        series.setdefault(nome, {"name": nome, "units": str(a.get("unidade") or un), "data": []})["data"].append(ponto)
    metrics = list(series.values())
    if sono:
        metrics.append({"name": "sleep_analysis", "units": "hr", "data": [
            {"sleepEnd": o["fim"].strftime("%Y-%m-%d %H:%M:%S"), "date": dia, "deep": round(o["deep"], 4), "rem": round(o["rem"], 4), "core": round(o["core"], 4), "inBed": round(o["inBed"], 4)}
            for dia, o in sorted(sono.items())]})
    return {"data": {"metrics": metrics}, "_recusados": recusados}
