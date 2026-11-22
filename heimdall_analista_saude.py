#!/usr/bin/env python3
"""Analista de saúde: o modelo olha TODAS as métricas, cruza umas com as outras e entrega análise, hipóteses, perigos e recomendações.

Fluxo:
  1. o código monta um dossiê com os números (cada medida contra o seu normal, tendência, correlações calculadas, treinos, sintomas, exames, condições);
  2. busca no PubMed resumos de estudos sobre os achados (a busca leva só termos genéricos, nunca os seus valores), com cache de 30 dias;
  3. o modelo (local por padrão) escreve a análise em JSON; o código confere o JSON, descarta citações que não existem e grava em português simples;
  4. o resultado vai para a aba Avisos do Heimdall Health; só avisa no Mac e no iPhone quando há algo que merece atenção (ou no resumo de domingo).
Sem modelo, sai uma análise feita só pelo código (desvios, explicações, correlações), sem hipóteses.
Não há freio de "não sou médico": o modelo pode levantar hipóteses com grau de probabilidade e dizer quando algo é urgente. A decisão de procurar um médico é sua.
Uso:  python3 heimdall_analista_saude.py [--dias 30] [--sem-modelo] [--sem-literatura] [--gravar]
Interruptores no .env: HEIMDALL_SAUDE_ANALISTA=0 (desliga a análise automática), HEIMDALL_SAUDE_LITERATURA=0 (não consulta o PubMed),
HEIMDALL_SAUDE_ANALISTA_MODELO e HEIMDALL_SAUDE_ANALISTA_URL (usar outro modelo, por exemplo um maior), HEIMDALL_SAUDE_CONDICOES (condições a acompanhar).
"""
import hashlib
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_anomalias as an  # noqa: E402
import heimdall_nuvem as nuvem  # noqa: E402
import heimdall_saude as hs  # noqa: E402

LLM_URL = os.environ.get("HEIMDALL_SAUDE_ANALISTA_URL", an.LLM_URL)
LLM_MODELO = os.environ.get("HEIMDALL_SAUDE_ANALISTA_MODELO", an.LLM_MODELO)
PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
CACHE_DIAS = 30
INTERVALO_HORAS = 20            # a análise automática roda no máximo uma vez por esse tempo
GRAVIDADES = ("informativo", "atencao", "importante", "urgente")
_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Limiares de referência geral: cruzar um deles sempre aparece, mesmo que o modelo falhe. (métrica, comparação, valor, gravidade, texto)
LIMIARES = [
    ("spo2_min", "<", 90, "urgente", "A menor leitura de oxigênio no sangue ficou abaixo de 90 por cento. Se a leitura for real, é uma queda que costuma exigir avaliação rápida; confira se o relógio estava bem ajustado e meça de novo."),
    ("spo2", "<", 92, "atencao", "A média de oxigênio no sangue ficou abaixo de 92 por cento."),
    ("fc_repouso", ">", 100, "atencao", "O pulso em repouso ficou acima de 100 bpm (taquicardia em repouso, se confirmado com o corpo parado)."),
    ("fc_min", "<", 40, "atencao", "A frequência mínima do dia ficou abaixo de 40 bpm (bradicardia; é comum em atletas, mas é incomum sem treino regular)."),
    ("resp", ">", 25, "atencao", "A respiração no sono ficou acima de 25 por minuto."),
    ("glicose", "<", 70, "importante", "A glicose ficou abaixo de 70 mg/dL, faixa de hipoglicemia."),
    ("glicose", "<", 54, "urgente", "A glicose ficou abaixo de 54 mg/dL, hipoglicemia importante."),
]

# Termos de busca no PubMed (em inglês, genéricos) por medida; vale só o que saiu do normal.
BUSCA = {
    "hrv": "heart rate variability decrease causes recovery stress illness",
    "fc_repouso": "resting heart rate increase causes sleep deprivation infection overtraining",
    "fc_madrugada": "nocturnal heart rate elevated causes alcohol fever sleep",
    "fc_horas": "elevated daytime heart rate causes",
    "resp": "sleeping respiratory rate increase causes",
    "spo2": "nocturnal oxygen saturation decrease wearable accuracy sleep apnea",
    "spo2_min": "nocturnal oxygen desaturation wearable sleep apnea",
    "sono_total": "short sleep duration effects heart rate variability recovery",
    "sono_profundo": "reduced deep sleep causes effects",
    "sono_rem": "reduced REM sleep causes effects",
    "glicose": "hypoglycemia nocturnal causes heart rate variability",
    "x:breathing_disturbances": "breathing disturbances apple watch sleep apnea detection",
    "x:apple_sleeping_wrist_temperature": "wrist temperature during sleep fever illness detection wearable",
}
BUSCA_COMBO = {"combo_estresse": "resting heart rate heart rate variability sleep combined physiological stress illness prediction wearable",
               "combo_sono_respiracao": "wearable oxygen saturation breathing disturbances sleep apnea screening"}


