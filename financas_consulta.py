"""Consultas do Finance para o terminal: saldo das contas, últimos lançamentos e resumo do mês.
Só lê o banco local e o estado da última sincronização; nada vai para a internet. Texto corrido e listas numeradas, bom para leitor de tela."""
from __future__ import annotations

from datetime import date, timedelta
import calendar

import financas_nucleo as fn


def _real(c: int) -> str:
    return fn.brl(c)


def resolver_conta(con, trecho: str) -> str:
    """Nome exato da conta a partir de um pedaço do nome (sem acento nem maiúsculas). Erro com a lista quando há dúvida."""
    nomes = [r["conta"] for r in con.execute("SELECT DISTINCT conta FROM transacoes ORDER BY conta")]
    if not trecho:
        return ""
    alvo = fn.norm(trecho)
    exatas = [n for n in nomes if fn.norm(n) == alvo]
    if exatas:
        return exatas[0]
    achadas = [n for n in nomes if alvo in fn.norm(n)]
    if len(achadas) == 1:
        return achadas[0]
    if not achadas:
        raise ValueError("Não encontrei essa conta. As contas são: " + "; ".join(nomes) + ".")
    raise ValueError("Mais de uma conta combina: " + "; ".join(achadas) + ". Escreva um pedaço maior do nome.")


def _ultimo_fechamento(hoje: date, regra) -> date:
    """Data do último fechamento até hoje. `regra` é um dia fixo do mês (int ou {"dia": 27}) ou {"vence": 1, "antes": 7} (fecha N dias antes do vencimento)."""
    if isinstance(regra, int):
        regra = {"dia": regra}

    def em(ano, mes, dia):
        return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))
    candidatas = []
    for desloc in (-2, -1, 0, 1):
        mes0 = hoje.month - 1 + desloc
        ano, mes = hoje.year + mes0 // 12, mes0 % 12 + 1
        if "dia" in regra:
            candidatas.append(em(ano, mes, regra["dia"]))
        else:
            candidatas.append(em(ano, mes, regra["vence"]) - timedelta(days=regra["antes"]))
    return max(c for c in candidatas if c <= hoje)


def fatura_calculada(con, conta: str, regra, hoje: date = None) -> tuple:
    """Fatura em aberto estimada pelas compras do cartão desde o dia seguinte ao último fechamento. Devolve (centavos, início)."""
    hoje = hoje or date.today()
    inicio = _ultimo_fechamento(hoje, regra) + timedelta(days=1)
    total = 0
    for r in con.execute("SELECT valor, desc_norm, categoria FROM transacoes WHERE conta=? AND data>=? AND data<=?", (conta, inicio.isoformat(), hoje.isoformat())):
        if r["valor"] > 0 and any(p in r["desc_norm"] for p in ("pagamento", "pgto", "pag fatura", "fatura")):
            continue  # pagamento da fatura anterior não reduz a fatura nova
        total += -r["valor"]
    return total, inicio


