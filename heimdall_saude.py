#!/usr/bin/env python3
"""Saúde do ecossistema Apple no Heimdall: treinos, ECG, frequência cardíaca, sintomas, humor, medicamentos e avisos do relógio.

Duas portas de entrada, a mesma gravação no banco pessoal (banco/heimdall.db):

1. Contínua: o Health Auto Export (app do iPhone) manda um JSON para o n8n, que repassa ao agente do Mac (POST /saude/hae).
   O n8n guarda o diário de sempre (passos, sono, pulso em repouso...); este módulo cuida do que é novo: treinos, ECG,
   frequência cardíaca por hora, sintomas, humor, medicamentos, ciclo e avisos de frequência cardíaca.
2. Histórico: o arquivo "Exportar todos os dados de saúde" do app Saúde (export.zip), que traz tudo desde o começo, inclusive os ECG (CSV)
   e as rotas dos treinos (GPX):
       python3 heimdall_saude.py --importar ~/Downloads/export.zip

Análises (texto corrido, para leitor de tela; informativas, nada aqui é diagnóstico):
       python3 heimdall_saude.py --relatorio [dias]     tudo junto
       python3 heimdall_saude.py --treinos [dias]       python3 heimdall_saude.py --ecg [dias]       python3 heimdall_saude.py --fc [dias]
As mesmas análises estão no chat como ferramentas (treinos_resumo, ecg_resumo, frequencia_cardiaca_resumo, relatorio_saude).

Privacidade: o arquivo de exportação traz nome e data de nascimento; nada disso é lido nem gravado. A rota (GPS) dos treinos fica só no banco
local; HEIMDALL_SAUDE_ROTA=0 no .env desliga o armazenamento dela. Só biblioteca padrão do Python.
"""
import csv
import hashlib
import io
import json
import math
import os
import re
import statistics
import struct
import sys
import unicodedata
import zipfile
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só a pasta do banco e as opções HEIMDALL_SAUDE_* (rodado à mão, o terminal não leu o .env)."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = (x.strip() for x in linha.split("=", 1))
        if chave == "HEIMDALL_DB_DIR" or chave.startswith("HEIMDALL_SAUDE_"):
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
                valor = valor[1:-1]
            os.environ.setdefault(chave, valor)


carregar_env()
import heimdall_banco as banco  # noqa: E402

GUARDAR_ROTA = os.environ.get("HEIMDALL_SAUDE_ROTA", "1") != "0"
MAX_SERIE_FC = 600
MAX_ROTA = 400


# ----------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------
def _sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode()


def _n(v):
    """Número ou None (aceita texto com vírgula decimal)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    else:
        try:
            f = float(str(v).strip().replace(",", "."))
        except ValueError:
            return None
    return f if math.isfinite(f) else None


def _qty(o):
    """{'qty': 5, 'units': 'km'} -> (5.0, 'km'); número solto -> (n, '')."""
    if isinstance(o, dict):
        return _n(o.get("qty", o.get("value"))), str(o.get("units") or o.get("unit") or "")
    return _n(o), ""


def _dt(s):
    """Data e hora de 'AAAA-MM-DD HH:MM:SS -0800', ISO com Z, ou segundos desde 1970 (devolve datetime com fuso, ou sem, se o texto não tinha)."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(float(s)).astimezone()
    t = str(s).strip()
    for f in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def _local(d: datetime) -> datetime:
    """Horário de parede do local: se o texto veio com fuso do próprio treino (-0800) vale o que está escrito; UTC ('Z') vira o fuso do Mac."""
    if d.tzinfo is not None and d.utcoffset() == timedelta(0):
        return d.astimezone().replace(tzinfo=None)
    return d.replace(tzinfo=None)


def _epoch(d: datetime) -> float:
    return d.timestamp() if d.tzinfo else d.astimezone().timestamp()


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _km(q, u):
    if q is None:
        return None
    u = (u or "km").lower()
    return q * 1.609344 if u in ("mi", "mile", "miles") else q / 1000 if u in ("m", "meter", "meters") else q


def _metros(q, u):
    if q is None:
        return None
    u = (u or "m").lower()
    return q * 0.3048 if u in ("ft", "foot", "feet") else q / 100 if u == "cm" else q


def _kcal(q, u):
    if q is None:
        return None
    return q / 4.184 if (u or "").lower() in ("kj", "kilojoule", "kilojoules") else q


def _kmh(q, u):
    if q is None:
        return None
    u = (u or "").lower().replace(" ", "")
    return q * 1.609344 if u in ("mi/hr", "mi/h", "mph") else q * 3.6 if u in ("m/s", "m/sec") else q


def _celsius(q, u):
    if q is None:
        return None
    return (q - 32) * 5 / 9 if "f" in (u or "").lower() else q


def _reduz(lista: list, maximo: int) -> list:
    if len(lista) <= maximo:
        return lista
    passo = len(lista) / maximo
    return [lista[int(i * passo)] for i in range(maximo)]


def _r(v, casas=1):
    return None if v is None else round(v, casas)


# ----------------------------------------------------------------------------------------
# Tipos de treino em português
# ----------------------------------------------------------------------------------------
_TIPOS = {
    "running": "Corrida", "outdoorrun": "Corrida ao ar livre", "indoorrun": "Corrida na esteira", "treadmillrunning": "Corrida na esteira",
    "walking": "Caminhada", "outdoorwalk": "Caminhada ao ar livre", "indoorwalk": "Caminhada em local fechado", "treadmillwalking": "Caminhada na esteira",
    "hiking": "Trilha", "cycling": "Ciclismo", "outdoorcycling": "Ciclismo ao ar livre", "indoorcycling": "Ciclismo em local fechado",
    "swimming": "Natação", "poolswim": "Natação na piscina", "openwaterswim": "Natação em águas abertas",
    "traditionalstrengthtraining": "Musculação", "strengthtraining": "Musculação", "functionalstrengthtraining": "Treino funcional de força",
    "highintensityintervaltraining": "Treino intervalado de alta intensidade", "hiit": "Treino intervalado de alta intensidade",
    "coretraining": "Treino de core", "yoga": "Ioga", "pilates": "Pilates", "elliptical": "Elíptico", "rowing": "Remo", "stairclimbing": "Escada",
    "stairs": "Escada", "mixedcardio": "Cardio misto", "cardiodance": "Dança", "socialdance": "Dança", "dance": "Dança", "cooldown": "Volta à calma",
    "flexibility": "Alongamento", "mindandbody": "Mente e corpo", "kickboxing": "Kickboxing", "boxing": "Boxe", "martialarts": "Artes marciais",
    "soccer": "Futebol", "basketball": "Basquete", "tennis": "Tênis", "volleyball": "Vôlei", "golf": "Golfe", "jumprope": "Pular corda",
    "wheelchairwalkpace": "Cadeira de rodas (caminhada)", "wheelchairrunpace": "Cadeira de rodas (corrida)", "other": "Outro", "preparationandrecovery": "Preparação e recuperação",
    "trainingwithweights": "Musculação", "skatingsports": "Patinação", "surfingsports": "Surfe", "paddlesports": "Remo e canoa", "play": "Brincadeira ativa",
}


def tipo_pt(nome: str) -> str:
    base = re.sub(r"^HKWorkoutActivityType", "", str(nome or "").strip())
    chave = re.sub(r"[^a-z]", "", base.lower())
    if chave in _TIPOS:
        return _TIPOS[chave]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).strip() or "Treino"


