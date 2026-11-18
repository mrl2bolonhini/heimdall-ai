#!/usr/bin/env python3
"""Testa financas_pluggy.py com uma API simulada (nenhuma chamada de rede): autenticação, contas, paginação por cursor, sinais, duplicidade e avisos."""
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import financas_nucleo as fn  # noqa: E402
import financas_pluggy as fp  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:500])


U = "11111111-2222-3333-4444-555555555555"
CONTA_CC, CONTA_CARTAO = "aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002"
chamadas = []


def api(metodo, caminho, params=None, corpo=None, chave=""):
    chamadas.append((metodo, caminho, dict(params or {}), chave))
    if caminho == "/auth":
        if (corpo or {}).get("clientSecret") != "segredo-correto-123456":
            raise fp.ErroPluggy("O Pluggy respondeu com erro 401.")
        return {"apiKey": "CHAVE-TESTE"}
    assert chave == "CHAVE-TESTE", "chamada sem chave"
    assert metodo == "GET", "só leitura"
    if caminho == f"/items/{U}":
        return {"status": "UPDATED", "consentExpiresAt": "2026-12-01T00:00:00.000Z"}
    if caminho == "/accounts":
        assert params["itemId"] == U
        return {"page": 1, "totalPages": 1, "results": [
            {"id": CONTA_CC, "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "Conta Corrente", "marketingName": "Itaú Personnalité", "number": "1234-5"},
            {"id": CONTA_CARTAO, "type": "CREDIT", "subtype": "CREDIT_CARD", "name": "Cartão", "marketingName": "Nubank", "number": "9876"}]}
    if caminho == "/v2/transactions":
        if params["accountId"] == CONTA_CC:
            if "after" not in params:
                return {"results": [
                    {"id": "t1", "date": "2026-11-10T00:00:00.000Z", "amount": -212.45, "type": "DEBIT", "status": "POSTED", "description": "PAGTO BOLETO ESCOLA"},
                    {"id": "t2", "date": "2026-11-11T00:00:00.000Z", "amount": 2482.26, "type": "CREDIT", "status": "POSTED", "description": "SALARIO EMPRESA"}],
                    "next": "after=CURSOR1"}
            assert params["after"] == "CURSOR1" and params["dateFrom"] and params["accountId"] == CONTA_CC
            return {"results": [
                {"id": "t3", "date": "2026-11-12", "amount": 99.9, "type": "DEBIT", "status": "POSTED", "description": "DEBITO COM SINAL POSITIVO"},
                {"id": "t4", "date": "2026-11-20", "amount": -50, "type": "DEBIT", "status": "PENDING", "description": "AGENDADO"}], "next": None}
        return {"results": [
            {"id": "c1", "date": "2026-11-05", "amount": 159.2, "type": "CREDIT", "status": "POSTED", "description": "LOJA XYZ"},
            {"id": "c2", "date": "2026-11-06", "amount": -500.0, "type": "DEBIT", "status": "POSTED", "description": "PAGAMENTO RECEBIDO"},
            {"id": "c3", "date": "2026-11-07", "amount": 30.0, "status": "PENDING", "description": "COMPRA NA FATURA ABERTA"}], "next": None}
    if caminho == "/bills":
        return {"results": []}
    raise AssertionError(caminho)


cfg = {"id": "cid", "segredo": "segredo-correto-123456", "itens": [U]}
d = Path(tempfile.mkdtemp())
con = fn.conectar(d / "p.db")
# conta já importada por extrato: o Heimdall deve reaproveitar o nome e começar depois da última data dela
fn.importar_itens(con, [{"data": "2026-11-09", "valor": -1000, "descricao": "ANTIGO"}], "ofx", "x.ofx", "Itaú conta")
cli = fp.Cliente(cfg, api)
hoje = date(2026, 11, 17)
aviso = fp.listar_contas(cfg, {}, con, cli)
confere("lista avisa que já existe conta de extrato com outro nome", aviso[0]["existente"] == "Itaú conta" and aviso[0]["nome"] == "Itaú conta corrente", aviso)
confere("nenhum nome traz Pluggy", not any("pluggy" in a["nome"].lower() or "pluggy" in a["rotulo"].lower() for a in aviso), aviso)
confere("renomear conta do Finance leva o histórico", fp.renomear_conta_finance(con, "Itaú conta", "Itaú conta corrente") == 1 and not con.execute("SELECT 1 FROM transacoes WHERE conta='Itaú conta'").fetchone())
r = fp.executar(con, cfg, d / "estado.json", None, hoje, cli)
por_conta = {c["conta"]: c for c in r["contas"]}
confere("conta renomeada do extrato é reconhecida pelo nome novo (sem duplicar)", "Itaú conta corrente" in por_conta, list(por_conta))
confere("cartão sem conta anterior ganha nome curto com banco e tipo", "Nubank cartão de crédito" in por_conta, list(por_conta))
confere("começa no dia seguinte à última data já importada", por_conta["Itaú conta corrente"]["desde"] == "2026-11-10", por_conta["Itaú conta corrente"])
cc = con.execute("SELECT data, valor, descricao FROM transacoes WHERE conta='Itaú conta corrente' AND descricao<>'ANTIGO' ORDER BY data").fetchall()
confere("conta corrente: débito negativo, crédito positivo, tipo manda mesmo com sinal trocado", [(x["data"], x["valor"]) for x in cc] == [("2026-11-10", -21245), ("2026-11-11", 248226), ("2026-11-12", -9990)], [(x["data"], x["valor"]) for x in cc])
confere("conta corrente: transação PENDING (agendada) fica de fora", not any(x["descricao"] == "AGENDADO" for x in cc))
cartao = [x for n in por_conta if n == "Nubank cartão de crédito" for x in con.execute("SELECT data, valor, descricao FROM transacoes WHERE conta=? ORDER BY data", (n,))]
confere("cartão: compra vira saída, pagamento vira crédito, compra pendente na fatura aberta entra", [(x["data"], x["valor"]) for x in cartao] == [("2026-11-05", -15920), ("2026-11-06", 50000), ("2026-11-07", -3000)], [(x["data"], x["valor"]) for x in cartao])
confere("paginação por cursor: segunda página lida com o cursor", any(c[2].get("after") == "CURSOR1" for c in chamadas))
confere("só leituras: nenhuma chamada além de POST /auth e GETs", all(c[0] == "GET" or c[1] == "/auth" for c in chamadas))
confere("a chave da API é reaproveitada (uma só autenticação)", sum(1 for c in chamadas if c[1] == "/auth") == 1)
confere("aviso de consentimento perto de vencer", any("expira" in a and "01/12/2026" in a for a in r["avisos"]), r["avisos"])
# segunda rodada: repete sem duplicar
r2 = fp.executar(con, cfg, d / "estado.json", None, hoje, fp.Cliente(cfg, api))
confere("segunda rodada relê a sobreposição e não duplica", all(c["novas"] == 0 for c in r2["contas"]) and sum(c["repetidas"] for c in r2["contas"]) > 0, r2["contas"])
confere("o estado guarda as contas e a hora, sem chave de API nem segredo", "CHAVE-TESTE" not in (d / "estado.json").read_text(encoding="utf-8") and "segredo-correto-123456" not in (d / "estado.json").read_text(encoding="utf-8"))
# nomear
est = fp.ler_estado(d / "estado.json")
fp.definir_nome(est, CONTA_CARTAO, "Nubank cartão")
fp.gravar_estado(d / "estado.json", est)
confere("nomear troca o nome e recomeça a contagem de datas", fp.ler_estado(d / "estado.json")["contas"][CONTA_CARTAO]["nome"] == "Nubank cartão" and "ultimo" not in fp.ler_estado(d / "estado.json")["contas"][CONTA_CARTAO])
lista = fp.listar_contas(cfg, fp.ler_estado(d / "estado.json"), con, fp.Cliente(cfg, api))
confere("listar mostra tipo, final e nome no Finance", len(lista) == 2 and lista[1]["nome"] == "Nubank cartão" and lista[0]["final"] == "12345"[-4:] and lista[1]["tipo"] == "cartão de crédito", lista)
# duas contas iguais (mesmo rótulo e final) não podem cair no mesmo nome do Finance
dup = [{"id": "a1", "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "conta itau", "number": "0001/1317"},
       {"id": "a2", "type": "BANK", "subtype": "SAVINGS_ACCOUNT", "name": "conta itau", "number": "0002/1317"},
       {"id": "a3", "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "conta itau", "number": "0003/1317"},
       {"id": "a4", "type": "CREDIT", "subtype": "CREDIT_CARD", "name": "platinum", "marketingName": "Nu Pagamentos S.A."}]
nm = fp.resolver_nomes(con, {"contas": {}}, dup)
confere("contas iguais ganham nomes diferentes", len(set(nm.values())) == 4, nm)
confere("marca reconhecida vira nome curto (Nu Pagamentos → Nubank cartão de crédito)", nm["a4"].startswith("Nubank cartão de crédito"), nm)
nm3 = fp.resolver_nomes(con, {"contas": {}}, [{"id": "k1", "itemId": "I", "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "conta Nu Pagamentos S.A."}, {"id": "k2", "itemId": "I", "type": "CREDIT", "name": "platinum"}])
confere("cartão sem nome de banco herda o banco da conta do mesmo item", nm3["k2"] == "Nubank cartão de crédito", nm3)
nm2 = fp.resolver_nomes(con, {"contas": {"a2": {"nome": "Itaú conta"}}}, dup)
confere("nome já guardado tem prioridade e ninguém mais o toma", nm2["a2"] == "Itaú conta" and list(nm2.values()).count("Itaú conta") == 1, nm2)
# renomear depois de já ter sincronizado não duplica na releitura
con2 = fn.conectar(d / "r.db")
its = [{"data": "2026-11-10", "valor": -500, "descricao": "PIX X", "fitid": "t1"}, {"data": "2026-11-11", "valor": -700, "descricao": "LOJA", "fitid": "t2"}, {"data": "2026-11-11", "valor": -100, "descricao": "SEM ID"}]
fn.importar_itens(con2, its, "pluggy", "Meu Pluggy", "Itaú conta")
est2 = {"contas": {"z": {"nome": "Itaú conta", "ultimo": "2026-11-11"}}}
fp.renomear_conta_finance(con2, "Itaú conta", "Itaú conta corrente", est2)
confere("renomear atualiza o nome guardado e mantém a data", est2["contas"]["z"]["nome"] == "Itaú conta corrente" and est2["contas"]["z"]["ultimo"] == "2026-11-11")
r5 = fn.importar_itens(con2, its, "pluggy", "Meu Pluggy", "Itaú conta corrente")
confere("depois de renomear, reler os mesmos lançamentos não duplica", r5["novas"] == 0 and r5["repetidas"] == 3, r5)
r6 = fn.importar_itens(con2, its + [{"data": "2026-11-12", "valor": -1, "descricao": "NOVO", "fitid": "t3"}], "pluggy", "Meu Pluggy", "Itaú conta corrente")
confere("lançamento novo continua entrando", r6["novas"] == 1, r6)
# padronizar nomes sozinho
con3 = fn.conectar(d / "s.db")
fn.importar_itens(con3, [{"data": "2026-11-10", "valor": -500, "descricao": "A", "fitid": "q1"}], "pluggy", "Meu Pluggy", "Pluggy: platinum cartão")
est3 = {"contas": {CONTA_CARTAO: {"nome": "Pluggy: platinum cartão", "ultimo": "2026-11-11"}}}
feitos = fp.padronizar_nomes(con3, est3, cfg, fp.Cliente(cfg, api))
confere("padronizar renomeia com histórico e atualiza o estado", feitos and feitos[0][1] == "Nubank cartão de crédito" and feitos[0][2] == 1 and est3["contas"][CONTA_CARTAO]["nome"] == "Nubank cartão de crédito", feitos)
confere("padronizar de novo não faz nada", fp.padronizar_nomes(con3, est3, cfg, fp.Cliente(cfg, api)) == [])
# Pluggy não repete o que já veio de extrato, e dá para limpar o que já repetiu
con4 = fn.conectar(d / "u.db")
fn.importar_itens(con4, [{"data": "2026-10-01", "valor": -1000, "descricao": "MERCADO", "fitid": "o1"}, {"data": "2026-10-02", "valor": -500, "descricao": "CAFE"}], "ofx", "x.ofx", "Itaú conta corrente")
pl = [{"data": "2026-10-01", "valor": -1000, "descricao": "MERCADO XYZ", "fitid": "p1"}, {"data": "2026-10-03", "valor": -700, "descricao": "NOVO", "fitid": "p2"}]
r7 = fn.importar_itens(con4, pl, "pluggy", "Meu Pluggy", "Itaú conta corrente")
confere("Pluggy pula lançamento que já veio de extrato e grava o novo", r7["novas"] == 1 and r7["repetidas"] == 1, r7)
con4.execute("INSERT INTO importacoes(arquivo, conta, quando, formato, novas, repetidas) VALUES('p','Itaú conta corrente','x','pluggy',1,0)")
iid = con4.execute("SELECT MAX(id) FROM importacoes").fetchone()[0]
con4.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em,importacao_id) VALUES('Itaú conta corrente','2026-10-02',-500,'CAFE X','cafe x','Outros','h-dup','x',?)", (iid,))
con4.commit()
confere("dedupe só mostra sem apagar", fn.repetidos_entre_fontes(con4) == {"Itaú conta corrente": 1} and con4.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 4)
confere("dedupe com aplicar apaga o do Pluggy e mantém o de extrato", fn.repetidos_entre_fontes(con4, True) == {"Itaú conta corrente": 1} and con4.execute("SELECT COUNT(*) FROM transacoes WHERE descricao='CAFE'").fetchone()[0] == 1 and con4.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 3)
# duas compras iguais no mesmo dia, só uma no extrato: entra uma, e a limpeza não apaga a legítima numa segunda rodada
con5 = fn.conectar(d / "v.db")
fn.importar_itens(con5, [{"data": "2026-10-05", "valor": -900, "descricao": "PADARIA", "fitid": "e1"}], "ofx", "x.ofx", "Itaú cartão de crédito")
dois = [{"data": "2026-10-05", "valor": -900, "descricao": "PADARIA", "fitid": "w1"}, {"data": "2026-10-05", "valor": -900, "descricao": "PADARIA", "fitid": "w2"}]
r8 = fn.importar_itens(con5, dois, "pluggy", "Meu Pluggy", "Itaú cartão de crédito")
confere("duas iguais no Pluggy e uma no extrato: entra só uma", r8["novas"] == 1 and r8["repetidas"] == 1, r8)
r9 = fn.importar_itens(con5, dois, "pluggy", "Meu Pluggy", "Itaú cartão de crédito")
confere("reler não muda nada", r9["novas"] == 0, r9)
con6 = fn.conectar(d / "w.db")
fn.importar_itens(con6, [{"data": "2026-10-05", "valor": -900, "descricao": "PADARIA", "fitid": "e1"}], "ofx", "x.ofx", "Itaú cartão de crédito")
con6.execute("INSERT INTO importacoes(arquivo, conta, quando, formato, novas, repetidas) VALUES('p','Itaú cartão de crédito','x','pluggy',2,0)")
iid6 = con6.execute("SELECT MAX(id) FROM importacoes").fetchone()[0]
for k in ("a", "b"):
    con6.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em,importacao_id) VALUES('Itaú cartão de crédito','2026-10-05',-900,'PADARIA','padaria','Outros',?,'x',?)", ("h" + k, iid6))
con6.commit()
fn.repetidos_entre_fontes(con6, True)
confere("primeira limpeza apaga uma", con6.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 2)
fn.repetidos_entre_fontes(con6, True)
confere("segunda limpeza não apaga a legítima", con6.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 2 and fn.repetidos_entre_fontes(con6) == {})
# parcelas: extrato 01/03; Pluggy 01/03 e 03/03 no mesmo dia e valor. Só a 01/03 do Pluggy repete.
con7 = fn.conectar(d / "x.db")
fn.importar_itens(con7, [{"data": "2026-08-05", "valor": -9300, "descricao": "PG *O RDEM ROSA 01/03"}], "ofx", "x.ofx", "Itaú cartão de crédito")
r10 = fn.importar_itens(con7, [{"data": "2026-08-05", "valor": -9300, "descricao": "PG *ORDEM ROSACRUZ03/03", "fitid": "z3"}, {"data": "2026-08-05", "valor": -9300, "descricao": "PG *ORDEM ROSACRUZ01/03", "fitid": "z1"}], "pluggy", "Meu Pluggy", "Itaú cartão de crédito")
confere("importação pareia pela descrição e parcela: entra a 03/03, pula a 01/03", r10["novas"] == 1 and con7.execute("SELECT COUNT(*) FROM transacoes WHERE descricao LIKE '%03/03'").fetchone()[0] == 1, r10)
con8 = fn.conectar(d / "y.db")
fn.importar_itens(con8, [{"data": "2026-08-05", "valor": -9300, "descricao": "PG *O RDEM ROSA 01/03"}], "ofx", "x.ofx", "Itaú cartão de crédito")
con8.execute("INSERT INTO importacoes(arquivo, conta, quando, formato, novas, repetidas) VALUES('p','Itaú cartão de crédito','x','pluggy',2,0)")
iid8 = con8.execute("SELECT MAX(id) FROM importacoes").fetchone()[0]
for k, ds in (("a", "PG *ORDEM ROSACRUZ01/03"), ("b", "PG *ORDEM ROSACRUZ03/03")):
    con8.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em,importacao_id) VALUES('Itaú cartão de crédito','2026-08-05',-9300,?,?,'Outros',?,'x',?)", (ds, ds.lower(), "g" + k, iid8))
con8.commit()
fn.repetidos_entre_fontes(con8, True)
confere("limpeza apaga a 01/03 do Pluggy e mantém a 03/03", [r[0] for r in con8.execute("SELECT descricao FROM transacoes ORDER BY id")] == ["PG *O RDEM ROSA 01/03", "PG *ORDEM ROSACRUZ03/03"], [r[0] for r in con8.execute("SELECT descricao FROM transacoes")])
sim = fp.simular(con, cfg, d / "sim.json", date(2026, 1, 1), hoje, fp.Cliente(cfg, api))
confere("simular devolve datas por conta e não grava", sim and all("primeira" in x for x in sim) and not (d / "sim.json").exists(), sim)
con9 = fn.conectar(d / "z.db")
fn.importar_itens(con9, [{"data": "2026-01-02", "valor": -100, "descricao": "ANTIGO EXTRATO"}], "ofx", "x.ofx", "Itaú conta corrente")
estz = d / "z.json"
r11 = fp.executar(con9, cfg, estz, None, hoje, fp.Cliente(cfg, api))
seco = fp.refazer_pelo_pluggy(con9, cfg, estz, date(2026, 1, 1), d / "bk", False, hoje, fp.Cliente(cfg, api))
confere("refazer sem aplicar só conta e não apaga", seco["contas"] and not (d / "bk").exists() and con9.execute("SELECT COUNT(*) FROM transacoes WHERE descricao='ANTIGO EXTRATO'").fetchone()[0] == 1, seco)
real = fp.refazer_pelo_pluggy(con9, cfg, estz, date(2026, 1, 1), d / "bk", True, hoje, fp.Cliente(cfg, api))
confere("refazer cria cópia do banco, apaga o extrato e relê pelo Pluggy", Path(real["backup"]).exists() and con9.execute("SELECT COUNT(*) FROM transacoes WHERE descricao='ANTIGO EXTRATO'").fetchone()[0] == 0 and sum(c["novas"] for c in real["sincronizado"]["contas"]) > 0, real)
import financas_consulta as fc
con10 = fn.conectar(d / "q.db")
fn.importar_itens(con10, [{"data": "2026-11-10", "valor": -2500, "descricao": "MERCADO X", "fitid": "1"}, {"data": "2026-11-11", "valor": 300000, "descricao": "SALARIO", "fitid": "2"}], "pluggy", "Meu Pluggy", "Itaú conta corrente")
confere("consulta: últimos lançamentos aceita pedaço do nome da conta", "R$ 3.000,00" in fc.texto_ultimos(con10, "itau") and "1. 11/11/2026" in fc.texto_ultimos(con10, "itau"))
try:
    fc.texto_ultimos(con10, "xyz")
    confere("conta desconhecida dá erro com a lista", False)
except ValueError as ex:
    confere("conta desconhecida dá erro com a lista", "Itaú conta corrente" in str(ex))
confere("consulta: resumo do mês", "entradas de R$ 3.000,00" in fc.texto_resumo(con10, "2026-11"))
txt = fc.texto_saldos({"ultima": "2026-11-18 05:00:00", "contas": {"a": {"nome": "Itaú conta corrente", "tipo": "BANK", "saldo": 10000}, "b": {"nome": "Itaú cartão de crédito", "tipo": "CREDIT", "saldo": 4000}}})
confere("consulta: saldos separam conta e cartão e somam", "saldo de R$ 100,00" in txt and "usado do limite (saldo devedor total, com parcelas futuras) de R$ 40,00" in txt and "Diferença: R$ 60,00" in txt, txt)
r_est = fp.ler_estado(d / "estado.json")
confere("sincronização guarda o saldo no estado", all("saldo" in g for g in r_est["contas"].values()), r_est["contas"])
dc = fp._dados_cartao({"creditData": {"creditLimit": 15000.0, "availableCreditLimit": 2939.69, "balanceDueDate": "2026-12-05T00:00:00.000Z", "minimumPayment": 1200.5}})
confere("dados do cartão: limite, disponível, vencimento e mínimo", dc == {"limite": 1500000, "disponivel": 293969, "minimo": 120050, "vence": "2026-12-05"}, dc)
txt2 = fc.texto_saldos({"contas": {"b": {"nome": "Itaú cartão de crédito", "tipo": "CREDIT", "saldo": 1206031, "credito": dc}}})
confere("saldos mostram limite, usado e vencimento do cartão", "limite de R$ 15.000,00" in txt2 and "usado do limite (saldo devedor total, com parcelas futuras) de R$ 12.060,31" in txt2 and "vence em 05/12/2026" in txt2, txt2)
pf = fp._proxima_fatura([{"dueDate": "2026-11-05T00:00:00.000Z", "totalAmount": 900.0}, {"dueDate": "2026-12-05T00:00:00.000Z", "totalAmount": 1234.56}], date(2026, 11, 18))
confere("próxima fatura é a que vence daqui para a frente", pf == {"fatura_vence": "2026-12-05", "fatura_valor": 123456, "fatura_aberta": True}, pf)
txt3 = fc.texto_saldos({"contas": {"b": {"nome": "Itaú cartão de crédito", "tipo": "CREDIT", "saldo": 1206031, "credito": {**dc, **pf}}}})
confere("saldos mostram a fatura a vencer", "fatura a vencer de R$ 1.234,56, vence em 05/12/2026" in txt3, txt3)
# fatura em aberto calculada pelo fechamento
con11 = fn.conectar(d / "f.db")
fn.importar_itens(con11, [{"data": "2026-10-20", "valor": -10000, "descricao": "ANTES", "fitid": "a"}, {"data": "2026-10-28", "valor": -20000, "descricao": "COMPRA 1", "fitid": "b"},
                          {"data": "2026-11-10", "valor": -30000, "descricao": "COMPRA 2", "fitid": "c"}, {"data": "2026-11-12", "valor": 99000, "descricao": "PAGAMENTO RECEBIDO", "fitid": "d"},
                          {"data": "2026-11-15", "valor": 5000, "descricao": "ESTORNO LOJA", "fitid": "e"}], "pluggy", "Meu Pluggy", "Itaú cartão de crédito")
v, ini = fc.fatura_calculada(con11, "Itaú cartão de crédito", {"dia": 27}, date(2026, 11, 18))
confere("fatura calculada: compras desde o dia seguinte ao fechamento, sem pagamento, com estorno", v == 45000 and ini == date(2026, 10, 28), (v, ini))
est5 = {"contas": {"x": {"nome": "Itaú cartão de crédito", "tipo": "CREDIT", "saldo": 1000}, "y": {"nome": "Nubank cartão de crédito", "tipo": "CREDIT", "saldo": 1}}}
confere("definir fechamento acha o cartão por pedaço do nome", fp.definir_fechamento(est5, "itau", "1:7") == "Itaú cartão de crédito" and est5["contas"]["x"]["fechamento"] == {"vence": 1, "antes": 7})
try:
    fp.definir_fechamento(est5, "cartao", 3)
    confere("nome ambíguo dá erro", False)
except fp.ErroPluggy:
    confere("nome ambíguo dá erro", True)
txt4 = fc.texto_saldos(est5, con11, date(2026, 11, 18))
fe = fc._ultimo_fechamento
confere("vence dia 1 e fecha 7 dias antes: 18/11 → 25/10... depende do mês; 24/11 e 02/12 → 24/11", fe(date(2026, 11, 18), {"vence": 1, "antes": 7}) == date(2026, 10, 25) and fe(date(2026, 11, 24), {"vence": 1, "antes": 7}) == date(2026, 11, 24) and fe(date(2026, 12, 2), {"vence": 1, "antes": 7}) == date(2026, 11, 24), [fe(date(2026, 11, 18), {"vence": 1, "antes": 7}), fe(date(2026, 11, 24), {"vence": 1, "antes": 7}), fe(date(2026, 12, 2), {"vence": 1, "antes": 7})])
confere("saldos mostram a fatura em aberto calculada", "fatura em aberto de R$ 450,00" in txt4, txt4)
# credencial errada
try:
    fp.Cliente({**cfg, "segredo": "errado"}, api).chave()
    confere("credencial errada dá mensagem clara", False)
except fp.ErroPluggy as ex:
    confere("credencial errada dá mensagem clara, sem o segredo", "recusou" in str(ex) and "errado" not in str(ex), str(ex))
# --desde
r3 = fp.executar(con, cfg, d / "e2.json", date(2026, 11, 1), hoje, fp.Cliente(cfg, api))
confere("--desde força o início", all(c["desde"] == "2026-11-01" for c in r3["contas"]), r3["contas"])
# autorização expirada
def api_exp(metodo, caminho, params=None, corpo=None, chave=""):
    if caminho.startswith("/items/"):
        return {"status": "LOGIN_ERROR", "error": {"code": "USER_AUTHORIZATION_EXPIRED"}}
    return api(metodo, caminho, params, corpo, chave)
r4 = fp.executar(con, cfg, d / "e3.json", None, hoje, fp.Cliente(cfg, api_exp))
confere("autorização expirada gera aviso para renovar", any("expirou" in a for a in r4["avisos"]), r4["avisos"])
# item indisponível (Meu Pluggy não libera /items): segue sem aviso
def api_sem_item(metodo, caminho, params=None, corpo=None, chave=""):
    if caminho.startswith("/items/"):
        raise fp.ErroPluggy("O Pluggy respondeu com erro 403.")
    return api(metodo, caminho, params, corpo, chave)
r5 = fp.executar(con, cfg, d / "e4.json", None, hoje, fp.Cliente(cfg, api_sem_item))
confere("item indisponível não derruba a sincronização", len(r5["contas"]) == 2 and r5["avisos"] == [])
# .env
env = d / ".env"
env.write_text("OUTRA=1\nHEIMDALL_PLUGGY_CLIENT_ID=velho\n", encoding="utf-8")
msg = fp.guardar_chave("id", U, env)
confere("guardar chave troca a linha antiga e não imprime o valor", f"HEIMDALL_PLUGGY_CLIENT_ID={U}" in env.read_text() and "velho" not in env.read_text() and U not in msg and "OUTRA=1" in env.read_text(), msg)
fp.guardar_chave("segredo", "segredo-correto-123456", env)
fp.guardar_chave("itens", f"{U}, 99999999-2222-3333-4444-555555555555", env)
fp.guardar_chave("itens", "88888888-2222-3333-4444-555555555555", env)
fp.guardar_chave("itens", U, env)
c = fp.credenciais(env)
fp.guardar_chave("itens", f"https://dashboard.pluggy.ai/applications/1000908b-ab01-445a-94f5-427a254ff17f/demo?item=77777777-2222-3333-4444-555555555555", env)
confere("endereço da página Demo: grava só o id do item, não o da aplicação", "77777777-2222-3333-4444-555555555555" in env.read_text() and "1000908b" not in env.read_text())
c = fp.credenciais(env)
confere("credenciais lidas do .env com vários itens", c["id"] == U and c["segredo"] == "segredo-correto-123456" and len(c["itens"]) == 4, c)
confere("o .env fica com permissão 600", oct(env.stat().st_mode)[-3:] == "600")
for qual, v in (("id", "isto não é uuid"), ("itens", "abc"), ("segredo", "curto"), ("id", U + "\noutra")):
    try:
        fp.guardar_chave(qual, v, env)
        confere(f"valor inválido recusado ({qual})", False)
    except fp.ErroPluggy:
        confere(f"valor inválido recusado ({qual})", True)
confere("sem as três chaves, não há credenciais", fp.credenciais(d / "nao-existe.env") == {})
fonte = Path(fp.__file__).read_text(encoding="utf-8")
confere("o módulo só chama api.pluggy.ai, sem redirecionar, e não escreve em banco algum", 'BASE = "https://api.pluggy.ai"' in fonte and "_SemRedirecionar" in fonte and '"PATCH"' not in fonte and '"PUT"' not in fonte and '"DELETE"' not in fonte)

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
