#!/usr/bin/env python3
"""Memória clínica: perfil, sugestões por regra (retorno antes de acabar o remédio, fisioterapia, pedido sem resultado, retirada de pontos com convênio),
revisão pelo modelo conferida, aceitar/recusar/adiar/responder. Dados FICTÍCIOS."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import json
import os
import tempfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-clinico-"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "banco"), "HEIMDALL_EXAMES_DIR": str(TMP / "health"), "HEIMDALL_EXAMES_LLM": "0"})
import heimdall_agenda as ag  # noqa: E402
import heimdall_clinico as cl  # noqa: E402
import heimdall_exames as ex  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


HOJE = date(2026, 11, 25)


def sql(q, *p):
    return ex._escrever(lambda con: con.execute(q, p).rowcount)


# ----- perfil
confere("perfil vazio orienta", "vazio" in cl.relatorio_perfil())
cl.perfil_adicionar("condicao", "hipoglicemia", "2020")
cl.perfil_adicionar("convenio", "Plano Exemplo Saúde")
confere("perfil: guarda e lista", "hipoglicemia (desde 2020)" in cl.relatorio_perfil() and "Convênio ou plano: Plano Exemplo Saúde" in cl.relatorio_perfil())
try:
    cl.perfil_adicionar("humor", "x")
    erro = False
except cl.ErroClinico:
    erro = True
confere("perfil: tipo inválido é recusado", erro)
pid = cl.perfil_listar()[0]["id"]
cl.perfil_remover(pid)
confere("perfil: remove", len(cl.perfil_listar()) == 1)
cl.perfil_adicionar("condicao", "hipoglicemia", "2020")

# ----- documentos fictícios já confirmados
sql("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, prescritor, quantidade) VALUES (1,'2026-11-16','Marcax (quetiapina)','100mg','TOMAR 1 CP A NOITE.','ANA EXEMPLO (CRM-SP 1)','2 embalagens (30un)')")
sql("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, prescritor, quantidade) VALUES (2,'2026-11-16','Sertralex (sertralina)','50mg','TOMAR 1 CP MANHA','ANA EXEMPLO (CRM-SP 1)','1 caixa')")
sql("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, prescritor, quantidade) VALUES (3,'2026-11-16','Vitaminex','1000mg','1 por dia','ANA EXEMPLO (CRM-SP 1)','2 embalagens (30un)')")
sql("INSERT INTO atestados (documento_id, dia, inicio, fim, dias, cid, medico) VALUES (4,'2026-07-13','2026-07-08','2026-07-21',14,'M23','BELTRANO EXEMPLO (CRM-SP 2)')")
sql("INSERT INTO pedidos_exame (documento_id, dia, exame, tuss) VALUES (5,'2026-08-17','Ferritina','1'),(5,'2026-08-17','Vitamina B12','2'),(5,'2026-08-17','Exame inventado sem catálogo','3')")
sql("INSERT INTO exames_resultados (documento_id, dia, chave, nome, nome_original, grupo, valor, valor_texto, unidade, catalogado, fonte, ordem) VALUES (9,'2026-09-02','vitamina_b12','Vitamina B12','B12','x',300,'300','pg/mL',1,'regra',1)")

f = cl._fatos(HOJE)
cands = {c["chave"]: c for c in cl._regras(f, HOJE)}
ret = next((c for k, c in cands.items() if k.startswith("retorno_receita")), None)
confere("remédio de acompanhamento: uma sugestão de retorno com os dois remédios e sem a vitamina", ret and "Marcax" in ret["motivo"] and "Sertralex" in ret["motivo"]
        and "Vitaminex" not in ret["motivo"], ret)
confere("suprimento: 2 caixas de 30 com 1 por dia = 60 dias; sertralina sem quantidade usa 30 dias e o menor vale", ret and "considerei 30 dias" in ret["motivo"] and ret["quando"] == "2026-12-09", ret)
confere("retorno: o texto não fala de dose nem de diagnóstico", ret and cl._seguro(ret["titulo"] + " " + ret["motivo"]))
confere("CID de joelho sem fisioterapia vira pergunta", "joelho_fisio|4" in cands and cands["joelho_fisio|4"]["tipo"] == "pergunta" and "CID M23" in cands["joelho_fisio|4"]["motivo"], list(cands))
confere("pedido sem resultado: só o que o catálogo conhece e não tem resultado depois do pedido", "pedido_sem_resultado|5" in cands and "Ferritina" in cands["pedido_sem_resultado|5"]["motivo"]
        and "Vitamina B12" not in cands["pedido_sem_resultado|5"]["motivo"] and "inventado" not in cands["pedido_sem_resultado|5"]["motivo"], cands.get("pedido_sem_resultado|5"))
confere("perfil preenchido: não pede perfil", "perfil|vazio" not in cands)
confere("dias_de_suprimento: 3 vezes por dia", cl.dias_de_suprimento({"quantidade": "1 caixa (30un)", "posologia": "1 comprimido de 8 em 8 horas"}) == (10, True))
confere("classe do remédio", cl.classe_do_medicamento("Marcax (escitalopram)")[0] == "antidepressivo" and cl.classe_do_medicamento("Vitaminex")[0] is None)

# fisioterapia e retorno ao ortopedista
sql("INSERT INTO encaminhamentos (documento_id, dia, especialidade, motivo, prescritor, cid) VALUES (6,'2026-08-13','Fisioterapia','10 SESSÕES DE FISIOTERAPIA; hipótese diagnóstica: PÓS OP. DE RECONSTRUÇÃO DO LCA DE JOELHO D','BELTRANO EXEMPLO','M23')")
cands = {c["chave"]: c for c in cl._regras(cl._fatos(HOJE), HOJE)}
confere("com encaminhamento de fisio: pergunta sobre as sessões, sem a pergunta do atestado", "fisio|6" in cands and "10 sessões" in cands["fisio|6"]["motivo"] and "joelho_fisio|4" not in cands, list(cands))
confere("pós-operatório há mais de 60 dias sem consulta: sugere retorno ao ortopedista", any(k.startswith("joelho_retorno") for k in cands), list(cands))
sql("INSERT INTO consultas (documento_id, dia, hora, medico, especialidade, local) VALUES (0,'2026-12-10','10:00','X','Ortopedia','Y')")
cands = {c["chave"]: c for c in cl._regras(cl._fatos(HOJE), HOJE)}
confere("com consulta de ortopedia marcada: não sugere retorno", not any(k.startswith("joelho_retorno") for k in cands))

# retirada de pontos: o local pode ser outro; considera o convênio
sql("INSERT INTO encaminhamentos (documento_id, dia, especialidade, motivo, prescritor) VALUES (7,'2026-11-24','Retirada de pontos (UBS)','SOLICITO RETIRADA DE PONTOS DO PACIENTE EM QUESTÃO, NO DIA 02/12/2026','BELTRANO')")
cands = {c["chave"]: c for c in cl._regras(cl._fatos(HOJE), HOJE)}
p = cands.get("pontos|7")
confere("retirada de pontos futura: avisa que a UBS pode não ser o único local e cita o convênio registrado", p and "Plano Exemplo Saúde" in p["motivo"] and "UBS" in p["motivo"] and p["quando"] == "2026-11-29", p)
cl.perfil_remover([x for x in cl.perfil_listar() if x["tipo"] == "convenio"][0]["id"])
p = {c["chave"]: c for c in cl._regras(cl._fatos(HOJE), HOJE)}["pontos|7"]
confere("sem convênio: sugere registrar o convênio", "registre o convênio" in p["motivo"])
cl.perfil_adicionar("convenio", "Plano Exemplo Saúde")
sql("DELETE FROM encaminhamentos WHERE documento_id = 7")

# ----- guardar e acompanhar
r = cl.atualizar(HOJE, com_modelo=False)
confere("atualizar guarda as sugestões", r["novas"] >= 3 and len(cl.listar(hoje=HOJE)) >= 3, r)
confere("atualizar de novo não duplica", cl.atualizar(HOJE, com_modelo=False)["novas"] == 0)
sid = next(s["id"] for s in cl.listar(hoje=HOJE) if s["chave"].startswith("retorno_receita"))

pedidos = []
def post(url, dado, cab):
    pedidos.append((url, dado))
    return {"ok": True, "lembrete": "ok"}

a = cl.aceitar(sid, post=post, hoje=HOJE)
confere("aceitar consulta vira lembrete com título que não cita remédio", a["lembrete"] and pedidos and pedidos[0][0].endswith("/lembretes/criar")
        and "Marcax" not in json.dumps(pedidos[0][1]) and pedidos[0][1]["vencimento"] == "2026-12-09", pedidos)
fisio_id = next(s["id"] for s in cl.listar(hoje=HOJE) if s["chave"].startswith("fisio|"))
a = cl.aceitar(fisio_id, post=post, hoje=HOJE)
confere("aceitar pergunta não cria lembrete", a["lembrete"] is False and len(pedidos) == 1)
cl.responder(fisio_id, "Fiz 8 sessões; vou pedir mais 10 no retorno.")
confere("responder guarda a resposta", "8 sessões" in cl.relatorio_sugestoes(todas=True))

def falha(url, dado, cab):
    raise OSError("sem rede")
outro = next(s["id"] for s in cl.listar(hoje=HOJE) if s["tipo"] == "pergunta" and s["chave"].startswith("pedido"))
cl.recusar(outro)
confere("recusar tira da lista e a sugestão não volta", outro not in [s["id"] for s in cl.listar(hoje=HOJE)] and cl.atualizar(HOJE, com_modelo=False)["novas"] == 0)
ped = next((s["id"] for s in cl.listar(hoje=HOJE) if s["chave"].startswith("joelho_retorno")), None)
if ped is None:
    sql("DELETE FROM consultas")
    cl.atualizar(HOJE, com_modelo=False)
    ped = next(s["id"] for s in cl.listar(hoje=HOJE) if s["chave"].startswith("joelho_retorno"))
a = cl.aceitar(ped, post=falha, hoje=HOJE)
confere("agente fora do ar: não cria, a sugestão continua aberta", a["lembrete"] is False and ped in [s["id"] for s in cl.listar(hoje=HOJE)], a)
cl.adiar(ped, 10, HOJE)
confere("adiar some e volta no dia", ped not in [s["id"] for s in cl.listar(hoje=HOJE)] and ped in [s["id"] for s in cl.listar(hoje=date(2026, 12, 5))])

# ----- receita renovada: a sugestão antiga deixa de valer
sql("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, prescritor, quantidade) VALUES (10,'2026-12-10','Marcax (quetiapina)','100mg','TOMAR 1 CP A NOITE.','ANA EXEMPLO (CRM-SP 1)','2 embalagens (30un)')")
sql("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, prescritor, quantidade) VALUES (10,'2026-12-10','Sertralex (sertralina)','50mg','TOMAR 1 CP MANHA','ANA EXEMPLO (CRM-SP 1)','2 embalagens (30un)')")
cl.atualizar(date(2026, 12, 11), com_modelo=False)
chaves = [s["chave"] for s in cl.listar(hoje=date(2026, 12, 11))]
confere("nova receita dos mesmos remédios gera a próxima sugestão de retorno com a data nova", any(k == "retorno_receita|ANA EXEMPLO (CRM-SP 1)|2026-12-10" for k in chaves), chaves)

# ----- revisão pelo modelo: conferida
ex.USAR_MODELO = True
f = cl._fatos(HOJE)
cands = cl._regras(f, HOJE)
alvo = next(c for c in cands if c["chave"].startswith("pedido_sem_resultado"))
resp = {"revisadas": [{"chave": alvo["chave"], "manter": True, "titulo": "Pedido de agosto ainda sem laudos", "motivo": "Confira se os exames do pedido de agosto já foram feitos."},
                      {"chave": "chave_que_nao_existe", "manter": False}],
        "novas": [{"tipo": "consulta", "titulo": "Marcar clínico geral", "motivo": "Há pedido de exames sem resultado.", "base": [5]},
                  {"tipo": "consulta", "titulo": "Aumentar a dose do remédio", "motivo": "x", "base": [1]},
                  {"tipo": "exame", "titulo": "Repetir exame", "motivo": "Sem documento real.", "base": [999]},
                  {"tipo": "diagnostico", "titulo": "Tipo inválido", "motivo": "x", "base": [1]}]}
ex._modelo = lambda prompt, max_tokens=1400: json.dumps(resp)
rev, av = cl.revisar_com_modelo(f, cands)
chaves = {c["chave"]: c for c in rev}
confere("modelo: reescreve título e motivo da sugestão existente", chaves[alvo["chave"]]["titulo"] == "Pedido de agosto ainda sem laudos" and chaves[alvo["chave"]]["origem"] == "regra+modelo")
confere("modelo: sugestão nova com documento real é aceita e marcada como do modelo", any(c["origem"] == "modelo" and c["titulo"] == "Marcar clínico geral" and c["base"] == [5] for c in rev))
confere("modelo: dose, documento inexistente e tipo inválido são descartados", not any(k.startswith("modelo|") and ("aumentar" in k or "repetir" in k or "tipo-invalido" in k) for k in chaves))
resp = {"revisadas": [{"chave": alvo["chave"], "manter": False, "motivo": "Os exames já foram feitos segundo o perfil."}], "novas": []}
rev, av = cl.revisar_com_modelo(f, cands)
confere("modelo: pode não manter uma sugestão, com aviso", alvo["chave"] not in [c["chave"] for c in rev] and av, av)
resp = {"revisadas": [{"chave": alvo["chave"], "manter": True, "titulo": "Suspender o remédio", "motivo": "Pare de tomar agora."}]}
rev, av = cl.revisar_com_modelo(f, cands)
confere("modelo: texto que manda suspender é ignorado e o original fica", next(c for c in rev if c["chave"] == alvo["chave"])["titulo"] == alvo["titulo"])
ex._modelo = lambda *a, **k: "lixo"
rev, av = cl.revisar_com_modelo(f, cands)
confere("modelo com resposta inválida: valem as regras", rev == cands)
ex.USAR_MODELO = False

confere("agenda: tipo sugestao_saude é lembrete", ag.destino("sugestao_saude") == "lembrete")
confere("banco: tabelas novas conhecidas", "perfil_clinico" in ex.banco.resumo() and "sugestoes_saude" in ex.banco.resumo())
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
raise SystemExit(1 if falhas else 0)
