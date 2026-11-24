#!/usr/bin/env python3
"""Páginas do Heimdall Finance para planilhas, investimentos, empréstimos e visões (a lógica está em financas_planilhas.py).
Link lê, botão age: abrir uma página é link; criar, mover coluna, responder dúvida e apagar são botões em formulário POST com token."""
import html
import re
from pathlib import Path

import financas_nucleo as fn
import financas_planilhas as fp
import financas_pluggy_dados as pd
import heimdall_design as design

e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
MAX_VISIVEIS = 500
ROTAS_GET = ("/planilhas", "/investimentos", "/emprestimos", "/conjunto", "/visoes", "/visao", "/contas", "/cartoes", "/cartoes/fechadas")
_CREDITO = re.compile(r"/credito/(" + "|".join(fp.CATEGORIAS_CREDITO) + ")")


def eh_rota_get(rota: str) -> bool:
    return rota in ROTAS_GET or bool(_CREDITO.fullmatch(rota))
ROTAS_POST = ("/planilhas", "/planilhas/duvida", "/planilhas/duvida/descartar", "/visoes/nova", "/visao/coluna", "/visao/regras", "/visao/renomear", "/visao/apagar")


def tabela(legenda: str, cabecalhos: list, linhas: list, numericas: set = None) -> str:
    num = numericas or set()

    def attr(i):
        return ' class="n"' if i in num else ""

    cab = "".join(f'<th scope="col"{attr(i)}>{e(c)}</th>' for i, c in enumerate(cabecalhos))
    corpo = "".join("<tr>" + "".join(f"<td{attr(i)}>{c}</td>" for i, c in enumerate(l)) + "</tr>" for l in linhas)
    return f"<table><caption>{e(legenda)}</caption><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>"


def _oculto(sess: dict, **campos) -> str:
    return f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">' + "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in campos.items())


def _opcoes(itens: list, sel: str = "", vazio: str = "") -> str:
    o = f'<option value="">{e(vazio)}</option>' if vazio else ""
    return o + "".join(f'<option value="{e(k)}"{" selected" if k == sel else ""}>{e(n)}</option>' for k, n in itens)


def _brl(v) -> str:
    return fn.brl(v) if v is not None else "sem valor"


# --------------------------------------------------------------------------------------------
# Planilhas
# --------------------------------------------------------------------------------------------
def pg_planilhas(con, sess: dict, pasta: Path) -> tuple:
    corpo = ['<p>Importe planilhas (xlsx ou csv) de gastos, investimentos, empréstimos ou qualquer outro assunto. O Heimdall lê o cabeçalho, descobre o que cada coluna é e guarda as linhas num conjunto. '
             'O jeito de ler fica gravado: quando você mandar outra planilha com as mesmas colunas, ou soltar o arquivo na pasta de entrada, as linhas novas entram sozinhas no mesmo conjunto, sem duplicar o que já estava. '
             'Quando a identificação não é segura, o arquivo fica guardado e a pergunta aparece logo abaixo, sem adivinhar. Planilhas de gastos também alimentam as transações, os orçamentos e o resumo.</p>',
             f'<form method="post" action="/planilhas" enctype="multipart/form-data">{_oculto(sess)}'
             '<label for="arquivo">Planilha (xlsx, xlsm, csv)</label><input id="arquivo" name="arquivo" type="file" accept=".xlsx,.xlsm,.csv,.tsv,.txt" required>'
             f'<label for="tipo">Tipo</label><select id="tipo" name="tipo">{_opcoes(list(fp.TIPOS_USUARIO.items()), "", "Deixar o Heimdall decidir")}</select>'
             '<label for="nome">Nome do conjunto (em branco: usa o nome do arquivo ou o que foi identificado)</label><input id="nome" name="nome" type="text" maxlength="60">'
             '<label><input type="checkbox" name="inverter" value="1"> Nesta planilha de gastos, os gastos vêm com valor positivo</label>'
             '<label><input type="checkbox" name="visao" value="1"> Criar uma visão a partir desta planilha (você escolhe as colunas e a ordem na aba Visões)</label>'
             '<button type="submit">Importar planilha</button></form>']
    ds = fp.duvidas(con)
    if ds:
        corpo.append("<h2>Dúvidas para você responder</h2>")
        for d in ds:
            campos = []
            for c in d["campos"]:
                campos.append(f'<label for="d{d["id"]}-{e(c["chave"])}">{e(c["rotulo"])}</label>'
                              f'<select id="d{d["id"]}-{e(c["chave"])}" name="{e(c["chave"])}" required>{_opcoes([tuple(o) for o in c["opcoes"]], "", "Escolha")}</select>')
            corpo.append(f'<div class="aviso" role="status"><p>{e(d["pergunta"])}</p>'
                         f'<form method="post" action="/planilhas/duvida">{_oculto(sess, id=d["id"])}{"".join(campos)}'
                         f'<label for="d{d["id"]}-nome">Nome do conjunto (opcional)</label><input id="d{d["id"]}-nome" name="nome" type="text" maxlength="60">'
                         f'<button type="submit">Responder e importar</button></form>'
                         f'<form method="post" action="/planilhas/duvida/descartar">{_oculto(sess, id=d["id"])}<button type="submit" aria-label="Descartar a planilha {e(d["arquivo"])}">Descartar esta planilha</button></form></div>')
    cs = fp.conjuntos(con)
    if cs:
        linhas = [[f'<a href="/conjunto?id={c["id"]}">{e(c["nome"])}</a>', e(fp.TIPOS.get(c["tipo"], c["tipo"])), str(c["n"]), e(c["ultimo"] or "")] for c in cs]
        corpo.append("<h2>Conjuntos</h2>" + tabela("Conjuntos de planilhas", ["Nome", "Tipo", "Linhas", "Última importação"], linhas, {2}))
    else:
        corpo.append("<p>Ainda não há conjuntos. Importe a primeira planilha acima.</p>")
    corpo.append(f'<p class="sub">Você também pode soltar planilhas na pasta sheets, dentro da pasta de dados do Finance: a cada minuto o Heimdall importa o que entender e deixa as dúvidas aqui. No terminal: heimdall finance --folder.</p>')
    return "Planilhas", "".join(corpo)


