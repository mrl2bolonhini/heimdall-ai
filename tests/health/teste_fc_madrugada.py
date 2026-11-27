#!/usr/bin/env python3
"""Testa o alerta de frequência cardíaca alta na madrugada (alerta_fc) e a linha correspondente na página Hoje."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="fc_madrugada_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "banco")
sys.path.insert(0, str(RAIZ))
import studio_saude as hs  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:500])


hs._garantir_banco()
HOJE = datetime.now().strftime("%Y-%m-%d")


def dia(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def grava(d, valores, horas=range(0, 7)):
    hs._upsert("fc_hora", "dia, hora", [{"dia": d, "hora": h, "fc_min": v - 5, "fc_media": v, "fc_max": v + 8, "leituras": 12} for h, v in zip(horas, valores)])


# 14 madrugadas normais, em torno de 64 bpm (com pequena variação)
for i in range(1, 15):
    grava(dia(i), [62 + (i % 4), 63 + (i % 3), 64, 65 - (i % 2), 64, 66, 67])

confere("sem dado de hoje: sem alerta", hs.alerta_fc(HOJE) is None, hs.alerta_fc(HOJE))
grava(HOJE, [64, 65, 63, 64, 66, 65, 67])
confere("madrugada normal: sem alerta", hs.alerta_fc(HOJE) is None, hs._fc_madrugada(HOJE))
grava(HOJE, [72, 83, 86, 88, 74, 87, 93])
a = hs.alerta_fc(HOJE)
confere("madrugada cerca de 20 bpm acima do normal: item de triagem alto", a is not None and a["nivel"] == "alto" and a["id"] == f"fc_madrugada|{HOJE}" and a["fonte"] == "saude", a)
confere("o resumo diz médias, dias e que não é diagnóstico", a and "bpm acima do seu normal" in a["resumo"] and "últimos 14 dias" in a["resumo"] and "Não é diagnóstico" in a["resumo"], a and a["resumo"])
confere("a data do resumo vai no padrão brasileiro", a and not __import__("re").search(r"\d{4}-\d\d-\d\d", a["resumo"]), a and a["resumo"])
# treino forte ontem explica a madrugada alta; só alerta se a noite anterior também estava alta
grava(HOJE, [72, 83, 86, 88, 74, 87, 93])
hs._upsert("treinos", "id", [{"id": "t-fc", "dia": dia(1), "inicio": dia(1) + "T18:00:00-03:00", "tipo": "Corrida", "duracao_min": 60, "energia_kcal": 640}])
confere("madrugada alta depois de treino forte: sem alerta", hs.alerta_fc(HOJE) is None, hs._fc_madrugada(HOJE))
grava(dia(1), [72, 80, 82, 84, 78, 83, 88])
confere("madrugada alta duas noites seguidas apesar do treino: alerta", hs.alerta_fc(HOJE) is not None)
grava(dia(1), [62 + (1 % 4), 63 + (1 % 3), 64, 65 - (1 % 2), 64, 66, 67])
__import__("sqlite3").connect(hs.banco.DB_PATH).execute("DELETE FROM treinos WHERE id = 't-fc'").connection.commit()
grava(HOJE, [70, 72, 71, 73, 74, 72, 75])
confere("alta pequena (menos de 10 bpm) não alerta", hs.alerta_fc(HOJE) is None, hs._fc_madrugada(HOJE))
con0 = __import__("sqlite3").connect(hs.banco.DB_PATH)
con0.execute("DELETE FROM fc_hora WHERE dia = ?", (HOJE,))
con0.commit()
con0.close()
grava(HOJE, [88, 90, 92], horas=range(0, 3))
confere("menos de 4 horas de madrugada com dado: não alerta", hs.alerta_fc(HOJE) is None, hs._fc_madrugada(HOJE))

# histórico curto: menos de 7 dias de base
import sqlite3  # noqa: E402
import studio_banco as banco  # noqa: E402
con = sqlite3.connect(banco.DB_PATH)
con.execute("DELETE FROM fc_hora WHERE dia < ?", (dia(5),))
con.commit()
con.close()
grava(HOJE, [72, 83, 86, 88, 74, 87, 93])
confere("histórico curto (menos de 7 madrugadas): não alerta", hs.alerta_fc(HOJE) is None, hs._fc_madrugada(HOJE))

# linha na página Hoje (precisa de 7 dias de base)
for i in range(1, 15):
    grava(dia(i), [62 + (i % 4), 63 + (i % 3), 64, 65 - (i % 2), 64, 66, 67])
grava(HOJE, [72, 83, 86, 88, 74, 87, 93])
txt = hs.relatorio_hoje()
confere("página Hoje mostra a madrugada comparada com o normal", "Frequência cardíaca na madrugada" in txt and "acima" in txt, txt[:700])
hs._upsert("saude_diaria", "dia, metrica", [{"dia": HOJE, "metrica": "spo2_min", "valor": 89.0, "unidade": "%"}])
txt = hs.relatorio_hoje()
confere("página Hoje mostra o oxigênio mínimo e avisa quando fica abaixo de 91", "menor leitura de hoje: 89" in txt and "Abaixo de 91" in txt, txt[:800])
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
