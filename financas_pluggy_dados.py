#!/usr/bin/env python3
"""Tudo o que o Pluggy entrega além das transações, guardado nos conjuntos do Finance (financas_planilhas): contas e cartões (saldo, limite, fechamento),
faturas de cartão, investimentos, movimentações de investimentos e empréstimos e financiamentos. Cada coleta vira uma foto do dia (coluna "Coletado em"),
então o histórico de saldos e posições se forma sozinho. Nenhuma coluna do Pluggy é descartada: o que não tem nome conhecido entra com o nome original.
Fica de fora de propósito a identidade (CPF, endereço, telefones). Falha em um produto (o plano pode não liberar) nunca atrapalha as transações."""
import json
from datetime import date, datetime

import financas_nucleo as fn
import financas_planilhas as fp

NOME_CONTAS = "Pluggy: contas e cartões"
NOME_FATURAS = "Pluggy: faturas de cartão"
NOME_INVEST = "Pluggy: investimentos"
NOME_MOV = "Pluggy: movimentações de investimentos"
NOME_EMPREST = "Pluggy: empréstimos e financiamentos"
MAX_INVESTIMENTOS_COM_MOVIMENTOS = 60
MAX_PAGINAS = 20

TIPOS_INVEST = {"FIXED_INCOME": "Renda fixa", "MUTUAL_FUND": "Fundo", "EQUITY": "Renda variável", "ETF": "ETF", "SECURITY": "Previdência e outros títulos",
                "COE": "COE", "OTHER": "Outros"}
TIPOS_CONTA = {"BANK": "Conta bancária", "CREDIT": "Cartão de crédito"}

# (chave do Pluggy com pontos, rótulo): vão primeiro e com nome em português; o resto entra depois com o nome original
PRIMEIRAS = {
    "contas": [("name", "Nome"), ("type", "Tipo"), ("subtype", "Subtipo"), ("number", "Número"), ("balance", "Saldo"), ("currencyCode", "Moeda"),
               ("creditData.creditLimit", "Limite do cartão"), ("creditData.availableCreditLimit", "Limite disponível"), ("creditData.balanceCloseDate", "Fechamento da fatura"),
               ("creditData.balanceDueDate", "Vencimento da fatura"), ("creditData.minimumPayment", "Pagamento mínimo"), ("creditData.brand", "Bandeira"),
               ("creditData.level", "Nível do cartão"), ("bankData.transferNumber", "Agência e conta"), ("bankData.closingBalance", "Saldo de fechamento"),
               ("bankData.automaticallyInvestedBalance", "Saldo investido automaticamente"), ("bankData.overdraftContractedLimit", "Limite do cheque especial"),
               ("bankData.overdraftUsedLimit", "Cheque especial usado")],
    "faturas": [("cartao", "Cartão"), ("dueDate", "Vencimento"), ("totalAmount", "Total da fatura"), ("minimumPaymentAmount", "Pagamento mínimo"),
                ("allowsInstallments", "Permite parcelar"), ("financeCharges", "Encargos"), ("totalAmountCurrencyCode", "Moeda")],
    "investimentos": [("name", "Nome"), ("classe", "Classe"), ("type", "Tipo"), ("subtype", "Subtipo"), ("instituicao", "Instituição"), ("balance", "Valor atual"),
                      ("amount", "Valor investido"), ("quantity", "Quantidade"), ("value", "Preço unitário"), ("rate", "Taxa contratada"), ("rateType", "Indexador"),
                      ("annualRate", "Rentabilidade anual"), ("lastMonthRate", "Rentabilidade no último mês"), ("lastTwelveMonthsRate", "Rentabilidade em 12 meses"),
                      ("taxes", "Impostos"), ("date", "Data da aplicação"), ("dueDate", "Vencimento"), ("issuer", "Emissor"), ("code", "Código"), ("status", "Situação"),
                      ("owner", "Titular"), ("currencyCode", "Moeda")],
    "mov": [("investimento", "Investimento"), ("date", "Data"), ("type", "Tipo"), ("movementType", "Entrada ou saída"), ("description", "Descrição"),
            ("quantity", "Quantidade"), ("value", "Preço unitário"), ("amount", "Valor"), ("tradeDate", "Data da operação"), ("netAmount", "Valor líquido"),
            ("brokerageNumber", "Corretora")],
    "emprestimos": [("productName", "Produto"), ("modalidade", "Modalidade"), ("credor", "Credor"), ("type", "Tipo no Open Finance"), ("contractNumber", "Contrato"),
                    ("contractDate", "Data da contratação"), ("dueDate", "Vencimento final"), ("firstInstallmentDueDate", "Primeira parcela"),
                    ("payments.contractOutstandingBalance", "Saldo devedor"), ("installments.paidInstallments", "Parcelas pagas"),
                    ("installments.dueInstallments", "Parcelas a vencer"), ("installments.pastDueInstallments", "Parcelas em atraso"),
                    ("installments.totalNumberOfInstallments", "Total de parcelas"), ("CET", "CET"), ("amortizationScheduled", "Amortização"),
                    ("contractAmount", "Valor contratado"), ("installmentPeriodicity", "Periodicidade")],
}


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (int, float)):
        return fp._formatar_numero(str(v))
    s = str(v).strip()
    if len(s) >= 19 and s[4:5] == "-" and s[10:11] == "T":
        return s[:10]
    return s


