#!/usr/bin/env python3
"""Análise de consultor do Heimdall Finance: semanal e mensal, sem dica de investimento.

Todos os números são calculados aqui, em código. O texto fixo já é a análise completa; o modelo local, se responder, só reescreve esse
texto em tom de conversa, e a resposta só vale se todos os valores e porcentagens dela já estiverem nos fatos (senão fica o texto fixo).
Nada sai do Mac: o modelo é o local, pelo LiteLLM, e não há reserva na nuvem.
"""
from collections import defaultdict
from datetime import date, timedelta

import financas_nucleo as fn
import heimdall_perguntar as hp

FLEXIVEIS = ["Restaurantes", "Lazer e viagens", "Compras", "Assinaturas", "Transporte", "Outros gastos"]


def _gastos_periodo(con, ini: str, fim: str) -> dict:
    tp = fn.tipos(con)
    out = defaultdict(int)
    for r in con.execute("SELECT categoria, SUM(-valor) t FROM transacoes WHERE data>=? AND data<=? AND valor<0 GROUP BY categoria", (ini, fim)):
        if tp.get(r["categoria"], "gasto") != "neutra":
            out[r["categoria"]] = r["t"]
    return out


def _receitas_periodo(con, ini: str, fim: str) -> int:
    tp = fn.tipos(con)
    return sum(r["valor"] for r in con.execute("SELECT categoria, valor FROM transacoes WHERE data>=? AND data<=? AND valor>0", (ini, fim)) if tp.get(r["categoria"], "renda") != "neutra")


def _variacoes(atual: dict, anterior: dict, minimo: int = 5000) -> tuple:
    sobe, desce = [], []
    for c in set(atual) | set(anterior):
        a, b = atual.get(c, 0), anterior.get(c, 0)
        d = a - b
        if abs(d) < minimo:
            continue
        pct = round(100 * d / b) if b else None
        (sobe if d > 0 else desce).append({"categoria": c, "atual": a, "anterior": b, "delta": d, "pct": pct})
    sobe.sort(key=lambda x: -x["delta"])
    desce.sort(key=lambda x: x["delta"])
    return sobe, desce


def _frase_var(x: dict, rotulo: str) -> str:
    pct = f", {abs(x['pct'])}% {'a mais' if x['delta'] > 0 else 'a menos'}" if x["pct"] is not None else ", categoria nova no período"
    return f"{x['categoria']}: {fn.brl(x['atual'])} contra {fn.brl(x['anterior'])} {rotulo} ({'+' if x['delta'] > 0 else '-'}{fn.brl(abs(x['delta']))}{pct})"


