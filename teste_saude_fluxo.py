#!/usr/bin/env python3
"""Testa os nós de código do fluxo de saúde (n8n_flows_avancados/15-saude.json) rodando-os com Node, sem n8n:
sinais vitais fora do normal ao mesmo tempo, resumo refeito quando o sono chega depois das 5h50, entrega no grupo certo e triagem."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

NODE = shutil.which("node")
if not NODE:
    print("pulado: o Node não está instalado nesta máquina.")
    sys.exit(0)

FLUXO = json.loads((Path(__file__).resolve().parent / "n8n_flows_avancados" / "15-saude.json").read_text(encoding="utf-8"))
NOS = {n["name"]: n for n in FLUXO["nodes"]}
falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


# Roda o código de um nó com o armazenamento (static data), a entrada e a hora simulados. Devolve a saída e o armazenamento depois.
DRIVER = r"""
const [codigo, estado, entrada, anterior, hora] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const mk = dt => ({ toFormat: f => f === 'H' ? String(dt.getUTCHours()) : dt.toISOString().slice(0, 10), minus: o => mk(new Date(dt.getTime() - o.days * 864e5)) });
const agora = mk(new Date('2026-11-14T' + String(hora).padStart(2, '0') + ':00:00Z'));
const sd = estado;
const f = new Function('$getWorkflowStaticData', '$input', '$now', '$', codigo);
const saida = f(() => sd, { first: () => ({ json: entrada }) }, agora, () => ({ first: () => ({ json: anterior }) }));
console.log(JSON.stringify({ saida, sd }));
"""


def rodar(codigo, estado, entrada=None, anterior=None, hora=5):
    r = subprocess.run([NODE, "-e", DRIVER], input=json.dumps([codigo, estado, entrada or {}, anterior or {}, hora]), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return json.loads(r.stdout)


def avaliar(expressao, anterior, hora):
    """Avalia o corpo de uma requisição ('={{ ... }}') com $('Preparar') e $('Montar') simulados."""
    corpo = expressao.strip()[3:-2]
    js = ("const mk = dt => ({ toFormat: f => String(dt.getUTCHours()) });\n"
          f"const $now = mk(new Date('2026-11-14T{hora:02d}:00:00Z'));\n"
          f"const $ = n => ({{ first: () => ({{ json: n === 'Preparar' ? {json.dumps(anterior)} : {{ linha: 'texto' }} }}) }});\n"
          f"console.log({corpo});")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return json.loads(r.stdout)


def codigo(nome):
    return NOS[nome]["parameters"]["jsCode"]


# todos os nós de código compilam
for nome, n in NOS.items():
    js = n["parameters"].get("jsCode")
    if js:
        try:
            subprocess.run([NODE, "-e", "new Function('$getWorkflowStaticData','$input','$now','$', require('fs').readFileSync(0,'utf8'))"], input=js, capture_output=True, text=True, timeout=30, check=True)
            ok = True
        except subprocess.CalledProcessError as ex:
            ok = False
            print(ex.stderr[-300:])
        confere(f"nó '{nome}' compila", ok)

# histórico de 30 dias, estável, e a manhã de hoje (2026-11-14)
dias = {}
for i in range(30):
    d = f"2026-{10 if i < 17 else 11}-{(15 + i) if i < 17 else (i - 16):02d}"
    k = i % 5
    dias[d] = {"sono_total": 400 + (k - 2) * 20, "fc_repouso": 64 + (k - 2), "resp": 15.5 + (k - 2) * 0.2, "spo2": 95.5 + (k % 2) * 0.5 - 0.25, "hrv": 38 + (k - 2) * 2, "passos": 6000, "energia": 400}
assert "2026-11-13" in dias and "2026-10-15" in dias and len(dias) == 30, sorted(dias)[:2] + sorted(dias)[-2:]
MANHA = {"sono_total": 215, "fc_repouso": 58, "resp": 14.9, "spo2": 94, "hrv": 20.7}


def estado(hoje):
    return {"saude": {"dias": {**json.loads(json.dumps(dias)), "2026-11-14": dict(hoje)}, "recebido": 0, "modo": {}, "un": {}}}


r = rodar(codigo("Preparar"), estado(MANHA))
rel = r["saida"][0]["json"]["rel"]
vit = [x for x in rel if x.startswith("Vários sinais vitais")]
confere("duas medidas da noite fora do normal viram um aviso de sinais vitais", len(vit) == 1 and vit[0].endswith("[MUITO RELEVANTE]"), rel)
confere("o aviso cita pulso em repouso e duração do sono, e não o oxigênio (variação pequena)", vit and "frequência cardíaca em repouso abaixo" in vit[0] and "duração do sono abaixo" in vit[0] and "oxigênio" not in vit[0], vit)

so_um = dict(MANHA, sono_total=400, spo2=95.5)
r = rodar(codigo("Preparar"), estado(so_um))
confere("só uma medida fora do normal não gera o aviso conjunto", not any(x.startswith("Vários sinais vitais") for x in r["saida"][0]["json"]["rel"]), r["saida"][0]["json"]["rel"])

# resumo sem o sono da noite: marca; com o sono: limpa
sem_sono = {k: v for k, v in MANHA.items() if k != "sono_total"}
e = estado(sem_sono)
r = rodar(codigo("Preparar"), e)
confere("resumo sem o sono da noite marca semSonoEm", r["sd"]["saude"].get("semSonoEm") == "2026-11-14" and r["saida"][0]["json"]["atrasado"] is False, r["sd"]["saude"].get("semSonoEm"))
r2 = rodar(codigo("Preparar"), estado(MANHA))
confere("resumo com o sono da noite não marca nada", r2["sd"]["saude"].get("semSonoEm") == "", r2["sd"]["saude"].get("semSonoEm"))

# nó 'Resumo atrasado?'
ATR = codigo("Resumo atrasado?")
e = estado(MANHA)
e["saude"]["semSonoEm"] = "2026-11-14"
r = rodar(ATR, e)
confere("sono e sinais chegaram: dispara o resumo atrasado e limpa a marca", r["saida"] == [{"json": {"atrasado": True}}] and r["sd"]["saude"]["semSonoEm"] == "", r["saida"])
r = rodar(ATR, r["sd"])
confere("não dispara uma segunda vez no mesmo dia", r["saida"] == [], r["saida"])
e = estado({"sono_total": 215})
e["saude"]["semSonoEm"] = "2026-11-14"
r = rodar(ATR, e)
confere("só o sono, sem nenhum sinal da noite: espera", r["saida"] == [] and r["sd"]["saude"]["semSonoEm"] == "2026-11-14", r["saida"])
e = estado(sem_sono)
e["saude"]["semSonoEm"] = "2026-11-14"
confere("sem o sono ainda: espera", rodar(ATR, e)["saida"] == [], "")
e = estado(MANHA)
confere("resumo das 5h50 já tinha o sono (sem marca): não dispara", rodar(ATR, e)["saida"] == [], "")
e = estado(MANHA)
e["saude"]["semSonoEm"] = "2026-11-13"
confere("marca de outro dia não dispara", rodar(ATR, e)["saida"] == [], "")

# o resumo refeito não apaga a marca nem se repete
e = estado(MANHA)
e["saude"]["semSonoEm"] = "2026-11-14"
r = rodar(codigo("Preparar"), e, entrada={"atrasado": True})
confere("Preparar com atrasado=true devolve o indicador e não mexe na marca", r["saida"][0]["json"]["atrasado"] is True and r["sd"]["saude"]["semSonoEm"] == "2026-11-14", r["sd"]["saude"].get("semSonoEm"))

# entrega: grupo certo conforme a hora
ENV = NOS["Enviar ao resumo"]["parameters"]["jsonBody"]
c = avaliar(ENV, {"atrasado": False}, 5)
confere("resumo normal vai ao grupo das 6h com o título de sempre", c["slot"] == "manha1" and c["titulo"] == "Saúde", c)
for hora, slot in ((7, "manha2"), (9, "meio"), (12, "direto"), (21, "direto")):
    c = avaliar(ENV, {"atrasado": True}, hora)
    confere(f"resumo atrasado às {hora}h vai ao grupo '{slot}' e com título distinto", c["slot"] == slot and c["titulo"] == "Saúde (atualizado)" and c["nivel"] == "passive", c)

# triagem
TRI = codigo("Itens de triagem")
P = {"ymd": "2026-11-14", "rel": ["Vários sinais vitais fora do seu intervalo típico ao mesmo tempo, como no app Sinais Vitais da Apple: oxigênio no sangue abaixo do normal (93 %); duração do sono abaixo do normal (215 min) [MUITO RELEVANTE]"]}
r = rodar(TRI, {}, anterior=P)
confere("aviso conjunto vira item 'alto', nunca 'crítico' só por citar oxigênio", len(r["saida"]) == 1 and r["saida"][0]["json"]["nivel"] == "alto", r["saida"])
P = {"ymd": "2026-11-14", "rel": ["Oxigênio no sangue: hoje 89 %, média de 30 dias 95 % (-6%) [MUITO RELEVANTE]"]}
r = rodar(TRI, {}, anterior=P)
confere("oxigênio muito baixo continua 'crítico'", r["saida"][0]["json"]["nivel"] == "critico", r["saida"])

# ligações
lig = FLUXO["connections"]
alvos = [x["node"] for x in lig["Guardar dados"]["main"][0]]
confere("ligações: Guardar dados -> Gravar no banco e Resumo atrasado?; Resumo atrasado? -> Preparar",
        "Gravar no banco" in alvos and "Resumo atrasado?" in alvos and [x["node"] for x in lig["Resumo atrasado?"]["main"][0]] == ["Preparar"], alvos)

print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