def resumo_resultados(res: list) -> str:
    partes = []
    for r in res:
        if r.get("duplicado"):
            partes.append(r["motivo"])
        elif r.get("ok"):
            txt = f"{r['conjunto']} ({fp.TIPOS[r['tipo']].lower()}): {r['lidas']} linhas lidas, {r['novas']} novas e {r['repetidas']} já existentes"
            if r.get("transacoes_novas") is not None:
                txt += f"; {r['transacoes_novas']} novos lançamentos nas transações"
            if r.get("linhas_ruins"):
                txt += f"; {r['linhas_ruins']} linha(s) sem data ou valor legível ficaram só no conjunto"
            if r.get("origem") == "aprendido":
                txt += ", lidas pelo layout que já conhecia"
            partes.append(txt + ".")
        elif r.get("duvida"):
            partes.append(f"Aba {r['aba']}: tenho uma dúvida, responda na aba Ajustes, em Importar planilha.")
        else:
            partes.append(f"Aba {r['aba']}: {r.get('motivo', 'não importada')}")
    return " ".join(partes)


# --------------------------------------------------------------------------------------------
# Conjunto e visões
# --------------------------------------------------------------------------------------------
def _tabela_visao(con, cid: int, cfg: dict, legenda: str) -> str:
    a = fp.aplicar_visao(con, cid, cfg)
    nomes = [n for _, n in a["colunas"]]
    corpo = [f'<p>{a["filtradas"]} de {a["total"]} linhas.' + (" O filtro da visão está ligado." if a["filtradas"] != a["total"] else "") + "</p>"]
    if a["grupos"]:
        g = a["grupos"]
        cab = [g["coluna"], "Linhas"] + ([f"Soma de {g['soma']}"] if g["soma"] else [])
        linhas = [[e(k), str(n)] + ([e(_brl(s))] if g["soma"] else []) for k, n, s in g["linhas"]]
        corpo.append(tabela(f"{legenda}, agrupado por {g['coluna']}", cab, linhas, {1, 2} if g["soma"] else {1}))
    if a["linhas"]:
        corpo.append(tabela(legenda, nomes, [[e(c) for c in l] for l in a["linhas"][:MAX_VISIVEIS]]))
        if len(a["linhas"]) > MAX_VISIVEIS:
            corpo.append(f'<p class="sub">Mostrando as primeiras {MAX_VISIVEIS} linhas.</p>')
    else:
        corpo.append("<p>Nenhuma linha para mostrar com este filtro.</p>")
    return "".join(corpo)