def achatar(d, pref: str = "", prof: int = 0, saida: dict = None) -> dict:
    """{'a.b': 'texto'}: objetos viram chaves com ponto; listas de valores simples viram texto separado por vírgula; listas de objetos viram JSON curto."""
    saida = {} if saida is None else saida
    for k, v in (d or {}).items():
        chave = f"{pref}{k}"
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, dict):
            if prof >= 3:
                saida[chave] = json.dumps(v, ensure_ascii=False)[:300]
            else:
                achatar(v, chave + ".", prof + 1, saida)
        elif isinstance(v, list):
            saida[chave] = ", ".join(_fmt(x) for x in v) if all(not isinstance(x, (dict, list)) for x in v) else json.dumps(v, ensure_ascii=False)[:300]
        else:
            saida[chave] = _fmt(v)
    return saida


def _chave(flat: str) -> str:
    return fp.chaves_das_colunas([flat])[0]


def _tabela(colecao: str, linhas_planas: list) -> tuple:
    """(colunas[(chave, rótulo)], linhas[dict chave->texto]) com as colunas conhecidas primeiro e todas as outras depois."""
    conhecidas = PRIMEIRAS[colecao]
    usadas = {k for k, _ in conhecidas}
    extras = sorted({k for l in linhas_planas for k in l} - usadas)
    cols = [(k, r) for k, r in conhecidas if any(k in l for l in linhas_planas)] + [(k, k) for k in extras]
    cols = cols[:fp.MAX_COLUNAS]
    colunas = [(_chave(k), r) for k, r in cols]
    linhas = [{_chave(k): l.get(k, "") for k, _ in cols} for l in linhas_planas]
    return colunas, linhas


def _lista(cli, caminho: str, params: dict) -> list:
    saida, pagina = [], 1
    while pagina <= MAX_PAGINAS:
        r = cli.get(caminho, dict(params, pageSize=500, page=pagina))
        saida += r.get("results") or []
        if pagina >= int(r.get("totalPages") or 1):
            break
        pagina += 1
    return saida


def _tentar(cli, caminho: str, params: dict, indisponiveis: dict, nome: str) -> list:
    try:
        return _lista(cli, caminho, params)
    except Exception as ex:  # noqa: BLE001  (produto não liberado no plano, banco sem o dado ou erro passageiro)
        indisponiveis[nome] = str(ex)[:120]
        return []


