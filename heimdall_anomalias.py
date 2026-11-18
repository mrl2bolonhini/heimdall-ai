#!/usr/bin/env python3
"""Anomalias nos dados de saúde: compara cada medida com o SEU normal e junta os sinais.

Para cada métrica guardada em saude_diaria (e para a frequência cardíaca hora a hora de fc_hora) o Heimdall:
  1. compara o último dia com o seu normal dos 30 dias anteriores (mediana e desvio robusto, sem se deixar levar por um dia atípico);
  2. conta há quantos dias seguidos o valor está fora do normal e olha a média dos últimos 7 dias;
  3. cruza os sinais: pulso alto + variabilidade baixa + respiração/oxigênio/sono ruins juntos (corpo sob estresse ou doença) e
     distúrbios respiratórios + oxigênio baixo + sono curto (possível apneia).
Só medidas fisiológicas de sistemas diferentes alertam (veja SISTEMA); o resto é contexto, o esforço físico recente explica desvios de pulso e variabilidade e o ruído só conta acima de 70 dB.
Nada aqui é diagnóstico. Uso:  python3 heimdall_anomalias.py [AAAA-MM-DD]
"""
import hashlib
import json
import os
import statistics
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_saude as hs  # noqa: E402

# chave: (nome, unidade, sentido ruim: 1 subir, -1 cair, 0 os dois, variação mínima absoluta, variação mínima relativa, mede o dia inteiro?, casas)
#   "mede o dia inteiro" = o valor de hoje ainda está incompleto; compara-se o último dia completo.
METRICAS = {
    "fc_repouso": ("Pulso em repouso", "bpm", 0, 4, 0.05, False, 0),
    "hrv": ("Variabilidade cardíaca (HRV)", "ms", -1, 8, 0.2, False, 0),
    "resp": ("Respiração no sono", "rpm", 0, 1, 0.05, False, 1),
    "spo2": ("Oxigênio no sangue (média)", "%", -1, 1.5, 0.0, False, 1),
    "spo2_min": ("Oxigênio no sangue (menor leitura)", "%", -1, 2, 0.0, False, 1),
    "sono_total": ("Duração do sono", "min", -1, 60, 0.15, False, 0),
    "sono_profundo": ("Sono profundo", "min", -1, 20, 0.25, False, 0),
    "sono_rem": ("Sono REM", "min", -1, 20, 0.25, False, 0),
    "fc_min": ("Frequência cardíaca mínima do dia", "bpm", 1, 4, 0.05, True, 0),
    "fc_media": ("Frequência cardíaca média do dia", "bpm", 1, 6, 0.07, True, 0),
    "passos": ("Passos", "", -1, 0, 0.4, True, 0),
    "energia": ("Energia ativa", "kcal", -1, 0, 0.4, True, 0),
    "x:apple_exercise_time": ("Minutos de exercício", "min", -1, 10, 0.4, True, 0),
    "x:apple_stand_hour": ("Horas em pé", "h", -1, 2, 0.3, True, 0),
    "x:flights_climbed": ("Andares subidos", "", -1, 0, 0.5, True, 0),
    "x:walking_running_distance": ("Distância a pé", "km", -1, 0, 0.4, True, 1),
    "x:time_in_daylight": ("Tempo à luz do dia", "min", -1, 0, 0.5, True, 0),
    "x:basal_energy_burned": ("Energia em repouso", "kcal", 0, 0, 0.15, True, 0),
    "x:breathing_disturbances": ("Distúrbios respiratórios no sono", "", 1, 8, 0.3, False, 1),
    "x:walking_heart_rate_average": ("Frequência cardíaca ao caminhar", "bpm", 1, 5, 0.05, False, 0),
    "x:walking_speed": ("Velocidade de caminhada", "", -1, 0, 0.1, False, 1),
    "x:walking_step_length": ("Comprimento do passo", "", -1, 0, 0.1, False, 1),
    "x:walking_asymmetry_percentage": ("Assimetria ao caminhar", "%", 1, 0, 0.3, False, 1),
    "x:walking_double_support_percentage": ("Apoio duplo ao caminhar", "%", 1, 0, 0.15, False, 1),
    "x:apple_sleeping_wrist_temperature": ("Temperatura do pulso no sono", "°C", 0, 0.3, 0.0, False, 2),
    "x:vo2_max": ("VO2 máximo", "", -1, 1.5, 0.0, False, 1),
    "x:environmental_audio_exposure": ("Ruído do ambiente", "dB", 1, 0, 0.15, False, 0),
    "x:weight_body_mass": ("Peso", "kg", 0, 1.5, 0.0, False, 1),
}
IGNORAR = {"sono_cama", "x:heart_rate", "fc_max", "x:physical_effort", "x:apple_stand_time", "x:apple_move_time", "x:stair_speed_up", "x:stair_speed_down"}
IGNORAR_PREFIXO = ("x:anel_",)

