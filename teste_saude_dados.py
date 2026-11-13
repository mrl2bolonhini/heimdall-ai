#!/usr/bin/env python3
"""Testes de heimdall_saude.py com dados FICTÍCIOS: treinos, ECG, frequência cardíaca, eventos, exportação do app Saúde e relatórios."""
import json
import math
import os
import random
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-saude-"))
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "banco")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_banco as banco  # noqa: E402
import heimdall_saude as hs  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


def sql(q, *p):
    con = sqlite3.connect(banco.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(q, p)]
    finally:
        con.close()


def onda(fs=512, seg=30, rrs=None, seed=1):
    """ECG sintético: R estreito, onda T, deriva da linha de base e ruído."""
    rnd = random.Random(seed)
    n = int(fs * seg)
    x = [300 * math.sin(2 * math.pi * 0.3 * i / fs) + rnd.gauss(0, 8) for i in range(n)]
    t, batidas = 0.4, 0
    rrs = rrs or (lambda: 0.857 + rnd.uniform(-0.04, 0.04))
    while t < seg - 0.4:
        c = int(t * fs)
        for k in range(-int(0.05 * fs), int(0.05 * fs)):
            if 0 <= c + k < n:
                x[c + k] += 1100 * math.exp(-0.5 * (k / (0.008 * fs)) ** 2)
        for k in range(int(0.15 * fs), int(0.35 * fs)):
            if c + k < n:
                x[c + k] += 220 * math.exp(-0.5 * ((k - 0.25 * fs) / (0.04 * fs)) ** 2)
        batidas += 1
        t += rrs()
    return x, batidas


# ---------------------------------------------------------------- forma de onda
x, bat = onda()
a = hs.analisar_onda(x, 512, 70)
confere("picos R: o número de batimentos bate", abs(a["picos"] - bat) <= 1, f"{a['picos']} x {bat}")
confere("frequência pela forma de onda perto de 70", a["fc_forma_onda"] and abs(a["fc_forma_onda"] - 70) < 3, a)
confere("ritmo regular: irregularidade baixa e qualidade boa", a["cv_rr"] < 8 and a["qualidade"] == "boa", a)
rnd = random.Random(7)
xa, _ = onda(rrs=lambda: rnd.uniform(0.45, 1.2), seed=3)
aa = hs.analisar_onda(xa, 512, None)
confere("ritmo irregular: irregularidade bem maior", aa["cv_rr"] > 18, aa)
confere("sinal sem batimentos não quebra", hs.analisar_onda([0.0] * 5000, 512)["qualidade"] == "ruim" and hs.analisar_onda([1, 2, 3], 512)["picos"] == 0)
confere("onda empacota e desempacota", hs.desempacotar_onda(hs._empacotar_onda([1, -5, 300, 40000, -40000])) == [1, -5, 300, 32767, -32768])
confere("classificação em português", [hs.classificacao_pt(s) for s in ("Sinus Rhythm", "Ritmo sinusal", "Atrial Fibrillation", "Inconclusive Low Heart Rate", "Inconclusive Poor Recording", "Not Set")]
        == ["Ritmo sinusal", "Ritmo sinusal", "Fibrilação atrial", "Inconclusivo (frequência cardíaca baixa)", "Inconclusivo (gravação ruim)", "Sem classificação"])
confere("tipos de treino em português", [hs.tipo_pt(s) for s in ("Running", "HKWorkoutActivityTypeTraditionalStrengthTraining", "Outdoor Walk", "HKWorkoutActivityTypePaddleTennis")]
        == ["Corrida", "Musculação", "Caminhada ao ar livre", "Paddle Tennis"])

