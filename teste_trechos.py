#!/usr/bin/env python3
"""Teste da leitura dos trechos de livros (ingest_docs.chunk_text + o código real do fluxo 13-estudo, rodado no Node).

    python3 teste_trechos.py

Confere que o trecho montado para estudo não repete frases, não corta palavra no meio e começa e termina em frase inteira,
tanto com trechos novos quanto com trechos antigos (indexados antes da correção, com a sobreposição repetida).
"""
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.modules.setdefault("requests", types.ModuleType("requests"))
sys.modules.setdefault("heimdall_tools", types.SimpleNamespace(QDRANT_COLLECTION="x", EMBED_MODEL="x", _embed=lambda t: [[0.0]]))
import ingest_docs as ig  # noqa: E402

ok_n, falhas = 0, []


def confere(nome, cond, detalhe=""):
    global ok_n
    if cond:
        ok_n += 1
    else:
        falhas.append(nome)
        print("FALHOU:", nome, detalhe[:300])


def chunk_antigo(text, size, overlap):  # cópia do chunk_text de antes da correção
    paras = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    pieces = []
    for p in paras:
        while len(p) > size:
            pieces.append(p[:size])
            p = p[size - overlap:]
        pieces.append(p)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks


def frase(i):
    return f"Esta é a frase {i:03d} do livro, com palavras suficientes para parecer um trecho de verdade e passar de cem letras."


gigante = " ".join(frase(i) for i in range(0, 70))                    # um parágrafo enorme, sem linha em branco (PDF)
normais = "\n\n".join(" ".join(frase(i) for i in range(70 + 4 * k, 74 + 4 * k)) for k in range(20))
TEXTO = gigante + "\n\n" + normais

JS = json.loads((AQUI / "n8n_flows_avancados" / "13-estudo.json").read_text(encoding="utf-8"))
CODIGO = next(n["parameters"]["jsCode"] for n in JS["nodes"] if n["name"] == "Montar leitura")
HARNESS = """
const dados = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const $ = () => ({ all: () => [{ json: { tema: 't', livro: 'L', trecho: dados[0] } }] });
const $input = { all: () => [{ json: { result: { points: dados.map((t, i) => ({ payload: { chunk: i, text: t } })) } } }] };
const f = new Function('$', '$input', %s);
console.log(JSON.stringify(f($, $input)[0].json.leitura));
""" % json.dumps(CODIGO)
NODE = shutil.which("node")


def leitura(trechos):
    r = subprocess.run([NODE, "-e", HARNESS], input=json.dumps(trechos), capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError(r.stderr[:500])
    return json.loads(r.stdout)


def checa(rotulo, trechos):
    t = leitura(trechos)
    ids = [int(x) for x in re.findall(r"frase (\d{3}) do livro", t)]
    confere(f"{rotulo}: nenhuma frase repetida", len(ids) == len(set(ids)), str(ids))
    confere(f"{rotulo}: frases em sequência", ids == list(range(ids[0], ids[0] + len(ids))) if ids else False, str(ids))
    confere(f"{rotulo}: termina em frase inteira", t[-1] in ".!?…", t[-60:])
    confere(f"{rotulo}: começa em frase inteira", t[0].isupper(), t[:60])
    confere(f"{rotulo}: sem palavra cortada", not re.search(r"\b(fra|livr|palavr|suficient)\s*$", t) and "\n\n" not in t.split("Esta é a frase")[1][:200] if len(ids) > 1 else True)
    return t, ids


# --- trechos novos ---
novos = ig.chunk_text(TEXTO, 1000, 150)
confere("novo: todo trecho cabe no tamanho", all(len(c) <= 1000 for c in novos), str(max(map(len, novos))))
confere("novo: nenhum trecho começa no meio de palavra", all(re.match(r"^(Esta é)", c) for c in novos))
confere("novo: sobreposição é o fim do anterior", all(any(novos[i].endswith(novos[i + 1][:k]) for k in range(20, 151)) for i in range(len(novos) - 1)))
confere("novo: nenhuma frase se perde", {f"{i:03d}" for i in range(0, 150)} >= set() and all(f"frase {i:03d} " in " ".join(novos) for i in range(0, 150)))
if NODE:
    for ini in (0, 2, 5, len(novos) - 5):
        checa(f"novo a partir do trecho {ini}", novos[ini:ini + 5])
    # --- trechos antigos: mostra o defeito e confere que o fluxo novo o corrige ---
    antigos = chunk_antigo(TEXTO, 1000, 150)
    com_dup = sum(1 for i in range(len(antigos) - 1) if antigos[i + 1][:150] and antigos[i + 1].count(antigos[i + 1][:150]) > 1)
    confere("antigo: o defeito existia nos dados antigos", com_dup > 0)
    for ini in (0, 1, 3, 6):
        checa(f"antigo a partir do trecho {ini}", antigos[ini:ini + 5])
    # --- limpeza ---
    t = leitura(["O exte-\nrior era claro e bonito.\nSegunda linha do mesmo parágrafo.\n\nOutro parágrafo vem aqui."])
    confere("hifenização de fim de linha é desfeita", "exterior" in t and "exte-" not in t, t)
    confere("quebra simples vira espaço", "bonito. Segunda linha" in t, t)
else:
    print("Node não encontrado: parte do fluxo pulada.")

# --- chunker: casos de borda ---
confere("texto vazio", ig.chunk_text("", 1000, 150) == [])
confere("texto curto vira um trecho", ig.chunk_text("Uma frase só.", 1000, 150) == ["Uma frase só."])
palavra_enorme = "x" * 2500
confere("palavra sem espaço maior que o trecho ainda termina", "".join(ig.chunk_text(palavra_enorme, 1000, 150)).count("x") >= 2500)

print(f"\n{ok_n} verificações passaram, {len(falhas)} falharam.")
sys.exit(1 if falhas else 0)
