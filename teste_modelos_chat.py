#!/usr/bin/env python3
"""Testa os modelos personalizados do chat: funções que existem, prompts coerentes e guia em dia."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelos_chat as mc  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:500])


confere("modelos, conexões e prompts consistentes", not mc.problemas(), mc.problemas())
saude = next(m for m in mc.MODELOS if m["nome"] == "Saúde")
fin = next(m for m in mc.MODELOS if m["nome"] == "Finanças")
confere("Saúde não enxerga função de finanças", not any(f.startswith("financas_") for f in mc.funcoes_do_modelo(saude)))
confere("Finanças não enxerga função de saúde nem consulta livre ao banco", not any(f in mc.funcoes_do_modelo(fin) for f in ("banco_consultar", "saude_historico", "analise_saude")))
confere("Finanças só lê: nenhuma função de escrita ou pagamento", all(f.startswith("financas_") or f == "get_system_timestamp" for f in mc.funcoes_do_modelo(fin)))
confere("Código e Conversas ficam sem ferramentas", all(not mc.funcoes_do_modelo(m) for m in mc.MODELOS if m["nome"] in ("Código", "Conversas")))
txt = (mc.AQUI / "modelos_open_webui.txt").read_text(encoding="utf-8")
confere("guia modelos_open_webui.txt em dia (rode python3 gerar_docs.py)", txt == mc.texto_guia())
confere("guia lista as 3 conexões do servidor de dados", all(("ID " + i) in txt for i in ("banco-pessoal", "banco-saude", "banco-financas")))
# o teste pega um erro de verdade: prompt citando função que o modelo não tem
orig = mc.MODELOS
try:
    mc.MODELOS = [dict(m) for m in orig]
    mc.MODELOS[1]["conexao"] = "banco-financas"
    confere("detecta modelo ligado à conexão errada", any("Saúde" in e for e in mc.problemas()))
finally:
    mc.MODELOS = orig
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
