#!/usr/bin/env python3
"""Testa os dados das abas Exercícios e Progresso do Learn: gabarito só depois de concluir, filtro dos erros, dias seguidos e acertos por tipo."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import studio_learn_dados as d  # noqa: E402
import studio_learn_licoes as li  # noqa: E402
import studio_learn_painel as pa  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


confere("sem lições não há exercícios nem progresso", pa.exercicios() == [] and pa.progresso()["pastas"] == [])

d.criar_pasta("Inglês", "", "Idiomas", "inglês")
(TMP / "knowledge" / "ingles" / "a.md").write_text("\n\n".join(("Frase %d do material sobre o verbo sentar e correr no parque. " % i) * 6 for i in range(8)), encoding="utf-8")
BOA = {"titulo": "O verbo sit", "explicacao": "Explicação.", "trecho_estudo": "The cat sits.",
       "exercicios": [{"tipo": "alternativas", "enunciado": "Como se diz senta?", "opcoes": ["sits", "run", "park"], "correta": 0},
                      {"tipo": "texto", "enunciado": "Traduza: o cachorro corre", "gabarito": "The dog runs."},
                      {"tipo": "alternativas", "enunciado": "Qual é o lugar?", "opcoes": ["park", "sits", "the"], "correta": 0}]}
i = li.nova_licao("ingles")
li.gerar(i, lambda *a, **k: json.dumps(BOA))
ex = pa.exercicios()
confere("lição aberta lista os exercícios sem gabarito", len(ex) == 3 and all(x["gabarito"] == "" and x["resultado"] == "sem resposta" for x in ex))
li.enviar_respostas(i, {0: "0", 1: "The dogs run", 2: "1"})
confere("antes da correção o gabarito continua escondido", all(x["gabarito"] == "" for x in pa.exercicios()))
li.corrigir_pendentes(i, lambda *a, **k: "PARCIAL. Faltou a terceira pessoa.")
ex = pa.exercicios()
res = {x["numero"]: x["resultado"] for x in ex}
confere("resultados certo, parcial e errado", res == {1: "certo", 2: "parcial", 3: "errado"}, res)
confere("lição concluída mostra o gabarito", {x["numero"]: x["gabarito"] for x in ex} == {1: "sits", 2: "The dog runs.", 3: "park"})
confere("filtro dos erros traz só parcial e errado", [x["numero"] for x in pa.exercicios("", True)] == [2, 3])
confere("filtro por pasta", len(pa.exercicios("ingles")) == 3 and pa.exercicios("outra") == [])
pr = pa.progresso()
p = pr["pastas"][0]
confere("progresso por pasta", p["nome"] == "Inglês" and p["licoes"] == 1 and p["concluidas"] == 1 and p["media"] is not None)
confere("acerto por tipo (alternativas 50%, texto 50%)", abs(pr["por_tipo"]["alternativas"]["acerto"] - 0.5) < 1e-9 and abs(pr["por_tipo"]["texto"]["acerto"] - 0.5) < 1e-9, pr["por_tipo"])
confere("dia de hoje conta na sequência", pr["seguidos"] == 1 and pr["dias_com_estudo"] == 1)
h = date(2026, 11, 23)
confere("sequência: três dias seguidos terminando hoje", pa.sequencia_de_dias(["2026-11-21 08:00:00", "2026-11-22", "2026-11-23 23:59:59"], h) == (3, 3))
confere("sequência continua se o último dia foi ontem", pa.sequencia_de_dias(["2026-11-21", "2026-11-22"], h) == (2, 2))
confere("sequência quebra com um dia de intervalo", pa.sequencia_de_dias(["2026-11-19", "2026-11-23"], h) == (1, 2))
confere("sequência zera se parou há dias, datas inválidas são ignoradas", pa.sequencia_de_dias(["2026-11-10", "lixo"], h) == (0, 1))
confere("sem datas", pa.sequencia_de_dias([], h) == (0, 0))

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
