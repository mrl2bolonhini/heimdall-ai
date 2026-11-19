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

# arquivos de importação do Open WebUI
import json  # noqa: E402
arq_m = mc.PASTA_IMPORTAR / "modelos_importar.json"
arq_f = mc.PASTA_IMPORTAR / "ferramentas_importar.json"
atual = mc.json_importar()
confere("arquivos de importação em dia (rode python3 gerar_docs.py)", all((mc.PASTA_IMPORTAR / n).exists() and (mc.PASTA_IMPORTAR / n).read_text(encoding="utf-8") == c for n, c in atual.items()))
mods, cons = json.loads(atual["modelos_importar.json"]), json.loads(atual["ferramentas_importar.json"])
ids_con = {c["info"]["id"] for c in cons}
confere("todo modelo usa uma conexão que existe", all(t.split(":")[-1] in ids_con for x in mods for t in x["meta"].get("toolIds", [])), mods)
confere("nenhum modelo importado dá acesso a outro usuário", all(not x["access_grants"] for x in mods))
confere("o arquivo de funções de cada conexão é a lista permitida", all((mc.PASTA_IMPORTAR / ("funcoes_%s.txt" % c["info"]["id"])).read_text(encoding="utf-8").strip() == ", ".join(mc.conexao(c["info"]["id"])["funcoes"]) for c in cons))
confere("a conexão importada tem só os campos que o Open WebUI exporta", all(set(c) == {"type", "url", "spec_type", "spec", "path", "auth_type", "key", "info"} for c in cons), cons[0])
confere("o prompt importado é o do arquivo", all(x["params"]["system"] == (mc.AQUI / m["prompt"]).read_text(encoding="utf-8").strip() for x, m in zip(mods, mc.MODELOS)))
confere("modelos de dados pessoais não ligam busca na web nem terminal", all(not x["meta"]["capabilities"]["web_search"] and not x["meta"]["capabilities"]["terminal"] for x in mods))
confere("a lista de funções não tem exclusões nem espaços sobrando", all("!" not in (mc.PASTA_IMPORTAR / ("funcoes_%s.txt" % c["info"]["id"])).read_text(encoding="utf-8") for c in cons))
confere("ids de modelo únicos e sem espaço", len({x["id"] for x in mods}) == len(mods) and all(" " not in x["id"] for x in mods))
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