# faixas fisiologicamente possíveis para o valor de um dia: fora delas o problema é do dado (unidade errada, dia incompleto, sensor), não do corpo
LIMITES = {"x:basal_energy_burned": (800, 4500), "fc_media": (35, 180), "fc_min": (30, 140), "fc_repouso": (30, 130), "spo2": (80, 100), "spo2_min": (60, 100),
           "x:environmental_audio_exposure": (20, 130), "hrv": (5, 300), "resp": (6, 40), "x:weight_body_mass": (20, 400)}

# O que pode alertar. Cada medida pertence a um sistema do corpo; só valem para o alerta medidas FISIOLÓGICAS, e dois sinais do mesmo sistema (pulso em repouso e pulso
# mínimo, por exemplo) contam como um só. Todo o resto (passos, energia, exercício, ruído, caminhada, peso, frequência média do dia...) é CONTEXTO: aparece no
# relatório e ajuda a interpretar, mas sozinho ou em dupla nunca vira aviso.
SISTEMA = {"fc_repouso": "coração", "fc_madrugada": "coração", "fc_min": "coração", "fc_horas": "coração", "hrv": "autonômico",
           "resp": "respiração", "spo2": "respiração", "spo2_min": "respiração", "x:breathing_disturbances": "respiração",
           "sono_total": "sono", "sono_profundo": "sono", "sono_rem": "sono", "x:apple_sleeping_wrist_temperature": "temperatura"}
# esforço físico forte recente explica estes desvios (pulso e respiração mais altos, variabilidade menor), a menos que durem 3 dias ou mais
EFEITO_ESFORCO = {"fc_repouso", "fc_madrugada", "fc_min", "fc_horas", "hrv", "resp"}
# exposição que só faz mal acima de um nível: (aviso, forte) em dB, média do dia. 70 dB em 24 h é o limite de referência da OMS e da EPA; abaixo disso nunca é achado.
EXPOSICAO = {"x:environmental_audio_exposure": (70.0, 75.0)}

BASE_DIAS = 30        # janela do "normal"
BASE_MIN = 10         # dias mínimos de histórico para comparar
Z_ALERTA = 2.5        # desvios robustos para sair do normal
Z_FORTE = 3.5
MAX_ATRASO = 2        # dias: um dado mais velho que isso não entra (não é "hoje")


def _fmt(chave: str, v, casas: int, un: str) -> str:
    if chave.startswith("sono_"):
        return hs._dur(v)
    return hs._num(v, casas) + (f" {un}" if un and un not in ("%",) else (" %" if un == "%" else ""))


def _sd_robusto(base: list, med: float, min_abs: float) -> float:
    mad = 1.4826 * statistics.median(abs(x - med) for x in base)
    return max(mad, 0.5 * statistics.pstdev(base), min_abs / 2.0, abs(med) * 0.005, 1e-6)


def _spec(chave: str):
    if chave in METRICAS:
        return METRICAS[chave]
    if chave in IGNORAR or chave.startswith(IGNORAR_PREFIXO):
        return None
    if chave.startswith("x:"):   # métrica nova que chegou do Health Auto Export: os dois sentidos, só variação grande
        return (chave[2:].replace("_", " ").capitalize(), "", 0, 0, 0.25, False, 1)
    return None