def pg_conjunto(con, q: dict, sess: dict) -> tuple:
    try:
        c = fp.conjunto(con, int((q.get("id") or ["0"])[0]))
    except ValueError:
        c = None
    if not c:
        return None
    vs = fp.visoes(con, c["id"])
    vid = (q.get("visao") or [""])[0]
    atual = next((v for v in vs if str(v["id"]) == vid), None)
    cfg = atual["cfg"] if atual else fp.config_padrao(c)
    corpo = [f'<p>{e(fp.TIPOS.get(c["tipo"], c["tipo"]))}. Criado em {e(c["criado"] or "")}. Linhas novas das próximas planilhas com o mesmo layout aparecem aqui e em todas as visões.</p>']
    botoes = design.botao("/conjunto", "Todas as colunas", {"id": c["id"]}, atual=atual is None)
    botoes += "".join(design.botao("/conjunto", v["nome"], {"id": c["id"], "visao": v["id"]}, f"Visão {v['nome']}", atual=atual is not None and v["id"] == atual["id"]) for v in vs)
    corpo.append(f'<h2>Visão</h2><div role="group" aria-label="Escolher a visão">{botoes}</div>')
    if atual:
        corpo.append(f'<p><a href="/visao?id={atual["id"]}">Personalizar a visão {e(atual["nome"])}</a></p>')
    corpo.append(f'<form method="post" action="/visoes/nova">{_oculto(sess, conjunto_id=c["id"])}'
                 '<label for="nv">Nome para uma nova visão (começa com as colunas da visão aberta)</label><input id="nv" name="nome" type="text" maxlength="60" required>'
                 + (f'<input type="hidden" name="copiar_de" value="{atual["id"]}">' if atual else "") + '<button type="submit">Criar visão</button></form>')
    corpo.append(_tabela_visao(con, c["id"], cfg, f"{c['nome']}" + (f", visão {atual['nome']}" if atual else "")))
    return c["nome"], "".join(corpo)


def pg_visoes(con, sess: dict = None) -> tuple:
    """Criar e ver as visões: o formulário de nova visão (conjunto e nome) e a tabela das visões gravadas."""
    vs = fp.visoes(con)
    cs = fp.conjuntos(con)
    corpo = ['<p>Visões são formas gravadas de mostrar uma planilha: você escolhe as colunas, a ordem delas, como ordenar, filtrar e agrupar, e o Heimdall mantém isso para as linhas novas que chegarem.</p>']
    if cs and sess:
        corpo.append("<h2>Criar uma visão</h2>"
                     f'<form method="post" action="/visoes/nova">{_oculto(sess)}'
                     f'<label for="vconj">Planilha (conjunto)</label><select id="vconj" name="conjunto_id" required>{_opcoes([(str(c["id"]), c["nome"]) for c in cs], "", "Escolha a planilha")}</select>'
                     '<label for="vnome">Nome da visão</label><input id="vnome" name="nome" type="text" maxlength="60" required>'
                     '<button type="submit">Criar visão</button></form>')
    elif not cs:
        corpo.append('<p>Ainda não há planilhas para criar visões. Importe uma em Ajustes, em Importar planilha, e marque a opção de criar uma visão.</p>')
    if vs:
        linhas = [[f'<a href="/conjunto?id={v["conjunto_id"]}&amp;visao={v["id"]}">{e(v["nome"])}</a>', e(v["conjunto_nome"]), str(len(v["cfg"].get("colunas", []))),
                   f'<a href="/visao?id={v["id"]}">Personalizar</a>'] for v in vs]
        corpo.append("<h2>Visões gravadas</h2>" + tabela("Visões gravadas", ["Visão", "Conjunto", "Colunas", "Personalizar"], linhas, {2}))
    elif cs:
        corpo.append("<p>Ainda não há visões gravadas.</p>")
    return "Visões", "".join(corpo)


