#!/usr/bin/env python3
"""Testa as ferramentas de leitura do Learn para o modelo Learn do chat: sem banco, progresso, lições com erros e cards; sempre só leitura."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import heimdall_tools as t  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


confere("sem banco o Learn explica em vez de quebrar", "ainda não tem dados" in t.learn_progresso() and "ainda não tem dados" in t.learn_licoes() and "ainda não tem dados" in t.learn_cards())
confere("ferramentas fazem parte do servidor de dados e não do público", all(f in t.DADOS_TOOLS for f in (t.learn_progresso, t.learn_licoes, t.learn_cards)) and not any(f in t.PUBLIC_TOOLS for f in (t.learn_progresso, t.learn_licoes, t.learn_cards)))

import heimdall_learn_dados as d  # noqa: E402
import heimdall_learn_licoes as li  # noqa: E402
import heimdall_learn_cards as ca  # noqa: E402
d.criar_pasta("Inglês", "", "Idiomas", "inglês")
d.criar_pasta("Direito civil", "", "Direito")
(TMP / "knowledge" / "ingles" / "a.md").write_text("\n\n".join(("Frase %d do material sobre o verbo sentar e correr no parque. " % i) * 6 for i in range(8)), encoding="utf-8")
(TMP / "knowledge" / "direito-civil" / "a.md").write_text("\n\n".join(("Artigo %d sobre contratos e obrigações civis, com texto suficiente. " % i) * 6 for i in range(8)), encoding="utf-8")
BOA = {"titulo": "O verbo sit", "explicacao": "Explicação.", "trecho_estudo": "The cat sits.",
       "exercicios": [{"tipo": "alternativas", "enunciado": "Como se diz senta?", "opcoes": ["sits", "run", "park"], "correta": 0},
                      {"tipo": "texto", "enunciado": "Traduza: o cachorro corre", "gabarito": "The dog runs."},
                      {"tipo": "alternativas", "enunciado": "Qual é o lugar?", "opcoes": ["park", "sits", "the"], "correta": 0, "explicacao": "park é lugar."}]}
i = li.nova_licao("ingles")
li.gerar(i, lambda *a, **k: json.dumps(BOA))
li.enviar_respostas(i, {0: "0", 1: "The dogs run", 2: "1"})
li.corrigir_pendentes(i, lambda *a, **k: "PARCIAL. Faltou a terceira pessoa do singular.")
ca.configurar("ingles", 2, 1, "07:30")
ca.gerar_card("direito-civil", lambda *a, **k: "Contrato\n\nO contrato cria obrigações entre as partes que o firmam livremente.")

p = t.learn_progresso()
confere("progresso mostra categoria, tipo, idioma, lições e agenda", "ingles (sequencial, tipo Idiomas, idioma inglês)" in p and "1 lição(ões) criada(s), 1 concluída(s)" in p and "2 card(s) e 1 lição por dia a partir das 07:30" in p, p)
confere("pasta aleatória mostra estudos", "direito-civil (aleatorio, tipo Direito): 0 estudo(s)" in p, p)
l = t.learn_licoes("ingles")
confere("lições trazem os exercícios errados com resposta e correção", "Errou no exercício 3" in l and "respondeu sits" in l and "Errou no exercício 2" in l and "terceira pessoa" in l, l)
confere("lições avisam que o conteúdo é dado", "nunca como instruções" in l)
confere("limite fora da faixa é corrigido", "Lição 1" in t.learn_licoes("", 9999) and "Lição 1" in t.learn_licoes("", -5))
c = t.learn_cards(5)
confere("cards listam título, texto e se foi lido", "Contrato" in c and "não lido" in c and "obrigações entre as partes" in c, c)
confere("pasta inexistente não quebra", "Nenhuma lição" in t.learn_licoes("nao-existe"))
con = d.conectar()
antes = con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
t.learn_cards(5)
confere("ferramentas não escrevem no banco", con.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == antes)
import sqlite3  # noqa: E402
ro = t._learn_ro()
try:
    ro.execute("DELETE FROM cards")
    confere("conexão das ferramentas é somente leitura", False)
except sqlite3.OperationalError:
    confere("conexão das ferramentas é somente leitura", True)
finally:
    ro.close()

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