def _analisa_metrica(chave: str, hoje: str) -> dict:
    spec = _spec(chave)
    if not spec:
        return {}
    nome, un, sentido, min_abs, min_rel, dia_todo, casas = spec
    de = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=BASE_DIAS + 10)).strftime("%Y-%m-%d")
    serie = hs._serie(chave, de)
    lim = LIMITES.get(chave)
    suspeito = None
    if lim:   # valores impossíveis nunca entram no normal; se o dia mais recente for um deles, o aviso é de dado suspeito, não de saúde
        fora = {d: v for d, v in serie.items() if not lim[0] <= v <= lim[1]}
        serie = {d: v for d, v in serie.items() if d not in fora}
        if fora and max(fora) >= max(serie or {"": ""}):
            d_ruim = max(fora)
            suspeito = f"{nome} em {hs._br(d_ruim)} ({hs._num(fora[d_ruim], 0)}{' ' + un if un else ''}), fora do que é possível medir em um dia inteiro"
    # o dia avaliado: o mais recente até hoje (o dia de hoje só vale se a medida não for do dia inteiro)
    limite = hoje if not dia_todo else (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    dias = sorted(d for d in serie if d <= limite)
    if suspeito:
        return {"dado_suspeito": suspeito}
    if not dias:
        return {}
    dia = dias[-1]
    if (datetime.strptime(hoje, "%Y-%m-%d") - datetime.strptime(dia, "%Y-%m-%d")).days > MAX_ATRASO + (1 if dia_todo else 0):
        return {"sem_dado_recente": nome}
    base_de = (datetime.strptime(dia, "%Y-%m-%d") - timedelta(days=BASE_DIAS)).strftime("%Y-%m-%d")
    base = [serie[d] for d in dias if base_de <= d < dia]
    if len(base) < BASE_MIN:
        return {"sem_base": nome}
    med = statistics.median(base)
    sd = _sd_robusto(base, med, min_abs)
    v = serie[dia]
    dif = v - med
    z = dif / sd
    rel = abs(dif) / abs(med) if med else 0
    ruim = sentido == 0 or (dif > 0) == (sentido > 0)
    achado = {"chave": chave, "nome": nome, "dia": dia, "valor": v, "normal": med, "z": z, "dif": dif, "ruim": ruim, "sentido": sentido, "seguidos": 0, "tipo": "dia"}
    if chave in EXPOSICAO:   # vale o nível absoluto, não o desvio do seu normal: ruído que mudou mas está baixo não faz mal
        aviso, forte = EXPOSICAO[chave]
        if v < aviso:
            achado["nivel"] = "normal"
            return achado
        achado.update(nivel="forte" if v >= forte else "moderada", ruim=True, tipo="exposicao",
                      texto=(f"{nome}: média de {_fmt(chave, v, casas, un)} em {hs._br(dia)}, acima de {_fmt(chave, aviso, 0, un)}, o limite de referência para 24 horas de exposição "
                             "(OMS e EPA); ruído assim por muito tempo pode prejudicar a audição"))
        return achado
    grande = ruim and min_abs > 0 and abs(dif) >= 2 * min_abs and abs(z) >= 1.5   # mudança absoluta grande, mesmo com um normal bem variável
    if (abs(z) >= Z_ALERTA or grande) and abs(dif) >= min_abs and rel >= min_rel:
        achado["nivel"] = ("forte" if abs(z) >= Z_FORTE else "moderada") if ruim else "positivo"
        # há quantos dias seguidos está fora do normal (no mesmo sentido)
        n = 0
        for d in reversed([x for x in dias if x <= dia][-7:]):
            if (serie[d] - med) / sd * (1 if dif > 0 else -1) >= 1.5:
                n += 1
            else:
                break
        achado["seguidos"] = n
        sinal = "acima" if dif > 0 else "abaixo"
        achado["texto"] = (f"{nome}: {_fmt(chave, v, casas, un)} em {hs._br(dia)}, {sinal} do seu normal de {_fmt(chave, med, casas, un)} "
                           f"({'+' if dif > 0 else '-'}{_fmt(chave, abs(dif), casas, un)})" + (f"; {n} dias seguidos fora do normal" if n >= 3 else ""))
        return achado
    # dentro do normal hoje: olha a média dos últimos 7 dias (uma mudança lenta que nenhum dia isolado mostra)
    ult = [serie[d] for d in dias if d <= dia][-7:]
    if len(ult) >= 5 and ruim is not None:
        m7 = statistics.fmean(ult)
        z7 = (m7 - med) / sd
        ruim7 = sentido == 0 or (m7 - med > 0) == (sentido > 0)
        if ruim7 and abs(z7) >= 1.5 and abs(m7 - med) >= max(min_abs * 0.75, 1e-9) and (abs(m7 - med) / abs(med) if med else 0) >= min_rel * 0.75:
            achado.update(nivel="moderada", tipo="tendencia", z=z7, valor=m7, dif=m7 - med,
                          texto=(f"{nome}: média dos últimos {len(ult)} dias de {_fmt(chave, m7, casas, un)}, {'acima' if m7 > med else 'abaixo'} do seu normal de "
                                 f"{_fmt(chave, med, casas, un)} (uma mudança gradual; o último dia isolado não saiu do normal)"))
            return achado
    achado["nivel"] = "normal"
    return achado


def _fc_horas(hoje: str) -> dict:
    """Frequência cardíaca nas horas já medidas de hoje contra as MESMAS horas dos 14 dias anteriores."""
    linhas = hs._ler("SELECT hora, fc_media, leituras FROM fc_hora WHERE dia = ? AND fc_media IS NOT NULL", (hoje,))
    hoje_h = {r["hora"]: r["fc_media"] for r in linhas}
    if len(hoje_h) < 6:
        return {}
    de = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")
    por_dia: dict = {}
    for r in hs._ler("SELECT dia, hora, fc_media FROM fc_hora WHERE dia >= ? AND dia < ? AND fc_media IS NOT NULL", (de, hoje)):
        if r["hora"] in hoje_h:
            por_dia.setdefault(r["dia"], {})[r["hora"]] = r["fc_media"]
    base = [statistics.fmean(h.values()) for h in por_dia.values() if len(h) >= 0.8 * len(hoje_h)]
    if len(base) < 7:
        return {}
    m_hoje, normal, sd = statistics.fmean(hoje_h.values()), statistics.fmean(base), max(statistics.pstdev(base), 2.0)
    dif = m_hoje - normal
    if dif >= 8 and dif / sd >= Z_ALERTA:
        return {"chave": "fc_horas", "nome": "Frequência cardíaca nas horas já medidas de hoje", "dia": hoje, "valor": m_hoje, "normal": normal, "z": dif / sd, "dif": dif,
                "ruim": True, "sentido": 1, "seguidos": 0, "tipo": "dia", "nivel": "forte" if dif >= 15 else "moderada",
                "texto": (f"Frequência cardíaca nas {len(hoje_h)} horas já medidas de hoje ({hs._br(hoje)}): média de {hs._num(m_hoje)} bpm, {hs._num(dif)} bpm acima do normal "
                          f"para essas mesmas horas ({hs._num(normal)} bpm)")}
    return {}


def _fc_madrugada(hoje: str) -> dict:
    a = hs.alerta_fc(hoje)
    if not a:
        return {}
    m = hs._fc_madrugada(hoje)
    return {"chave": "fc_madrugada", "nome": "Frequência cardíaca na madrugada", "dia": hoje, "valor": m["hoje"], "normal": m["normal"], "z": (m["hoje"] - m["normal"]) / max(m["sd"] or 0, 2.0),
            "dif": m["hoje"] - m["normal"], "ruim": True, "sentido": 1, "seguidos": 0, "tipo": "dia", "nivel": "forte",
            "texto": (f"Frequência cardíaca na madrugada de {hs._br(hoje)} (0h às 7h): média de {hs._num(m['hoje'])} bpm, {hs._num(m['hoje'] - m['normal'])} bpm acima do seu normal "
                      f"de {hs._num(m['normal'])} bpm")}


def _combos(f: dict) -> list:
    """Cruza os sinais. f: chave -> achado (só os que saíram do normal em sentido ruim)."""
    def sobe(*ks):
        return any(k in f and f[k]["dif"] > 0 for k in ks)

    def cai(*ks):
        return any(k in f and f[k]["dif"] < 0 for k in ks)
    fc_alta = sobe("fc_repouso", "fc_media", "fc_min", "fc_madrugada", "fc_horas", "x:walking_heart_rate_average")
    sinais = {"pulso alto": fc_alta, "variabilidade (HRV) baixa": cai("hrv"), "respiração mais rápida": sobe("resp"),
              "oxigênio baixo": cai("spo2", "spo2_min"), "sono curto ou pior": cai("sono_total", "sono_profundo", "sono_rem"),
              "temperatura do pulso alta": sobe("x:apple_sleeping_wrist_temperature")}
    ativos = [k for k, v in sinais.items() if v]
    out = []
    if len(ativos) >= 3:
        out.append({"chave": "combo_estresse", "nivel": "forte",
                    "texto": ("Vários sinais fora do normal ao mesmo tempo (" + ", ".join(ativos) + "). É um padrão comum quando o corpo está sob estresse, com infecção ou com má recuperação, "
                              "mas também pode ter outras causas. Não é diagnóstico: observe febre, falta de ar, palpitação ou tontura e procure atendimento se houver.")})
    apneia = {"distúrbios respiratórios altos": sobe("x:breathing_disturbances"), "oxigênio baixo": cai("spo2", "spo2_min"),
              "sono curto ou pior": cai("sono_total", "sono_profundo", "sono_rem"), "pulso alto na madrugada": sobe("fc_madrugada", "fc_min")}
    a_ativos = [k for k, v in apneia.items() if v]
    if len(a_ativos) >= 3 or (apneia["distúrbios respiratórios altos"] and apneia["oxigênio baixo"]):
        out.append({"chave": "combo_sono_respiracao", "nivel": "forte",
                    "texto": ("Sinais de respiração e sono alterados juntos (" + ", ".join(a_ativos) + "). Esse conjunto costuma ser investigado quando há suspeita de apneia do sono. "
                              "Não é diagnóstico: vale levar os números a um médico, que pode pedir uma avaliação do sono.")})
    return out


def analisar(hoje: str = None) -> dict:
    """Devolve {dia, achados, combos, positivos, sem_base, sem_dado_recente, analisadas}."""
    hoje = hoje or datetime.now().strftime("%Y-%m-%d")
    hs.banco.normalizar_energia()   # energia que chegou em kJ vira kcal antes de qualquer comparação
    chaves = [r["metrica"] for r in hs._ler("SELECT DISTINCT metrica FROM saude_diaria WHERE dia >= ?", ((datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=BASE_DIAS + 10)).strftime("%Y-%m-%d"),))]
    achados, positivos, sem_base, sem_recente, analisadas, suspeitos = [], [], [], [], 0, []
    for ch in sorted(chaves):
        r = _analisa_metrica(ch, hoje)
        if not r:
            continue
        if "dado_suspeito" in r:
            suspeitos.append(r["dado_suspeito"])
            continue
        if "sem_base" in r:
            sem_base.append(r["sem_base"])
            continue
        if "sem_dado_recente" in r:
            sem_recente.append(r["sem_dado_recente"])
            continue
        analisadas += 1
        if r.get("nivel") in ("forte", "moderada"):
            achados.append(r)
        elif r.get("nivel") == "positivo":
            positivos.append(r)
    for extra in (_fc_madrugada(hoje), _fc_horas(hoje)):
        if extra:
            analisadas += 1
            achados.append(extra)
    esforco = hs.esforco_recente(hoje)
    for a in achados:   # contexto: esforço recente explica pulso/variabilidade/respiração; medidas de contexto não alertam
        if a["chave"] in EFEITO_ESFORCO and a["seguidos"] < 3 and (esforco["hoje"] if a["chave"] == "fc_horas" else esforco["recente"]):
            a["explicado"] = esforco["texto"]
            a["texto"] += f" (provável efeito de {esforco['texto']}, não necessariamente um problema)"
        a["contexto"] = a["chave"] not in SISTEMA and a.get("tipo") != "exposicao"
    achados.sort(key=lambda a: (a["nivel"] != "forte", -abs(a["z"])))
    combos = _combos({a["chave"]: a for a in achados if a["ruim"] and a["chave"] in SISTEMA and not a.get("explicado")})
    return {"dia": hoje, "achados": achados, "combos": combos, "positivos": positivos, "sem_base": sem_base, "sem_dado_recente": sem_recente, "analisadas": analisadas,
            "suspeitos": suspeitos, "esforco": esforco}


