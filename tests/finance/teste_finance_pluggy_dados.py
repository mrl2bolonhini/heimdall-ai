#!/usr/bin/env python3
"""Testa a coleta de tudo o que o Pluggy entrega (contas, faturas, investimentos, movimentações, empréstimos) com uma API simulada, as categorias de crédito e as abas dinâmicas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import financas_nucleo as fn  # noqa: E402
import financas_planilhas as fp  # noqa: E402
import financas_pluggy_dados as pd  # noqa: E402
import financas_pluggy as fpl  # noqa: E402
import heimdall_finance as hf  # noqa: E402
import heimdall_finance_planilhas as hfp  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:500])


CONTAS = [
    {"id": "c1", "itemId": "i1", "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "Conta Corrente", "number": "1234-5", "balance": 1500.5, "currencyCode": "BRL",
     "bankData": {"transferNumber": "0001/1234-5", "overdraftContractedLimit": 1000, "overdraftUsedLimit": 0}},
    {"id": "c2", "itemId": "i1", "type": "CREDIT", "subtype": "CREDIT_CARD", "name": "Cartão Black", "balance": 800, "currencyCode": "BRL",
     "creditData": {"creditLimit": 10000, "availableCreditLimit": 9200, "balanceCloseDate": "2026-12-05", "balanceDueDate": "2026-12-12", "minimumPayment": 120, "brand": "MASTERCARD", "level": "BLACK"}},
]
FATURAS = {"c2": [{"id": "f1", "dueDate": "2026-12-12T00:00:00.000Z", "totalAmount": 800, "minimumPaymentAmount": 120, "allowsInstallments": True, "financeCharges": []}]}
INVESTIMENTOS = [
    {"id": "v1", "itemId": "i1", "name": "CDB Banco X", "balance": 2000, "amount": 1900, "type": "FIXED_INCOME", "subtype": "CDB", "annualRate": 11.5, "date": "2025-01-02T00:00:00.000Z",
     "institution": {"name": "Banco X", "number": "1"}},
    {"id": "v2", "itemId": "i1", "name": "PETR4", "balance": 3500, "quantity": 100, "value": 35, "type": "EQUITY", "subtype": "STOCK", "code": "PETR4"},
]
MOVS = [{"id": "m1", "type": "BUY", "movementType": "DEBIT", "description": "Compra", "quantity": 100, "value": 30, "amount": 3000, "date": "2025-03-01T00:00:00.000Z"}]
EMPRESTIMOS = [
    {"id": "l1", "itemId": "i1", "productName": "Crédito Pessoal Consignado", "type": "CREDITO_PESSOAL_COM_CONSIGNACAO", "contractNumber": "111", "contractDate": "2022-08-01T00:00:00",
     "dueDate": "2030-08-01T00:00:00", "CET": 0.29, "installments": {"paidInstallments": 65, "dueInstallments": 55, "pastDueInstallments": 0}, "payments": {"contractOutstandingBalance": 25000}},
    {"id": "l2", "itemId": "i1", "productName": "Financiamento de Veículo", "type": "FINANCIAMENTOS_AQUISICAO_BENS_VEICULOS_AUTOMOTORES", "contractNumber": "222",
     "installments": {"paidInstallments": 10, "dueInstallments": 38}, "payments": {"contractOutstandingBalance": 42000}},
    {"id": "l3", "itemId": "i1", "productName": "Financiamento Habitacional", "type": "FINANCIAMENTOS_IMOBILIARIOS", "contractNumber": "333", "payments": {"contractOutstandingBalance": 310000}},
]


class Falso:
    def __init__(self, bloquear=()):
        self.bloquear = bloquear
        self.chamadas = []

    def item(self, i):
        return {"connector": {"name": "Banco X"}}

    def get(self, caminho, params=None):
        self.chamadas.append(caminho)
        if any(b in caminho for b in self.bloquear):
            raise fpl.ErroPluggy("O Pluggy respondeu com erro 403.")
        if caminho == "/investments":
            return {"results": INVESTIMENTOS, "totalPages": 1}
        if caminho.startswith("/investments/") and caminho.endswith("/transactions"):
            return {"results": MOVS if "v1" in caminho else [], "totalPages": 1}
        if caminho == "/loans":
            return {"results": EMPRESTIMOS, "totalPages": 1}
        raise AssertionError(caminho)


con = fn.conectar(Path(tempfile.mkdtemp()) / "f.db")
cli = Falso()
ex = pd.coletar_extras(cli, ["i1"], CONTAS, FATURAS, date(2026, 11, 22))
confere("coleta lê investimentos, movimentações e empréstimos", len(ex["investimentos"]) == 2 and len(ex["mov"]) == 1 and len(ex["emprestimos"]) == 3 and not ex["indisponiveis"], ex["indisponiveis"])
confere("achatar traz os campos aninhados com ponto", ex["contas"][1]["creditData.creditLimit"] == "10000" and ex["contas"][0]["bankData.transferNumber"] == "0001/1234-5")
confere("datas ISO viram AAAA-MM-DD e números usam vírgula", ex["investimentos"][0]["date"] == "2025-01-02" and ex["contas"][0]["balance"] == "1500,5", ex["investimentos"][0])
confere("a identidade não é coletada", "/identity" not in cli.chamadas)
r = pd.gravar(con, ex, "2026-11-22 10:00:00")
confere("tudo é gravado em conjuntos", r["contas"] == 2 and r["faturas"] == 1 and r["investimentos"] == 2 and r["mov"] == 1 and r["emprestimos"] == 3, r)
nomes = {c["nome"]: c for c in fp.conjuntos(con)}
confere("cinco conjuntos do Pluggy", all(n in nomes for n in (pd.NOME_CONTAS, pd.NOME_FATURAS, pd.NOME_INVEST, pd.NOME_MOV, pd.NOME_EMPREST)), list(nomes))
confere("visão Principais criada com as colunas conhecidas primeiro", fp.visoes(con, nomes[pd.NOME_INVEST]["id"])[0]["cfg"]["colunas"][:3] == ["name", "classe", "type"], fp.visoes(con, nomes[pd.NOME_INVEST]["id"]))
antes = sum(c["n"] for c in fp.conjuntos(con))
pd.gravar(con, ex, "2026-11-22 12:00:00")
confere("sem mudança nada é regravado", antes == sum(c["n"] for c in fp.conjuntos(con)))
# outro dia, saldo mudou: nova foto
CONTAS[0]["balance"] = 1600
ex2 = pd.coletar_extras(Falso(), ["i1"], CONTAS, FATURAS, date(2026, 11, 23))
pd.gravar(con, ex2, "2026-11-23 10:00:00")
atual = fp.linhas_atuais(con, pd.NOME_CONTAS)
confere("a foto mais recente vale e o histórico fica", any(d["balance"] == "1600" for d in atual) and not any(d["balance"] == "1500,5" for d in atual)
        and next(c for c in fp.conjuntos(con) if c["nome"] == pd.NOME_CONTAS)["n"] == 4)

# investimentos e categorias
inv = fp.resumo_investimentos(con)
confere("investimentos do Pluggy: total e classe", inv["total"] == 550000 and dict(inv["por_tipo"]).get("Renda fixa (CDB)") == 200000, inv)
cats = fp.categorias_de_credito(con)
confere("categorias de crédito achadas pelos tipos do Open Finance", [k for k, _ in cats] == ["veiculo", "imovel", "consignado"], cats)
e = fp.resumo_emprestimos(con, "consignado")
confere("consignado: saldo, parcelas pagas e a vencer", e["saldo"] == 2500000 and e["itens"][0]["pagas"] == "65" and e["itens"][0]["restantes"] == "55" and e["itens"][0]["credor"] == "Banco X", e)
confere("classificador de texto", [fp.categoria_credito(x) for x in ("Crédito Pessoal Consignado", "CDC veículo Santander", "Financiamento Habitacional Caixa", "Empréstimo pessoal Nubank", "Cheque especial")]
        == ["consignado", "veiculo", "imovel", "pessoal", "outros"])

# planilha de dívidas entra nas mesmas categorias
import teste_planilhas_util as u  # noqa: E402
emp = u.xlsx({"Dívidas": [["Contrato", "Credor", "Saldo devedor", "Valor da parcela"], ["Empréstimo pessoal Nubank", "Nubank", 5000, 300]]})
fp.processar(con, emp, "dividas.xlsx", Path(tempfile.mkdtemp()), usar_modelo=False)
confere("dívida de planilha vira empréstimo pessoal", [k for k, _ in fp.categorias_de_credito(con)] == ["veiculo", "imovel", "consignado", "pessoal"], fp.categorias_de_credito(con))

# produto não liberado no plano
bloq = pd.coletar_extras(Falso(("/loans", "/investments")), ["i1"], CONTAS, FATURAS)
confere("produto bloqueado vira aviso e não derruba a coleta", "empréstimos e financiamentos" in bloq["indisponiveis"] and "investimentos" in bloq["indisponiveis"] and bloq["contas"], bloq["indisponiveis"])
con_vazio = fn.conectar(Path(tempfile.mkdtemp()) / "v.db")
confere("sem dados as abas dinâmicas não aparecem", [r for r, _ in hfp.nav(con_vazio, hf.NAV)] == [r for r, _ in hf.NAV])

# abas e páginas
fn.importar_itens(con, [{"data": "2026-11-20", "valor": -5000, "descricao": "Mercado"}], "ofx", "x", "Itaú conta")
fn.importar_itens(con, [{"data": "2026-11-20", "valor": -9000, "descricao": "Loja"}], "ofx", "x", "Nubank cartão")
rotas = [r for r, _ in hfp.nav(con, hf.NAV)]
confere("abas criadas pelos dados, depois de Transações", rotas[:2] == ["/", "/transacoes"] and rotas[2:9] == ["/contas", "/cartoes", "/investimentos", "/emprestimos", "/credito/veiculo", "/credito/imovel", "/credito/consignado"] and "/credito/pessoal" in rotas, rotas)
rot = hfp.nav(con, hf.NAV)
confere("rótulos em português", ("/credito/veiculo", "Financiamento de veículo") in rot and ("/credito/imovel", "Financiamento imobiliário") in rot and ("/credito/consignado", "Consignado") in rot)
t, c = hfp.get(con, "/contas", {}, {"csrf": "x"}, None)
confere("Contas separa extrato de cartão e mostra saldo do banco", "Itaú conta" in c and "Nubank cartão" not in c and "R$ 1.600,00" in c and "Cheque especial" in c, c[:300])
t, c = hfp.get(con, "/cartoes", {}, {"csrf": "x"}, None)
confere("Cartões mostra limite, fechamento e faturas", "Nubank cartão" in c and "R$ 10.000,00" in c and "2026-12-05" in c and "R$ 800,00" in c and "Faturas dos cartões" in c, c[:400])
t, c = hfp.get(con, "/credito/imovel", {}, {"csrf": "x"}, None)
confere("aba de financiamento imobiliário", t == "Financiamento imobiliário" and "R$ 310.000,00" in c, c[:300])
t, c = hfp.get(con, "/emprestimos", {}, {"csrf": "x"}, None)
confere("visão geral das dívidas soma por tipo", "Dívidas por tipo" in c and "<caption>" in c and "Consignado" in c, c[:300])
confere("rota de crédito inexistente não existe", hfp.get(con, "/credito/outros", {}, {"csrf": "x"}, None)[1].startswith("<p>Ainda não há dados"))
confere("só categorias conhecidas são rota", hfp.eh_rota_get("/credito/veiculo") and not hfp.eh_rota_get("/credito/xyz"))

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
