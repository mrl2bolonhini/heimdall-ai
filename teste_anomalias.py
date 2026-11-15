#!/usr/bin/env python3
"""Testa heimdall_anomalias: normal, desvio, tendência lenta, sequência, cruzamentos, medidas do dia inteiro e métricas desconhecidas."""
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="anomalias_"))
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "banco")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_saude as hs  # noqa: E402
import heimdall_anomalias as an  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


hs._garantir_banco()
HOJE = datetime.now().strftime("%Y-%m-%d")


def dia(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def grava(metrica, d, v, un=""):
    hs._upsert("saude_diaria", "dia, metrica", [{"dia": d, "metrica": metrica, "valor": v, "unidade": un, "atualizado": datetime.now().astimezone().isoformat()}])


NORMAL = {"fc_repouso": 58, "hrv": 55, "resp": 14.5, "spo2": 96.5, "sono_total": 420, "sono_profundo": 70, "sono_rem": 90, "x:breathing_disturbances": 4}
for i in range(1, 31):
    for m, v in NORMAL.items():
        ruido = ((i * 7) % 5 - 2) * (0.01 * v)
        grava(m, dia(i), v + ruido)
    grava("passos", dia(i), 8000 + (i % 5) * 300)

# 1. dia normal
for m, v in NORMAL.items():
    grava(m, HOJE, v)
r = an.analisar(HOJE)
confere("tudo normal: nenhum achado", not r["achados"] and not r["combos"], r["achados"])
confere("tudo normal: alerta None", an.alerta(HOJE) is None)
confere("relatório diz que nada saiu do normal", "Nenhuma medida saiu do seu normal" in an.relatorio(HOJE))

# 2. um desvio isolado
grava("fc_repouso", HOJE, 75)
r = an.analisar(HOJE)
ch = [a["chave"] for a in r["achados"]]
confere("pulso em repouso muito alto é achado forte", ch == ["fc_repouso"] and r["achados"][0]["nivel"] == "forte", r["achados"])
confere("um achado só não gera alerta de triagem", an.alerta(HOJE) is None)

# 3. HRV mais alta que o normal é positivo, não alerta
grava("fc_repouso", HOJE, 58)
grava("hrv", HOJE, 80)
r = an.analisar(HOJE)
confere("HRV bem maior é positivo", [a["chave"] for a in r["positivos"]] == ["hrv"] and not r["achados"], (r["positivos"], r["achados"]))
grava("hrv", HOJE, 55)

# 4. variação pequena não conta, mesmo com desvio padrão minúsculo
grava("spo2", HOJE, 95.8)
confere("oxigênio 0,7 ponto abaixo não alerta", not an.analisar(HOJE)["achados"], an.analisar(HOJE)["achados"])
grava("spo2", HOJE, 96.5)

# 5. combo de estresse
grava("fc_repouso", HOJE, 72)
grava("hrv", HOJE, 30)
grava("resp", HOJE, 17.5)
grava("sono_total", HOJE, 300)
r = an.analisar(HOJE)
confere("pulso alto + HRV baixa + respiração + sono curto: combo de estresse", any(c["chave"] == "combo_estresse" for c in r["combos"]), r["combos"])
a = an.alerta(HOJE)
confere("combo gera um item de triagem alto, com id estável", a and a["nivel"] == "alto" and a["id"].startswith(f"anomalias|{HOJE}|") and an.alerta(HOJE)["id"] == a["id"], a)
confere("resumo não é diagnóstico e usa datas brasileiras", a and "não é diagnóstico" in a["resumo"].lower() and not re.search(r"\d{4}-\d\d-\d\d", a["resumo"]), a and a["resumo"])

# 6. combo respiração/sono (apneia)
for m, v in NORMAL.items():
    grava(m, HOJE, v)
grava("x:breathing_disturbances", HOJE, 20)
grava("spo2", HOJE, 93)
grava("sono_total", HOJE, 300)
r = an.analisar(HOJE)
confere("distúrbios respiratórios + oxigênio baixo + sono curto: combo de sono", any(c["chave"] == "combo_sono_respiracao" for c in r["combos"]), (r["combos"], r["achados"]))
confere("o texto cita médico e diz que não é diagnóstico", any("médico" in c["texto"] and "Não é diagnóstico" in c["texto"] for c in r["combos"]))

# 7. tendência lenta: últimos 7 dias um pouco piores, hoje dentro do normal
for m, v in NORMAL.items():
    grava(m, HOJE, v)
for i in range(1, 8):
    grava("fc_repouso", dia(i), 58 + 4.2 + (i % 2) * 0.4)
grava("fc_repouso", HOJE, 62.2)
r = an.analisar(HOJE)
confere("pulso subindo uns dias seguidos aparece (dia ou tendência)", any(a["chave"] == "fc_repouso" for a in r["achados"]), r["achados"])
for i in range(1, 8):
    grava("fc_repouso", dia(i), 58 + ((i * 7) % 5 - 2) * 0.58)
grava("fc_repouso", HOJE, 58)

# 8. sequência de dias seguidos
for i in range(0, 4):
    grava("hrv", dia(i), 38)
a = [x for x in an.analisar(HOJE)["achados"] if x["chave"] == "hrv"]
confere("HRV baixa 4 dias seguidos: conta a sequência", a and a[0]["seguidos"] >= 4 and "dias seguidos" in a[0]["texto"], a)
for i in range(0, 4):
    grava("hrv", dia(i), 55)

# 9. medida do dia inteiro usa o último dia completo (hoje, incompleto, não conta)
grava("passos", HOJE, 300)
confere("passos de hoje (incompletos) não geram achado", not [x for x in an.analisar(HOJE)["achados"] if x["chave"] == "passos"])
grava("passos", dia(1), 900)
confere("passos de ontem (completo) muito baixos geram achado", [x for x in an.analisar(HOJE)["achados"] if x["chave"] == "passos"], an.analisar(HOJE)["achados"])
grava("passos", dia(1), 8200)
grava("passos", HOJE, 3000)

# 10. métrica desconhecida de HAE: genérica, só variação grande
for i in range(1, 21):
    grava("x:metrica_nova", dia(i), 100 + (i % 3))
grava("x:metrica_nova", HOJE, 101)
confere("métrica nova dentro do normal: sem achado", not [x for x in an.analisar(HOJE)["achados"] if x["chave"] == "x:metrica_nova"])
grava("x:metrica_nova", HOJE, 190)
confere("métrica nova muito fora: achado", [x for x in an.analisar(HOJE)["achados"] if x["chave"] == "x:metrica_nova"])
grava("x:metrica_nova", HOJE, 101)

# 11. sem histórico e sem dado recente
for i in range(1, 4):
    grava("x:vo2_max", dia(i), 40)
r = an.analisar(HOJE)
confere("pouco histórico entra em 'sem base'", "VO2 máximo" in r["sem_base"], r["sem_base"])
for i in range(20, 31):
    grava("x:walking_speed", dia(i), 5)
confere("dado velho entra em 'sem dado recente'", "Velocidade de caminhada" in an.analisar(HOJE)["sem_dado_recente"], an.analisar(HOJE)["sem_dado_recente"])

# 12. ignoradas
grava("x:anel_qualquer", HOJE, 999)
grava("sono_cama", HOJE, 1)
confere("métricas da lista de ignoradas não são analisadas", not any(a["chave"] in ("x:anel_qualquer", "sono_cama") for a in an.analisar(HOJE)["achados"]))

# 13. frequência cardíaca por hora
for i in range(1, 15):
    hs._upsert("fc_hora", "dia, hora", [{"dia": dia(i), "hora": h, "fc_min": 55, "fc_media": 64 + (i % 3), "fc_max": 80, "leituras": 10} for h in range(0, 10)])
hs._upsert("fc_hora", "dia, hora", [{"dia": HOJE, "hora": h, "fc_min": 70, "fc_media": 90, "fc_max": 110, "leituras": 10} for h in range(0, 10)])
r = an.analisar(HOJE)
chs = [a["chave"] for a in r["achados"]]
confere("fc por hora bem acima do normal aparece (madrugada e horas do dia)", "fc_madrugada" in chs and "fc_horas" in chs, chs)
txt = an.relatorio(HOJE)
confere("relatório em português do Brasil, sem datas ISO", not re.search(r"\d{4}-\d\d-\d\d", txt) and "Isto não é diagnóstico" in txt, txt[:600])

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