def pg_visao(con, q: dict, sess: dict) -> tuple:
    try:
        v = fp.visao(con, int((q.get("id") or ["0"])[0]))
    except ValueError:
        v = None
    if not v:
        return None
    c = fp.conjunto(con, v["conjunto_id"])
    nomes = dict(fp.colunas_do_conjunto(c))
    cfg = v["cfg"]
    cols = [k for k in cfg.get("colunas", []) if k in nomes]
    corpo = [f'<p>Conjunto <a href="/conjunto?id={c["id"]}&amp;visao={v["id"]}">{e(c["nome"])}</a>. Tudo o que você mudar aqui fica gravado e vale também para as linhas que chegarem depois.</p>',
             f'<form method="post" action="/visao/renomear">{_oculto(sess, id=v["id"])}<label for="rn">Nome da visão</label><input id="rn" name="nome" type="text" maxlength="60" value="{e(v["nome"])}" required>'
             '<button type="submit">Renomear</button></form>']
    linhas = []
    for i, k in enumerate(cols):
        def acao(rotulo, a):
            return (f'<form class="acao" method="post" action="/visao/coluna">{_oculto(sess, id=v["id"], chave=k, acao=a)}'
                    f'<button type="submit" aria-label="{e(rotulo)}: {e(nomes[k])}">{e(rotulo)}</button></form>')
        botoes = (acao("Mover para cima", "acima") if i > 0 else "") + (acao("Mover para baixo", "abaixo") if i < len(cols) - 1 else "") + (acao("Tirar da visão", "tirar") if len(cols) > 1 else "")
        linhas.append([str(i + 1), e(nomes[k]), botoes])
    corpo.append("<h2>Colunas da visão, na ordem em que aparecem</h2>" + tabela("Colunas da visão", ["Posição", "Coluna", "Ações"], linhas, {0}))
    fora = [k for k in nomes if k not in cols]
    if fora:
        corpo.append("<h2>Colunas fora da visão</h2>" + tabela("Colunas fora da visão", ["Coluna", "Ação"], [[e(nomes[k]), (
            f'<form class="acao" method="post" action="/visao/coluna">{_oculto(sess, id=v["id"], chave=k, acao="incluir")}<button type="submit" aria-label="Incluir na visão: {e(nomes[k])}">Incluir no fim da visão</button></form>')] for k in fora]))
    todas = [(k, n) for k, n in nomes.items()]
    corpo.append(f'<h2>Ordenar, filtrar e agrupar</h2><form method="post" action="/visao/regras">{_oculto(sess, id=v["id"])}'
                 f'<label for="o">Ordenar por</label><select id="o" name="ordem">{_opcoes(todas, cfg.get("ordem", ""), "Ordem original")}</select>'
                 f'<label for="dr">Direção</label><select id="dr" name="direcao">{_opcoes([("asc", "Crescente (A a Z, menor para maior, mais antigo primeiro)"), ("desc", "Decrescente (Z a A, maior para menor, mais recente primeiro)")], cfg.get("dir", "asc"))}</select>'
                 f'<label for="fc">Mostrar só as linhas em que a coluna</label><select id="fc" name="filtro_col">{_opcoes(todas, cfg.get("filtro_col", ""), "Sem filtro")}</select>'
                 f'<label for="fv">contém o texto</label><input id="fv" name="filtro_valor" type="text" maxlength="80" value="{e(cfg.get("filtro_valor", ""))}">'
                 f'<label for="ag">Agrupar por</label><select id="ag" name="agrupar">{_opcoes(todas, cfg.get("agrupar", ""), "Sem agrupamento")}</select>'
                 f'<label for="so">Somar a coluna (em cada grupo)</label><select id="so" name="somar">{_opcoes(todas, cfg.get("somar", ""), "Não somar")}</select>'
                 '<button type="submit">Salvar ordenação, filtro e agrupamento</button></form>')
    corpo.append("<h2>Como a visão fica agora</h2>" + _tabela_visao(con, c["id"], cfg, v["nome"]))
    corpo.append(f'<form method="post" action="/visao/apagar">{_oculto(sess, id=v["id"])}<button type="submit" aria-label="Apagar a visão {e(v["nome"])}">Apagar esta visão</button></form>'
                 '<p class="sub">Apagar a visão não apaga nenhuma linha da planilha.</p>')
    return f"Visão {v['nome']}", "".join(corpo)