def _env(c: str, padrao: str = "") -> str:
    return os.environ.get(c, padrao).strip()


# ----------------------------------------------------------------------------------------
# 1. Dossiê
# ----------------------------------------------------------------------------------------
def _correlacoes(chaves: list, hoje: str, dias: int = 90, maximo: int = 8) -> list:
    """Pares de medidas que andam juntas (no mesmo dia, ou a medida de ontem contra a de hoje). Cálculo do código; o modelo só interpreta."""
    de = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=dias)).strftime("%Y-%m-%d")
    series = {c: hs._serie(c, de) for c in chaves}
    series = {c: s for c, s in series.items() if len(s) >= 20}
    achados = []
    nomes = {c: (an._spec(c) or (c,))[0] for c in series}
    ks = sorted(series)
    melhor = {}
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            for atraso in (0, -1, 1):   # -1: a medida b de ontem contra a de hoje; 1: a de ontem contra b de hoje
                xs, ys = [], []
                for d, v in series[a].items():
                    d2 = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=atraso)).strftime("%Y-%m-%d")
                    if d2 in series[b]:
                        xs.append(v)
                        ys.append(series[b][d2])
                r = hs._correlacao(xs, ys)
                if r is None or abs(r) < 0.4:
                    continue
                pri, seg, lag = (a, b, 1) if atraso == 1 else (b, a, 1) if atraso == -1 else (a, b, 0)
                item = {"a": nomes[pri], "b": nomes[seg], "r": round(r, 2), "n": len(xs), "atraso_dias": lag, "chaves": [pri, seg]}
                if (a, b) not in melhor or abs(r) > abs(melhor[(a, b)]["r"]) + 0.02:   # empate favorece o mesmo dia
                    melhor[(a, b)] = item
    achados = list(melhor.values())
    achados.sort(key=lambda x: -abs(x["r"]))
    return achados[:maximo]