def classificacao_pt(s: str) -> str:
    """Classificação do ECG em português, venha em inglês (Health Auto Export) ou no idioma do iPhone (arquivo de exportação)."""
    t = _sem_acento(s)
    if not t or "not set" in t or "nao defin" in t:
        return "Sem classificação"
    if "fibril" in t or "atrial fib" in t:
        return "Fibrilação atrial"
    if "inconclu" in t:
        if "low" in t or "baix" in t:
            return "Inconclusivo (frequência cardíaca baixa)"
        if "high" in t or "alta" in t or "elevad" in t:
            return "Inconclusivo (frequência cardíaca alta)"
        if "poor" in t or "ruim" in t or "qualidade" in t:
            return "Inconclusivo (gravação ruim)"
        return "Inconclusivo"
    if "sinus" in t:
        return "Ritmo sinusal"
    if "unrecogn" in t or "nao reconhec" in t:
        return "Não reconhecida"
    return str(s).strip()[:80]


# ----------------------------------------------------------------------------------------
# Gravação no banco
# ----------------------------------------------------------------------------------------
def _upsert(tabela: str, chave: str, linhas: list) -> int:
    """linhas: lista de dicts com as mesmas colunas. Atualiza pela chave e sempre carimba 'atualizado'."""
    if not linhas:
        return 0
    cols = list(linhas[0].keys())
    if "atualizado" not in cols:
        cols.append("atualizado")
    sql = (f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
           f"ON CONFLICT ({chave}) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in cols if c not in chave.split(", ")))
    agora = _agora()
    dados = [[l.get(c, agora) if c != "atualizado" else agora for c in cols] for l in linhas]
    with banco._trava:
        con = banco.conectar()
        try:
            con.executemany(sql, dados)
            con.commit()
        finally:
            con.close()
    return len(linhas)


def _garantir_banco() -> None:
    if not banco.DB_PATH.exists():
        banco.iniciar()
    else:
        with banco._trava:
            con = banco.conectar()
            try:
                con.executescript(banco.ESQUEMA)   # só cria o que falta
                con.commit()
            finally:
                con.close()


# ----------------------------------------------------------------------------------------
# Treinos
# ----------------------------------------------------------------------------------------
def _salvar_treino(t: dict) -> int:
    t.setdefault("fim", "")
    t.setdefault("fc_serie", [])
    t.setdefault("rota", [])
    linha = dict(t)
    linha["fc_serie"] = json.dumps(_reduz(t["fc_serie"], MAX_SERIE_FC), separators=(",", ":"))
    linha["rota"] = json.dumps(_reduz(t["rota"], MAX_ROTA), separators=(",", ":")) if GUARDAR_ROTA else "[]"
    linha["extra"] = json.dumps(t.get("extra") or {}, ensure_ascii=False)[:4000]
    return _upsert("treinos", "id", [linha])


def treino_de_hae(w: dict):
    """Um treino do Health Auto Export (versão 2 ou a antiga) em linha da tabela treinos. None se faltar o essencial."""
    ini, fim = _dt(w.get("start")), _dt(w.get("end"))
    if ini is None:
        return None
    nome = str(w.get("name") or "")
    seg_total = _n(w.get("duration"))
    if seg_total is None and fim is not None:
        seg_total = (_local(fim) - _local(ini)).total_seconds()
    dist = _qty(w.get("distance"))
    ene_obj = w.get("activeEnergyBurned")
    if not isinstance(ene_obj, dict):
        ene_obj = w.get("activeEnergy") if isinstance(w.get("activeEnergy"), dict) else None   # na versão 2, activeEnergy é uma série
    ene = _qty(ene_obj)
    tot = _qty(w.get("totalEnergy"))
    subida = _qty(w.get("elevationUp"))
    vel = _qty(w.get("avgSpeed") or w.get("speed"))
    temp = _qty(w.get("temperature"))
    met = _qty(w.get("intensity"))[0]
    esforco = _qty(w.get("effortScore") or w.get("estimatedEffortScore"))[0]
    # frequência cardíaca: resumo, ou calculada da série
    fc = w.get("heartRate") if isinstance(w.get("heartRate"), dict) else {}
    fmin, fmed, fmax = _qty(fc.get("min"))[0], _qty(fc.get("avg"))[0], _qty(fc.get("max"))[0]
    fmed = fmed if fmed is not None else _qty(w.get("avgHeartRate"))[0]
    fmax = fmax if fmax is not None else _qty(w.get("maxHeartRate"))[0]
    serie, pontos = [], []
    for p in (w.get("heartRateData") or []):
        if not isinstance(p, dict):
            continue
        d = _dt(p.get("date") or p.get("start"))
        avg = _n(p.get("Avg", p.get("avg", p.get("qty"))))
        if d is None or avg is None:
            continue
        pontos.append((_epoch(d), avg, _n(p.get("Min", p.get("min"))), _n(p.get("Max", p.get("max")))))
    t0 = _epoch(ini)
    if pontos:
        serie = [[int(round(e - t0)), round(a, 1)] for e, a, _, _ in pontos]
        if fmed is None:
            fmed = statistics.fmean(a for _, a, _, _ in pontos)
        mins = [m if m is not None else a for _, a, m, _ in pontos]
        maxs = [m if m is not None else a for _, a, _, m in pontos]
        fmin = fmin if fmin is not None else min(mins)
        fmax = fmax if fmax is not None else max(maxs)
    # recuperação: queda entre o fim do treino e cerca de 1 minuto depois
    recup = None
    rec = [p for p in (w.get("heartRateRecovery") or []) if isinstance(p, dict)]
    if rec and pontos and fim is not None:
        fim_e = _epoch(fim)
        final = [a for e, a, _, _ in pontos if e >= fim_e - 20] or [pontos[-1][1]]
        base = statistics.fmean(final)
        alvo = min(((abs(_epoch(_dt(p.get("date") or p.get("start"))) - (fim_e + 60)), _n(p.get("Avg", p.get("qty")))) for p in rec
                    if _dt(p.get("date") or p.get("start")) is not None and _n(p.get("Avg", p.get("qty"))) is not None), default=None)
        if alvo and alvo[0] <= 45:
            recup = base - alvo[1]
    passos = sum(_n(p.get("qty")) or 0 for p in (w.get("stepCount") or []) if isinstance(p, dict)) if isinstance(w.get("stepCount"), list) else _qty(w.get("stepCount"))[0]
    rota = []
    for p in (w.get("route") or []):
        if isinstance(p, dict):
            la, lo = _n(p.get("latitude", p.get("lat"))), _n(p.get("longitude", p.get("lon")))
            if la is not None and lo is not None:
                rota.append([round(la, 5), round(lo, 5), _r(_n(p.get("altitude", p.get("alt"))), 0)])
    loc = str(w.get("location") or "")
    local = {"indoor": "interno", "outdoor": "externo", "pool": "piscina", "open water": "águas abertas"}.get(loc.lower(), "interno" if w.get("isIndoor") is True else "")
    fonte = w.get("source", {}).get("name") if isinstance(w.get("source"), dict) else w.get("source")
    chave = str(w.get("id") or hashlib.sha1((nome + str(w.get("start"))).encode()).hexdigest()[:16])
    return {
        "id": chave, "dia": _local(ini).strftime("%Y-%m-%d"), "inicio": _iso(ini), "fim": _iso(fim) if fim else "",
        "tipo": tipo_pt(nome), "tipo_original": nome[:80], "duracao_min": _r(seg_total / 60 if seg_total is not None else None, 1),
        "local": local, "distancia_km": _r(_km(dist[0], dist[1]), 3), "energia_kcal": _r(_kcal(ene[0], ene[1]), 1),
        "energia_total_kcal": _r(_kcal(tot[0], tot[1]), 1), "met": _r(met, 2), "fc_min": _r(fmin), "fc_media": _r(fmed), "fc_max": _r(fmax),
        "fc_recuperacao": _r(recup), "subida_m": _r(_metros(subida[0], subida[1]), 1), "passos": _r(passos, 0),
        "velocidade_kmh": _r(_kmh(vel[0], vel[1]), 2), "esforco": _r(esforco, 1), "temperatura_c": _r(_celsius(temp[0], temp[1]), 1),
        "fc_serie": serie, "rota": rota, "fonte": str(fonte or "")[:80], "extra": w.get("metadata") if isinstance(w.get("metadata"), dict) else {},
    }


# ----------------------------------------------------------------------------------------
# ECG: gravação e análise da forma de onda
# ----------------------------------------------------------------------------------------
def _media_movel(x: list, janela: int) -> list:
    n = len(x)
    cs = [0.0]
    for v in x:
        cs.append(cs[-1] + v)
    meio = janela // 2
    saida = []
    for i in range(n):
        a, b = max(0, i - meio), min(n, i + meio + 1)
        saida.append((cs[b] - cs[a]) / (b - a))
    return saida


def picos_r(x: list, fs: float) -> list:
    """Posições (índices) dos picos R. Linha de base removida, derivada ao quadrado, janela móvel e limiar adaptativo. Sem bibliotecas."""
    n = len(x)
    if fs <= 0 or n < fs * 5:
        return []
    base = _media_movel(x, max(3, int(fs * 0.6)) | 1)
    y = [x[i] - base[i] for i in range(n)]
    d = [0.0] * n
    for i in range(1, n - 1):
        d[i] = (y[i + 1] - y[i - 1]) ** 2
    sm = _media_movel(d, max(3, int(fs * 0.08)) | 1)
    ordenado = sorted(sm)
    p99 = ordenado[int(0.995 * (n - 1))]
    if p99 <= 0:
        return []
    limiar = 0.22 * p99
    refrat = int(fs * 0.25)
    folga = int(fs * 0.06)
    picos, i = [], 0
    while i < n:
        if sm[i] > limiar:
            j = i
            while j < n and sm[j] > limiar:
                j += 1
            a, b = max(0, i - folga), min(n, j + folga)
            k = max(range(a, b), key=lambda q: abs(y[q]))
            if not picos or k - picos[-1] >= refrat:
                picos.append(k)
            elif abs(y[k]) > abs(y[picos[-1]]):
                picos[-1] = k
            i = j
        else:
            i += 1
    return picos


def analisar_onda(x: list, fs: float, fc_relogio=None) -> dict:
    """Medidas dos intervalos entre batimentos (RR) de uma gravação de ECG. Informativas: não são diagnóstico."""
    vazio = {"picos": 0, "fc_forma_onda": None, "rr_medio_ms": None, "sdnn_ms": None, "rmssd_ms": None, "pnn50": None, "cv_rr": None, "qualidade": "ruim"}
    p = picos_r(x, fs)
    if len(p) < 5:
        vazio["picos"] = len(p)
        return vazio
    rr_bruto = [(p[i + 1] - p[i]) * 1000.0 / fs for i in range(len(p) - 1)]
    rr = [v for v in rr_bruto if 300 <= v <= 2000]
    if len(rr) < 4:
        vazio["picos"] = len(p)
        return vazio
    media = statistics.fmean(rr)
    sdnn = statistics.pstdev(rr)
    difs = [rr[i + 1] - rr[i] for i in range(len(rr) - 1)]
    rmssd = math.sqrt(statistics.fmean(d * d for d in difs)) if difs else None
    pnn50 = 100.0 * sum(1 for d in difs if abs(d) > 50) / len(difs) if difs else None
    fc = 60000.0 / media
    ok_rr = len(rr) / len(rr_bruto)
    ok_fc = fc_relogio is None or abs(fc - fc_relogio) <= 10
    qual = "boa" if ok_rr >= 0.95 and ok_fc else "regular" if ok_rr >= 0.8 or ok_fc else "ruim"
    return {"picos": len(p), "fc_forma_onda": round(fc, 1), "rr_medio_ms": round(media, 1), "sdnn_ms": round(sdnn, 1),
            "rmssd_ms": _r(rmssd), "pnn50": _r(pnn50), "cv_rr": round(100.0 * sdnn / media, 1), "qualidade": qual}


def _empacotar_onda(x: list) -> bytes:
    return zlib.compress(struct.pack("<%dh" % len(x), *[max(-32768, min(32767, int(round(v)))) for v in x]), 6)


def desempacotar_onda(blob: bytes) -> list:
    b = zlib.decompress(blob)
    return list(struct.unpack("<%dh" % (len(b) // 2), b))


def _salvar_ecg(inicio: datetime, fs, amostras: list, class_orig: str, fc_media, sintomas: str, fonte: str, total_declarado=None) -> str:
    fs = fs or 512.0
    an = analisar_onda(amostras, fs, fc_media)
    eid = "ecg|" + str(int(_epoch(inicio)))
    n = len(amostras)
    linha = {
        "id": eid, "dia": _local(inicio).strftime("%Y-%m-%d"), "inicio": _iso(inicio), "classificacao": classificacao_pt(class_orig),
        "classificacao_original": str(class_orig)[:80], "fc_media": _r(fc_media), "freq_hz": fs, "amostras": int(total_declarado or n),
        "duracao_s": round(n / fs, 1) if fs else None, "completo": 0 if (total_declarado and n < 0.98 * total_declarado) else 1,
        "sintomas": sintomas[:200], "fonte": fonte[:80], **an,
    }
    _upsert("ecg", "id", [linha])
    if amostras:
        _upsert("ecg_ondas", "ecg_id", [{"ecg_id": eid, "freq_hz": fs, "amostras": _empacotar_onda(amostras), "atualizado": _agora()}])
    return eid


def ecg_de_hae(e: dict):
    ini = _dt(e.get("start"))
    if ini is None:
        return None
    volts = []
    for p in (e.get("voltageMeasurements") or []):
        v = _n(p.get("voltage") if isinstance(p, dict) else p)
        if v is not None:
            volts.append(v)
    return _salvar_ecg(ini, _n(e.get("samplingFrequency")), volts, str(e.get("classification") or ""), _n(e.get("averageHeartRate")),
                       "", str(e.get("source") if not isinstance(e.get("source"), dict) else e["source"].get("name") or ""),
                       int(_n(e.get("numberOfVoltageMeasurements")) or 0) or None)


def ecg_de_csv(texto: str):
    """CSV do arquivo de exportação. Nome e data de nascimento que vêm no cabeçalho são ignorados de propósito."""
    meta, valores, em_dados = {}, [], False
    for linha in texto.splitlines():
        s = linha.strip().lstrip("\ufeff")
        if not em_dados:
            if not s:
                if "record date" in meta or "data do registro" in meta or meta.get("_tem_taxa"):
                    em_dados = True
                continue
            k, _, v = s.partition(",")
            k = _sem_acento(k).strip()
            if k in ("name", "nome", "date of birth", "data de nascimento"):
                continue
            meta[k] = v.strip().strip('"')
            if "sample rate" in k or "taxa de amostragem" in k:
                meta["_tem_taxa"] = True
            continue
        v = _n(s.strip('"'))
        if v is not None:
            valores.append(v)
    ini = _dt(meta.get("record date") or meta.get("data do registro") or meta.get("data de gravacao") or "")
    if ini is None or not valores:
        return None
    m = re.search(r"[\d.,]+", meta.get("sample rate") or meta.get("taxa de amostragem") or "")
    fs = _n(m.group(0)) if m else 512.0
    sint = meta.get("symptoms") or meta.get("sintomas") or ""
    sint = "" if _sem_acento(sint) in ("none", "nenhum", "nenhuma", "") else sint
    return _salvar_ecg(ini, fs, valores, meta.get("classification") or meta.get("classificacao") or "", None, sint, meta.get("device") or meta.get("dispositivo") or "")


# ----------------------------------------------------------------------------------------
# Frequência cardíaca por hora
# ----------------------------------------------------------------------------------------
class AgregadorFC:
    """Junta leituras de frequência cardíaca por (dia, hora) e grava mínimo, média e máximo."""

    def __init__(self):
        self.h = {}

    def add(self, dia: str, hora: int, media: float, mn=None, mx=None, n: int = 1):
        c = self.h.get((dia, hora))
        mn = media if mn is None else mn
        mx = media if mx is None else mx
        if c is None:
            self.h[(dia, hora)] = [mn, mx, media * n, n]
        else:
            c[0], c[1], c[2], c[3] = min(c[0], mn), max(c[1], mx), c[2] + media * n, c[3] + n

    def gravar(self) -> int:
        linhas = [{"dia": d, "hora": h, "fc_min": round(c[0], 1), "fc_media": round(c[2] / c[3], 1), "fc_max": round(c[1], 1), "leituras": c[3]}
                  for (d, h), c in self.h.items() if 0 <= h <= 23]
        for i in range(0, len(linhas), 2000):
            _upsert("fc_hora", "dia, hora", linhas[i:i + 2000])
        _fc_diaria(sorted({d for d, _ in self.h}))
        return len(linhas)


def _fc_diaria(dias: list) -> None:
    """Mínimo, média e máximo do dia (a partir de fc_hora) em saude_diaria: fc_min, fc_media, fc_max."""
    if not dias:
        return
    con = banco.conectar(somente_leitura=True)
    try:
        regs = []
        for i in range(0, len(dias), 500):
            parte = dias[i:i + 500]
            for dia, mn, mx, soma, n in con.execute(
                    f"SELECT dia, MIN(fc_min), MAX(fc_max), SUM(fc_media * leituras), SUM(leituras) FROM fc_hora WHERE dia IN ({','.join('?' * len(parte))}) GROUP BY dia", parte):
                if n:
                    regs += [{"dia": dia, "metrica": "fc_min", "valor": mn, "unidade": "bpm"}, {"dia": dia, "metrica": "fc_max", "valor": mx, "unidade": "bpm"},
                             {"dia": dia, "metrica": "fc_media", "valor": soma / n, "unidade": "bpm"}]
    finally:
        con.close()
    for i in range(0, len(regs), 4000):
        banco.gravar("saude_diaria", regs[i:i + 4000])


# ----------------------------------------------------------------------------------------
# Eventos: sintomas, humor, medicamentos, avisos do relógio, ciclo
# ----------------------------------------------------------------------------------------
_AVISOS_FC = {"high_heart_rate_notification": "Aviso de frequência cardíaca alta", "low_heart_rate_notification": "Aviso de frequência cardíaca baixa",
              "irregular_rhythm_notification": "Aviso de ritmo irregular", "irregular_heart_rhythm_notification": "Aviso de ritmo irregular"}


def _evento(tipo: str, inicio, titulo: str, valor=None, texto: str = "", extra=None):
    d = _dt(inicio)
    if d is None:
        return None
    return {"id": f"{tipo}|{int(_epoch(d))}|{_sem_acento(titulo)[:40]}", "tipo": tipo, "dia": _local(d).strftime("%Y-%m-%d"), "inicio": _iso(d),
            "titulo": str(titulo)[:120], "valor": valor, "texto": str(texto)[:400], "extra": json.dumps(extra or {}, ensure_ascii=False)[:2000]}


def eventos_de_hae(d: dict) -> list:
    ev = []
    for s in d.get("symptoms") or []:
        if isinstance(s, dict) and s.get("name"):
            ev.append(_evento("sintoma", s.get("start"), s["name"], None, s.get("severity", ""), {"inicio_ciclo": bool(s.get("cycleStart"))}))
    for m in d.get("stateOfMind") or []:
        if isinstance(m, dict):
            rotulos = ", ".join(str(x) for x in (m.get("labels") or [])) or str(m.get("kind") or "humor")
            texto = " | ".join(x for x in (str(m.get("kind") or ""), "contextos: " + ", ".join(str(a) for a in (m.get("associations") or [])) if m.get("associations") else "",
                                           str(m.get("valenceClassification") or "")) if x)
            ev.append(_evento("humor", m.get("start"), rotulos, _n(m.get("valence")), texto))
    for m in d.get("medications") or []:
        if isinstance(m, dict) and (m.get("displayText") or m.get("nickname")):
            nome = m.get("nickname") or m.get("displayText")
            ev.append(_evento("medicamento", m.get("start") or m.get("scheduledDate"), nome, _n(m.get("dosage")),
                              f"{m.get('status', '')} {m.get('units', '')}".strip()))
    for a in d.get("heartRateNotifications") or []:
        if isinstance(a, dict):
            tipo = str(a.get("heartNotification") or "")
            lei = [x for x in (_n(p.get("qty")) for p in (a.get("heartRateData") or []) if isinstance(p, dict)) if x is not None]
            texto = (f"{len(lei)} leituras, de {min(lei):.0f} a {max(lei):.0f} bpm" if lei else "sem leituras") + (f"; limite {a['threshold']:.0f} bpm" if _n(a.get("threshold")) else "")
            ev.append(_evento("aviso_fc", a.get("start"), _AVISOS_FC.get(tipo, tipo.replace("_", " ") or "Aviso do relógio"), _n(a.get("threshold")), texto))
    for c in d.get("cycleTracking") or []:
        if isinstance(c, dict):
            nome = str(c.get("name") or c.get("type") or c.get("category") or "ciclo")
            ev.append(_evento("ciclo", c.get("start") or c.get("date"), nome, None, str(c.get("value") or c.get("severity") or c.get("flow") or "")))
    return [e for e in ev if e]


# ----------------------------------------------------------------------------------------
# Entrada contínua: JSON do Health Auto Export
# ----------------------------------------------------------------------------------------
def processar_hae(payload) -> dict:
    """Recebe o corpo que o Health Auto Export manda e grava treinos, ECG, frequência por hora e eventos. As demais métricas diárias o n8n já cuida."""
    _garantir_banco()
    d = payload.get("data", payload) if isinstance(payload, dict) else {}
    res = {"treinos": 0, "ecg": 0, "ecg_fibrilacao": [], "eventos": 0, "fc_horas": 0, "recusados": 0}
    for w in d.get("workouts") or []:
        try:
            t = treino_de_hae(w) if isinstance(w, dict) else None
            if t:
                res["treinos"] += _salvar_treino(t)
            else:
                res["recusados"] += 1
        except Exception:  # noqa: BLE001 - um treino ruim não derruba o resto
            res["recusados"] += 1
    for e in d.get("ecg") or []:
        try:
            eid = ecg_de_hae(e) if isinstance(e, dict) else None
            if eid:
                res["ecg"] += 1
                if classificacao_pt(str(e.get("classification") or "")) == "Fibrilação atrial":
                    res["ecg_fibrilacao"].append({"id": eid, "inicio": str(e.get("start"))})
            else:
                res["recusados"] += 1
        except Exception:  # noqa: BLE001
            res["recusados"] += 1
    eventos = eventos_de_hae(d)
    if eventos:
        res["eventos"] = _upsert("saude_eventos", "id", eventos)
    ag = AgregadorFC()
    for m in d.get("metrics") or []:
        if not (isinstance(m, dict) and m.get("name") == "heart_rate"):
            continue
        pts = [p for p in (m.get("data") or []) if isinstance(p, dict)]
        horario = any(str(p.get("date", ""))[11:19] not in ("", "00:00:00") for p in pts)
        for p in pts:
            dia_hora = _dt(p.get("date"))
            media = _n(p.get("Avg", p.get("avg", p.get("qty"))))
            if dia_hora is None or media is None:
                continue
            loc = _local(dia_hora)
            if horario:
                ag.add(loc.strftime("%Y-%m-%d"), loc.hour, media, _n(p.get("Min", p.get("min"))), _n(p.get("Max", p.get("max"))))
            else:   # um ponto por dia: só entra no resumo diário
                dia = loc.strftime("%Y-%m-%d")
                banco.gravar("saude_diaria", [{"dia": dia, "metrica": k, "valor": v, "unidade": "bpm"} for k, v in
                                              (("fc_media", media), ("fc_min", _n(p.get("Min"))), ("fc_max", _n(p.get("Max")))) if v is not None])
    res["fc_horas"] = ag.gravar() if ag.h else 0
    return res


# ----------------------------------------------------------------------------------------
# Entrada de histórico: arquivo de exportação do app Saúde
# ----------------------------------------------------------------------------------------
_REG_DIARIOS = {   # tipo do registro: (métrica, soma ou media, fator, unidade)
    "StepCount": ("passos", "soma", 1, "count"), "ActiveEnergyBurned": ("energia", "soma", 1, "kcal"),
    "RestingHeartRate": ("fc_repouso", "media", 1, "bpm"), "HeartRateVariabilitySDNN": ("hrv", "media", 1, "ms"),
    "RespiratoryRate": ("resp", "media", 1, "rpm"), "OxygenSaturation": ("spo2", "media", 100, "%"),
    "VO2Max": ("x:vo2_max", "media", 1, "mL/min·kg"), "WalkingHeartRateAverage": ("x:walking_heart_rate_average", "media", 1, "bpm"),
    "HeartRateRecoveryOneMinute": ("x:cardio_recovery", "media", 1, "bpm"), "AppleExerciseTime": ("x:apple_exercise_time", "soma", 1, "min"),
    "FlightsClimbed": ("x:flights_climbed", "soma", 1, "count"), "DistanceWalkingRunning": ("x:walking_running_distance", "soma", 1, "km"),
    "BodyMass": ("x:weight_body_mass", "media", 1, "kg"),
}
_PREFIXO_REG = "HKQuantityTypeIdentifier"


class _Origem:
    """Pasta ou zip com a exportação."""

    def __init__(self, caminho: str):
        p = Path(caminho).expanduser()
        self.zip = zipfile.ZipFile(p) if p.is_file() and p.suffix.lower() == ".zip" else None
        self.pasta = p if p.is_dir() else (p.parent if p.is_file() and not self.zip else None)
        self.xml_direto = p if p.is_file() and p.suffix.lower() == ".xml" else None
        if not (self.zip or self.pasta):
            raise FileNotFoundError(f"não achei {p}")

    def nomes(self) -> list:
        if self.zip:
            return self.zip.namelist()
        return [str(x.relative_to(self.pasta)) for x in self.pasta.rglob("*") if x.is_file()]

    def abrir(self, nome: str):
        return self.zip.open(nome) if self.zip else open(self.pasta / nome, "rb")

    def achar(self, fim: str):
        return next((n for n in self.nomes() if n.replace("\\", "/").lower().endswith(fim)), None)


def _gpx(origem: _Origem, caminho: str) -> list:
    alvo = caminho.replace("\\", "/").lstrip("/")
    nome = next((n for n in origem.nomes() if n.replace("\\", "/").endswith(alvo.split("/")[-1]) and "route" in n.lower()), None)
    if not nome:
        return []
    try:
        with origem.abrir(nome) as f:
            raiz = ET.parse(f).getroot()
    except (ET.ParseError, OSError, KeyError):
        return []
    pts = []
    for tp in raiz.iter():
        if tp.tag.endswith("trkpt"):
            la, lo = _n(tp.get("lat")), _n(tp.get("lon"))
            if la is None or lo is None:
                continue
            alt = None
            for c in tp:
                if c.tag.endswith("ele"):
                    alt = _n(c.text)
            pts.append([round(la, 5), round(lo, 5), _r(alt, 0)])
    return pts


def _treino_de_xml(el, origem: _Origem):
    ini, fim = _dt(el.get("startDate")), _dt(el.get("endDate"))
    if ini is None:
        return None
    nome = el.get("workoutActivityType") or ""
    dur = _n(el.get("duration"))
    un = (el.get("durationUnit") or "min").lower()
    dur_min = None if dur is None else dur if un.startswith("min") else dur / 60 if un.startswith("s") else dur * 60 if un.startswith("h") else dur
    dist = _km(_n(el.get("totalDistance")), el.get("totalDistanceUnit") or "km")
    ene = _kcal(_n(el.get("totalEnergyBurned")), el.get("totalEnergyBurnedUnit") or "kcal")
    fmin = fmed = fmax = passos = None
    meta, rota_ref = {}, None
    for c in el:
        if c.tag == "WorkoutStatistics":
            tp = c.get("type") or ""
            if tp.endswith("HeartRate"):
                fmin, fmed, fmax = _n(c.get("minimum")), _n(c.get("average")), _n(c.get("maximum"))
            elif tp.endswith("StepCount"):
                passos = _n(c.get("sum"))
            elif tp.endswith("ActiveEnergyBurned") and ene is None:
                ene = _kcal(_n(c.get("sum")), c.get("unit"))
            elif tp.endswith("DistanceWalkingRunning") and dist is None:
                dist = _km(_n(c.get("sum")), c.get("unit"))
        elif c.tag == "MetadataEntry":
            meta[c.get("key") or ""] = c.get("value") or ""
        elif c.tag == "WorkoutRoute":
            for r in c:
                if r.tag == "FileReference":
                    rota_ref = r.get("path")
    num = lambda k: _n(re.match(r"\s*(-?[\d.,]+)", meta.get(k, "")).group(1)) if re.match(r"\s*(-?[\d.,]+)", meta.get(k, "")) else None  # noqa: E731
    subida = _metros(num("HKElevationAscended"), "cm")
    temp_txt = meta.get("HKWeatherTemperature", "")
    temp = _celsius(num("HKWeatherTemperature"), "degF" if "degF" in temp_txt else "degC") if temp_txt else None
    vel = (dist / (dur_min / 60)) if dist and dur_min else None
    chave = "treino|" + str(int(_epoch(ini))) + "|" + re.sub(r"\W", "", tipo_pt(nome))[:20]
    return {
        "id": chave, "dia": _local(ini).strftime("%Y-%m-%d"), "inicio": _iso(ini), "fim": _iso(fim) if fim else "", "tipo": tipo_pt(nome),
        "tipo_original": re.sub(r"^HKWorkoutActivityType", "", nome)[:80], "duracao_min": _r(dur_min), "local": "interno" if meta.get("HKIndoorWorkout") == "1" else "",
        "distancia_km": _r(dist, 3), "energia_kcal": _r(ene), "energia_total_kcal": None, "met": _r(num("HKAverageMETs"), 2), "fc_min": _r(fmin), "fc_media": _r(fmed),
        "fc_max": _r(fmax), "fc_recuperacao": None, "subida_m": _r(subida), "passos": _r(passos, 0), "velocidade_kmh": _r(vel, 2), "esforco": None,
        "temperatura_c": _r(temp), "fc_serie": [], "rota": _gpx(origem, rota_ref) if (rota_ref and GUARDAR_ROTA) else [], "fonte": (el.get("sourceName") or "")[:80], "extra": {},
    }


def _uniao_min(intervalos: list) -> float:
    """Minutos cobertos por uma lista de (início, fim) em segundos, sem contar sobreposição (relógio e iPhone gravando o mesmo sono)."""
    total, fim_at = 0.0, None
    for a, b in sorted(intervalos):
        if fim_at is None or a > fim_at:
            total += b - a
            fim_at = b
        elif b > fim_at:
            total += b - fim_at
            fim_at = b
    return total / 60.0


def importar_exportacao(caminho: str, aviso=print) -> dict:
    """Lê export.zip (ou a pasta, ou o export.xml) do app Saúde e grava tudo no banco. Pode rodar de novo: grava pela chave, sem duplicar."""
    _garantir_banco()
    origem = _Origem(caminho)
    nome_xml = str(origem.xml_direto) if origem.xml_direto else origem.achar("/export.xml") or origem.achar("export.xml")
    res = {"registros": 0, "treinos": 0, "ecg": 0, "dias_metricas": 0, "fc_horas": 0, "ecg_fibrilacao": 0, "sono_noites": 0, "aneis": 0}
    fcs = AgregadorFC()
    soma = {}      # (dia, métrica, fonte) -> [soma, n]
    sono = {}      # dia -> {"asleep": [], "deep": [], "rem": [], "inbed": []}
    aneis = []
    if nome_xml:
        fonte = open(nome_xml, "rb") if origem.xml_direto else origem.abrir(nome_xml)
        with fonte as f:
            raiz = None
            for ev, el in ET.iterparse(f, events=("start", "end")):
                if ev == "start":
                    raiz = raiz if raiz is not None else el
                    continue
                tag = el.tag
                if tag == "Record":
                    res["registros"] += 1
                    tipo = (el.get("type") or "").replace(_PREFIXO_REG, "")
                    if tipo == "HeartRate":
                        s = el.get("startDate") or ""
                        v = _n(el.get("value"))
                        if v is not None and len(s) >= 13:
                            fcs.add(s[:10], int(s[11:13]), v)
                    elif tipo in _REG_DIARIOS:
                        metrica, modo, fator, un = _REG_DIARIOS[tipo]
                        v, s = _n(el.get("value")), el.get("startDate") or ""
                        if v is not None and len(s) >= 10:
                            if metrica == "spo2":
                                v = v * 100 if v <= 1 else v
                            elif metrica == "energia":
                                v = _kcal(v, el.get("unit"))
                            elif metrica == "x:walking_running_distance":
                                v = _km(v, el.get("unit"))
                            elif metrica == "x:weight_body_mass" and (el.get("unit") or "").lower() in ("lb", "lbs"):
                                v = v * 0.45359237
                            c = soma.setdefault((s[:10], metrica, modo, un, el.get("sourceName") or ""), [0.0, 0])
                            c[0] += v
                            c[1] += 1
                    elif (el.get("type") or "") == "HKCategoryTypeIdentifierSleepAnalysis":
                        ini, fim = el.get("startDate") or "", el.get("endDate") or ""
                        try:
                            a = datetime.strptime(ini[:19], "%Y-%m-%d %H:%M:%S")
                            b = datetime.strptime(fim[:19], "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            a = None
                        if a is not None and b > a:
                            noite = (a + timedelta(hours=12)).strftime("%Y-%m-%d")   # a noite pertence ao dia em que a pessoa acorda
                            cat = (el.get("value") or "").replace("HKCategoryValueSleepAnalysis", "")
                            par = (a.timestamp(), b.timestamp())
                            o = sono.setdefault(noite, {"asleep": [], "deep": [], "rem": [], "inbed": []})
                            if cat in ("AsleepCore", "AsleepDeep", "AsleepREM", "AsleepUnspecified", "Asleep"):
                                o["asleep"].append(par)
                                if cat == "AsleepDeep":
                                    o["deep"].append(par)
                                elif cat == "AsleepREM":
                                    o["rem"].append(par)
                            elif cat == "InBed":
                                o["inbed"].append(par)
                    el.clear()
                elif tag == "Workout":
                    try:
                        t = _treino_de_xml(el, origem)
                        if t:
                            res["treinos"] += _salvar_treino(t)
                    except Exception:  # noqa: BLE001
                        pass
                    el.clear()
                elif tag == "ActivitySummary":
                    dia = el.get("dateComponents") or ""
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", dia):
                        for atr, metrica, un in (("activeEnergyBurned", "x:anel_movimento_kcal", "kcal"), ("appleExerciseTime", "x:anel_exercicio_min", "min"),
                                                 ("appleStandHours", "x:anel_pe_horas", "h")):
                            v = _n(el.get(atr))
                            if v:
                                aneis.append({"dia": dia, "metrica": metrica, "valor": v, "unidade": un})
                    el.clear()
                elif tag in ("Correlation", "Audiogram", "ClinicalRecord", "Me", "WorkoutEvent"):
                    el.clear()
                if raiz is not None and res["registros"] and res["registros"] % 200000 == 0 and tag == "Record":
                    aviso(f"  {res['registros']} registros lidos...")
                    raiz.clear()
    else:
        aviso("Não achei o export.xml (só os ECG serão importados).")
    # diário: para somas, usa só a fonte com o maior total do dia (evita contar iPhone e relógio em dobro)
    por_dia = {}
    for (dia, metrica, modo, un, fonte_n), (s, n) in soma.items():
        por_dia.setdefault((dia, metrica, modo, un), []).append((s, n))
    diarios = []
    for (dia, metrica, modo, un), lst in por_dia.items():
        if modo == "soma":
            val = max(x[0] for x in lst)
        else:
            val = sum(x[0] for x in lst) / max(1, sum(x[1] for x in lst))
        diarios.append({"dia": dia, "metrica": metrica, "valor": round(val, 2), "unidade": un})
    for noite, o in sono.items():
        tot = _uniao_min(o["asleep"])
        if tot > 0:
            diarios.append({"dia": noite, "metrica": "sono_total", "valor": round(tot, 1), "unidade": "min"})
            if o["deep"]:
                diarios.append({"dia": noite, "metrica": "sono_profundo", "valor": round(_uniao_min(o["deep"]), 1), "unidade": "min"})
            if o["rem"]:
                diarios.append({"dia": noite, "metrica": "sono_rem", "valor": round(_uniao_min(o["rem"]), 1), "unidade": "min"})
            res["sono_noites"] += 1
        elif o["inbed"]:
            diarios.append({"dia": noite, "metrica": "sono_cama", "valor": round(_uniao_min(o["inbed"]), 1), "unidade": "min"})
    diarios += aneis
    res["aneis"] = len(aneis)
    # as métricas já gravadas pelo n8n (dias recentes) não são sobrescritas por estimativas do arquivo
    existentes = set()
    con = banco.conectar(somente_leitura=True)
    try:
        existentes = {(d, m) for d, m in con.execute("SELECT dia, metrica FROM saude_diaria")}
    finally:
        con.close()
    novos = [r for r in diarios if (r["dia"], r["metrica"]) not in existentes]
    for i in range(0, len(novos), 4000):
        banco.gravar("saude_diaria", novos[i:i + 4000])
    res["dias_metricas"] = len(novos)
    res["fc_horas"] = fcs.gravar() if fcs.h else 0
    for nome in origem.nomes():
        n = nome.replace("\\", "/")
        if "electrocardiograms/" in n and n.lower().endswith(".csv"):
            try:
                with origem.abrir(nome) as f:
                    eid = ecg_de_csv(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace").read())
                if eid:
                    res["ecg"] += 1
            except Exception:  # noqa: BLE001
                pass
    con = banco.conectar(somente_leitura=True)
    try:
        res["ecg_fibrilacao"] = con.execute("SELECT COUNT(*) FROM ecg WHERE classificacao = 'Fibrilação atrial'").fetchone()[0]
    finally:
        con.close()
    return res


# ----------------------------------------------------------------------------------------
# Análises (texto corrido)
# ----------------------------------------------------------------------------------------
AVISO = "Isto é informação do seu histórico, não diagnóstico. Qualquer dúvida sobre o coração, converse com um médico."


def _ler(sql: str, params: tuple = ()) -> list:
    _garantir_banco()
    con = banco.conectar(somente_leitura=True)
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def _dias_atras(dias: int) -> str:
    return (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")


def _num(v, casas=0) -> str:
    if v is None:
        return "sem dado"
    t = f"{v:.{casas}f}".replace(".", ",")
    return t


def _dur(min_) -> str:
    if min_ is None:
        return "sem duração"
    m = int(round(min_))
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} minutos"


def _media(v: list):
    v = [x for x in v if x is not None]
    return statistics.fmean(v) if v else None


def _semana(dia: str) -> str:
    d = datetime.strptime(dia, "%Y-%m-%d")
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def relatorio_treinos(dias: int = 30, tipo: str = "") -> str:
    dias = max(1, min(int(dias), 3650))
    linhas = _ler("SELECT * FROM treinos WHERE dia >= ? ORDER BY inicio", (_dias_atras(dias),))
    if tipo:
        alvo = _sem_acento(tipo)
        linhas = [l for l in linhas if alvo in _sem_acento(l["tipo"])]
    if not linhas:
        return f"Nenhum treino{' de ' + tipo if tipo else ''} nos últimos {dias} dias no banco. Para trazer o histórico: python3 heimdall_saude.py --importar export.zip."
    por_tipo = {}
    for l in linhas:
        por_tipo.setdefault(l["tipo"], []).append(l)
    out = [f"Treinos dos últimos {dias} dias: {len(linhas)} no total, {_dur(sum(l['duracao_min'] or 0 for l in linhas))} de atividade."]
    for t, ls in sorted(por_tipo.items(), key=lambda x: -len(x[1])):
        frase = f"{t}: {len(ls)} treino(s), {_dur(sum(l['duracao_min'] or 0 for l in ls))}"
        km = sum(l["distancia_km"] or 0 for l in ls)
        if km > 0:
            frase += f", {_num(km, 1)} km"
        kcal = sum(l["energia_kcal"] or 0 for l in ls)
        if kcal:
            frase += f", {_num(kcal)} kcal ativas"
        fm = _media([l["fc_media"] for l in ls])
        if fm:
            frase += f", frequência cardíaca média {_num(fm)} bpm"
        out.append(frase + ".")
    u = linhas[-1]
    ultimo = f"Último treino: {u['tipo']} em {u['dia']}, {_dur(u['duracao_min'])}"
    if u["distancia_km"]:
        ultimo += f", {_num(u['distancia_km'], 2)} km"
    if u["fc_media"]:
        ultimo += f", frequência cardíaca média {_num(u['fc_media'])} e máxima {_num(u['fc_max'])} bpm"
    if u["fc_recuperacao"] is not None:
        ultimo += f", recuperação de {_num(u['fc_recuperacao'])} bpm no primeiro minuto"
    out.append(ultimo + ".")
    mais = max(linhas, key=lambda l: l["duracao_min"] or 0)
    out.append(f"Treino mais longo: {mais['tipo']} em {mais['dia']}, {_dur(mais['duracao_min'])}.")
    rec = [l["fc_recuperacao"] for l in linhas if l["fc_recuperacao"] is not None]
    if len(rec) >= 4:
        meio = len(rec) // 2
        a, b = _media(rec[:meio]), _media(rec[meio:])
        out.append(f"Recuperação da frequência cardíaca no primeiro minuto: média de {_num(a)} bpm na primeira metade do período e {_num(b)} bpm na segunda"
                   f" ({'melhorou' if b > a + 1 else 'piorou' if b < a - 1 else 'ficou estável'}; quanto maior a queda, melhor o condicionamento).")
    out += _carga(dias)
    return "\n".join(out)


def _carga(dias: int) -> list:
    """Minutos de treino por semana e a razão entre a última semana e a média das 4 anteriores."""
    todos = _ler("SELECT dia, duracao_min FROM treinos WHERE dia >= ?", (_dias_atras(35),))
    if not todos:
        return []
    hoje = _semana(datetime.now().strftime("%Y-%m-%d"))
    sem = {}
    for l in todos:
        sem[_semana(l["dia"])] = sem.get(_semana(l["dia"]), 0) + (l["duracao_min"] or 0)
    atual = sem.get(hoje, 0)
    anteriores = [sem.get((datetime.strptime(hoje, "%Y-%m-%d") - timedelta(weeks=k)).strftime("%Y-%m-%d"), 0) for k in range(1, 5)]
    base = statistics.fmean(anteriores)
    out = [f"Carga de treino: esta semana {_dur(atual)}; média das 4 semanas anteriores {_dur(base)}."]
    if base >= 30 and atual > 0:
        razao = atual / base
        if razao > 1.5:
            out.append("A semana está com carga mais de 50 por cento acima da média recente: aumento rápido, vale observar cansaço, pulso em repouso e variabilidade.")
        elif razao < 0.5:
            out.append("A semana está com menos da metade da carga recente.")
    return out


def relatorio_ecg(dias: int = 365) -> str:
    dias = max(1, min(int(dias), 3650))
    linhas = _ler("SELECT * FROM ecg WHERE dia >= ? ORDER BY inicio", (_dias_atras(dias),))
    if not linhas:
        return f"Nenhum ECG nos últimos {dias} dias no banco. Para trazer o histórico: python3 heimdall_saude.py --importar export.zip."
    cont = {}
    for l in linhas:
        cont[l["classificacao"] or "Sem classificação"] = cont.get(l["classificacao"] or "Sem classificação", 0) + 1
    out = [f"ECG dos últimos {dias} dias: {len(linhas)} gravação(ões). " + "; ".join(f"{k}: {v}" for k, v in sorted(cont.items(), key=lambda x: -x[1])) + "."]
    af = [l for l in linhas if l["classificacao"] == "Fibrilação atrial"]
    if af:
        out.append("Atenção: houve gravação classificada pela Apple como fibrilação atrial em " + ", ".join(l["dia"] for l in af[-5:]) +
                   ". Mostre ao seu médico; o Heimdall não faz diagnóstico.")
    inc = [l for l in linhas if l["classificacao"].startswith("Inconclusivo")]
    if inc:
        out.append(f"{len(inc)} gravação(ões) inconclusiva(s); costuma ser movimento ou dedo mal posicionado, mas uma frequência muito baixa ou alta também gera isso.")
    u = linhas[-1]
    frase = f"Último ECG: {u['dia']}, {u['classificacao'] or 'sem classificação'}"
    if u["fc_media"]:
        frase += f", frequência média de {_num(u['fc_media'])} bpm"
    if u["rr_medio_ms"]:
        frase += (f". Pela forma de onda (análise do Heimdall, qualidade {u['qualidade']}): {u['picos']} batimentos, intervalo médio de {_num(u['rr_medio_ms'])} ms, "
                  f"variação entre batimentos (RMSSD) de {_num(u['rmssd_ms'])} ms, irregularidade de {_num(u['cv_rr'], 1)} por cento")
    out.append(frase + ".")
    boas = [l for l in linhas if l["qualidade"] == "boa" and l["cv_rr"] is not None and l["classificacao"] == "Ritmo sinusal"]
    if len(boas) >= 5:
        out.append(f"Em ritmo sinusal com boa qualidade, a irregularidade típica dos seus ECG é de {_num(_media([l['cv_rr'] for l in boas]), 1)} por cento (varia com a respiração; "
                   "valores bem acima disso aparecem em arritmias).")
    out.append(AVISO)
    return "\n".join(out)


def relatorio_fc(dias: int = 14) -> str:
    dias = max(1, min(int(dias), 3650))
    de = _dias_atras(dias)
    diario = _ler("SELECT dia, metrica, valor FROM saude_diaria WHERE dia >= ? AND metrica IN ('fc_repouso','hrv','fc_min','fc_max','fc_media','x:walking_heart_rate_average','x:cardio_recovery','x:vo2_max') ORDER BY dia", (de,))
    por = {}
    for r in diario:
        por.setdefault(r["metrica"], []).append((r["dia"], r["valor"]))
    out = []
    nomes = {"fc_repouso": "Frequência em repouso", "hrv": "Variabilidade (HRV)", "x:walking_heart_rate_average": "Frequência média ao caminhar",
             "x:cardio_recovery": "Recuperação cardíaca", "x:vo2_max": "VO2 máx"}
    un = {"fc_repouso": "bpm", "hrv": "ms", "x:walking_heart_rate_average": "bpm", "x:cardio_recovery": "bpm", "x:vo2_max": "mL/min·kg"}
    for k, nome in nomes.items():
        v = por.get(k)
        if v:
            vals = [x[1] for x in v]
            frase = f"{nome}: média de {_num(statistics.fmean(vals), 1)} {un[k]} em {len(vals)} dia(s), último {_num(vals[-1], 1)} em {v[-1][0]}"
            if len(vals) >= 6:
                a, b = statistics.fmean(vals[:len(vals) // 2]), statistics.fmean(vals[len(vals) // 2:])
                frase += f"; a segunda metade do período ficou {'acima' if b > a + 0.5 else 'abaixo' if b < a - 0.5 else 'igual'} da primeira"
            out.append(frase + ".")
    horas = _ler("SELECT dia, hora, fc_min, fc_media, fc_max, leituras FROM fc_hora WHERE dia >= ?", (de,))
    if horas:
        noite = [h["fc_min"] for h in horas if 0 <= h["hora"] <= 5 and h["fc_min"]]
        if noite:
            out.append(f"Frequência mínima de madrugada (0h às 6h): média de {_num(_media(noite))} bpm; a menor foi {_num(min(noite))} bpm.")
        por_hora = {}
        for h in horas:
            por_hora.setdefault(h["hora"], []).append(h["fc_media"])
        mais_alta = max(por_hora.items(), key=lambda x: _media(x[1]) or 0)
        out.append(f"A hora do dia com a frequência média mais alta é {mais_alta[0]}h ({_num(_media(mais_alta[1]))} bpm).")
        dias_max = {}
        for h in horas:
            dias_max[h["dia"]] = max(dias_max.get(h["dia"], 0), h["fc_max"] or 0)
        pico = max(dias_max.items(), key=lambda x: x[1])
        out.append(f"Maior pico no período: {_num(pico[1])} bpm em {pico[0]}.")
    av = _ler("SELECT dia, titulo, texto FROM saude_eventos WHERE tipo = 'aviso_fc' AND dia >= ? ORDER BY inicio", (de,))
    if av:
        out.append(f"Avisos do relógio no período: {len(av)}. " + "; ".join(f"{a['dia']}: {a['titulo']} ({a['texto']})" for a in av[-5:]) + ".")
    return "\n".join(out) if out else f"Sem dados de frequência cardíaca nos últimos {dias} dias no banco."


def relatorio_eventos(dias: int = 30) -> str:
    de = _dias_atras(dias)
    ev = _ler("SELECT tipo, dia, titulo, valor, texto FROM saude_eventos WHERE dia >= ? AND tipo != 'aviso_fc' ORDER BY inicio", (de,))
    if not ev:
        return ""
    out = []
    sint = [e for e in ev if e["tipo"] == "sintoma"]
    if sint:
        cont = {}
        for e in sint:
            cont[e["titulo"]] = cont.get(e["titulo"], 0) + 1
        out.append("Sintomas registrados: " + "; ".join(f"{k} ({v}x)" for k, v in sorted(cont.items(), key=lambda x: -x[1])[:8]) + ".")
    hum = [e["valor"] for e in ev if e["tipo"] == "humor" and e["valor"] is not None]
    if hum:
        out.append(f"Humor registrado: {len(hum)} entrada(s), valor médio {_num(statistics.fmean(hum), 2)} (de menos 1, muito desagradável, a 1, muito agradável).")
    med = [e for e in ev if e["tipo"] == "medicamento"]
    if med:
        cont = {}
        for e in med:
            k = (e["titulo"], (e["texto"] or "").split(" ")[0])
            cont[k] = cont.get(k, 0) + 1
        out.append("Medicamentos: " + "; ".join(f"{k[0]} {k[1].lower()} ({v}x)" for k, v in sorted(cont.items(), key=lambda x: -x[1])[:8]) + ".")
    return "\n".join(out)


def relatorio_cruzado(dias: int = 30) -> str:
    """Cruza carga de treino com pulso em repouso e variabilidade: o que mudou depois de semanas mais pesadas."""
    sem = _ler("SELECT dia, duracao_min FROM treinos WHERE dia >= ?", (_dias_atras(dias + 14),))
    if len(sem) < 3:
        return ""
    dias_treino = {}
    for l in sem:
        dias_treino[l["dia"]] = dias_treino.get(l["dia"], 0) + (l["duracao_min"] or 0)
    met = _ler("SELECT dia, metrica, valor FROM saude_diaria WHERE dia >= ? AND metrica IN ('fc_repouso','hrv')", (_dias_atras(dias + 14),))
    por = {"fc_repouso": {}, "hrv": {}}
    for r in met:
        por[r["metrica"]][r["dia"]] = r["valor"]
    out = []
    hoje = datetime.now().date()
    for nome, chave, un in (("pulso em repouso", "fc_repouso", "bpm"), ("variabilidade (HRV)", "hrv", "ms")):
        serie = por[chave]
        if len(serie) < 8:
            continue
        # compara dias que vêm depois de um dia com mais de 45 minutos de treino com os que vêm depois de dia sem treino
        apos, sem_t = [], []
        for dia, v in serie.items():
            ant = (datetime.strptime(dia, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
            (apos if dias_treino.get(ant, 0) >= 45 else sem_t).append(v)
        if len(apos) >= 3 and len(sem_t) >= 3:
            a, b = statistics.fmean(apos), statistics.fmean(sem_t)
            out.append(f"Depois de dias com 45 minutos ou mais de treino, o {nome} foi em média {_num(a, 1)} {un}, contra {_num(b, 1)} {un} depois de dias sem treino pesado.")
    return ("Cruzamento com o treino: " + " ".join(out)) if out else ""


def relatorio_geral(dias: int = 30) -> str:
    partes = [relatorio_treinos(dias), relatorio_cruzado(dias), "Coração:\n" + relatorio_fc(min(dias, 60)), relatorio_ecg(max(dias, 90)), relatorio_eventos(dias)]
    return "\n\n".join(p for p in partes if p) + "\n\n" + AVISO


# ----------------------------------------------------------------------------------------
# Linha de comando
# ----------------------------------------------------------------------------------------
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Saúde do ecossistema Apple no Heimdall (treinos, ECG, frequência cardíaca)")
    ap.add_argument("--importar", metavar="EXPORT", help="importa o export.zip (ou pasta, ou export.xml) do app Saúde")
    ap.add_argument("--relatorio", nargs="?", const=30, type=int, metavar="DIAS", help="análise geral (padrão 30 dias)")
    ap.add_argument("--treinos", nargs="?", const=30, type=int, metavar="DIAS")
    ap.add_argument("--ecg", nargs="?", const=365, type=int, metavar="DIAS")
    ap.add_argument("--fc", nargs="?", const=14, type=int, metavar="DIAS")
    a = ap.parse_args()
    if a.importar:
        print("Importando (um export grande pode levar vários minutos)...")
        try:
            r = importar_exportacao(a.importar)
        except (OSError, zipfile.BadZipFile, ET.ParseError) as e:
            print(f"Não consegui ler: {e}")
            return 1
        print(f"Registros lidos: {r['registros']}. Treinos gravados: {r['treinos']}. ECG gravados: {r['ecg']}. Horas de frequência cardíaca: {r['fc_horas']}. "
              f"Valores diários novos: {r['dias_metricas']} (noites de sono: {r['sono_noites']}; anéis de atividade: {r['aneis']}).")
        if r["ecg_fibrilacao"]:
            print(f"Atenção: {r['ecg_fibrilacao']} ECG classificado(s) como fibrilação atrial pela Apple. Isto não é diagnóstico; mostre ao seu médico.")
        print("Rode de novo à vontade: não duplica. Para ver: python3 heimdall_saude.py --relatorio")
        return 0
    if a.treinos is not None:
        print(relatorio_treinos(a.treinos))
    elif a.ecg is not None:
        print(relatorio_ecg(a.ecg))
    elif a.fc is not None:
        print(relatorio_fc(a.fc))
    elif a.relatorio is not None:
        print(relatorio_geral(a.relatorio))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