# --------------------------------------------------------------------------------------------
# Investimentos e empréstimos
# --------------------------------------------------------------------------------------------
def pg_investimentos(con) -> tuple:
    r = fp.resumo_investimentos(con)
    if not r["itens"]:
        return "Investimentos", ('<p>Ainda não há investimentos. Importe uma planilha da sua carteira (com colunas como ativo, tipo, quantidade e valor) na página Planilhas, e o resumo será montado aqui.</p>'
                                 '<p><a href="/planilhas">Ir para Planilhas</a></p>')
    corpo = [f'<p>Posição mais recente de {len(r["itens"])} ativo(s), somando {e(fn.brl(r["total"]))}. Quando a planilha tem coluna de data, uso a linha mais recente de cada ativo; '
             'quando não tem, uso a última importada. Planilhas antigas continuam guardadas no conjunto.</p>']
    if r["sem_valor"]:
        corpo.append(f'<div class="aviso" role="status">{r["sem_valor"]} ativo(s) ficaram sem valor legível e não entram na soma.</div>')
    if r["por_tipo"]:
        corpo.append("<h2>Por tipo</h2>" + tabela("Investimentos por tipo", ["Tipo", "Valor", "Parte do total"],
                                                   [[e(t), e(fn.brl(v)), f"{round(100 * v / r['total'])}%" if r["total"] else ""] for t, v in r["por_tipo"]], {1, 2}))
    corpo.append("<h2>Ativos</h2>" + tabela("Ativos", ["Ativo", "Tipo", "Instituição", "Valor", "Data", "Rentabilidade", "Conjunto"],
                                              [[e(i["ativo"]), e(i["tipo"]), e(i["instituicao"]), e(_brl(i["valor"])), e(i["data"]), e(i["rentabilidade"]), e(i["conjunto"])] for i in r["itens"]], {3}))
    return "Investimentos", "".join(corpo)


def _dinheiro(txt: str) -> str:
    try:
        return fn.brl(fn.parse_valor(txt))
    except ValueError:
        return txt or ""


def pg_emprestimos(con, categoria: str = "") -> tuple:
    titulo = fp.CATEGORIAS_CREDITO.get(categoria, "Dívidas e financiamentos")
    r = fp.resumo_emprestimos(con, categoria)
    if not r["itens"]:
        return titulo, ('<p>Ainda não há dados aqui. O Heimdall cria esta aba sozinho quando encontra o tipo de crédito nos dados do Pluggy (heimdall finance --sync) ou numa planilha de dívidas '
                        '(com colunas como contrato, saldo devedor, parcela e taxa) importada em Planilhas.</p><p><a href="/planilhas">Ir para Planilhas</a></p>')
    corpo = [f'<p>{len(r["itens"])} contrato(s): saldo devedor total de {e(fn.brl(r["saldo"]))}'
             + (f' e parcelas que somam {e(fn.brl(r["parcelas"]))} por mês' if r["parcelas"] else "") + ".</p>"]
    if r["sem_valor"]:
        corpo.append(f'<div class="aviso" role="status">{r["sem_valor"]} contrato(s) ficaram sem saldo nem parcela legíveis.</div>')
    if not categoria:
        por = {}
        for i in r["itens"]:
            x = por.setdefault(i["categoria"], [0, 0])
            x[0] += 1
            x[1] += i["saldo"] or 0
        corpo.append(tabela("Dívidas por tipo", ["Tipo", "Contratos", "Saldo devedor"],
                            [[f'<a href="/credito/{k}">{e(fp.CATEGORIAS_CREDITO[k])}</a>', str(por[k][0]), e(fn.brl(por[k][1]))] for k in fp.CATEGORIAS_CREDITO if k in por], {1, 2}))
    cab = ["Contrato", "Credor", "Saldo devedor", "Parcela", "Taxa ou CET", "Vencimento", "Parcelas pagas", "Parcelas a vencer", "Origem"]
    linhas = [[e(i["contrato"]), e(i["credor"]), e(_brl(i["saldo"])), e(_brl(i["parcela"])), e(i["taxa"]), e(i["vencimento"]), e(i["pagas"]), e(i["restantes"]),
               f'<a href="/conjunto?id={i["conjunto_id"]}">{e(i["conjunto"])}</a>'] for i in r["itens"]]
    if not categoria:
        cab.insert(1, "Tipo")
        for l, i in zip(linhas, r["itens"]):
            l.insert(1, e(fp.CATEGORIAS_CREDITO[i["categoria"]]))
    corpo.append(tabela(f"Contratos: {titulo}", cab, linhas, {2, 3} if categoria else {3, 4}))
    return titulo, "".join(corpo)


def _contas_pluggy(con, tipo: str) -> list:
    return [d for d in fp.linhas_atuais(con, pd.NOME_CONTAS) if d.get("type", "").upper() == tipo]


def _por_conta_transacoes(con, cartao: bool) -> list:
    from datetime import date, timedelta
    desde = (date.today() - timedelta(days=30)).isoformat()
    linhas = []
    for c in con.execute("SELECT conta, COUNT(*) n, MIN(data) ini, MAX(data) fim, "
                         "SUM(CASE WHEN data>=? AND valor>0 THEN valor ELSE 0 END) ent, SUM(CASE WHEN data>=? AND valor<0 THEN valor ELSE 0 END) sai "
                         "FROM transacoes GROUP BY conta ORDER BY conta", (desde, desde)):
        if ("cartao" in fn.norm(c["conta"])) == cartao:
            linhas.append(c)
    return linhas