def fatos(con, tipo: str = "mes", hoje=None) -> dict:
    """tipo 'semana' (últimos 7 dias contra os 7 anteriores) ou 'mes' (mês mais recente com dados contra o anterior). Devolve seções com frases prontas."""
    hoje = hoje or date.today()
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje)
    ms = fn.meses(con)
    if not ms:
        raise fn.ErroFinance("O Finance ainda não tem lançamentos. Importe um extrato primeiro.")
    ultimo_dado = con.execute("SELECT MAX(data) FROM transacoes").fetchone()[0]
    sec = {"Resumo": [], "O que subiu": [], "O que baixou": [], "Pontos de atenção": [], "Onde dá para reduzir": [], "Datas de pagamento": []}
    if tipo == "semana":
        fim = min(hoje, date.fromisoformat(ultimo_dado))
        ini = fim - timedelta(days=6)
        ant_fim, ant_ini = ini - timedelta(days=1), ini - timedelta(days=7)
        atual, ant = _gastos_periodo(con, ini.isoformat(), fim.isoformat()), _gastos_periodo(con, ant_ini.isoformat(), ant_fim.isoformat())
        rec = _receitas_periodo(con, ini.isoformat(), fim.isoformat())
        nome, nome_ant = f"os 7 dias até {fn.data_br(fim.isoformat())}", "nos 7 dias anteriores"
        total, total_ant, mes_ref = sum(atual.values()), sum(ant.values()), (fim.strftime("%Y-%m"))
        if mes_ref not in ms:
            mes_ref = ms[0]
        sec["Resumo"].append(f"Nos {nome}, você gastou {fn.brl(total)} e recebeu {fn.brl(rec)}. {nome_ant.capitalize()} foram {fn.brl(total_ant)} de gastos"
                             + (f" ({'+' if total >= total_ant else '-'}{abs(round(100 * (total - total_ant) / total_ant))}%)." if total_ant else "."))
    else:
        mes_ref = ms[0]
        r = fn.resumo_mes(con, mes_ref)
        atual, ant = {c["categoria"]: c["total"] for c in r["categorias"]}, {c["categoria"]: c["anterior"] for c in r["categorias"]}
        for c, v in fn._gastos_por_categoria(con, fn.mes_anterior(mes_ref), fn.tipos(con)).items():
            ant.setdefault(c, v)
        total, total_ant, rec = r["despesas"], r["despesas_anterior"], r["receitas"]
        nome_ant = f"em {fn.nome_mes(fn.mes_anterior(mes_ref))}"
        sec["Resumo"].append(f"Em {fn.nome_mes(mes_ref)}: receitas {fn.brl(rec)}, despesas {fn.brl(total)} e saldo {fn.brl(rec - total, True)}. Despesas {nome_ant}: {fn.brl(total_ant)}"
                             + (f" ({'+' if total >= total_ant else '-'}{abs(round(100 * (total - total_ant) / total_ant))}%)." if total_ant else "."))
        if mes_ref == hoje.strftime("%Y-%m") and hoje.day >= 5:
            import calendar
            dias = calendar.monthrange(hoje.year, hoje.month)[1]
            sec["Resumo"].append(f"No ritmo atual ({fn.brl(total // hoje.day)} por dia), o mês fecha perto de {fn.brl(total // hoje.day * dias)} em despesas.")
    sobe, desce = _variacoes(atual, ant)
    for x in sobe[:4]:
        sec["O que subiu"].append(_frase_var(x, nome_ant))
    for x in desce[:3]:
        sec["O que baixou"].append(_frase_var(x, nome_ant))
    if not sobe:
        sec["O que subiu"].append("Nenhuma categoria subiu de forma relevante.")
    if not desce:
        sec["O que baixou"].append("Nenhuma categoria caiu de forma relevante.")
    # pontos de atenção
    o = fn.orcamentos(con, mes_ref)
    for x in o["linhas"]:
        if x["estado"] == "estourado":
            sec["Pontos de atenção"].append(f"Orçamento de {x['categoria']} estourado: {fn.brl(x['gasto'])} para um limite de {fn.brl(x['limite'])} (passou {fn.brl(-x['restante'])}).")
        elif x["estado"] == "perto":
            sec["Pontos de atenção"].append(f"Orçamento de {x['categoria']} perto do limite: {fn.brl(x['gasto'])} de {fn.brl(x['limite'])} ({x['pct']}%).")
    tarifas = atual.get("Impostos e tarifas", 0)
    if tarifas >= 1000:
        sec["Pontos de atenção"].append(f"Impostos e tarifas (inclui juros, multa e IOF) somaram {fn.brl(tarifas)} no período: vale conferir se algum é evitável.")
    sem = con.execute("SELECT COUNT(*) FROM transacoes WHERE categoria=?", (fn.SEM_CATEGORIA,)).fetchone()[0]
    if sem:
        sec["Pontos de atenção"].append(f"{sem} lançamento(s) estão sem categoria, o que distorce esta análise. Classifique na página Transações.")
    import financas_boletos as fb
    abertos = fb.listar(con, hoje)
    venc = [b for b in abertos if b["dias"] is not None and b["dias"] < 0]
    prox = [b for b in abertos if b["dias"] is not None and 0 <= b["dias"] <= 7]
    if venc:
        sec["Pontos de atenção"].append(f"{len(venc)} boleto(s) vencido(s), somando {fn.brl(sum(b['valor'] or 0 for b in venc))}.")
    if prox:
        sec["Pontos de atenção"].append(f"{len(prox)} boleto(s) vencem em até 7 dias, somando {fn.brl(sum(b['valor'] or 0 for b in prox))}.")
    rec_s = fn.recorrentes(con, hoje)
    atras = [s for s in rec_s["series"] if s["situacao"] == "atrasada" and not s["entrada"]]
    if atras:
        sec["Pontos de atenção"].append("Contas recorrentes que passaram do dia habitual e não apareceram: " + "; ".join(f"{s['descricao'][:40]} ({fn.brl(abs(s['valor']))})" for s in atras[:5]) + ".")
    fut = fn.futuros(con, 3, hoje)
    parc_total = 0
    for p in fn.parcelamentos(con, hoje):
        if not p["ignorado"] and p["proximas"]:
            parc_total += -p["valor"]
    if parc_total and total:
        sec["Pontos de atenção"].append(f"As parcelas em andamento somam {fn.brl(parc_total)} por mês, cerca de {round(100 * parc_total / total)}% das despesas do período.")
    if len(fut["meses"]) > 1:
        prox_mes = fut["meses"][1]
        sec["Pontos de atenção"].append(f"Já previsto para {fn.nome_mes(prox_mes['mes'])}: {fn.brl(prox_mes['saidas'])} em saídas (parcelas, recorrentes, cadastrados e boletos).")
    if not sec["Pontos de atenção"]:
        sec["Pontos de atenção"].append("Nada fora do normal nos dados disponíveis.")
    # redução
    base3 = defaultdict(list)
    for m in ms[:3]:
        for c, v in fn._gastos_por_categoria(con, m, fn.tipos(con)).items():
            base3[c].append(v)
    flex = sorted(((c, sum(base3[c]) // len(base3[c])) for c in FLEXIVEIS if base3.get(c)), key=lambda x: -x[1])
    for c, media in flex[:3]:
        sec["Onde dá para reduzir"].append(f"{c}: média de {fn.brl(media)} por mês nos últimos meses. Cortar 10% liberaria {fn.brl(media // 10)} por mês.")
    assin = [s for s in rec_s["series"] if s["categoria"] == "Assinaturas" and s["situacao"] != "encerrada" and not s["entrada"]]
    if assin:
        sec["Onde dá para reduzir"].append("Assinaturas ativas: " + "; ".join(f"{s['descricao'][:30]} {fn.brl(abs(s['valor']))}" for s in assin[:6]) + f", total {fn.brl(sum(abs(s['valor']) for s in assin))} por mês. Vale rever as que você não usa.")
    if not sec["Onde dá para reduzir"]:
        sec["Onde dá para reduzir"].append("Ainda não há histórico suficiente nas categorias flexíveis para sugerir cortes.")
    # datas
    salario = [s for s in rec_s["series"] if s["entrada"] and s["situacao"] != "encerrada"]
    if salario:
        s = max(salario, key=lambda s: s["valor"])
        dia_sal = s["dia"]
        antes = [x for m in fut["meses"][:2] for x in m["itens"] if x["valor"] < 0 and int(x["data"][8:10]) < dia_sal and x["origem"] in ("recorrente", "manual", "boleto")]
        sec["Datas de pagamento"].append(f"Sua maior entrada recorrente ({s['descricao'][:30]}, {fn.brl(s['valor'])}) cai por volta do dia {dia_sal}.")
        if antes:
            sec["Datas de pagamento"].append("Vencem antes de o dinheiro entrar: " + "; ".join(f"{x['descricao'][:35]} dia {x['data'][8:10]} ({fn.brl(-x['valor'])})" for x in antes[:5])
                                             + f". Se o banco ou o emissor permitir, mover o vencimento para depois do dia {dia_sal} evita usar limite ou cheque especial.")
        else:
            sec["Datas de pagamento"].append("Nenhuma conta prevista vence antes de a entrada cair.")
    por_dia = defaultdict(int)
    for m in fut["meses"][:2]:
        for x in m["itens"]:
            if x["valor"] < 0:
                por_dia[int(x["data"][8:10])] += -x["valor"]
    if por_dia:
        d, v = max(por_dia.items(), key=lambda kv: kv[1])
        sec["Datas de pagamento"].append(f"O dia de maior concentração de pagamentos nos próximos dois meses é o dia {d}, com {fn.brl(v)}. Espalhar os vencimentos alivia o caixa.")
    if not sec["Datas de pagamento"]:
        sec["Datas de pagamento"].append("Ainda não há contas previstas para sugerir datas.")
    return {"tipo": tipo, "mes": mes_ref, "gerado": hoje.isoformat(), "secoes": sec}


def texto_fixo(f: dict) -> str:
    titulo = "Análise da semana" if f["tipo"] == "semana" else f"Análise de {fn.nome_mes(f['mes'])}"
    partes = [titulo]
    for nome, linhas in f["secoes"].items():
        partes.append(nome + ":")
        partes += [f"{i}. {l}" for i, l in enumerate(linhas, 1)]
    return "\n".join(partes)


def com_modelo(f: dict, modelo: str = "") -> dict:
    """{'texto','origem','avisos'}: o texto reescrito pelo modelo local se ele só usar números dos fatos; senão o texto fixo."""
    fixo = texto_fixo(f)
    sistema = (hp.SISTEMA_PADRAO + " Você é um consultor de finanças pessoais: reescreva os FATOS como uma análise clara e direta, na ordem Resumo, O que subiu, O que baixou, Pontos de atenção, "
               "Onde dá para reduzir e Datas de pagamento, com lista numerada simples em cada parte. Não acrescente fatos, categorias ou valores que não estejam no CONTEXTO.")
    try:
        r = hp.responder(fixo, "Reescreva estes fatos como a análise de um consultor de finanças pessoais.", sistema, modelo)
    except Exception as ex:  # noqa: BLE001
        return {"texto": fixo, "origem": "regras", "avisos": [f"O modelo local não respondeu ({type(ex).__name__}); mostrei a análise calculada pelas regras."]}
    if r["avisos"] or len(r["texto"]) < 200:
        return {"texto": fixo, "origem": "regras", "avisos": ["O modelo citou valores que não estão nos dados, então mostrei a análise calculada pelas regras."]}
    return {"texto": r["texto"], "origem": "modelo local", "avisos": []}


def contexto_pergunta(con, pergunta: str, hoje=None, mes_pagina: str = "") -> str:
    """Contexto para o campo Perguntar: resumo dos dois últimos meses, orçamentos, futuros, boletos, recorrentes e lançamentos que casam com palavras da pergunta."""
    import re
    import financas_boletos as fb
    hoje = hoje or date.today()
    ms = fn.meses(con)
    if not ms:
        raise fn.ErroFinance("O Finance ainda não tem lançamentos. Importe um extrato primeiro.")
    nomes = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
    pedidos = [ms[0], fn.mes_anterior(ms[0])]
    if mes_pagina in ms and mes_pagina not in pedidos:
        pedidos.insert(0, mes_pagina)  # o mês que o usuário está olhando na página entra primeiro
    for palavra in re.findall(r"[a-zçã]+", pergunta.lower()):
        if palavra in nomes:
            cand = [m for m in ms if int(m[5:7]) == nomes[palavra]]
            if cand and cand[0] not in pedidos:
                pedidos.append(cand[0])
    partes = []
    for m in pedidos[:4]:
        if m not in ms:
            continue
        r = fn.resumo_mes(con, m)
        partes.append(f"[{fn.nome_mes(m)}] receitas {fn.brl(r['receitas'])}, despesas {fn.brl(r['despesas'])}, saldo {fn.brl(r['saldo'], True)}. Por categoria: "
                      + "; ".join(f"{c['categoria']} {fn.brl(c['total'])}" for c in r["categorias"]) + ".")
        o = fn.orcamentos(con, m)
        lim = [x for x in o["linhas"] if x["limite"] is not None]
        if lim:
            partes.append("Orçamentos: " + "; ".join(f"{x['categoria']} limite {fn.brl(x['limite'])} gasto {fn.brl(x['gasto'])} ({x['estado']})" for x in lim) + ".")
    f = fn.futuros(con, 3, hoje)
    for m in f["meses"]:
        partes.append(f"[Previsto {fn.nome_mes(m['mes'])}] saídas {fn.brl(m['saidas'])}, entradas {fn.brl(m['entradas'])}: " + "; ".join(f"dia {x['data'][8:10]} {x['descricao'][:40]} {fn.brl(x['valor'], True)}" for x in m["itens"][:12]) + ".")
    bol = fb.listar(con, hoje)
    if bol:
        partes.append("[Boletos em aberto] " + "; ".join(fb.frase(b) + f" ({b['estado']})" for b in bol[:10]) + ".")
    palavras = [p for p in re.findall(r"[a-zçãéíóúâêô0-9]{4,}", fn.norm(pergunta)) if p not in {"quanto", "quais", "qual", "gastei", "gastou", "esse", "esta", "este", "mes", "meses", "foram", "tenho", "valor", "total", "ultimo", "ultimos", "passado", "sobre", "minhas", "minha", "mais", "como"}]
    vistos = 0
    for p in palavras[:3]:
        total, linhas = fn.listar(con, "", "", p, 12)
        if linhas:
            partes.append(f"[Lançamentos com '{p}': {total} no total; os mais recentes] " + "; ".join(f"{fn.data_br(t['data'])} {t['descricao'][:40]} {fn.brl(t['valor'], True)} ({t['categoria']})" for t in linhas))
            vistos += 1
    return "\n".join(partes)[:9000]
