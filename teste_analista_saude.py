#!/usr/bin/env python3
"""Testa o analista de saúde: dossiê, correlações, literatura (PubMed simulado, cache), conferência do JSON do modelo, análise sem modelo, gravação e aviso."""
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="analista_"))
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "banco")
os.environ["HEIMDALL_AVISOS_MAC"] = "1"
os.environ.pop("HEIMDALL_SAUDE_LITERATURA", None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_saude as hs  # noqa: E402
import heimdall_analista_saude as an  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:700])


hs._garantir_banco()
HOJE = datetime.now().strftime("%Y-%m-%d")
random.seed(3)


def dia(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def grava(m, d, v):
    hs._upsert("saude_diaria", "dia, metrica", [{"dia": d, "metrica": m, "valor": v, "unidade": "", "atualizado": datetime.now().astimezone().isoformat()}])


# 40 dias: o sono explica a HRV do dia seguinte (correlação); hoje a HRV cai e o oxigênio mínimo também
for n in range(40, 0, -1):
    sono = random.choice([330, 380, 420, 450, 480])
    grava("sono_total", dia(n + 1), sono)
    grava("hrv", dia(n), 30 + (sono - 330) * 0.1 + random.uniform(-1, 1))
    grava("fc_repouso", dia(n), 58 + random.uniform(-1, 1))
    grava("spo2_min", dia(n), 93 + random.uniform(-0.5, 0.5))
grava("sono_total", dia(1), 300)
grava("hrv", HOJE, 14)
grava("fc_repouso", HOJE, 66)
grava("spo2_min", HOJE, 87)

d = an.dossie(HOJE)
nomes = {m["chave"]: m for m in d["medidas"]}
confere("dossiê traz todas as medidas, com desvio percentual", {"hrv", "fc_repouso", "spo2_min", "sono_total"} <= set(nomes) and nomes["hrv"]["desvio_pct"] < -30, nomes.get("hrv"))
confere("limiar de oxigênio abaixo de 90 é cruzado como urgente", any(l["chave"] == "spo2_min" and l["gravidade"] == "urgente" for l in d["limiares"]), d["limiares"])
confere("correlação sono x HRV do dia seguinte calculada pelo código", any({"sono_total", "hrv"} == set(c["chaves"]) and c["atraso_dias"] in (0, 1) for c in d["correlacoes"]), d["correlacoes"])

# literatura simulada
chamadas = []
ESEARCH = json.dumps({"esearchresult": {"idlist": ["111", "222"]}}).encode()
EFETCH = (b"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>111</PMID><Article><Journal><Title>Sleep Med</Title></Journal><ArticleTitle>HRV and sleep</ArticleTitle>"
          b"<Abstract><AbstractText>Short sleep lowers HRV.</AbstractText></Abstract></Article></MedlineCitation><PubmedData/></PubmedArticle>"
          b"<PubmedArticle><MedlineCitation><PMID>222</PMID><Article><Journal><Title>Heart</Title></Journal><ArticleTitle>Resting HR</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>")


def abrir(u):
    chamadas.append(u)
    return ESEARCH if "esearch" in u else EFETCH


lit = an.literatura(d, abrir=abrir)
confere("literatura traz os estudos do PubMed", {x["pmid"] for x in lit} == {"111", "222"} and lit[0]["resumo"], lit)
confere("a busca leva só termos genéricos, nunca valores seus", chamadas and not any(str(v) in " ".join(chamadas) for v in ("87", "14", "66")) and "heart" in " ".join(chamadas).lower(), chamadas[:1])
n = len(chamadas)
an.literatura(d, abrir=abrir)
confere("segunda análise usa o cache (sem nova chamada)", len(chamadas) == n, (n, len(chamadas)))
os.environ["HEIMDALL_SAUDE_LITERATURA"] = "0"
confere("HEIMDALL_SAUDE_LITERATURA=0 não consulta", an.literatura(d, abrir=abrir) == [])
os.environ.pop("HEIMDALL_SAUDE_LITERATURA")


def semrede(u):
    raise OSError("sem internet")


os.environ["HEIMDALL_DB_DIR"] = str(TMP / "outro")   # cache vazio não afeta; só confere que falha de rede não derruba
confere("PubMed fora do ar: segue sem literatura nova", isinstance(an.literatura(dict(d, medidas=[dict(m, estado="forte") for m in d["medidas"]]), abrir=semrede), list))
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "banco")