def _contexto_clinico(hoje: str) -> dict:
    ctx = {}
    de = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")
    try:
        t = hs._ler("SELECT dia, tipo, duracao_min FROM treinos WHERE dia >= ? ORDER BY dia", (de,))
        ctx["treinos_14d"] = {"quantidade": len(t), "minutos": round(sum((x["duracao_min"] or 0) for x in t)), "tipos": sorted({x["tipo"] for x in t if x["tipo"]})[:6]}
    except Exception:  # noqa: BLE001
        pass
    try:
        ev = hs._ler("SELECT tipo, dia, titulo, texto FROM saude_eventos WHERE dia >= ? AND tipo != 'aviso_fc' ORDER BY dia DESC LIMIT 30", (de,))
        ctx["eventos_14d"] = [f"{e['dia']} {e['tipo']}: {e['titulo']} {e['texto']}".strip()[:120] for e in ev]
    except Exception:  # noqa: BLE001
        pass
    try:
        ex = hs._ler("SELECT dia, nome, valor_texto, unidade, ref_texto, sinal FROM exames_resultados WHERE dia >= ? AND sinal IN ('abaixo','acima') ORDER BY dia DESC LIMIT 25",
                     ((datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d"),))
        ctx["exames_fora_da_faixa_12m"] = [f"{e['dia']} {e['nome']}: {e['valor_texto']} {e['unidade']} ({e['sinal']}; referência {e['ref_texto']})".strip()[:140] for e in ex]
    except Exception:  # noqa: BLE001
        pass
    cond = _env("HEIMDALL_SAUDE_CONDICOES")
    if cond:
        ctx["condicoes_da_pessoa"] = cond
    return ctx


def dossie(hoje: str = None, dias: int = 30) -> dict:
    hoje = hoje or datetime.now().strftime("%Y-%m-%d")
    hs._garantir_banco()
    hs.banco.normalizar_energia()
    de = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=an.BASE_DIAS + 10)).strftime("%Y-%m-%d")
    chaves = sorted(r["metrica"] for r in hs._ler("SELECT DISTINCT metrica FROM saude_diaria WHERE dia >= ?", (de,)))
    medidas, limiares = [], []
    for ch in chaves:
        r = an._analisa_metrica(ch, hoje)
        if not r or "valor" not in r:
            continue
        un = (an._spec(ch) or ("", ""))[1]
        item = {"chave": ch, "nome": r["nome"], "unidade": un, "dia": r["dia"], "valor": round(r["valor"], 2), "normal_30d": round(r["normal"], 2),
                "desvio_pct": round(r.get("pct", 0), 1), "z": round(r["z"], 1), "estado": r.get("nivel", "normal"), "sentido_ruim": r["sentido"],
                "dias_seguidos_fora": r.get("seguidos", 0), "raridade": f"{r.get('tao_extremo', '?')} de {r.get('n_base', '?')} dias tão extremo"}
        serie = hs._serie(ch, (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d"))
        if len(serie) >= 4:
            item["media_7d"] = round(statistics.fmean(serie.values()), 2)
        medidas.append(item)
        for chave, cmp, lim, grav, texto in LIMIARES:
            if chave == ch and ((cmp == "<" and r["valor"] < lim) or (cmp == ">" and r["valor"] > lim)):
                limiares.append({"chave": ch, "gravidade": grav, "texto": texto, "valor": round(r["valor"], 1), "dia": r["dia"]})
    # entre dois limiares da mesma medida, fica o mais grave
    pior = {}
    for l in limiares:
        if l["chave"] not in pior or GRAVIDADES.index(l["gravidade"]) > GRAVIDADES.index(pior[l["chave"]]["gravidade"]):
            pior[l["chave"]] = l
    base = an.analisar(hoje)
    medidas.sort(key=lambda m: (m["estado"] == "normal", -abs(m["z"])))
    return {"dia": hoje, "medidas": medidas, "combos": [c["texto"] for c in base["combos"]], "combos_chaves": [c["chave"] for c in base["combos"]],
            "limiares": list(pior.values()), "correlacoes": _correlacoes([m["chave"] for m in medidas], hoje), "contexto": _contexto_clinico(hoje),
            "esforco_recente": base.get("esforco", {}).get("texto", ""), "dados_suspeitos": base.get("suspeitos", []), "sem_dado_recente": base.get("sem_dado_recente", [])}


# ----------------------------------------------------------------------------------------
# 2. Literatura (PubMed)
# ----------------------------------------------------------------------------------------
def _cache_arq() -> Path:
    return hs.banco.DB_DIR / "literatura_cache.json"


def _ler_cache() -> dict:
    try:
        d = json.loads(_cache_arq().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _buscar_pubmed(consulta: str, maximo: int = 3, abrir=None) -> list:
    abrir = abrir or (lambda u: urllib.request.urlopen(u, timeout=20).read(3_000_000))
    q = urllib.parse.quote(consulta + " AND (review[pt] OR systematic[sb] OR humans[mh])")
    ids = json.loads(abrir(f"{PUBMED}esearch.fcgi?db=pubmed&retmode=json&retmax={maximo}&sort=relevance&term={q}"))["esearchresult"].get("idlist", [])
    if not ids:
        return []
    raiz = ET.fromstring(abrir(f"{PUBMED}efetch.fcgi?db=pubmed&retmode=xml&id={','.join(ids)}"))
    saida = []
    for art in raiz.iter("PubmedArticle"):
        pmid = (art.findtext(".//PMID") or "").strip()
        titulo = "".join(art.find(".//ArticleTitle").itertext()).strip() if art.find(".//ArticleTitle") is not None else ""
        resumo = " ".join("".join(t.itertext()).strip() for t in art.findall(".//AbstractText"))
        ano = art.findtext(".//PubDate/Year") or (art.findtext(".//PubDate/MedlineDate") or "")[:4]
        saida.append({"pmid": pmid, "titulo": titulo[:200], "revista": (art.findtext(".//Journal/Title") or "")[:80], "ano": ano, "resumo": re.sub(r"\s+", " ", resumo)[:700]})
    return [s for s in saida if s["pmid"] and s["titulo"]]


def literatura(d: dict, abrir=None, agora: float = None) -> list:
    """Resumos de estudos sobre o que saiu do normal. Só termos genéricos saem da máquina. Sem internet, devolve o que há em cache (ou nada)."""
    if _env("HEIMDALL_SAUDE_LITERATURA", "1") == "0":
        return []
    consultas = []
    for m in d["medidas"]:
        if m["estado"] in ("forte", "moderada") and m["chave"] in BUSCA and BUSCA[m["chave"]] not in consultas:
            consultas.append(BUSCA[m["chave"]])
    for c in d["combos_chaves"]:
        if c in BUSCA_COMBO:
            consultas.append(BUSCA_COMBO[c])
    for l in d["limiares"]:
        if l["chave"] in BUSCA and BUSCA[l["chave"]] not in consultas:
            consultas.append(BUSCA[l["chave"]])
    agora = agora or time.time()
    cache = _ler_cache()
    achados, vistos = [], set()
    mudou = False
    for q in consultas[:4]:
        e = cache.get(q)
        if not e or agora - e.get("t", 0) > CACHE_DIAS * 86400:
            try:
                e = {"t": agora, "itens": _buscar_pubmed(q, abrir=abrir)}
                cache[q] = e
                mudou = True
            except Exception:  # noqa: BLE001 - sem internet ou PubMed fora: segue sem literatura nova
                e = e or {"itens": []}
        for it in e["itens"]:
            if it["pmid"] not in vistos:
                vistos.add(it["pmid"])
                achados.append(it)
    if mudou:
        try:
            _cache_arq().parent.mkdir(parents=True, exist_ok=True)
            _cache_arq().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return achados[:8]


# ----------------------------------------------------------------------------------------
# 3. Modelo
# ----------------------------------------------------------------------------------------
def _prompt(d: dict, lit: list, anterior: dict) -> str:
    medidas = "\n".join(f"- {m['nome']} ({m['chave']}): {m['valor']} {m['unidade']} em {m['dia']}; normal dos 30 dias {m['normal_30d']}; desvio {m['desvio_pct']:+} por cento (z {m['z']}); "
                        f"estado {m['estado']}; {m['raridade']}" + (f"; média de 7 dias {m['media_7d']}" if "media_7d" in m else "") +
                        (f"; {m['dias_seguidos_fora']} dias seguidos fora do normal" if m["dias_seguidos_fora"] >= 2 else "") for m in d["medidas"][:45])
    corr = "\n".join(f"- {c['a']} x {c['b']}: r = {c['r']} em {c['n']} dias" + (" (a primeira medida de ONTEM contra a segunda de hoje)" if c["atraso_dias"] else " (mesmo dia)") for c in d["correlacoes"]) or "nenhuma correlação forte"
    ctx = d["contexto"]
    litt = "\n".join(f"[PMID {x['pmid']}] {x['titulo']} ({x['revista']}, {x['ano']}): {x['resumo']}" for x in lit) or "nenhum estudo disponível (sem internet ou sem busca)"
    return (
        "Você é o analista de saúde pessoal de UM adulto, que usa o Apple Watch e o iPhone. Escreva em português do Brasil, em linguagem simples; o texto é lido por leitor de tela (frases curtas, sem tabelas nem símbolos). "
        "A pessoa sabe que você não é médico e NÃO quer avisos genéricos: quer análise de verdade para decidir sozinha se procura um médico.\n\n"
        "O QUE FAZER:\n"
        "1. Explique o que cada sinal relevante mede, quanto desviou, se é raro e o impacto prático. Nunca devolva só 'valor X, média Y'.\n"
        "2. Correlacione as medidas entre si e com treinos, sintomas, exames e condições da pessoa; diga o que as correlações calculadas sugerem e o que NÃO provam.\n"
        "3. Levante hipóteses (inclusive condições de saúde possíveis) com probabilidade baixa, media ou alta, e o que há a favor e contra cada uma. Considere sempre a hipótese de dado errado (relógio frouxo, dia incompleto).\n"
        "4. Aponte perigos concretos e em que ponto ficaria urgente (limiar ou sintoma), e o que acompanhar nos próximos dias.\n"
        "5. Dê recomendações práticas e priorizadas, com o motivo de cada uma.\n"
        "6. Use os estudos fornecidos quando ajudarem, citando o PMID; diga o que o estudo mostra com as suas palavras. NUNCA cite estudo que não esteja na lista e nunca invente número.\n"
        "Use só os dados abaixo. Se nada importante saiu do normal, diga isso com clareza e aponte o que está bom; não invente alarme.\n\n"
        f"DIA: {d['dia']}\nMEDIDAS (cada uma contra o normal pessoal dos 30 dias anteriores):\n{medidas}\n\n"
        f"CRUZAMENTOS FEITOS PELO CÓDIGO:\n" + ("\n".join("- " + c for c in d["combos"]) or "nenhum padrão combinado") + f"\n\nCORRELAÇÕES (últimos 90 dias):\n{corr}\n\n"
        f"LIMIARES DE REFERÊNCIA CRUZADOS: " + ("; ".join(f"{l['chave']} = {l['valor']} ({l['gravidade']})" for l in d["limiares"]) or "nenhum") + "\n"
        f"ESFORÇO RECENTE: {d['esforco_recente'] or 'sem treino forte recente'}\nCONTEXTO: {json.dumps(ctx, ensure_ascii=False)}\n"
        + ("DADOS SUSPEITOS (ignorados): " + "; ".join(d["dados_suspeitos"]) + "\n" if d["dados_suspeitos"] else "")
        + ("SEM DADO RECENTE: " + ", ".join(d["sem_dado_recente"]) + "\n" if d["sem_dado_recente"] else "")
        + f"\nANÁLISE ANTERIOR (para dizer o que mudou): {anterior.get('panorama', 'primeira análise')[:400]}\n\nESTUDOS (PubMed):\n{litt}\n\n"
        'Responda SOMENTE com JSON: {"panorama": "3 a 5 frases com o quadro geral", "gravidade": "informativo|atencao|importante|urgente", '
        '"sinais": [{"medida": "...", "o_que_e": "...", "o_que_mostra": "...", "impacto": "...", "gravidade": "informativo|atencao|importante|urgente"}], '
        '"correlacoes": [{"texto": "...", "interpretacao": "..."}], "hipoteses": [{"texto": "...", "probabilidade": "baixa|media|alta", "a_favor": "...", "contra": "..."}], '
        '"perigos": [{"texto": "...", "quando_agir": "..."}], "recomendacoes": [{"acao": "...", "porque": "...", "prioridade": "alta|media|baixa"}], '
        '"acompanhar": ["..."], "literatura": [{"pmid": "...", "o_que_diz": "..."}], "mudou": "uma frase sobre o que mudou desde a análise anterior"}')


SISTEMA_NUVEM = "Você é o analista de saúde pessoal descrito pelo usuário. Siga exatamente as instruções e responda SOMENTE com o JSON pedido."
modelo_usado = ""   # quem respondeu a última análise (mostrado no fim do texto)


def _chamar_modelo(prompt: str) -> str:
    """Modelo grande da nuvem (gpt-oss-120b pelo gateway da Cloudflare) quando HEIMDALL_NUVEM=1; se falhar, ou com HEIMDALL_SAUDE_ANALISTA_NUVEM=0, o modelo local."""
    global modelo_usado
    if nuvem.ativo() and _env("HEIMDALL_SAUDE_ANALISTA_NUVEM", "1") != "0":
        try:
            txt = nuvem.chat(SISTEMA_NUVEM, prompt, max_tokens=3000, timeout=300)
            modelo_usado = "gpt-oss-120b (nuvem)"
            return txt
        except RuntimeError:
            pass   # nuvem fora do ar ou limite de gasto: cai para o modelo local
    corpo = json.dumps({"model": LLM_MODELO, "temperature": 0.2, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]}).encode()
    cab = {"Content-Type": "application/json"}
    if os.environ.get("LITELLM_MASTER_KEY"):
        cab["Authorization"] = "Bearer " + os.environ["LITELLM_MASTER_KEY"]
    with _abridor.open(urllib.request.Request(LLM_URL, data=corpo, headers=cab), timeout=420) as resp:
        txt = json.loads(resp.read(4_000_000))["choices"][0]["message"]["content"] or ""
    modelo_usado = f"{LLM_MODELO} (local)"
    return txt


def _txt(v, n=600) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _lista(v) -> list:
    return [x for x in (v if isinstance(v, list) else []) if isinstance(x, dict)]


def conferir(bruto: str, lit: list) -> dict:
    """Lê o JSON do modelo e o deixa em formato seguro: textos curtos, gravidade válida, e só citações de estudos que foram fornecidos."""
    txt = re.sub(r"(?is)<think>.*?</think>", "", bruto or "")
    a, b = txt.find("{"), txt.rfind("}")
    try:
        d = json.loads(txt[a:b + 1]) if a >= 0 < b else {}
    except ValueError:
        return {}
    if not isinstance(d, dict) or not _txt(d.get("panorama")):
        return {}
    grav = lambda x: x if x in GRAVIDADES else "informativo"  # noqa: E731
    pmids = {x["pmid"] for x in lit}
    return {"panorama": _txt(d.get("panorama"), 900), "gravidade": grav(_txt(d.get("gravidade"), 20).lower()),
            "sinais": [{"medida": _txt(s.get("medida"), 80), "o_que_e": _txt(s.get("o_que_e")), "o_que_mostra": _txt(s.get("o_que_mostra")), "impacto": _txt(s.get("impacto")),
                        "gravidade": grav(_txt(s.get("gravidade"), 20).lower())} for s in _lista(d.get("sinais"))[:8]],
            "correlacoes": [{"texto": _txt(c.get("texto")), "interpretacao": _txt(c.get("interpretacao"))} for c in _lista(d.get("correlacoes"))[:5]],
            "hipoteses": [{"texto": _txt(h.get("texto")), "probabilidade": _txt(h.get("probabilidade"), 10).lower(), "a_favor": _txt(h.get("a_favor")), "contra": _txt(h.get("contra"))}
                          for h in _lista(d.get("hipoteses"))[:5]],
            "perigos": [{"texto": _txt(p.get("texto")), "quando_agir": _txt(p.get("quando_agir"))} for p in _lista(d.get("perigos"))[:5]],
            "recomendacoes": [{"acao": _txt(r.get("acao")), "porque": _txt(r.get("porque")), "prioridade": _txt(r.get("prioridade"), 10).lower()} for r in _lista(d.get("recomendacoes"))[:6]],
            "acompanhar": [_txt(x, 200) for x in (d.get("acompanhar") if isinstance(d.get("acompanhar"), list) else [])[:5]],
            "literatura": [{"pmid": _txt(l.get("pmid"), 12), "o_que_diz": _txt(l.get("o_que_diz"))} for l in _lista(d.get("literatura")) if _txt(l.get("pmid"), 12) in pmids][:5],
            "mudou": _txt(d.get("mudou"), 300)}


def sem_modelo(d: dict) -> dict:
    """Análise feita só pelo código: desvios explicados, correlações em palavras e limiares cruzados."""
    fora = [m for m in d["medidas"] if m["estado"] in ("forte", "moderada")]
    sinais = []
    for m in fora[:8]:
        e = an.EXPLICACAO.get(m["chave"])
        sinais.append({"medida": m["nome"], "o_que_e": e[0] if e else "", "o_que_mostra": f"{m['valor']} {m['unidade']}, {abs(m['desvio_pct']):.0f} por cento {'abaixo' if m['valor'] < m['normal_30d'] else 'acima'} do seu normal de {m['normal_30d']} ({m['raridade']}).",
                       "impacto": e[1] if e else "", "gravidade": "atencao" if m["estado"] == "forte" else "informativo"})
    for l in d["limiares"]:
        sinais.append({"medida": l["chave"], "o_que_e": "", "o_que_mostra": l["texto"], "impacto": "", "gravidade": l["gravidade"]})
    grav = max([s["gravidade"] for s in sinais] + ["informativo"], key=GRAVIDADES.index)
    corr = [{"texto": f"{c['a']} e {c['b']} andam {'juntas' if c['r'] > 0 else 'em sentidos opostos'} (r {c['r']}, {c['n']} dias" + (", com a primeira medida um dia antes" if c["atraso_dias"] else "") + ").",
             "interpretacao": "Correlação mostra que variam juntas, não que uma causa a outra."} for c in d["correlacoes"][:4]]
    pan = (f"{len(fora)} medida(s) fora do seu normal. " if fora else "Nenhuma medida saiu muito do seu normal. ") + " ".join(d["combos"][:2]) + " (Análise feita só pelo código: o modelo não respondeu.)"
    return {"panorama": pan.strip(), "gravidade": grav, "sinais": sinais, "correlacoes": corr, "hipoteses": [], "perigos": [], "recomendacoes": [], "acompanhar": [], "literatura": [], "mudou": ""}


# ----------------------------------------------------------------------------------------
# 4. Texto, gravação e aviso
# ----------------------------------------------------------------------------------------
ROT_G = {"informativo": "informativo", "atencao": "atenção", "importante": "importante", "urgente": "urgente"}


def renderizar(r: dict, d: dict, lit: list) -> str:
    L = [f"Análise de saúde de {hs._br(d['dia'])}. Gravidade geral: {ROT_G[r['gravidade']]}.", "", r["panorama"]]
    if r.get("mudou"):
        L += ["", "O que mudou: " + r["mudou"]]
    for l in d["limiares"]:
        L += ["", f"Atenção ao limite: {l['texto']}"]
    if r["sinais"]:
        L += ["", "Sinais, um por um:"]
        for i, s in enumerate(r["sinais"], 1):
            L.append(f"{i}. {s['medida']} ({ROT_G[s['gravidade']]}). " + " ".join(x for x in (s["o_que_e"], s["o_que_mostra"], ("Impacto: " + s["impacto"]) if s["impacto"] else "") if x))
    if r["correlacoes"]:
        L += ["", "Como as medidas se relacionam:"] + [f"{i}. {c['texto']} {c['interpretacao']}".strip() for i, c in enumerate(r["correlacoes"], 1)]
    if r["hipoteses"]:
        L += ["", "Hipóteses (não são diagnóstico):"]
        for i, h in enumerate(r["hipoteses"], 1):
            L.append(f"{i}. {h['texto']} Probabilidade {h['probabilidade'] or 'não informada'}. A favor: {h['a_favor'] or 'não informado'}. Contra: {h['contra'] or 'não informado'}.")
    if r["perigos"]:
        L += ["", "Perigos e quando agir:"] + [f"{i}. {p['texto']} Quando agir: {p['quando_agir'] or 'não informado'}." for i, p in enumerate(r["perigos"], 1)]
    if r["recomendacoes"]:
        L += ["", "Recomendações:"] + [f"{i}. {x['acao']} Por quê: {x['porque']}" + (f" (prioridade {x['prioridade']})" if x["prioridade"] else "") for i, x in enumerate(r["recomendacoes"], 1)]
    if r["acompanhar"]:
        L += ["", "O que acompanhar nos próximos dias:"] + [f"{i}. {x}" for i, x in enumerate(r["acompanhar"], 1)]
    if r["literatura"]:
        por = {x["pmid"]: x for x in lit}
        L += ["", "Estudos consultados (PubMed):"] + [f"{i}. {por[x['pmid']]['titulo']} ({por[x['pmid']]['revista']}, {por[x['pmid']]['ano']}), PMID {x['pmid']}. {x['o_que_diz']}" for i, x in enumerate(r["literatura"], 1)]
    L += ["", "A decisão de procurar um médico é sua; esta análise é feita pelo Heimdall a partir dos seus dados e de resumos de estudos, e pode errar."
          + (f" Modelo: {modelo_usado}." if modelo_usado and r.get("_modelo") else "")]
    return "\n".join(L)


def resumo_curto(r: dict, d: dict) -> str:
    """Texto do aviso (Mac e iPhone): o quadro geral, o limite cruzado, a hipótese principal e as recomendações mais importantes."""
    p = [r["panorama"]]
    p += [l["texto"] for l in d["limiares"][:1]]
    if r["hipoteses"]:
        p.append("Hipótese principal: " + r["hipoteses"][0]["texto"] + f" (probabilidade {r['hipoteses'][0]['probabilidade'] or 'não informada'}).")
    if r["recomendacoes"]:
        p.append("O que fazer: " + " ".join(f"{i}. {x['acao'].rstrip('.')}." for i, x in enumerate(r["recomendacoes"][:3], 1)))
    p.append("Análise completa na aba Avisos do Heimdall Health.")
    return an._cortar(" ".join(p), 1600)


def _estado_arq() -> Path:
    return hs.banco.DB_DIR / "analista_saude_estado.json"


def _ler_estado() -> dict:
    try:
        d = json.loads(_estado_arq().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def analisar(hoje: str = None, usar_modelo: bool = True, usar_literatura: bool = True, modelo=None, abrir=None) -> dict:
    d = dossie(hoje)
    anterior = _ler_estado().get("ultima", {})
    lit = literatura(d, abrir=abrir) if usar_literatura else []
    r = {}
    if usar_modelo and d["medidas"]:
        try:
            r = conferir((modelo or _chamar_modelo)(_prompt(d, lit, anterior)), lit)
            if r and not modelo:
                r["_modelo"] = True
        except Exception:  # noqa: BLE001 - modelo fora do ar: segue com a análise do código
            r = {}
    com_modelo = bool(r)
    if not r:
        r = sem_modelo(d)
    # o código nunca deixa a gravidade ficar abaixo do que um limiar de referência cruzado exige
    for l in d["limiares"]:
        if GRAVIDADES.index(l["gravidade"]) > GRAVIDADES.index(r["gravidade"]):
            r["gravidade"] = l["gravidade"]
    return {"dia": d["dia"], "dossie": d, "literatura": lit, "resultado": r, "com_modelo": com_modelo, "texto": renderizar(r, d, lit), "curto": resumo_curto(r, d)}


def rodar(agora: datetime = None, forcar: bool = False, avisar_mac=None, **kw) -> dict:
    """Roda a análise, grava na aba Avisos do Heimdall Health e avisa só se a gravidade pede (ou no domingo). Devolve {} se ainda não é hora."""
    if _env("HEIMDALL_SAUDE_ANALISTA", "1") == "0" and not forcar:
        return {}
    agora = agora or datetime.now()
    est = _ler_estado()
    if not forcar and est.get("quando") and (agora - datetime.strptime(est["quando"], "%Y-%m-%dT%H:%M:%S")).total_seconds() / 3600 < INTERVALO_HORAS:
        return {}
    a = analisar(agora.strftime("%Y-%m-%d"), **kw)
    r = a["resultado"]
    import heimdall_avisos as avisos
    novo = avisos.do_servico("saude").gravar(f"Análise de saúde {hs._br(a['dia'])}", a["texto"])
    assinatura = hashlib.sha1(json.dumps([r["gravidade"], [s["medida"] for s in r["sinais"] if s["gravidade"] != "informativo"]], ensure_ascii=False).encode()).hexdigest()[:10]
    mudou = assinatura != est.get("assinatura")
    domingo = agora.weekday() == 6
    avisar = (r["gravidade"] in ("importante", "urgente") or (r["gravidade"] == "atencao" and mudou) or domingo) and bool(a["dossie"]["medidas"])
    if avisar:
        import heimdall_avisos_mac as mac
        titulo = {"urgente": "Saúde, urgente: ", "importante": "Saúde, importante: ", "atencao": "Saúde, atenção: "}.get(r["gravidade"], "Saúde: ") + "análise de " + hs._br(a["dia"])
        (avisar_mac or mac.publicar)({"title": titulo, "body": a["curto"], "group": "saude", "level": "timeSensitive" if r["gravidade"] in ("importante", "urgente") else "active"})
    try:
        _estado_arq().parent.mkdir(parents=True, exist_ok=True)
        _estado_arq().write_text(json.dumps({"quando": agora.strftime("%Y-%m-%dT%H:%M:%S"), "assinatura": assinatura, "ultima": {"panorama": r["panorama"], "dia": a["dia"]}}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    a.update(aviso=novo, avisou=avisar)
    return a


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Análise de saúde por modelo: todas as métricas, correlações, hipóteses, perigos e recomendações")
    ap.add_argument("--sem-modelo", action="store_true", help="só a análise do código")
    ap.add_argument("--sem-literatura", action="store_true", help="não consulta o PubMed")
    ap.add_argument("--gravar", action="store_true", help="também grava na aba Avisos do Heimdall Health e avisa se for o caso")
    a = ap.parse_args()
    hs._garantir_banco()
    kw = {"usar_modelo": not a.sem_modelo, "usar_literatura": not a.sem_literatura}
    if a.gravar:
        r = rodar(forcar=True, **kw)
        print(r["texto"] + f"\n\n(Gravado na aba Avisos, aviso {r['aviso']}; avisou: {'sim' if r['avisou'] else 'não'}.)")
    else:
        r = analisar(**kw)
        print(r["texto"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