def tem_contas(con) -> bool:
    return bool(_por_conta_transacoes(con, False) or _contas_pluggy(con, "BANK"))


def tem_cartoes(con) -> bool:
    return bool(_por_conta_transacoes(con, True) or _contas_pluggy(con, "CREDIT") or fp.linhas_atuais(con, pd.NOME_FATURAS))


def _tabela_lancamentos(linhas, cartao: bool) -> str:
    rot = ("Gastos em 30 dias" if cartao else "Saídas em 30 dias", "Créditos em 30 dias" if cartao else "Entradas em 30 dias")
    return tabela("Lançamentos por cartão" if cartao else "Lançamentos por conta", ["Nome", "Lançamentos", "Primeiro", "Último", rot[1], rot[0]],
                  [[f'<a href="/transacoes?conta={e(c["conta"])}">{e(c["conta"])}</a>', str(c["n"]), e(fn.data_br(c["ini"])), e(fn.data_br(c["fim"])), e(fn.brl(c["ent"])), e(fn.brl(-c["sai"]))]
                   for c in linhas], {1, 4, 5})


def pg_contas(con) -> tuple:
    corpo = ['<p>Extratos das contas correntes e de pagamento: os lançamentos vêm de extratos importados e da conexão com os bancos. Os cartões de crédito ficam na aba Cartões.</p>']
    t = _por_conta_transacoes(con, False)
    if t:
        corpo.append("<h2>Lançamentos</h2>" + _tabela_lancamentos(t, False))
    p = _contas_pluggy(con, "BANK")
    if p:
        total = 0
        linhas = []
        for d in p:
            try:
                total += fn.parse_valor(d.get("balance", ""))
            except ValueError:
                pass
            linhas.append([e(d.get("name", "")), e(d.get("subtype", "")), e(d.get("bankdata_transfernumber", "") or d.get("number", "")), e(_dinheiro(d.get("balance", ""))),
                           e(_dinheiro(d.get("bankdata_overdraftcontractedlimit", ""))), e(_dinheiro(d.get("bankdata_overdraftusedlimit", ""))), e(d.get("coletado_em", ""))])
        corpo.append(f"<h2>Saldos informados pelos bancos</h2><p>Saldo somado de {len(p)} conta(s): {e(fn.brl(total))}.</p>"
                     + tabela("Contas bancárias no Pluggy", ["Nome", "Tipo", "Agência e conta", "Saldo", "Limite do cheque especial", "Cheque especial usado", "Lido em"], linhas, {3, 4, 5}))
        c = next((x for x in fp.conjuntos(con) if x["nome"] == pd.NOME_CONTAS), None)
        if c:
            corpo.append(f'<p><a href="/conjunto?id={c["id"]}">Ver todos os dados das contas e criar visões</a></p>')
    if not t and not p:
        corpo.append("<p>Ainda não há contas. Importe um extrato ou sincronize o Pluggy.</p>")
    return "Contas", "".join(corpo)