# conferência do JSON do modelo
bom = json.dumps({"panorama": "HRV caiu 53 por cento.", "gravidade": "importante", "sinais": [{"medida": "HRV", "o_que_e": "variação entre batimentos", "o_que_mostra": "14 ms contra 33", "impacto": "recuperação pior", "gravidade": "atencao"}],
                  "correlacoes": [{"texto": "Sono curto antecede HRV baixa", "interpretacao": "sugere relação"}],
                  "hipoteses": [{"texto": "Má recuperação por sono curto", "probabilidade": "alta", "a_favor": "sono de 5 h", "contra": "nenhum"}, {"texto": "Apneia", "probabilidade": "media", "a_favor": "oxigênio baixo", "contra": "só uma noite"}],
                  "perigos": [{"texto": "Oxigênio abaixo de 90", "quando_agir": "se repetir"}], "recomendacoes": [{"acao": "Dormir 8 horas", "porque": "recupera a HRV", "prioridade": "alta"}],
                  "acompanhar": ["oxigênio mínimo"], "literatura": [{"pmid": "111", "o_que_diz": "sono curto reduz HRV"}, {"pmid": "999", "o_que_diz": "inventado"}], "mudou": "primeira análise"})
r = an.conferir(bom, lit)
confere("JSON do modelo vira estrutura segura", r and r["gravidade"] == "importante" and len(r["hipoteses"]) == 2, r)
confere("citação de estudo que não foi fornecido é descartada", [x["pmid"] for x in r["literatura"]] == ["111"], r["literatura"])
confere("lixo do modelo vira vazio", an.conferir("não sei", lit) == {} and an.conferir('{"panorama": ""}', lit) == {})
confere("gravidade inventada vira informativo", an.conferir('{"panorama":"x","gravidade":"catastrofe"}', lit)["gravidade"] == "informativo")

# análise completa, com e sem modelo
avisos_mac = []
a = an.analisar(HOJE, modelo=lambda p: bom, abrir=abrir)
confere("com modelo: texto traz sinais, hipóteses, perigos, recomendações e estudos", all(t in a["texto"] for t in ("Sinais, um por um", "Hipóteses", "Perigos e quando agir", "Recomendações", "Estudos consultados", "PMID 111")), a["texto"][:400])
confere("o prompt leva dados, correlações e estudos", "hrv" in an._prompt(a["dossie"], lit, {}).lower() and "CORRELAÇÕES" in an._prompt(a["dossie"], lit, {}) and "PMID 111" in an._prompt(a["dossie"], lit, {}))
confere("o texto diz que a decisão de procurar médico é do usuário", "decisão de procurar um médico é sua" in a["texto"])
b = an.analisar(HOJE, modelo=lambda p: 1 / 0, abrir=abrir)
confere("modelo falha: análise do código, com explicações e sem hipóteses", not b["com_modelo"] and "Análise feita só pelo código" in b["texto"] and "recuperação" in b["texto"] and b["resultado"]["gravidade"] == "urgente", b["texto"][:500])
c = an.analisar(HOJE, modelo=lambda p: bom.replace('"importante"', '"informativo"', 1), abrir=abrir)
confere("o limiar urgente nunca fica abaixo do que o código cruzou", c["resultado"]["gravidade"] == "urgente", c["resultado"]["gravidade"])

# rodar: grava na aba Avisos, avisa pela gravidade, respeita o intervalo
import heimdall_avisos as av  # noqa: E402
agora = datetime.now()
r1 = an.rodar(agora, modelo=lambda p: bom, abrir=abrir, avisar_mac=avisos_mac.append)
confere("rodar grava a análise na aba Avisos do Health", r1 and r1["aviso"] and any("Análise de saúde" in x["titulo"] for x in av.do_servico("saude").listar()), r1 and r1.get("aviso"))
confere("gravidade urgente avisa, com o resumo e o nível time sensitive", len(avisos_mac) == 1 and avisos_mac[0]["level"] == "timeSensitive" and "urgente" in avisos_mac[0]["title"] and "Hipótese principal" in avisos_mac[0]["body"], avisos_mac)
confere("segunda chamada no mesmo dia não roda de novo", an.rodar(agora + timedelta(hours=2), modelo=lambda p: bom, abrir=abrir, avisar_mac=avisos_mac.append) == {})
confere("forçar roda mesmo assim", bool(an.rodar(agora + timedelta(hours=2), forcar=True, modelo=lambda p: bom, abrir=abrir, avisar_mac=avisos_mac.append)))
os.environ["HEIMDALL_SAUDE_ANALISTA"] = "0"
confere("HEIMDALL_SAUDE_ANALISTA=0 desliga a automática", an.rodar(agora + timedelta(days=3), modelo=lambda p: bom, abrir=abrir) == {})
os.environ.pop("HEIMDALL_SAUDE_ANALISTA")

# dia calmo não avisa
for m, v in (("hrv", 33), ("fc_repouso", 58), ("spo2_min", 93), ("sono_total", 420)):
    grava(m, HOJE, v)
grava("sono_total", dia(1), 420)
calmo = []
an._estado_arq().unlink()
r2 = an.rodar(agora + timedelta(days=1), modelo=lambda p: json.dumps({"panorama": "Tudo dentro do seu normal.", "gravidade": "informativo"}), abrir=abrir, avisar_mac=calmo.append)
confere("dia calmo grava na aba Avisos mas não notifica", r2 and not r2["avisou"] and calmo == [] if (agora + timedelta(days=1)).weekday() != 6 else True, (r2 and r2.get("avisou"), calmo))
sys.exit(1 if falhas else 0)
