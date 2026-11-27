#!/usr/bin/env python3
"""Testa studio_anomalias: normal, desvio, tendência lenta, sequência, cruzamentos, medidas do dia inteiro e métricas desconhecidas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="anomalias_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "banco")
sys.path.insert(0, str(RAIZ))
import studio_saude as hs  # noqa: E402
import studio_anomalias as an  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


hs._garantir_banco()
confere("banco vazio não diz que está tudo normal", "histórico suficiente" in an.relatorio() and "Nenhuma medida saiu" not in an.relatorio(), an.relatorio())
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

# 5b. o aviso explica a medida, o tamanho do desvio e o impacto (nunca só "20 ms contra 29 ms")
txt_hrv = next((a["texto"] for a in r["achados"] if a["chave"] == "hrv"), "")
confere("achado traz percentual e quão raro foi", "por cento" in txt_hrv and ("dos últimos" in txt_hrv), txt_hrv)
sig = an.explicar(r["achados"])
confere("glossário diz o que é a HRV e o efeito prático", "variabilidade da frequência cardíaca" in sig and "recuperação" in sig, sig)
a_sem = an.alerta(HOJE, interpretar=None)
confere("sem o modelo, o aviso ainda explica o significado", a_sem and "O que isso significa" in a_sem["resumo"], a_sem and a_sem["resumo"][:300])
confere("resumo cabe no limite e não corta no meio da frase", a_sem and len(a_sem["resumo"]) < 1800, a_sem and len(a_sem["resumo"]))

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


# 14. dado impossível não vira alerta de saúde (energia em repouso de 384 num dia inteiro; antes chegava em kJ e era lida como kcal)
from datetime import datetime as _dt  # noqa: E402
for i in range(1, 31):
    grava("x:basal_energy_burned", dia(i), 8400 + (i % 4) * 150, "kJ")      # chega em kJ: o banco converte para kcal
hs.banco.normalizar_energia()
con = hs.banco.conectar()
unid = {r_[0] for r_ in con.execute("SELECT unidade FROM saude_diaria WHERE metrica = 'x:basal_energy_burned'")}
vals = [r_[0] for r_ in con.execute("SELECT valor FROM saude_diaria WHERE metrica = 'x:basal_energy_burned'")]
con.close()
confere("energia em kJ vira kcal (8.400 kJ ~ 2.000 kcal)", unid == {"kcal"} and all(1900 < v < 2300 for v in vals), (unid, vals[:3]))
grava("x:basal_energy_burned", dia(1), 384 / 4.184, "kcal")
r = an.analisar(HOJE)
confere("dia com energia em repouso impossível entra em 'dados suspeitos', não em achados", any("Energia em repouso" in x for x in r["suspeitos"]) and not any(a["chave"] == "x:basal_energy_burned" for a in r["achados"]), (r["suspeitos"], [a["chave"] for a in r["achados"]]))
grava("x:basal_energy_burned", dia(1), 2000, "kcal")

# 15. aviso só quando algo muda; o modelo interpreta; sem repetir a cada ciclo
for m, v in NORMAL.items():
    grava(m, HOJE, v)
estado = an.ESTADO
if estado.exists():
    estado.unlink()
agora = _dt.now()
chamadas = []


def interprete(r, fortes, antes, mudou):
    chamadas.append(mudou["resumo"])
    return {"veredito": "atencao", "explicacao": "O pulso subiu e a variabilidade caiu juntos, o que costuma indicar cansaço ou início de infecção.", "acoes": ["Meça a temperatura hoje.", "Durma mais cedo."], "mudou": "primeiro quadro"}


grava("fc_repouso", HOJE, 72)
grava("hrv", HOJE, 30)
grava("resp", HOJE, 17.5)
grava("sono_total", HOJE, 300)
a1 = an.alerta(HOJE, agora, interprete)
confere("primeiro quadro: avisa, com a interpretação do modelo e as ações", a1 and "O pulso subiu" in a1["resumo"] and "1. Meça a temperatura hoje." in a1["resumo"] and "_estado" in a1, a1)
confere("sem confirmar o estado, o aviso se repete (aviso perdido não conta como entregue)", an.alerta(HOJE, agora, interprete) is not None)
an.salvar_estado(a1.pop("_estado"))
confere("mesmo quadro no ciclo seguinte: não avisa de novo", an.alerta(HOJE, agora + timedelta(hours=2), interprete) is None)
confere("mesmo quadro um dia depois: continua quieto", an.alerta(HOJE, agora + timedelta(hours=26), interprete) is None)
l = an.alerta(HOJE, agora + timedelta(hours=125), interprete)
confere("depois de 5 dias de quadro igual: um lembrete, dizendo que não mudou", l and l["titulo"].startswith("Lembrete") and "continua há 5 dias" in l["resumo"], l and (l["titulo"], l["resumo"][:120]))
grava("spo2", HOJE, 91)
grava("spo2_min", HOJE, 88)
for i in range(1, 31):
    grava("spo2_min", dia(i), 94)
n = an.alerta(HOJE, agora + timedelta(hours=3), interprete)
confere("sinal novo (oxigênio) avisa de novo e diz o que mudou", n and any("sinal novo" in c for c in chamadas[-1:]), chamadas)
an.salvar_estado(n.pop("_estado"))
for m, v in NORMAL.items():
    grava(m, HOJE, v)
grava("spo2_min", HOJE, 94)
confere("quadro normalizou: não avisa", an.alerta(HOJE, agora + timedelta(hours=6), interprete) is None and not an._ler_estado().get("sinais"))
grava("fc_repouso", HOJE, 72)
grava("hrv", HOJE, 30)
grava("resp", HOJE, 17.5)
grava("sono_total", HOJE, 300)
confere("se o mesmo quadro voltar depois de normalizar, é novidade", an.alerta(HOJE, agora + timedelta(hours=9), interprete) is not None)
sem_modelo = an.alerta(HOJE, agora + timedelta(hours=9), lambda *a: {})
confere("modelo fora do ar: avisa com o texto simples e diz que não houve interpretação", sem_modelo and "sem interpretação" in sem_modelo["resumo"], sem_modelo)

# 11. contexto: frequência média do dia e ruído do ambiente não dão alerta juntos (medidas sem relação, e o ruído baixo não faz mal)
for m in ("fc_media", "x:environmental_audio_exposure"):
    for i in range(1, 31):
        grava(m, dia(i), (72 if m == "fc_media" else 48) + (i % 4))
for m, v in NORMAL.items():
    grava(m, HOJE, v)
grava("fc_media", dia(1), 108)
grava("x:environmental_audio_exposure", HOJE, 63)
r = an.analisar(HOJE)
confere("frequência média muito alta aparece, mas como contexto", [a for a in r["achados"] if a["chave"] == "fc_media" and a["contexto"]], r["achados"])
confere("ruído de 63 dB não é achado, mesmo muito acima do seu normal de 48", not [a for a in r["achados"] if a["chave"] == "x:environmental_audio_exposure"], r["achados"])
confere("frequência média alta + ruído mudado: nenhum alerta", an.alerta(HOJE) is None)
grava("x:environmental_audio_exposure", HOJE, 66)
confere("ruído de 66 dB (abaixo de 70) ainda não é achado", not [a for a in an.analisar(HOJE)["achados"] if a["chave"] == "x:environmental_audio_exposure"])
confere("e frequência média alta com ruído de 66 dB continua sem alerta", an.alerta(HOJE) is None)
grava("x:environmental_audio_exposure", HOJE, 72)
a_ruido = [a for a in an.analisar(HOJE)["achados"] if a["chave"] == "x:environmental_audio_exposure"]
confere("ruído com média de 72 dB passa do limite de 70 e vira achado moderado, citando OMS e EPA", a_ruido and a_ruido[0]["nivel"] == "moderada" and "OMS" in a_ruido[0]["texto"], a_ruido)
confere("moderado sozinho não gera alerta", an.alerta(HOJE) is None)
grava("x:environmental_audio_exposure", HOJE, 78)
a_ruido = [a for a in an.analisar(HOJE)["achados"] if a["chave"] == "x:environmental_audio_exposure"]
alerta_ruido = an.alerta(HOJE, datetime.now(), lambda *x: {})
confere("ruído com média de 78 dB é forte e sozinho gera alerta", a_ruido and a_ruido[0]["nivel"] == "forte" and alerta_ruido is not None, a_ruido)
grava("x:environmental_audio_exposure", HOJE, 48)
grava("fc_media", dia(1), 74)

# 12. dois sinais do mesmo sistema contam como um; sistemas diferentes alertam; esforço recente explica
for m, v in NORMAL.items():
    grava(m, HOJE, v)
for i in range(1, 31):
    grava("fc_min", dia(i), 48 + (i % 3))
grava("fc_repouso", HOJE, 75)
grava("fc_min", dia(1), 66)   # medida do dia inteiro: vale o último dia completo
r = an.analisar(HOJE)
confere("pulso em repouso e pulso mínimo muito altos são dois achados fortes", {a["chave"] for a in r["achados"] if a["nivel"] == "forte"} >= {"fc_repouso", "fc_min"}, r["achados"])
confere("mas são o mesmo sistema (coração): sem alerta", an.alerta(HOJE, datetime.now(), lambda *x: {}) is None)
grava("hrv", HOJE, 30)
confere("pulso alto e variabilidade baixa, sistemas diferentes e sem esforço: alerta", an.alerta(HOJE, datetime.now(), lambda *x: {}) is not None)
hs._upsert("treinos", "id", [{"id": "teste-corrida", "dia": dia(1), "inicio": dia(1) + "T18:00:00-03:00", "tipo": "Corrida", "duracao_min": 55, "energia_kcal": 620}])
r = an.analisar(HOJE)
expl = [a["chave"] for a in r["achados"] if a.get("explicado")]
confere("com corrida forte ontem, pulso e variabilidade ficam explicados pelo esforço", {"fc_repouso", "hrv"} <= set(expl), r["achados"])
confere("o texto explica o esforço", any("efeito de treino forte recente" in a["texto"] for a in r["achados"] if a.get("explicado")))
confere("explicados pelo esforço: sem alerta", an.alerta(HOJE, datetime.now(), lambda *x: {}) is None)
for i in range(0, 4):   # o desvio dura 4 dias: deixa de ser explicado só pelo treino
    grava("hrv", dia(i), 30)
a_hrv = [a for a in an.analisar(HOJE)["achados"] if a["chave"] == "hrv"]
confere("variabilidade baixa por 4 dias seguidos não é mais explicada pelo treino", a_hrv and not a_hrv[0].get("explicado"), a_hrv)
for m, v in NORMAL.items():
    grava(m, HOJE, v)
grava("spo2", HOJE, 92)
grava("x:breathing_disturbances", HOJE, 25)
confere("oxigênio baixo e distúrbios respiratórios continuam alertando apesar do treino", an.alerta(HOJE, datetime.now(), lambda *x: {}) is not None)

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
