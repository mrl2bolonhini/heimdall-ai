#!/usr/bin/env python3
"""Testes de financas_planilhas.py: leitura de xlsx e csv, interpretação, aprendizado do layout, dúvidas, visões e resumos. Sem rede e sem modelo real."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import financas_nucleo as fn  # noqa: E402
import financas_planilhas as fp  # noqa: E402
from teste_planilhas_util import xlsx  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"  {detalhe}"))
    if not ok:
        falhas += 1


def sem_modelo(sistema, usuario):
    raise RuntimeError("sem modelo no teste")


def novo():
    pasta = Path(tempfile.mkdtemp())
    return fn.conectar(pasta / "f.db"), pasta


# --- leitura de xlsx e csv ---
dados = xlsx({"Gastos": [["Gastos de outubro", ""], ["Data", "Descrição", "Valor"], [("data", 46296), "Mercado Zona Sul", -123.45], [("data", 46297), "Salário", 5000], ["Total", "", 4876.55]]})
abas = fp.ler_xlsx(dados)
confere("xlsx: uma aba lida", len(abas) == 1 and abas[0][0] == "Gastos", abas)
cab, linhas = fp.achar_tabela(abas[0][1])
confere("cabeçalho achado depois do título", cab == ["Data", "Descrição", "Valor"], cab)
confere("linha de total ignorada", len(linhas) == 2, linhas)
confere("data do Excel vira AAAA-MM-DD", linhas[0][0] == "2026-10-01", linhas[0])
confere("número vira vírgula decimal", linhas[0][2] == "-123,45", linhas[0])
confere("porcentagem do Excel", fp.ler_xlsx(xlsx({"a": [["Taxa", "x"], [("pct", 0.0189), "y"]]}))[0][1][1][0] == "1,89%")
csvs = "Ativo;Tipo;Quantidade;Valor atual\nPETR4;Ação;100;R$ 3.500,00\nTesouro Selic 2029;Renda fixa;1;R$ 10.000,00\n".encode("utf-8")
confere("csv com ponto e vírgula", fp.ler_csv(csvs)[0][1][0][0] == "Ativo")
try:
    fp.ler_planilha(b"PK\x03\x04lixo", "x.xlsx")
    confere("xlsx quebrado dá erro claro", False)
except fp.ErroPlanilha:
    confere("xlsx quebrado dá erro claro", True)

# --- gastos: interpretação por palavras, sem modelo ---
con, pasta = novo()
r = fp.processar(con, dados, "gastos_2026_10.xlsx", pasta, modelo=sem_modelo, agora="2026-11-22 10:00:00")
confere("gastos reconhecidos sem modelo", r[0]["ok"] and r[0]["tipo"] == "gastos" and r[0]["novas"] == 2, r)
confere("gastos alimentam as transações", con.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 2 and r[0]["transacoes_novas"] == 2, r)
confere("nome do conjunto sem data nem sublinhado", r[0]["conjunto"] == "Gastos", r[0]["conjunto"])
r2 = fp.processar(con, dados, "gastos_2026_10.xlsx", pasta, modelo=sem_modelo)
confere("reimportar não duplica", r2[0]["novas"] == 0 and r2[0]["repetidas"] == 2 and con.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 2, r2)
confere("layout aprendido na segunda vez", r2[0]["origem"] == "aprendido", r2)
dados2 = xlsx({"Gastos": [["Data", "Descrição", "Valor"], [("data", 46296), "Mercado Zona Sul", -123.45], [("data", 46320), "Farmácia", -40]]})
r3 = fp.processar(con, dados2, "gastos_2026_11.xlsx", pasta, modelo=sem_modelo)
confere("arquivo novo com o mesmo layout soma só o que é novo", r3[0]["novas"] == 1 and r3[0]["repetidas"] == 1 and r3[0]["origem"] == "aprendido", r3)
confere("o mesmo conjunto recebeu tudo", len(fp.conjuntos(con)) == 1 and fp.conjuntos(con)[0]["n"] == 3)
r4 = fp.importar_arquivo(con, dados2, "gastos_2026_11.xlsx", pasta, modelo=sem_modelo)
r5 = fp.importar_arquivo(con, dados2, "copia.xlsx", pasta, modelo=sem_modelo)
confere("arquivo idêntico é reconhecido como já importado", r5[0].get("duplicado"), (r4, r5))

# --- investimentos ---
inv = xlsx({"Carteira": [["Ativo", "Tipo", "Quantidade", "Valor atual", "Data"], ["PETR4", "Ação", 100, 3500, ("data", 46296)], ["Tesouro Selic 2029", "Renda fixa", 1, 10000, ("data", 46296)]]})
r = fp.processar(con, inv, "carteira.xlsx", pasta, modelo=sem_modelo)
confere("investimentos reconhecidos pelos cabeçalhos", r[0]["ok"] and r[0]["tipo"] == "investimentos", r)
inv2 = xlsx({"Carteira": [["Ativo", "Tipo", "Quantidade", "Valor atual", "Data"], ["PETR4", "Ação", 100, 3800, ("data", 46327)], ["Tesouro Selic 2029", "Renda fixa", 1, 10100, ("data", 46327)]]})
fp.processar(con, inv2, "carteira_novembro.xlsx", pasta, modelo=sem_modelo)
res = fp.resumo_investimentos(con)
confere("resumo usa a posição mais recente de cada ativo", res["total"] == 1390000 + 0 + 0 or res["total"] == 3800 * 100 + 10100 * 100, res["total"])
confere("resumo por tipo", dict(res["por_tipo"]).get("Ação") == 380000, res["por_tipo"])
confere("investimentos não viram transações", con.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 3)

# --- empréstimos ---
emp = xlsx({"Dívidas": [["Contrato", "Credor", "Saldo devedor", "Valor da parcela", "Taxa de juros", "Parcelas restantes"],
                         ["Financiamento do carro", "Banco X", 25000, 850, ("pct", 0.0189), 30], ["Consignado", "Banco Y", 8000, 400, ("pct", 0.021), 20]]})
r = fp.processar(con, emp, "dividas.xlsx", pasta, modelo=sem_modelo)
confere("empréstimos reconhecidos", r[0]["ok"] and r[0]["tipo"] == "emprestimos", r)
res = fp.resumo_emprestimos(con)
confere("resumo de empréstimos soma saldo e parcelas", res["saldo"] == 3300000 and res["parcelas"] == 125000 and res["itens"][0]["taxa"] == "1,89%", res)

# --- dúvida: planilha que ninguém entende, depois resposta ---
estranha = xlsx({"Plan": [["Coisa", "Outra coisa", "Mais"], ["a", "b", 1], ["c", "d", 2]]})
r = fp.importar_arquivo(con, estranha, "estranha.xlsx", pasta, modelo=sem_modelo)
confere("planilha sem pistas vira pergunta", not r[0]["ok"] and r[0].get("duvida"), r)
d = fp.duvidas(con)
confere("pergunta pede o tipo", d and d[0]["campos"][0]["chave"] == "tipo", d)
r = fp.responder_duvida(con, pasta, d[0]["id"], {"tipo": "outros", "nome": "Coisas"}, modelo=sem_modelo)
confere("resposta importa como outros", r[0]["ok"] and r[0]["conjunto"] == "Coisas" and fp.duvidas(con) == [], r)
r = fp.processar(con, estranha, "estranha2.xlsx", pasta, modelo=sem_modelo)
confere("o jeito de ler foi guardado", r[0]["ok"] and r[0]["origem"] == "aprendido" and r[0]["conjunto"] == "Coisas", r)
parcial = xlsx({"Plan": [["Data", "Descrição", "Quanto vezes"], ["2026-10-01", "x", 3], ["2026-10-02", "y", 4]]})
r = fp.processar(con, parcial, "extrato_conta.xlsx", pasta, modelo=sem_modelo)
confere("faltando coluna obrigatória pergunta qual é", not r[0]["ok"] and any(c["chave"] == "papel:valor" for c in fp.duvidas(con)[0]["campos"]), (r, fp.duvidas(con)))
did = fp.duvidas(con)[0]["id"]
r = fp.responder_duvida(con, pasta, did, {"papel:valor": "quanto_vezes"}, modelo=sem_modelo)
confere("resposta por coluna conclui", r[0]["ok"] and r[0]["tipo"] == "gastos", r)

# --- modelo de linguagem ajuda quando as palavras não bastam ---
def modelo_ok(sistema, usuario):
    return 'Claro: {"tipo":"investimentos","nome":"Fundos da família","papeis":{"ativo":"Coisa","valor":"Mais"},"duvida":""} fim'


con2, pasta2 = novo()
r = fp.processar(con2, estranha, "estranha.xlsx", pasta2, modelo=modelo_ok)
confere("modelo define tipo, nome e colunas", r[0]["ok"] and r[0]["tipo"] == "investimentos" and r[0]["conjunto"] == "Fundos da família" and r[0]["origem"] == "modelo", r)
confere("modelo que inventa coluna é ignorado", fp._pedir_ao_modelo(lambda s, u: '{"tipo":"gastos","papeis":{"data":"Inexistente"}}', "x", ["A"], [["1"]]).get("tipo") == "gastos")
con3, pasta3 = novo()
r = fp.processar(con3, estranha, "e.xlsx", pasta3, modelo=lambda s, u: "não sei")
confere("resposta torta do modelo vira pergunta", r[0].get("duvida"), r)

# --- visões ---
con4, pasta4 = novo()
fp.processar(con4, dados, "gastos_2026_10.xlsx", pasta4, modelo=sem_modelo)
cid = fp.conjuntos(con4)[0]["id"]
vid = fp.criar_visao(con4, cid, "Só valores")
fp.tirar_coluna(con4, vid, "descricao")
fp.mover_coluna(con4, vid, "valor", -1)
v = fp.visao(con4, vid)
confere("visão com colunas removidas e reordenadas", v["cfg"]["colunas"] == ["valor", "data"], v["cfg"])
fp.definir_regras(con4, vid, ordem="valor", direcao="desc")
a = fp.aplicar_visao(con4, cid, fp.visao(con4, vid)["cfg"])
confere("visão mostra só as colunas pedidas na ordem", [k for k, _ in a["colunas"]] == ["valor", "data"] and a["linhas"][0] == ["5000", "2026-10-02"], a["linhas"])
dados_novos = xlsx({"Gastos": [["Data", "Descrição", "Valor"], [("data", 46330), "Livraria", -90]]})
fp.processar(con4, dados_novos, "gastos_2026_12.xlsx", pasta4, modelo=sem_modelo)
a = fp.aplicar_visao(con4, cid, fp.visao(con4, vid)["cfg"])
confere("lançamento novo aparece na visão gravada", a["total"] == 3 and len(a["linhas"]) == 3 and [k for k, _ in a["colunas"]] == ["valor", "data"], a)
fp.por_coluna(con4, vid, "descricao")
confere("coluna incluída vai para o fim", fp.visao(con4, vid)["cfg"]["colunas"] == ["valor", "data", "descricao"])
fp.definir_regras(con4, vid, filtro_col="descricao", filtro_valor="merc")
a = fp.aplicar_visao(con4, cid, fp.visao(con4, vid)["cfg"])
confere("filtro por texto sem acento nem caixa", a["filtradas"] == 1 and a["total"] == 3, a["filtradas"])
fp.definir_regras(con4, vid, agrupar="descricao", somar="valor")
a = fp.aplicar_visao(con4, cid, fp.visao(con4, vid)["cfg"])
confere("agrupamento soma o valor", a["grupos"] and a["grupos"]["linhas"][0][0] == "Salário" and a["grupos"]["linhas"][0][2] == 500000, a["grupos"])
try:
    fp.criar_visao(con4, cid, "Só valores")
    confere("nome de visão repetido é recusado", False)
except fn.ErroFinance:
    confere("nome de visão repetido é recusado", True)
try:
    fp.definir_regras(con4, vid, ordem="coluna_que_nao_existe")
    confere("coluna desconhecida é recusada", False)
except fn.ErroFinance:
    confere("coluna desconhecida é recusada", True)
try:
    fp.tirar_coluna(con4, fp.criar_visao(con4, cid, "Uma"), "data")
    fp.tirar_coluna(con4, fp.criar_visao(con4, cid, "Duas") , "data")
    v2 = fp.visao(con4, fp.criar_visao(con4, cid, "Tres"))
    for k in v2["cfg"]["colunas"][:-1]:
        fp.tirar_coluna(con4, v2["id"], k)
    fp.tirar_coluna(con4, v2["id"], v2["cfg"]["colunas"][-1])
    confere("não deixa a visão sem colunas", False)
except fn.ErroFinance:
    confere("não deixa a visão sem colunas", True)
copia = fp.criar_visao(con4, cid, "Cópia", copiar_de=vid)
confere("visão copiada herda a configuração", fp.visao(con4, copia)["cfg"]["agrupar"] == "descricao")
fp.apagar_visao(con4, copia)
confere("visão apagada some", fp.visao(con4, copia) is None)

# --- pasta vigiada ---
con5, pasta5 = novo()
ent = fp.pasta_de_entrada(pasta5)
(ent / "carteira.xlsx").write_bytes(inv)
(ent / "estranha.xlsx").write_bytes(estranha)
import os, time  # noqa: E402,E401
for f in ent.iterdir():
    if f.is_file():
        os.utime(f, (time.time() - 10, time.time() - 10))
res = fp.processar_pasta(con5, pasta5, modelo=sem_modelo)
confere("pasta: o que entendeu foi importado", any(x["arquivo"] == "carteira.xlsx" and x["resultados"][0]["ok"] for x in res), res)
confere("pasta: dúvida vira pergunta e o arquivo sai da pasta", len(fp.duvidas(con5)) == 1 and not (ent / "estranha.xlsx").exists())
confere("pasta: importado vai para imported/", (ent / "imported" / "carteira.xlsx").exists())

print("\nFalhas:", falhas)
sys.exit(1 if falhas else 0)