def coletar_extras(cli, itens: list, contas: list, faturas_por_conta: dict, hoje: date = None) -> dict:
    """Parte de rede. Devolve linhas planas por coleção e o que não veio."""
    hoje = hoje or date.today()
    ind = {}
    saida = {"contas": [], "faturas": [], "investimentos": [], "mov": [], "emprestimos": [], "indisponiveis": ind}
    nome_conta = {c["id"]: c.get("name") or c.get("marketingName") or "Cartão" for c in contas}
    for c in contas:
        saida["contas"].append(achatar({k: v for k, v in c.items() if k not in ("itemId",)}))
    for cid, faturas in (faturas_por_conta or {}).items():
        for f in faturas:
            l = achatar(f)
            l["cartao"] = nome_conta.get(cid, "Cartão")
            saida["faturas"].append(l)
    for item_id in itens:
        conector = ""
        try:
            conector = ((cli.item(item_id) or {}).get("connector") or {}).get("name") or ""
        except Exception:  # noqa: BLE001
            conector = ""
        invs = _tentar(cli, "/investments", {"itemId": item_id}, ind, "investimentos")
        for i in invs:
            l = achatar({k: v for k, v in i.items() if k not in ("itemId", "metadata")})
            tipo = TIPOS_INVEST.get(str(i.get("type")), str(i.get("type") or "")) or "Sem tipo"
            l["classe"] = f"{tipo} ({i['subtype']})" if i.get("subtype") else tipo
            l["instituicao"] = ((i.get("institution") or {}).get("name") or conector)
            l.pop("institution.name", None)
            l.pop("institution.number", None)
            saida["investimentos"].append(l)
        for i in invs[:MAX_INVESTIMENTOS_COM_MOVIMENTOS]:
            try:
                movs = []
                pagina = 1
                while pagina <= 5:
                    r = cli.get(f"/investments/{i['id']}/transactions", {"pageSize": 500, "page": pagina})
                    movs += r.get("results") or []
                    if pagina >= int(r.get("totalPages") or 1):
                        break
                    pagina += 1
            except Exception as ex:  # noqa: BLE001
                ind["movimentações de investimentos"] = str(ex)[:120]
                break
            for m in movs:
                l = achatar({k: v for k, v in m.items() if k not in ("id",)})
                l["investimento"] = i.get("name") or ""
                saida["mov"].append(l)
        for e in _tentar(cli, "/loans", {"itemId": item_id}, ind, "empréstimos e financiamentos"):
            l = achatar({k: v for k, v in e.items() if k not in ("itemId",)})
            l["credor"] = conector
            l["modalidade"] = fp.CATEGORIAS_CREDITO[fp.categoria_credito(f"{e.get('type', '')} {e.get('productName', '')}")]
            saida["emprestimos"].append(l)
    saida["coletado_em"] = hoje.isoformat()
    return saida


def _gravar(con, nome: str, tipo: str, colecao: str, linhas_planas: list, papeis: dict, dia: str, agora: str, principais: list) -> int:
    if not linhas_planas:
        return 0
    for l in linhas_planas:
        l["coletado_em"] = dia
    PRIMEIRAS_LOCAL = PRIMEIRAS[colecao]
    colunas, linhas = _tabela(colecao, linhas_planas)
    colunas.append(("coletado_em", "Coletado em"))
    for l in linhas:
        l["coletado_em"] = dia
    cid_papeis = {p: (_chave(k) if k != "coletado_em" else "coletado_em") for p, k in papeis.items()}
    chaves = [k for k, _ in colunas]
    cid = fp._achar_ou_criar_conjunto(con, nome, tipo, [[k, r] for k, r in colunas], cid_papeis, agora)
    novas, _ = fp._gravar_registros(con, cid, chaves, [[l.get(k, "") for k in chaves] for l in linhas], "Meu Pluggy", agora)
    if con.execute("SELECT 1 FROM visoes WHERE conjunto_id=? AND nome='Principais'", (cid,)).fetchone() is None:
        cols = [_chave(k) for k, _ in PRIMEIRAS_LOCAL if _chave(k) in chaves] + ["coletado_em"]
        vid = fp.criar_visao(con, cid, "Principais", agora)
        cfg = fp.visao(con, vid)["cfg"]
        cfg["colunas"] = cols
        fp._salvar_cfg(con, vid, cfg)
    con.commit()
    return novas


def gravar(con, extras: dict, agora: str = None) -> dict:
    """Parte local. Devolve {coleção: linhas lidas} e o que não veio."""
    if not extras:
        return {}
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dia = extras.get("coletado_em") or agora[:10]
    n = {}
    pap_inv = {"ativo": "name", "tipo_ativo": "classe", "instituicao": "instituicao", "quantidade": "quantity", "preco": "value", "valor": "balance",
               "data": "coletado_em", "rentabilidade": "annualRate", "lote": "coletado_em", "id": "id"}
    pap_emp = {"contrato": "productName", "credor": "credor", "saldo": "payments.contractOutstandingBalance", "taxa": "CET", "vencimento": "dueDate",
               "restantes": "installments.dueInstallments", "lote": "coletado_em", "id": "id"}
    cfg = [
        ("contas", NOME_CONTAS, "contas", "contas", {"lote": "coletado_em", "id": "id"}),
        ("faturas", NOME_FATURAS, "faturas", "faturas", {"lote": "coletado_em", "id": "id"}),
        ("investimentos", NOME_INVEST, "investimentos", "investimentos", pap_inv),
        ("mov", NOME_MOV, "movimentos", "mov", {}),
        ("emprestimos", NOME_EMPREST, "emprestimos", "emprestimos", pap_emp),
    ]
    for chave, nome, tipo, colecao, papeis in cfg:
        linhas = extras.get(chave) or []
        n[chave] = len(linhas)
        _gravar(con, nome, tipo, colecao, linhas, papeis, dia, agora, [])
    n["indisponiveis"] = extras.get("indisponiveis") or {}
    return n