# ---------------------------------------------------------------- Health Auto Export
hoje = datetime.now().replace(microsecond=0)
def fmt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S -0300")
ini = hoje - timedelta(days=2, hours=3)
fim = ini + timedelta(minutes=40)
hr = [{"date": fmt(ini + timedelta(seconds=30 * i)), "Min": 110 + i, "Avg": 120 + i, "Max": 130 + i, "units": "count/min", "source": "Apple Watch"} for i in range(80)]
rec = [{"date": fmt(fim + timedelta(seconds=s)), "Min": 150 - s // 3, "Avg": 150 - s // 3, "Max": 150 - s // 3, "units": "count/min"} for s in (10, 30, 60, 90)]
treino = {"id": "AAA-111", "name": "Running", "start": fmt(ini), "end": fmt(fim), "duration": 2400, "location": "Outdoor",
          "distance": {"qty": 6.2, "units": "mi"}, "activeEnergyBurned": {"qty": 2090, "units": "kJ"}, "totalEnergy": {"qty": 600, "units": "kcal"},
          "intensity": {"qty": 9.8, "units": "kcal/hr·kg"}, "elevationUp": {"qty": 300, "units": "ft"}, "temperature": {"qty": 77, "units": "degF"},
          "avgSpeed": {"qty": 9.3, "units": "mi/hr"}, "stepCount": [{"date": fmt(ini), "qty": 3000, "units": "count"}, {"date": fmt(ini), "qty": 2000, "units": "count"}],
          "heartRateData": hr, "heartRateRecovery": rec, "source": {"name": "Apple Watch", "identifier": "x"},
          "route": [{"latitude": -23.55 + i / 1000, "longitude": -46.63, "altitude": 760 + i} for i in range(5)], "metadata": {"clima": "bom"}}
volts = [{"date": 1700000000 + i / 512, "voltage": v, "units": "mcV"} for i, v in enumerate(x)]
ecg = {"start": fmt(hoje - timedelta(days=1)), "end": fmt(hoje - timedelta(days=1) + timedelta(seconds=30)), "classification": "Sinus Rhythm", "averageHeartRate": 70,
       "numberOfVoltageMeasurements": len(x), "voltageMeasurements": volts, "samplingFrequency": 512, "source": "Apple Watch"}
ecg_af = dict(ecg, start=fmt(hoje - timedelta(hours=5)), classification="Atrial Fibrillation", averageHeartRate=95, numberOfVoltageMeasurements=15360, voltageMeasurements=[{"date": 1, "voltage": v} for v in xa[:5000]])
carga = {"data": {
    "workouts": [treino, {"name": "sem data"}],
    "ecg": [ecg, ecg_af],
    "symptoms": [{"start": fmt(hoje), "end": fmt(hoje), "name": "Fadiga", "severity": "Mild", "userEntered": True}],
    "stateOfMind": [{"id": "s1", "start": (hoje.astimezone().astimezone(None).strftime("%Y-%m-%dT%H:%M:%S") + "Z"), "kind": "daily_mood", "labels": ["calm"], "associations": ["work"], "valence": 0.6, "valenceClassification": "pleasant"}],
    "medications": [{"displayText": "Remédio X", "start": fmt(hoje), "status": "Taken", "dosage": 1, "units": "count"}],
    "heartRateNotifications": [{"heartNotification": "high_heart_rate_notification", "start": fmt(hoje), "end": fmt(hoje), "threshold": 120, "heartRateData": [{"qty": 130, "units": "count/min", "start": 1, "end": 2}]}],
    "metrics": [{"name": "heart_rate", "units": "count/min", "data": [{"date": fmt(hoje.replace(hour=h, minute=m)), "Min": 50 + h, "Avg": 60 + h, "Max": 70 + h} for h in (2, 3, 14) for m in (0, 30)]},
                {"name": "step_count", "units": "count", "data": []}]}}
r = hs.processar_hae(carga)
confere("HAE: grava 1 treino e recusa o que não tem data", r["treinos"] == 1 and r["recusados"] == 1, r)
confere("HAE: 2 ECG, um com fibrilação", r["ecg"] == 2 and len(r["ecg_fibrilacao"]) == 1, r)
confere("HAE: 4 eventos (sintoma, humor, medicamento, aviso)", r["eventos"] == 4, r)
confere("HAE: horas de frequência cardíaca", r["fc_horas"] == 3, r)
t = sql("SELECT * FROM treinos")[0]
confere("treino: tipo, duração, unidades convertidas",
        t["tipo"] == "Corrida" and t["duracao_min"] == 40 and abs(t["distancia_km"] - 9.978) < 0.01 and abs(t["energia_kcal"] - 499.5) < 1 and abs(t["subida_m"] - 91.4) < 0.1
        and abs(t["temperatura_c"] - 25) < 0.1 and abs(t["velocidade_kmh"] - 14.97) < 0.1 and t["passos"] == 5000 and t["local"] == "externo", t)
confere("treino: frequência cardíaca da série", t["fc_min"] == 110 and t["fc_max"] == 209 and 158 < t["fc_media"] < 162, t)
confere("treino: recuperação em 1 minuto (queda de bpm)", t["fc_recuperacao"] is not None and 40 < t["fc_recuperacao"] < 70, t["fc_recuperacao"])
confere("treino: série e rota guardadas", len(json.loads(t["fc_serie"])) == 80 and len(json.loads(t["rota"])) == 5 and json.loads(t["extra"]) == {"clima": "bom"})
e = sql("SELECT * FROM ecg ORDER BY inicio")
confere("ECG: sinusal com análise e qualidade", e[0]["classificacao"] == "Ritmo sinusal" and e[0]["qualidade"] == "boa" and abs(e[0]["fc_forma_onda"] - 70) < 3 and e[0]["completo"] == 1, e[0])
confere("ECG: o que veio cortado fica marcado incompleto", e[1]["classificacao"] == "Fibrilação atrial" and e[1]["completo"] == 0 and e[1]["amostras"] == 15360, e[1])
w = sql("SELECT amostras FROM ecg_ondas WHERE ecg_id = ?", e[0]["id"])[0]["amostras"]
confere("ECG: forma de onda guardada e recuperável", len(hs.desempacotar_onda(w)) == len(x))
ev = {x_["tipo"]: x_ for x_ in sql("SELECT * FROM saude_eventos")}
confere("eventos: humor com valência, medicamento com dose, aviso com limite",
        ev["humor"]["valor"] == 0.6 and ev["medicamento"]["valor"] == 1 and ev["aviso_fc"]["titulo"] == "Aviso de frequência cardíaca alta" and ev["sintoma"]["titulo"] == "Fadiga")
fh = sql("SELECT * FROM fc_hora ORDER BY hora")
confere("fc por hora: mínimo, média e máximo", [h["hora"] for h in fh] == [2, 3, 14] and fh[0]["fc_min"] == 52 and fh[0]["fc_max"] == 72 and fh[0]["leituras"] == 2, fh)
dia = sql("SELECT metrica, valor FROM saude_diaria WHERE metrica LIKE 'fc_m%' AND dia = ?", hoje.strftime("%Y-%m-%d"))
confere("fc diária em saude_diaria", {d["metrica"] for d in dia} == {"fc_min", "fc_media", "fc_max"})
r2 = hs.processar_hae(carga)
confere("repetir o mesmo envio não duplica", sql("SELECT COUNT(*) n FROM treinos")[0]["n"] == 1 and sql("SELECT COUNT(*) n FROM ecg")[0]["n"] == 2 and sql("SELECT COUNT(*) n FROM saude_eventos")[0]["n"] == 4)
confere("payload estranho não quebra", hs.processar_hae({"data": {"workouts": "x", "ecg": [1], "metrics": [{"name": "heart_rate", "data": [{"date": "lixo"}]}]}})["treinos"] == 0 and hs.processar_hae([])["treinos"] == 0)
hs.GUARDAR_ROTA = False
hs.processar_hae({"data": {"workouts": [dict(treino, id="BBB-222")]}})
confere("HEIMDALL_SAUDE_ROTA=0 não guarda a rota", json.loads(sql("SELECT rota FROM treinos WHERE id='BBB-222'")[0]["rota"]) == [])
hs.GUARDAR_ROTA = True

# ---------------------------------------------------------------- arquivo de exportação do app Saúde
d0 = (hoje - timedelta(days=5)).strftime("%Y-%m-%d")
def reg(tipo, v, s, un="", fonte="Apple Watch", fim_=None):
    return f'<Record type="{tipo}" sourceName="{fonte}" unit="{un}" startDate="{s}" endDate="{fim_ or s}" value="{v}"/>'
DTD = "".join(f"<!ELEMENT Elemento{i} (#PCDATA)><!ATTLIST Elemento{i} atributo{i} CDATA #IMPLIED>" for i in range(150))   # o cabeçalho real tem milhares de bytes de DTD
xml = ['<?xml version="1.0"?><!DOCTYPE HealthData [<!ELEMENT HealthData (Record)>' + DTD + ']><HealthData locale="pt_BR">',
       '<Me HKCharacteristicTypeIdentifierDateOfBirth="1980-05-05" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/>']
for i in range(5):
    xml.append(reg("HKQuantityTypeIdentifierHeartRate", 60 + i * 10, f"{d0} 10:0{i}:00 -0300", "count/min"))
xml.append(reg("HKQuantityTypeIdentifierHeartRate", 140, f"{d0} 15:20:00 -0300", "count/min"))
xml.append(reg("HKQuantityTypeIdentifierStepCount", 1000, f"{d0} 11:00:00 -0300", "count", "iPhone"))
xml.append(reg("HKQuantityTypeIdentifierStepCount", 900, f"{d0} 11:00:00 -0300", "count", "Apple Watch"))
xml.append(reg("HKQuantityTypeIdentifierStepCount", 500, f"{d0} 12:00:00 -0300", "count", "Apple Watch"))
xml.append(reg("HKQuantityTypeIdentifierRestingHeartRate", 55, f"{d0} 09:00:00 -0300", "count/min"))
xml.append(reg("HKQuantityTypeIdentifierOxygenSaturation", 0.97, f"{d0} 09:00:00 -0300", "%"))
for cat, a, b, fonte in (("AsleepCore", "00:00", "03:00", "Apple Watch"), ("AsleepDeep", "03:00", "04:00", "Apple Watch"), ("AsleepREM", "04:00", "05:30", "Apple Watch"),
                         ("AsleepUnspecified", "00:30", "02:30", "iPhone"), ("InBed", "23:30", "06:00", "iPhone")):
    dd = (datetime.strptime(d0, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    xml.append(f'<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="{fonte}" startDate="{dd} {a}:00 -0300" endDate="{dd} {b}:00 -0300" value="HKCategoryValueSleepAnalysis{cat}"/>')
xml.append(f'<Workout workoutActivityType="HKWorkoutActivityTypeCycling" duration="45" durationUnit="min" totalDistance="18" totalDistanceUnit="km" totalEnergyBurned="400" '
           f'totalEnergyBurnedUnit="kcal" sourceName="Apple Watch" startDate="{d0} 15:00:00 -0300" endDate="{d0} 15:45:00 -0300">'
           '<MetadataEntry key="HKAverageMETs" value="8.2 kcal/hr·kg"/><MetadataEntry key="HKElevationAscended" value="12000 cm"/><MetadataEntry key="HKWeatherTemperature" value="68 degF"/>'
           '<WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" average="141" minimum="96" maximum="171" unit="count/min"/>'
           '<WorkoutRoute sourceName="Apple Watch"><FileReference path="/workout-routes/route_1.gpx"/></WorkoutRoute></Workout>')
xml.append(f'<ActivitySummary dateComponents="{d0}" activeEnergyBurned="650" appleExerciseTime="48" appleStandHours="11"/>')
xml.append("</HealthData>")
gpx = '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>' + "".join(
    f'<trkpt lat="-23.5{i}" lon="-46.6{i}"><ele>{760 + i}</ele><time>2026-11-10T15:0{i}:00Z</time></trkpt>' for i in range(6)) + "</trkseg></trk></gpx>"
csv_ecg = ("Nome,Fulano de Tal\nData de nascimento,1980-05-05\nData do registro," + f"{d0} 18:00:00 -0300\nClassificação,Ritmo Sinusal\nSintomas,Nenhum\n"
           "Versão do software,2.0\nDispositivo,Watch6,2\nTaxa de amostragem,512 hertz\nDerivação,Derivação I\nUnidade,µV\n\n" + "\n".join(f'"{v:.2f}"'.replace(".", ",") for v in x) + "\n")
zpath = TMP / "export.zip"
with zipfile.ZipFile(zpath, "w") as z:
    z.writestr("apple_health_export/exportar.xml", "\n".join(xml))   # no iPhone em português o nome é exportar.xml
    z.writestr("apple_health_export/exportar_cda.xml", "<ClinicalDocument/>")
    z.writestr("apple_health_export/workout-routes/route_1.gpx", gpx)
    z.writestr("apple_health_export/electrocardiograms/ecg_2026-11-10.csv", csv_ecg)
with zipfile.ZipFile(TMP / "outro-nome.zip", "w") as z2:
    z2.writestr("apple_health_export/dados_saude.xml", "\n".join(xml))
confere("pacote com outro nome de arquivo é achado pelo conteúdo", hs._Origem(str(TMP / "outro-nome.zip")).achar_xml_saude() == "apple_health_export/dados_saude.xml")
avisos = []
res = hs.importar_exportacao(str(zpath), aviso=avisos.append)
confere("exportação: treino, ECG, horas, sono e anéis", res["treinos"] == 1 and res["ecg"] == 1 and res["fc_horas"] == 2 and res["sono_noites"] == 1 and res["aneis"] == 3, res)
t = sql("SELECT * FROM treinos WHERE tipo = 'Ciclismo'")[0]
confere("exportação: treino com MET, subida, temperatura, FC e rota do GPX",
        t["duracao_min"] == 45 and t["distancia_km"] == 18 and t["met"] == 8.2 and t["subida_m"] == 120 and t["temperatura_c"] == 20 and t["fc_media"] == 141 and t["fc_max"] == 171
        and t["velocidade_kmh"] == 24 and len(json.loads(t["rota"])) == 6, t)
fh = {h["hora"]: h for h in sql("SELECT * FROM fc_hora WHERE dia = ?", d0)}
confere("exportação: frequência por hora", fh[10]["fc_min"] == 60 and fh[10]["fc_max"] == 100 and fh[10]["fc_media"] == 80 and fh[15]["fc_media"] == 140)
dm = {(r_["metrica"]): r_["valor"] for r_ in sql("SELECT metrica, valor FROM saude_diaria WHERE dia = ?", d0)}
confere("exportação: passos sem contar iPhone e relógio em dobro", dm["passos"] == 1400, dm)
confere("exportação: pulso em repouso, oxigênio e anéis", dm["fc_repouso"] == 55 and dm["spo2"] == 97 and dm["x:anel_movimento_kcal"] == 650 and dm["x:anel_pe_horas"] == 11, dm)
dd = (datetime.strptime(d0, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
sono = {r_["metrica"]: r_["valor"] for r_ in sql("SELECT metrica, valor FROM saude_diaria WHERE dia = ?", dd)}
confere("exportação: sono sem contar a sobreposição (330 min, 60 profundo, 90 REM)", sono.get("sono_total") == 330 and sono.get("sono_profundo") == 60 and sono.get("sono_rem") == 90, sono)
ec = sql("SELECT * FROM ecg WHERE inicio LIKE ?", d0 + " 18%")[0] if sql("SELECT * FROM ecg WHERE inicio LIKE ?", d0 + " 18%") else sql("SELECT * FROM ecg WHERE fonte LIKE 'Watch%'")[0]
confere("exportação: ECG em português com vírgula decimal e taxa de amostragem", ec["classificacao"] == "Ritmo sinusal" and ec["freq_hz"] == 512 and ec["qualidade"] == "boa" and abs(ec["fc_forma_onda"] - 70) < 3, ec)
despejo = " ".join(str(v) for tabela in ("treinos", "ecg", "saude_eventos", "saude_diaria") for l in sql(f"SELECT * FROM {tabela}") for v in l.values())
confere("privacidade: nome e data de nascimento do arquivo não entram no banco", "Fulano" not in despejo and "1980-05-05" not in despejo and "Male" not in despejo)
n1 = sql("SELECT COUNT(*) n FROM treinos")[0]["n"], sql("SELECT COUNT(*) n FROM ecg")[0]["n"], sql("SELECT COUNT(*) n FROM fc_hora")[0]["n"]
hs.importar_exportacao(str(zpath), aviso=avisos.append)
confere("importar de novo não duplica", (sql("SELECT COUNT(*) n FROM treinos")[0]["n"], sql("SELECT COUNT(*) n FROM ecg")[0]["n"], sql("SELECT COUNT(*) n FROM fc_hora")[0]["n"]) == n1)
try:
    hs.importar_exportacao(str(TMP / "nao-existe.zip"))
    confere("arquivo inexistente dá erro claro", False)
except FileNotFoundError:
    confere("arquivo inexistente dá erro claro", True)
confere("a exportação não sobrescreve valor que já veio do n8n",
        (banco.gravar("saude_diaria", [{"dia": d0, "metrica": "fc_repouso", "valor": 99, "unidade": "bpm"}]) or True) and (hs.importar_exportacao(str(zpath), aviso=avisos.append) or True)
        and sql("SELECT valor FROM saude_diaria WHERE dia = ? AND metrica = 'fc_repouso'", d0)[0]["valor"] == 99)

# ---------------------------------------------------------------- relatórios
rt = hs.relatorio_treinos(30)
confere("relatório de treinos", "Corrida" in rt and "Ciclismo" in rt and "Último treino" in rt and "Carga de treino" in rt, rt)
confere("relatório de treinos por tipo", "Ciclismo" not in hs.relatorio_treinos(30, "corrida") and "Nenhum treino" in hs.relatorio_treinos(30, "natacao"))
re_ = hs.relatorio_ecg(30)
confere("relatório de ECG avisa da fibrilação, sem diagnosticar", "fibrilação atrial" in re_ and "médico" in re_ and "Ritmo sinusal" in re_ and "RMSSD" in re_, re_)
rf = hs.relatorio_fc(30)
confere("relatório de frequência cardíaca", "Frequência em repouso" in rf and "madrugada" in rf and "Maior pico" in rf and "Avisos do relógio" in rf, rf)
rg = hs.relatorio_geral(30)
confere("relatório geral junta tudo", "Corrida" in rg and "Coração" in rg and "ECG" in rg and "Sintomas registrados: Fadiga" in rg and "Humor registrado" in rg and "não diagnóstico" in rg, rg)
confere("banco_resumo e esquema conhecem as tabelas novas", all(k in banco.resumo() for k in ("treinos", "ecg", "fc_hora", "saude_eventos")) and "treinos(" in banco.tabelas_para_modelo())
# análises do dia a dia com 200 dias sintéticos (sem depender de treinos)
import random as _rnd
from datetime import datetime as _dt, timedelta as _td
_rnd.seed(7)
_con = sqlite3.connect(banco.DB_PATH)
_agora = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
for i in range(200):
    d = (_dt.now() - _td(days=i)).strftime("%Y-%m-%d")
    sono = _rnd.gauss(400, 60) - (40 if i < 7 else 0)
    hrv_v = 30 + (sono - 400) * 0.08 + _rnd.gauss(0, 3) - (8 if i < 7 else 0)
    for m, v in (("sono_total", sono), ("sono_profundo", sono * 0.15), ("sono_rem", sono * 0.2), ("sono_cama", sono + 30), ("hrv", hrv_v),
                 ("fc_repouso", 64 + _rnd.gauss(0, 2) + (5 if i < 7 else 0)), ("passos", max(500, _rnd.gauss(6500, 2500))),
                 ("x:apple_exercise_time", max(0, _rnd.gauss(25, 15))), ("energia", _rnd.gauss(400, 80))):
        _con.execute("INSERT OR REPLACE INTO saude_diaria (dia, metrica, valor, unidade, atualizado) VALUES (?,?,?,?,?)", (d, m, v, "", _agora))
    _con.execute("INSERT OR REPLACE INTO fc_hora (dia, hora, fc_min, fc_media, fc_max, leituras, atualizado) VALUES (?,?,?,?,?,?,?)", (d, 18, 80, 110, 150 if i % 5 == 0 else 120, 10, _agora))
_con.commit()
_con.close()
confere("estado atual compara 7 dias com 90", "Como você está agora" in hs.relatorio_estado_atual() and "fora do seu padrão" in hs.relatorio_estado_atual() or "pior" in hs.relatorio_estado_atual(), hs.relatorio_estado_atual())
confere("tendências ordenadas", "Tendências" in hs.relatorio_tendencias(60) and "Sono" in hs.relatorio_tendencias(60), hs.relatorio_tendencias(60))
rs_ = hs.relatorio_sono(90)
confere("relatório de sono", "noites com dado" in rs_ and "Sono profundo" in rs_ and "Eficiência" in rs_ and "dia da semana" in rs_ and "Noites mais curtas" in rs_, rs_)
ra_ = hs.relatorio_atividade(90)
confere("relatório de atividade", "Passos" in ra_ and "Minutos de exercício" in ra_ and "130 bpm" in ra_ and "150 minutos" in ra_, ra_)
rr_ = hs.relatorio_recuperacao(180)
confere("relatório de recuperação acha a ligação sono-HRV", "sono da noite" in rr_ and "variabilidade" in rr_ and "HRV mais baixa" in rr_, rr_)
rg2 = hs.relatorio_geral(30)
confere("relatório geral inclui análises do dia a dia", "Como você está agora" in rg2 and "Sono (" in rg2 and "Atividade" in rg2 and "Recuperação" in rg2, rg2)
# banco novo e vazio: relatórios não quebram
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "vazio")
banco.DB_DIR = TMP / "vazio"
banco.DB_PATH = banco.DB_DIR / "heimdall.db"
confere("banco vazio: mensagens úteis", "Nenhum treino" in hs.relatorio_treinos() and "Nenhum ECG" in hs.relatorio_ecg() and "Sem dados" in hs.relatorio_fc())
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