def texto_saldos(estado: dict, con=None, hoje: date = None) -> str:
    contas = [g for g in (estado.get("contas") or {}).values() if g.get("nome")]
    if not contas:
        return "Ainda não há saldos: rode antes heimdall finance --sync."
    linhas, disponivel, devido, sem = [], 0, 0, 0
    ordem = sorted(contas, key=lambda g: ((g.get("tipo") or "").upper() == "CREDIT", g["nome"]))
    for i, g in enumerate(ordem, 1):
        cartao = (g.get("tipo") or "").upper() == "CREDIT"
        s = g.get("saldo")
        if s is None:
            sem += 1
            linhas.append(f"{i}. {g['nome']}: saldo não informado.")
            continue
        if cartao:
            devido += s
            cr = g.get("credito") or {}
            extra = []
            if "limite" in cr:
                extra.append(f"limite de {_real(cr['limite'])}")
            if "disponivel" in cr:
                extra.append(f"disponível {_real(cr['disponivel'])}")
            if cr.get("fecha"):
                extra.append(f"fatura fecha em {fn.data_br(cr['fecha'])}")
            if cr.get("vence") and "fatura_valor" not in cr:
                extra.append(f"vence em {fn.data_br(cr['vence'])}")
            if "minimo" in cr:
                extra.append(f"pagamento mínimo {_real(cr['minimo'])}")
            fat = ""
            if "fatura_valor" in cr:
                fat = (f"fatura a vencer de {_real(cr['fatura_valor'])}, vence em {fn.data_br(cr['fatura_vence'])}; " if cr.get("fatura_aberta")
                       else f"última fatura de {_real(cr['fatura_valor'])}, venceu em {fn.data_br(cr['fatura_vence'])}; ")
            if con is not None and g.get("fechamento"):
                v, ini = fatura_calculada(con, g["nome"], g["fechamento"], hoje)
                fat = f"fatura em aberto de {_real(v)} (calculada pelas compras desde {fn.data_br(ini.isoformat())}); " + ("" if not fat else "além disso, " + fat)
            linhas.append(f"{i}. {g['nome']}: {fat}usado do limite (saldo devedor total, com parcelas futuras) de {_real(s)}" + (" (" + ", ".join(extra) + ")" if extra else "") + ".")
        else:
            disponivel += s
            linhas.append(f"{i}. {g['nome']}: saldo de {_real(s)}.")
    quando = estado.get("ultima") or ""
    saida = ["Saldos das contas, na última leitura do banco" + (f" ({fn.data_br(quando[:10])} às {quando[11:16]})" if quando else "") + ":"] + linhas
    saida.append(f"Total nas contas: {_real(disponivel)}. Total usado dos limites dos cartões: {_real(devido)}. Diferença: {_real(disponivel - devido)}.")
    saida.append("O banco só atualiza limite, disponível e faturas a cada 24 horas pelo Meu Pluggy; se você mudou algo agora há pouco, esses valores podem estar defasados.")
    if sem:
        saida.append(f"{sem} conta(s) sem saldo informado; rode heimdall finance --sync para atualizar.")
    return "\n".join(saida)


def texto_ultimos(con, conta: str = "", mes: str = "", busca: str = "", categoria: str = "", limite: int = 15) -> str:
    nome = resolver_conta(con, conta)
    total, linhas = fn.listar(con, mes=mes, cat=categoria, q=busca, limite=max(1, min(limite, 200)), conta=nome)
    if not linhas:
        return "Nenhum lançamento encontrado com esse filtro."
    saida = [f"{len(linhas)} lançamento(s) mais recente(s) de {total}" + (f", na conta {nome}" if nome else "") + ":"]
    for i, r in enumerate(linhas, 1):
        tipo = "entrada" if r["valor"] > 0 else "saída"
        saida.append(f"{i}. {fn.data_br(r['data'])}, {r['conta']}, {tipo} de {_real(abs(r['valor']))}, {r['descricao']}, categoria {r['categoria']}.")
    return "\n".join(saida)


def texto_resumo(con, mes: str = "") -> str:
    mes = mes or date.today().strftime("%Y-%m")
    r = fn.resumo_mes(con, mes)
    if not (r["receitas"] or r["despesas"]):
        return f"Não há lançamentos em {fn.nome_mes(mes)}."
    saida = [f"Resumo de {fn.nome_mes(mes)}: entradas de {_real(r['receitas'])}, gastos de {_real(r['despesas'])}, resultado de {_real(r['saldo'])}."]
    if r["despesas_anterior"]:
        saida.append(f"No mês anterior os gastos foram de {_real(r['despesas_anterior'])}.")
    if r["categorias"]:
        saida.append("Onde mais gastou:")
        for i, c in enumerate(r["categorias"][:8], 1):
            var = "" if c["variacao"] is None else f", {c['variacao']:+d}% sobre o mês anterior"
            saida.append(f"{i}. {c['categoria']}: {_real(c['total'])} ({str(c['pct']).replace('.', ',')}% dos gastos{var}).")
    if r["maiores"]:
        saida.append("Maiores gastos:")
        for i, m in enumerate(r["maiores"][:5], 1):
            saida.append(f"{i}. {fn.data_br(m['data'])}, {m['descricao']}, {_real(abs(m['valor']))}.")
    if r["sem_categoria"]:
        saida.append(f"{r['sem_categoria']} lançamento(s) do mês estão sem categoria.")
    return "\n".join(saida)