def relatorio(hoje: str = None) -> str:
    r = analisar(hoje)
    linhas = []
    if r["combos"]:
        linhas.append("Padrões que juntam sinais:")
        linhas += [c["texto"] + "." for c in r["combos"]]
    fortes = [a for a in r["achados"] if a["nivel"] == "forte"]
    outros = [a for a in r["achados"] if a["nivel"] != "forte"]
    if fortes:
        linhas.append("Muito fora do seu normal:")
        linhas += [a["texto"] + "." for a in fortes]
    if outros:
        linhas.append("Um pouco fora do seu normal:")
        linhas += [a["texto"] + "." for a in outros]
    if not r["achados"] and not r["analisadas"]:
        linhas.append("Ainda não há medidas com histórico suficiente (pelo menos 10 dias) para comparar com o seu normal.")
    elif not r["achados"]:
        linhas.append("Nenhuma medida saiu do seu normal.")
    if r["positivos"]:
        linhas.append("Melhor que o seu normal:")
        linhas += [a["texto"] + "." for a in r["positivos"][:6]]
    rodape = f"Medidas comparadas com o seu normal dos últimos {BASE_DIAS} dias: {r['analisadas']}."
    if r.get("suspeitos"):
        rodape += " Dados que parecem incorretos ou incompletos (ignorados, não são alerta de saúde): " + "; ".join(r["suspeitos"]) + "."
    if r["sem_dado_recente"]:
        rodape += " Sem dado recente (não entraram): " + ", ".join(sorted(r["sem_dado_recente"])) + "."
    if r["sem_base"]:
        rodape += " Ainda sem histórico suficiente: " + ", ".join(sorted(r["sem_base"])) + "."
    linhas.append(rodape + " Isto não é diagnóstico.")
    return hs._br("Anomalias de " + hs._br(r["dia"]) + ":\n" + "\n".join(linhas))