def pg_cartoes(con, fechadas: bool = False) -> tuple:
    """Cartões em duas subabas: a fatura aberta (limite, fechamento, vencimento e os lançamentos em andamento) e as faturas fechadas (as já emitidas)."""
    corpo = []
    p = _contas_pluggy(con, "CREDIT")
    fat = fp.linhas_atuais(con, pd.NOME_FATURAS)
    if fechadas:
        corpo.append('<p>Faturas já fechadas dos cartões de crédito, da mais recente para a mais antiga.</p>')
        if fat:
            fat = sorted(fat, key=lambda d: d.get("duedate", ""), reverse=True)
            corpo.append("<h2>Faturas fechadas</h2>" + tabela("Faturas fechadas dos cartões", ["Cartão", "Vencimento", "Total", "Pagamento mínimo", "Permite parcelar"],
                                                              [[e(d.get("cartao", "")), e(d.get("duedate", "")), e(_dinheiro(d.get("totalamount", ""))), e(_dinheiro(d.get("minimumpaymentamount", ""))),
                                                                e(d.get("allowsinstallments", ""))] for d in fat], {2, 3}))
        else:
            corpo.append("<p>Ainda não há faturas fechadas. Importe uma fatura em PDF, OFX ou CSV em Ajustes, ou sincronize o Pluggy.</p>")
        if fat:
            c = next((x for x in fp.conjuntos(con) if x["nome"] in (pd.NOME_FATURAS, pd.NOME_CONTAS)), None)
            if c:
                corpo.append(f'<p><a href="/conjunto?id={c["id"]}">Ver todos os dados e criar visões</a></p>')
        return "Faturas fechadas", "".join(corpo)
    corpo.append('<p>Fatura aberta dos cartões de crédito: limite, fechamento, vencimento e o que já foi lançado. Os extratos das contas ficam em Extratos.</p>')
    if p:
        linhas = [[e(d.get("name", "")), e(d.get("creditdata_brand", "")), e(d.get("creditdata_level", "")), e(_dinheiro(d.get("creditdata_creditlimit", ""))),
                   e(_dinheiro(d.get("creditdata_availablecreditlimit", ""))), e(d.get("creditdata_balanceclosedate", "")), e(d.get("creditdata_balanceduedate", "")),
                   e(_dinheiro(d.get("creditdata_minimumpayment", "")))] for d in p]
        corpo.append("<h2>Limites e fatura atual</h2>" + tabela("Cartões no Pluggy", ["Nome", "Bandeira", "Nível", "Limite", "Disponível", "Fecha em", "Vence em", "Pagamento mínimo"],
                                                              linhas, {3, 4, 7}))
    t = _por_conta_transacoes(con, True)
    if t:
        corpo.append("<h2>Lançamentos</h2>" + _tabela_lancamentos(t, True))
    if not (t or p):
        corpo.append("<p>Ainda não há cartões. Importe uma fatura em Ajustes ou sincronize o Pluggy.</p>")
    return "Fatura aberta", "".join(corpo)


def nav(con, base: list) -> list:
    """As abas fixas mais as que os dados pedem: Contas, Cartões, Investimentos e um tipo de crédito por aba (só os que existem)."""
    din = []
    try:
        if tem_contas(con):
            din.append(("/contas", "Contas"))
        if tem_cartoes(con):
            din.append(("/cartoes", "Cartões"))
        if fp.resumo_investimentos(con)["itens"]:
            din.append(("/investimentos", "Investimentos"))
        cats = fp.categorias_de_credito(con)
        if len(cats) > 1:
            din.append(("/emprestimos", "Todas as dívidas"))
        din += [(f"/credito/{k}", fp.CATEGORIAS_CREDITO[k]) for k, _ in cats]
    except Exception:  # noqa: BLE001  (a navegação nunca derruba a página)
        din = []
    i = next((n + 1 for n, (r, _) in enumerate(base) if r == "/transacoes"), len(base))
    return base[:i] + din + base[i:]


# --------------------------------------------------------------------------------------------
# GET e POST
# --------------------------------------------------------------------------------------------
def get(con, rota: str, q: dict, sess: dict, pasta: Path):
    """(título, corpo) ou None quando a página não existe."""
    if rota == "/planilhas":
        return pg_planilhas(con, sess, pasta)
    if rota == "/investimentos":
        return pg_investimentos(con)
    if rota == "/emprestimos":
        return pg_emprestimos(con)
    if rota == "/contas":
        return pg_contas(con)
    if rota == "/cartoes":
        return pg_cartoes(con)
    if rota == "/cartoes/fechadas":
        return pg_cartoes(con, True)
    m = _CREDITO.fullmatch(rota)
    if m:
        return pg_emprestimos(con, m.group(1))
    if rota == "/conjunto":
        return pg_conjunto(con, q, sess)
    if rota == "/visoes":
        return pg_visoes(con, sess)
    if rota == "/visao":
        return pg_visao(con, q, sess)
    return None


def _inteiro(campos: dict, nome: str) -> int:
    try:
        return int(campos.get(nome, ""))
    except ValueError as ex:
        raise fn.ErroFinance("Pedido inválido.") from ex


