#!/usr/bin/env python3
"""Teste da catalogação de notas (heimdall_catalogo.py) e do cliente do Notion (heimdall_notion.py), sem rede e sem modelo.

    python3 teste_catalogo.py
"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["HEIMDALL_NOTION_TOKEN"] = "segredo-de-teste"
os.environ["HEIMDALL_NOTION_DB_IDEIAS"] = "https://www.notion.so/ws/Ideias-0123456789abcdef0123456789abcdef?v=1"
os.environ["HEIMDALL_NOTION_DB_CONTATOS"] = "abcdef01-2345-6789-abcd-ef0123456789"
os.environ.pop("HEIMDALL_NOTION_DB_ENDERECOS", None)
import heimdall_agenda as ag  # noqa: E402
import heimdall_catalogo as cat  # noqa: E402
import heimdall_notion as nt  # noqa: E402

ok = falha = 0


def confere(nome, cond, detalhe=""):
    global ok, falha
    if cond:
        ok += 1
    else:
        falha += 1
        print("FALHOU:", nome, detalhe)


HOJE = date(2026, 11, 21)
AMANHA = (HOJE + timedelta(days=1)).isoformat()

# agenda: os dois tipos novos estão cadastrados e roteiam certo
confere("lembrete_nota é lembrete", ag.destino("lembrete_nota") == "lembrete")
confere("evento_nota é evento", ag.destino("evento_nota") == "evento")
chamadas = []
confere("agenda.desfazer usa a rota de desfazer", ag.desfazer("evento_nota", {"titulo": "x", "data": AMANHA}, post=lambda u, d, c: (chamadas.append(u) or {"ok": True, "resultado": "apagado"})) == (True, "apagado") and chamadas[0].endswith("/calendario/desfazer"))

# classificação
resp = 'Claro!\n[{"tipo":"contato","titulo":"Ana","texto":"11 98888-7777"},{"tipo":"banana","titulo":"x"},{"tipo":"evento","titulo":"Dentista","data":"2026-12-01","hora":"9:30"}]\nfim'
itens = cat.interpretar(resp)
confere("interpretar ignora tipo inválido e acha o array no meio do texto", [i["tipo"] for i in itens] == ["contato", "evento"] and itens[1]["hora"] == "09:30")
confere("lixo do modelo vira uma ideia com a nota inteira", cat.classificar("texto qualquer da nota", HOJE, llm=lambda s, u: "não sei")[0]["tipo"] == "ideia")
confere("erro do modelo também", cat.classificar("outra nota", HOJE, llm=lambda s, u: 1 / 0)[0]["texto"] == "outra nota")
vistos = []
cat.classificar("n", HOJE, llm=lambda s, u: (vistos.append(u) or "[]"))
confere("pedido ao modelo leva a data de hoje e a nota", "2026-11-21" in vistos[0] and "NOTA:\nn" in vistos[0])

# execução
enviados, notion_ch, locais = [], [], []
deps = {"hoje": lambda: HOJE, "enviar": lambda t, d: (enviados.append((t, d)) or (True, "criado")),
        "notion": lambda t, ti, tx: (notion_ch.append(t) or (True, "pg1")), "nota": lambda r, d: (locais.append(d) or (True, "ok"))}
r = cat.executar({"tipo": "lembrete", "titulo": "Pagar", "texto": "", "data": "2026-11-20", "hora": "", "incerto": False}, deps)
confere("data no passado fica pendente", r["estado"] == "pendente" and not enviados)
r = cat.executar({"tipo": "evento", "titulo": "Show", "texto": "", "data": "", "hora": "", "incerto": False}, deps)
confere("sem data fica pendente", r["estado"] == "pendente")
r = cat.executar({"tipo": "evento", "titulo": "Show", "texto": "", "data": AMANHA, "hora": "21:00", "incerto": True}, deps)
confere("incerto fica pendente mesmo com data", r["estado"] == "pendente")
r = cat.executar({"tipo": "evento", "titulo": "Show", "texto": "", "data": AMANHA, "hora": "21:00", "incerto": False}, deps)
confere("evento claro é criado com hora", r["estado"] == "feito" and enviados[-1][0] == "evento_nota" and enviados[-1][1]["hora"] == "21:00")
r = cat.executar({"tipo": "endereco", "titulo": "Padaria", "texto": "Rua A, 10", "data": "", "hora": "", "incerto": False}, deps)
confere("endereço comum vai ao Notion", r["destino"] == "Notion" and notion_ch == ["endereco"])
for txt in ("saldo da conta", "resultado do exame de sangue", "minha senha do banco"):
    notion_ch.clear()
    r = cat.executar({"tipo": "ideia", "titulo": txt, "texto": txt, "data": "", "hora": "", "incerto": False}, deps)
    confere(f"sensível nunca vai ao Notion: {txt}", not notion_ch and r["destino"] == "nota local")
falho = dict(deps, notion=lambda t, ti, tx: (False, "o Notion recusou (401)"))
r = cat.executar({"tipo": "ideia", "titulo": "Ideia boa", "texto": "x", "data": "", "hora": "", "incerto": False}, falho)
confere("Notion fora do ar: a ideia não se perde, vai para nota local", r["estado"] == "feito" and r["destino"] == "nota local")
confere("nota local vai para uma pasta Heimdall", locais[-1]["pasta"].startswith("Heimdall"))

# Notion
confere("id do banco aceita endereço colado do Notion", nt.id_do_banco("ideia") == "0123456789abcdef0123456789abcdef")
confere("id do banco aceita id com hífens", nt.id_do_banco("contato") == "abcdef0123456789abcdef0123456789")
confere("banco sem id não está configurado", not nt.configurado("endereco") and nt.criar("endereco", "x", "y")[0] is False)
log = []


def http(m, url, corpo, cab):
    log.append((m, url, corpo, cab))
    if m == "GET":
        return {"properties": {"Data": {"type": "date"}, "Nome": {"type": "title"}}}
    return {"id": "pagina-1"}


r = nt.criar("ideia", "Minha ideia", "linha 1\nlinha 2", http)
confere("criar página usa a coluna de título e põe o texto como parágrafos", r == (True, "pagina-1") and "Nome" in log[-1][2]["properties"] and len(log[-1][2]["children"]) == 2)
confere("token vai no cabeçalho e não no corpo", log[-1][3]["Authorization"] == "Bearer segredo-de-teste" and "segredo-de-teste" not in json.dumps(log[-1][2]))
confere("arquivar usa PATCH archived", nt.arquivar("pagina-1", http) == (True, "arquivada") and log[-1][0] == "PATCH" and log[-1][2] == {"archived": True})
confere("verificar lista os três bancos", len(nt.verificar(http)) == 3 and nt.verificar(http)[2].startswith("endereco: falta"))

# registros, confirmar, desfazer
cat._registros.clear()
cat.processar("s1", "nota", deps=dict(deps, desfazer=lambda t, d: (True, "apagado"), arquivar=lambda p: (True, "ok")),
              llm=lambda s, u: json.dumps([{"tipo": "lembrete", "titulo": "L", "data": AMANHA}, {"tipo": "evento", "titulo": "E"}, {"tipo": "ideia", "titulo": "I", "texto": "i"}]))
reg = {r["item"]["titulo"]: r for r in cat.registros("s1")}
confere("processar guarda os três itens", set(reg) == {"L", "E", "I"} and reg["E"]["estado"] == "pendente")
confere("confirmar com data inválida não cria", "inválida" in cat.confirmar("s1", reg["E"]["id"], "31/02", deps=deps))
confere("confirmar com data boa cria", cat.confirmar("s1", reg["E"]["id"], AMANHA, deps=deps) == "Item criado.")
d2 = dict(deps, desfazer=lambda t, d: (True, "apagado"), arquivar=lambda p: (True, "ok"))
confere("desfazer lembrete", cat.desfazer("s1", reg["L"]["id"], d2) == "Item desfeito.")
confere("desfazer ideia no Notion", cat.desfazer("s1", reg["I"]["id"], d2) == "Item desfeito.")
confere("não desfaz duas vezes", "não pode" in cat.desfazer("s1", reg["L"]["id"], d2))
confere("outra sessão não enxerga nem desfaz", cat.registros("s2") == [] and "não pode" in cat.desfazer("s2", reg["I"]["id"], d2))
h = cat.bloco_html("s1", "tok")
confere("HTML não traz o token do Notion", "segredo-de-teste" not in h)
cat._registros["s3"] = [{"id": "aaaaaaaaaa", "quando": "", "estado": "feito", "destino": "Notion", "detalhe": "<b>x</b>", "desfazer": False, "item": {"tipo": "ideia", "titulo": "<script>", "texto": "", "data": "", "hora": ""}}]
confere("HTML escapa título e detalhe", "<script>" not in cat.bloco_html("s3", "t") and "&lt;script&gt;" in cat.bloco_html("s3", "t"))

print(f"\n{ok} verificações passaram, {falha} falharam.")
sys.exit(1 if falha else 0)