# ----------------------------------------------------------------------------------------
# Aviso na triagem: só quando algo MUDA, com a interpretação do modelo local
# ----------------------------------------------------------------------------------------
ESTADO = hs.banco.DB_DIR / "anomalias_estado.json"
LEMBRETE_HORAS = int(os.environ.get("HEIMDALL_ANOMALIAS_LEMBRETE_H", "120"))   # sinal que persiste igual: um lembrete a cada tantas horas, nunca a cada ciclo
PIORA_Z = 1.0                                                                    # quanto o desvio precisa crescer para contar como piora
LLM_URL = os.environ.get("HEIMDALL_SAUDE_LLM_URL", os.environ.get("HEIMDALL_NEWS_LLM_URL", "http://127.0.0.1:9000/v1/chat/completions"))
LLM_MODELO = os.environ.get("HEIMDALL_SAUDE_MODELO", os.environ.get("HEIMDALL_NEWS_MODELO", "gemma3-4b"))
_abridor_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # só o LiteLLM desta máquina: dado de saúde nunca sai do Mac


def _ler_estado() -> dict:
    try:
        d = json.loads(ESTADO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def salvar_estado(estado: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")


def _agora_iso(agora: datetime = None) -> str:
    return (agora or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def _horas_desde(iso: str, agora: datetime) -> float:
    try:
        return (agora - datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def _interpretar(r: dict, fortes: list, antes: dict, mudou: dict) -> dict:
    """Pede ao modelo local que avalie se o conjunto faz sentido e o que fazer. Devolve {} se o modelo não responder (o aviso sai com o texto simples)."""
    achados = [a["texto"] for a in fortes] + [c["texto"] for c in r["combos"]]
    ja_avisado = "; ".join(f"{k} (z {v['z']:.1f})" for k, v in (antes.get("sinais") or {}).items()) or "nada ainda"
    prompt = (
        "Você analisa dados de saúde de um adulto vindos do Apple Watch e do iPhone, em português do Brasil. O texto vai para um leitor de tela: frases curtas, sem listas, sem símbolos.\n\n"
        "TAREFA: avalie se os achados abaixo fazem sentido juntos e se merecem atenção. Pense em duas hipóteses antes de concluir: (a) o corpo realmente mudou; (b) o dado está errado ou incompleto "
        "(relógio fora do pulso ou sem sincronizar, dia ainda em andamento, unidade trocada, ambiente barulhento). Diga qual é a mais provável e por quê, citando os números.\n"
        "Não diagnostique, não invente números, não trate variação pequena como perigo. Sugira de duas a três ações concretas e proporcionais (por exemplo conferir se o relógio estava no pulso, "
        "medir a temperatura, descansar, hidratar, repetir a medida amanhã). Só sugira procurar atendimento se houver combinação clara de sinais ou sintomas relatados.\n"
        + (f"Condições da pessoa que você deve respeitar: {os.environ['HEIMDALL_SAUDE_CONDICOES']}.\n" if os.environ.get("HEIMDALL_SAUDE_CONDICOES") else "")
        + "Regras de interpretação: esforço físico forte recente explica pulso, respiração e variabilidade alterados; ruído só importa acima de 70 dB de média no dia; "
          "passos, energia e exercício diferentes do normal são contexto, não problema; nunca ligue dois sinais sem relação fisiológica.\n"
        + "\nACHADOS DE HOJE:\n" + "\n".join(achados)
        + ("\nCONTEXTO (não são alerta por si): " + "; ".join(a["texto"] for a in r["achados"] if a.get("contexto") or a.get("explicado"))[:700]
           if any(a.get("contexto") or a.get("explicado") for a in r["achados"]) else "")
        + ("\nESFORÇO RECENTE: " + r["esforco"]["texto"] if r.get("esforco", {}).get("texto") else "")
        + "\n\nO QUE JÁ FOI AVISADO ANTES: " + ja_avisado
        + "\nO QUE MUDOU DESDE O ÚLTIMO AVISO: " + (mudou.get("resumo") or "primeiro aviso")
        + ("\nDADOS SUSPEITOS (ignorados): " + "; ".join(r["suspeitos"]) if r.get("suspeitos") else "")
        + ("\nSEM DADO RECENTE: " + ", ".join(r["sem_dado_recente"]) if r.get("sem_dado_recente") else "")
        + '\n\nResponda só com JSON: {"veredito": "atencao" ou "provavel_artefato" ou "inconclusivo", "explicacao": "duas a quatro frases", "acoes": ["...", "..."], "mudou": "uma frase sobre o que mudou em relação ao último aviso"}')
    corpo = json.dumps({"model": LLM_MODELO, "temperature": 0.2, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}).encode()
    cab = {"Content-Type": "application/json"}
    if os.environ.get("LITELLM_MASTER_KEY"):
        cab["Authorization"] = "Bearer " + os.environ["LITELLM_MASTER_KEY"]
    try:
        with _abridor_local.open(urllib.request.Request(LLM_URL, data=corpo, headers=cab), timeout=120) as resp:
            txt = json.loads(resp.read(2_000_000))["choices"][0]["message"]["content"] or ""
    except Exception:  # noqa: BLE001 - sem modelo, o aviso sai com o texto simples
        return {}
    import re
    txt = re.sub(r"(?is)<think>.*?</think>", "", txt)
    a, b = txt.find("{"), txt.rfind("}")
    try:
        d = json.loads(txt[a:b + 1]) if a >= 0 < b else {}
    except ValueError:
        return {}
    if not isinstance(d, dict) or not str(d.get("explicacao", "")).strip():
        return {}
    d["acoes"] = [str(x).strip() for x in (d.get("acoes") or []) if str(x).strip()][:3]
    return d


def alerta(hoje: str = None, agora: datetime = None, interpretar=_interpretar):
    """Item de triagem quando há um padrão combinado ou pelo menos duas medidas muito fora do normal, e SÓ se algo mudou desde o último aviso:
    sinal novo, sinal que piorou, ou (a cada LEMBRETE_HORAS) lembrete de que o mesmo quadro continua. O item traz '_estado': quem o grava na
    triagem chama salvar_estado(item.pop('_estado')) depois que dá certo, para um aviso perdido não ser dado como entregue."""
    agora = agora or datetime.now()
    r = analisar(hoje)
    todos_fortes = [a for a in r["achados"] if a["nivel"] == "forte" and a["chave"] != "fc_madrugada"]
    # só medidas fisiológicas não explicadas por esforço, e só de sistemas diferentes, mais exposição acima do limite (ruído)
    fortes = [a for a in todos_fortes if (a["chave"] in SISTEMA and not a.get("explicado")) or a.get("tipo") == "exposicao"]
    sistemas = {SISTEMA[a["chave"]] for a in fortes if a["chave"] in SISTEMA}
    antes = _ler_estado()
    if not r["combos"] and len(sistemas) < 2 and not any(a.get("tipo") == "exposicao" for a in fortes):
        if antes.get("sinais"):
            salvar_estado({"sinais": {}, "quando": antes.get("quando", ""), "normalizou": _agora_iso(agora)})   # quadro normalizou: a próxima ocorrência volta a ser novidade
        return None
    sinais = {a["chave"]: {"z": round(abs(a["z"]), 2), "nome": a["nome"]} for a in fortes}
    sinais.update({c["chave"]: {"z": 9.0, "nome": c["chave"]} for c in r["combos"]})
    ant = antes.get("sinais") or {}
    novos = [k for k in sinais if k not in ant]
    pioraram = [k for k in sinais if k in ant and sinais[k]["z"] >= ant[k]["z"] + PIORA_Z]
    horas = _horas_desde(antes.get("quando", ""), agora)
    if not novos and not pioraram:
        if horas < LEMBRETE_HORAS:
            if set(ant) != set(sinais):   # algum sinal saiu e nada entrou: guarda o quadro menor, sem avisar
                salvar_estado({"sinais": sinais, "quando": antes.get("quando", "")})
            return None
        mudou = {"resumo": f"nada de novo: o mesmo quadro continua há {int(horas // 24)} dias"}
        motivo = "lembrete"
    else:
        nomes = {a["chave"]: a["nome"] for a in fortes}
        partes = ([f"sinal novo: {nomes.get(k, k)}" for k in novos] + [f"piorou: {nomes.get(k, k)}" for k in pioraram])
        mudou = {"resumo": "; ".join(partes)}
        motivo = "mudou"
    interp = interpretar(r, fortes, antes, mudou) if interpretar else {}
    sel = hashlib.sha1((motivo + "|".join(sorted(sinais)) + _agora_iso(agora)[:13]).encode()).hexdigest()[:8]
    n = len(fortes) + len(r["combos"])
    if interp:
        acoes = " ".join(f"{i}. {a.rstrip('.')}." for i, a in enumerate(interp["acoes"], 1))
        resumo = (interp["explicacao"].strip() + (" O que mudou: " + str(interp.get("mudou", "")).strip() if str(interp.get("mudou", "")).strip() and motivo == "mudou" else "")
                  + (" O que fazer: " + acoes if acoes else ""))
        artefato = interp.get("veredito") == "provavel_artefato"
        titulo = "Saúde: sinais fora do normal, mas o dado pode estar errado" if artefato else f"Saúde: {n} sinal(is) fora do seu normal merece(m) atenção"
        nivel = "medio" if artefato else "alto"
    else:
        partes_t = [c["texto"] for c in r["combos"]] + [a["texto"] for a in fortes[:4]]
        resumo = hs._br(" ".join(p + "." for p in partes_t)) + (" (O modelo local não respondeu, por isso sem interpretação.)")
        titulo = f"Saúde: {n} sinal(is) muito fora do seu normal"
        nivel = "alto"
    if motivo == "lembrete":
        titulo = "Lembrete: " + titulo
        resumo = f"O mesmo quadro continua há {int(horas // 24)} dias, sem mudança. " + resumo
    return {"id": f"anomalias|{r['dia']}|{sel}", "titulo": titulo, "nivel": nivel, "fonte": "saude",
            "resumo": resumo[:850] + " Detalhes na página Anomalias do painel de saúde. Isto não é diagnóstico.",
            "_estado": {"sinais": sinais, "quando": _agora_iso(agora)}}


if __name__ == "__main__":
    hs._garantir_banco()
    print(relatorio(sys.argv[1] if len(sys.argv) > 1 else None))