def post(con, rota: str, campos: dict, arquivos: dict, sess: dict, pasta: Path, max_bytes: int) -> str:
    """Executa a ação e devolve a rota para onde voltar. Erros de uso viram aviso na própria página."""
    volta = "/planilhas"
    try:
        if rota == "/planilhas":
            arq = arquivos.get("arquivo")
            if not arq or not arq[1]:
                raise fn.ErroFinance("Escolha a planilha.")
            if len(arq[1]) > max_bytes:
                raise fn.ErroFinance(f"O limite é de {max_bytes // (1024 * 1024)} MB por arquivo.")
            res = fp.importar_arquivo(con, arq[1], arq[0], pasta, tipo=campos.get("tipo", "") if campos.get("tipo") in fp.TIPOS_USUARIO else "",
                                      nome=campos.get("nome", ""), inverter=campos.get("inverter") == "1")
            sess["flash"] = ("ok", resumo_resultados(res))
            ok = [r for r in res if r.get("ok") and r.get("conjunto_id")]
            if len(ok) == 1 and len(res) == 1:
                volta = f"/conjunto?id={ok[0]['conjunto_id']}"
            if campos.get("visao") == "1" and ok:
                criadas = []
                for r in ok:
                    nome_v = str(r.get("conjunto") or "Visão")[:60]
                    if con.execute("SELECT 1 FROM visoes WHERE conjunto_id=? AND nome=?", (r["conjunto_id"], nome_v)).fetchone():
                        continue   # importar de novo a mesma planilha não cria visão repetida
                    criadas.append(fp.criar_visao(con, r["conjunto_id"], nome_v))
                if criadas:
                    sess["flash"] = ("ok", sess["flash"][1] + (" Visão criada; escolha as colunas e a ordem abaixo." if len(criadas) == 1 else f" {len(criadas)} visões criadas na aba Visões."))
                    volta = f"/visao?id={criadas[0]}" if len(criadas) == 1 else "/visoes"
        elif rota == "/planilhas/duvida":
            did = _inteiro(campos, "id")
            res = fp.responder_duvida(con, pasta, did, {k: v for k, v in campos.items() if k in ("tipo", "nome") or k.startswith("papel:")})
            sess["flash"] = ("ok", resumo_resultados(res))
        elif rota == "/planilhas/duvida/descartar":
            fp.descartar_duvida(con, pasta, _inteiro(campos, "id"))
            sess["flash"] = ("ok", "Planilha descartada.")
        elif rota == "/visoes/nova":
            cid = _inteiro(campos, "conjunto_id")
            copiar = int(campos["copiar_de"]) if campos.get("copiar_de", "").isdigit() else None
            vid = fp.criar_visao(con, cid, campos.get("nome", ""), copiar_de=copiar)
            sess["flash"] = ("ok", "Visão criada. Escolha as colunas e a ordem abaixo.")
            volta = f"/visao?id={vid}"
        else:
            vid = _inteiro(campos, "id")
            volta = f"/visao?id={vid}"
            if not fp.visao(con, vid):
                raise fn.ErroFinance("Essa visão não existe mais.")
            if rota == "/visao/coluna":
                a, k = campos.get("acao", ""), campos.get("chave", "")
                if a == "acima":
                    fp.mover_coluna(con, vid, k, -1)
                elif a == "abaixo":
                    fp.mover_coluna(con, vid, k, 1)
                elif a == "tirar":
                    fp.tirar_coluna(con, vid, k)
                elif a == "incluir":
                    fp.por_coluna(con, vid, k)
                else:
                    raise fn.ErroFinance("Pedido inválido.")
                nome = dict(fp.colunas_do_conjunto(fp.conjunto(con, fp.visao(con, vid)["conjunto_id"]))).get(k, k)
                sess["flash"] = ("ok", {"acima": "Coluna movida para cima", "abaixo": "Coluna movida para baixo", "tirar": "Coluna tirada da visão", "incluir": "Coluna incluída na visão"}[a] + f": {nome}.")
            elif rota == "/visao/regras":
                fp.definir_regras(con, vid, campos.get("ordem", ""), campos.get("direcao", "asc"), campos.get("filtro_col", ""), campos.get("filtro_valor", ""),
                                  campos.get("agrupar", ""), campos.get("somar", ""))
                sess["flash"] = ("ok", "Ordenação, filtro e agrupamento salvos.")
            elif rota == "/visao/renomear":
                fp.renomear_visao(con, vid, campos.get("nome", ""))
                sess["flash"] = ("ok", "Visão renomeada.")
            elif rota == "/visao/apagar":
                cid = fp.visao(con, vid)["conjunto_id"]
                fp.apagar_visao(con, vid)
                sess["flash"] = ("ok", "Visão apagada. As linhas da planilha continuam guardadas.")
                volta = f"/conjunto?id={cid}"
    except fn.ErroFinance as ex:
        sess["flash"] = ("erro", str(ex))
    return volta
