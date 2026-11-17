#!/usr/bin/env python3
"""Heimdall Finance (finance.heimdall-ai.tech): suas finanças em páginas de texto e tabelas, para leitor de tela.

Você importa extratos (OFX ou CSV) do banco e do cartão; o painel classifica os gastos por categoria com regras que você
ajusta, mostra o resumo do mês, os maiores gastos, a evolução mês a mês e avisa quando uma categoria dispara.

Privacidade: nada aqui chama a internet. O banco SQLite fica em dados_financas/ (fora do git) e os dados financeiros nunca vão
para a Cloudflare nem para modelo de fora. O Cloudflare só repassa as páginas, como nos outros painéis.

Segurança (mesmas camadas dos outros painéis):
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada com a senha e o código de 6 dígitos do Heimdall Cloud (ou o Cloudflare Access, se ligado).
  3. Limite de tentativas, sessão em cookie HttpOnly e SameSite=Strict, token CSRF em todo POST.
  4. Só atende os nomes de site permitidos (HEIMDALL_FINANCE_HOSTS) e manda cabeçalhos de segurança.
  5. Sem senha e sem código configurados, o servidor não sobe.

Variáveis opcionais no .env: HEIMDALL_FINANCE_PORT (8016), HEIMDALL_FINANCE_HOST (127.0.0.1),
HEIMDALL_FINANCE_HOSTS (finance.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_FINANCE_DIR (pasta do banco) e HEIMDALL_FINANCE_MAX_MB (8).
"""
import html
import os
import re
import secrets
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis deste servidor."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if not chave.startswith("HEIMDALL_FINANCE_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import financas_arquivos as fa  # noqa: E402
import financas_analise as fanal  # noqa: E402
import financas_boletos as fb  # noqa: E402
import financas_email as femail  # noqa: E402
import heimdall_perguntar as perguntar  # noqa: E402
import financas_nucleo as fn  # noqa: E402
import heimdall_design as design  # noqa: E402  (padrão de interface: link lê, botão age)
import heimdall_paginacao as paginacao  # noqa: E402  (paginação em botões, igual no News e no Notas)
import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)

HOST = os.environ.get("HEIMDALL_FINANCE_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("HEIMDALL_FINANCE_PORT", "8016")))
except ValueError:
    PORT = 8016
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_FINANCE_HOSTS", "finance.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
DIR_DADOS = Path(os.environ.get("HEIMDALL_FINANCE_DIR") or (PROJECT_DIR / "dados_financas"))
try:
    MAX_ENVIO = int(float(os.environ.get("HEIMDALL_FINANCE_MAX_MB", "8")) * 1024 * 1024)
except ValueError:
    MAX_ENVIO = 8 * 1024 * 1024
COOKIE = nuvem.COOKIE
POR_PAGINA = 100
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

_con = None
_trava = threading.RLock()


def banco():
    global _con
    with _trava:
        if _con is None:
            DIR_DADOS.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(DIR_DADOS, 0o700)
            except OSError:
                pass
            caminho = DIR_DADOS / "financas.db"
            _con = fn.conectar(caminho)
            try:
                os.chmod(caminho, 0o600)
            except OSError:
                pass
        return _con


CSS = nuvem.CSS + paginacao.CSS + """
body{font-size:19px;line-height:1.6;max-width:62rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .4rem;font-size:1.25em}
table{border-collapse:collapse;width:100%;margin:.6rem 0}caption{text-align:left;font-weight:bold;padding:.3rem 0}
th,td{border:1px solid var(--linha);padding:.4rem .6rem;text-align:left;vertical-align:top}td.n,th.n{text-align:right;white-space:nowrap}
input[type=text],input[type=search],input[type=file],select{font-size:1em;padding:.5rem;margin:.3rem 0;max-width:28rem;width:100%}
button{margin:.3rem .3rem .3rem 0;padding:.5rem 1rem;font-size:1em}
.aviso{border:1px solid var(--linha);padding:.7rem;margin:1rem 0}.ok{border-left:6px solid var(--ok)}
form.linha{display:inline}.sub{color:inherit;opacity:.85}
td form.lim{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}td form.lim input{width:8rem;margin:0}td form.lim button{margin:0}
"""

NAV = [("/", "Resumo"), ("/transacoes", "Transações"), ("/tendencias", "Tendências"), ("/importar", "Importar extrato"), ("/orcamentos", "Orçamentos"), ("/recorrentes", "Contas recorrentes"), ("/analise", "Análise"), ("/futuros", "Pagamentos futuros"), ("/boletos", "Boletos"), ("/regras", "Regras")]


def pagina(titulo: str, corpo: str, sess: dict = None) -> bytes:
    nav = ""
    flash = ""
    perguntar_html = ""
    if sess:
        try:
            perguntar_html = _bloco_perguntar(sess)
        except Exception:  # noqa: BLE001  (a página nunca deixa de abrir por causa do campo Perguntar)
            perguntar_html = ""
        itens = "".join(f'<li><a href="{u}">{e(t)}</a></li>' for u, t in NAV)
        nav = (f'<nav aria-label="Principal"><ul>{itens}<li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
        f = sess.get("flash")
        if f:
            sess["flash"] = None
            flash = f'<div class="aviso {"ok" if f[0] == "ok" else ""}" role="status">{e(f[1])}</div>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Finance</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Finance", nav)}'
            f'<main id="principal"><h1>{e(titulo)}</h1>{flash}{corpo}{perguntar_html}</main></body></html>').encode("utf-8")


def tabela(legenda: str, cabecalhos: list, linhas: list, numericas: set = None) -> str:
    num = numericas or set()

    def attr(i):
        return ' class="n"' if i in num else ""

    cab = "".join(f'<th scope="col"{attr(i)}>{e(c)}</th>' for i, c in enumerate(cabecalhos))
    corpo = "".join("<tr>" + "".join(f"<td{attr(i)}>{c}</td>" for i, c in enumerate(l)) + "</tr>" for l in linhas)
    return f"<table><caption>{e(legenda)}</caption><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>"


def seletor_mes(atual: str, rota: str = "/", extra: str = "") -> str:
    ms = fn.meses(banco())
    if not ms:
        return ""
    op = "".join(f'<option value="{e(m)}"{" selected" if m == atual else ""}>{e(fn.nome_mes(m))}</option>' for m in ms)
    return (f'<form method="get" action="{rota}"><label for="mes">Mês</label><select id="mes" name="mes">{op}</select>{extra}'
            '<button type="submit">Ver</button></form>')


def seletor_visao(visao: str, rota: str, mes: str = "") -> str:
    """Troca entre a visão por compra (competência) e a visão por saída de caixa, mantendo o mês."""
    outra = "caixa" if visao != "caixa" else "competencia"
    atual = "por saída de caixa: conta o que saiu das suas contas, inclusive o pagamento da fatura, e as compras do cartão ficam de fora" if visao == "caixa" else "por compra: o gasto conta no dia da compra, e o pagamento da fatura fica de fora para não contar duas vezes"
    troca = "Ver por compra (competência)" if visao == "caixa" else "Ver por saída de caixa"
    return f'<p>Visão {e(atual)}.</p>' + design.botao(rota, troca, {"mes": mes, "visao": outra})


def opcoes_categoria(sel: str = "", incluir_todas: bool = False) -> str:
    tp = fn.tipos(banco())
    nomes = sorted(tp, key=lambda n: (n == fn.SEM_CATEGORIA, tp[n] != "gasto", n))
    o = '<option value="">Todas</option>' if incluir_todas else ""
    return o + "".join(f'<option value="{e(n)}"{" selected" if n == sel else ""}>{e(n)}{" (não entra nas somas)" if tp[n] == "neutra" else ""}</option>' for n in nomes)


def pg_resumo(mes: str, visao: str = "") -> tuple:
    visao = visao if visao in fn.VISOES else "competencia"
    ms = fn.meses(banco())
    if not ms:
        return "Resumo", ('<p>Ainda não há lançamentos. Comece importando o extrato do seu banco ou o da fatura do cartão (OFX ou CSV).</p>'
                          + design.botao("/importar", "Importar extrato"))
    if mes not in ms:
        mes = ms[0]
    r = fn.resumo_mes(banco(), mes, visao)
    dif = ""
    if r["despesas_anterior"]:
        v = round(100 * (r["despesas"] - r["despesas_anterior"]) / r["despesas_anterior"])
        dif = f' Isso é {abs(v)}% {"a mais" if v > 0 else "a menos"} que em {fn.nome_mes(fn.mes_anterior(mes))} ({fn.brl(r["despesas_anterior"])}).' if v else " Igual ao mês anterior."
    corpo = [seletor_mes(mes, "/", f'<input type="hidden" name="visao" value="{e(visao)}">'), seletor_visao(visao, "/", mes)]
    corpo.append(f'<p>Em {e(fn.nome_mes(mes))}: receitas de {e(fn.brl(r["receitas"]))}, despesas de {e(fn.brl(r["despesas"]))} e saldo de {e(fn.brl(r["saldo"], True))}.{e(dif)}</p>')
    orc = fn.orcamentos(banco(), mes, visao)
    if orc["com_limite"]:
        partes = []
        if orc["estourados"]:
            partes.append(f'{orc["estourados"]} estourado(s)')
        if orc["perto"]:
            partes.append(f'{orc["perto"]} perto do limite')
        corpo.append(f'<p>Orçamentos de {e(fn.nome_mes(mes))}: ' + (", ".join(partes) if partes else "todos dentro do limite") + ". "
                     + design.botao("/orcamentos", "Ver orçamentos", {"mes": mes, "visao": visao}) + "</p>")
    abertos = fb.listar(banco())
    urgentes = [b for b in abertos if b["dias"] is not None and b["dias"] <= 7]
    if urgentes:
        vencidos = len([b for b in urgentes if b["dias"] < 0])
        corpo.append(f'<p role="status">Boletos: {vencidos} vencido(s) e {len(urgentes) - vencidos} vencendo em até 7 dias, somando '
                     f'{e(fn.brl(sum(b["valor"] or 0 for b in urgentes)))}. ' + design.botao("/boletos", "Ver boletos") + "</p>")
    progr = [b for b in fb.listar(banco(), incluir_pagos=True) if b["estado"] == "programado"]
    if progr:
        corpo.append(f'<p class="sub">{len(progr)} boleto(s) já estão programados em débito automático ou cartão e ficaram fora das contas a pagar. ' + design.botao("/boletos", "Ver boletos") + "</p>")
    if r["neutros"]:
        texto = ("investimentos, transferências entre suas contas e faturas de terceiros" if visao == "caixa" else "pagamento de fatura, investimentos, transferências entre suas contas e faturas de terceiros")
        corpo.append(f'<p class="sub">Ficaram fora das somas {e(fn.brl(r["neutros"]))} em {texto}, para não contar duas vezes.</p>')
    if r["sem_fatura"] and visao != "caixa":
        itens = "".join(f'<li>{e(fn.data_br(p["data"]))}, {e(p["descricao"])}, {e(fn.brl(p["valor"]))} (conta {e(p["conta"])}). ' + design.botao(f"/transacao/{p['id']}", "Alterar categoria", None, f"Alterar categoria de {p['descricao'][:40]}") + '</li>' for p in r["sem_fatura"])
        corpo.append('<div class="aviso" role="status"><h2>Faturas pagas sem fatura importada</h2>'
                     f'<p>{len(r["sem_fatura"])} pagamento(s) de fatura deste mês não têm fatura importada que os explique. Entraram nas despesas como "{e(fn.SEM_FATURA)}", para você não perder o gasto. '
                     f'Se a fatura for de outra pessoa, mude a categoria do pagamento para "{e(fn.TERCEIROS)}" e ele sai das somas.</p><ul>{itens}</ul>'
                     + design.botao("/transacoes", "Ver todos os pagamentos sem fatura importada", {"produto": "fatura_sem"}) + '</div>')
    if r["sem_categoria"]:
        corpo.append(f'<div class="aviso" role="status">{r["sem_categoria"]} lançamento(s) sem categoria neste mês. '
                     + design.botao("/transacoes", "Classificar agora", {"mes": mes, "cat": fn.SEM_CATEGORIA}) + '</div>')
    linhas = []
    for c in r["categorias"]:
        var = "sem gasto no mês anterior" if c["variacao"] is None else (f'{c["variacao"]:+d}%' if c["variacao"] else "igual")
        elo = "/transacoes?produto=fatura_sem" if c["categoria"] == fn.SEM_FATURA else f'/transacoes?mes={e(mes)}&amp;cat={e(c["categoria"])}'
        linhas.append([f'<a href="{elo}">{e(c["categoria"])}</a>', e(fn.brl(c["total"])), f'{c["pct"]:.1f}%'.replace(".", ","), e(var)])
    corpo.append("<h2>Gastos por categoria</h2>" + (tabela(f"Gastos por categoria em {fn.nome_mes(mes)}", ["Categoria", "Total", "Parte das despesas", "Variação sobre o mês anterior"], linhas, {1, 2}) if linhas else "<p>Sem despesas neste mês.</p>"))
    mx = [[e(fn.data_br(m["data"])), e(m["descricao"]), e(m["categoria"]), e(fn.brl(-m["valor"])), e(m["conta"])] for m in r["maiores"]]
    corpo.append("<h2>Maiores gastos</h2>" + (tabela(f"Dez maiores gastos de {fn.nome_mes(mes)}", ["Data", "Descrição", "Categoria", "Valor", "Conta"], mx, {3}) if mx else "<p>Sem despesas neste mês.</p>"))
    return "Resumo", "".join(corpo)


def pg_transacoes(q: dict, sess: dict) -> tuple:
    mes, cat, busca = (q.get("mes") or [""])[0], (q.get("cat") or [""])[0], (q.get("q") or [""])[0][:80]
    conta, produto = (q.get("conta") or [""])[0][:80], (q.get("produto") or [""])[0][:20]
    soma = fn.somas_listagem(banco(), mes, cat, busca, conta, produto)
    paginas = paginacao.total_de_paginas(soma["n"], POR_PAGINA)
    pg = paginacao.limitar((q.get("pg") or ["1"])[0], paginas)
    total, linhas = fn.listar(banco(), mes, cat, busca, POR_PAGINA, (pg - 1) * POR_PAGINA, conta, produto)
    contas, produtos = fn.contas_e_produtos(banco())
    opconta = '<option value="">Todas</option>' + "".join(f'<option value="{e(c)}"{" selected" if c == conta else ""}>{e(c)} ({n})</option>' for c, n in contas)
    opprod = '<option value="">Todos</option>' + "".join(f'<option value="{e(k)}"{" selected" if k == produto else ""}>{e(fn.PRODUTOS[k])} ({n})</option>' for k, n in produtos)
    ms = fn.meses(banco())
    opmes = '<option value="">Todos</option>' + "".join(f'<option value="{e(m)}"{" selected" if m == mes else ""}>{e(fn.nome_mes(m))}</option>' for m in ms)
    filtro = ('<form method="get" action="/transacoes"><label for="mes">Mês</label><select id="mes" name="mes">' + opmes + '</select>'
              f'<label for="conta">Conta (banco e tipo)</label><select id="conta" name="conta">{opconta}</select>'
              f'<label for="produto">Produto</label><select id="produto" name="produto">{opprod}</select>'
              f'<label for="cat">Categoria</label><select id="cat" name="cat">{opcoes_categoria(cat, True)}</select>'
              f'<label for="q">Buscar na descrição</label><input id="q" name="q" type="search" value="{e(busca)}"><button type="submit">Filtrar</button></form>')
    inline = cat == fn.SEM_CATEGORIA
    rows = []
    for t in linhas:
        if inline:
            acao = (f'<form method="post" action="/transacao/{t["id"]}"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
                    f'<input type="hidden" name="volta" value="{e(mes)}"><label for="c{t["id"]}">Categoria de {e(t["descricao"][:40])}</label>'
                    f'<select id="c{t["id"]}" name="categoria">{opcoes_categoria()}</select><button type="submit">Salvar</button></form>')
        else:
            acao = design.botao(f"/transacao/{t['id']}", "Alterar categoria", None, f"Alterar categoria de {t['descricao'][:40]}")
        rows.append([e(fn.data_br(t["data"])), e(t["descricao"]), e(fn.brl(t["valor"], True)), e(t["categoria"]) + (" (manual)" if t["manual"] else ""), e(t["conta"]), e(fn.PRODUTOS.get(t["produto"], "")), acao])
    corpo = [filtro, f"<p>{total} lançamento(s) encontrado(s). Entradas: {e(fn.brl(soma['entradas']))}. Saídas: {e(fn.brl(soma['saidas']))}. Saldo do filtro: {e(fn.brl(soma['liquido'], True))}.</p>"]
    if rows:
        corpo.append(tabela("Lançamentos", ["Data", "Descrição", "Valor", "Categoria", "Conta", "Produto", "Ação"], rows, {2}))
    corpo.append(paginacao.html_paginacao("/transacoes", pg, paginas, {"mes": mes, "cat": cat, "q": busca, "conta": conta, "produto": produto}, f"{total} lançamentos", "pg"))
    corpo.append(design.botao("/exportar.csv", "Baixar tudo em CSV"))
    return "Transações", "".join(corpo)


def pg_transacao(tid: int, sess: dict):
    r = banco().execute("SELECT * FROM transacoes WHERE id=?", (tid,)).fetchone()
    if not r:
        return None
    corpo = (f'<p>{e(fn.data_br(r["data"]))}, {e(r["descricao"])}, {e(fn.brl(r["valor"], True))}, conta {e(r["conta"])}. Categoria atual: {e(r["categoria"])}.</p>'
             f'<form method="post" action="/transacao/{tid}"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
             f'<label for="categoria">Nova categoria</label><select id="categoria" name="categoria">{opcoes_categoria(r["categoria"])}</select>'
             '<label><input type="checkbox" name="regra" value="1" checked> Criar regra e aplicar aos lançamentos parecidos que você ainda não mexeu</label>'
             '<button type="submit">Salvar</button></form>'
             + ('<p class="sub">Atenção: este é um pagamento de fatura. Se você paga faturas de mais de uma pessoa e o texto no extrato é igual para todas, desmarque a opção de criar regra, para não mudar as suas também.</p>' if r["categoria"] == fn.FATURA_PAGA else "")
             + f'<p class="sub">Trecho que a regra usaria: {e(fn.padrao_da_descricao(r["desc_norm"]) or "(nenhum, só este lançamento muda)")}</p>'
             '<p><a href="/transacoes">Voltar às transações</a></p>')
    return "Alterar categoria", corpo


def pg_tendencias(visao: str = "") -> tuple:
    visao = visao if visao in fn.VISOES else "competencia"
    t = fn.tendencias(banco(), 12, visao)
    if not t["meses"]:
        return "Tendências", '<p>Importe pelo menos um extrato para ver a evolução.</p>' + design.botao("/importar", "Importar extrato")
    corpo = [seletor_visao(visao, "/tendencias")]
    if t["alertas"]:
        corpo.append('<div class="aviso" role="status"><h2>Atenção</h2><ul>' + "".join(f"<li>{e(a)}</li>" for a in t["alertas"]) + "</ul></div>")
    corpo.append(f'<p>Média de despesas por mês no período: {e(fn.brl(t["media_despesas"]))}.</p>')
    linhas = [[e(fn.nome_mes(l["mes"])), e(fn.brl(l["receitas"])), e(fn.brl(l["despesas"])), e(fn.brl(l["saldo"], True))] for l in reversed(t["linhas"])]
    corpo.append(tabela("Receitas, despesas e saldo por mês (do mais recente ao mais antigo)", ["Mês", "Receitas", "Despesas", "Saldo"], linhas, {1, 2, 3}))
    top = t["categorias"][:8]
    if top:
        cab = ["Mês"] + top
        lin = [[e(fn.nome_mes(l["mes"]))] + [e(fn.brl(l["cats"].get(c, 0))) for c in top] for l in reversed(t["linhas"])]
        corpo.append(tabela("Gasto por categoria em cada mês (as 8 categorias que mais pesam)", cab, lin, set(range(1, len(cab)))))
    return "Tendências", "".join(corpo)


def pg_importar(sess: dict) -> tuple:
    imp = banco().execute("SELECT * FROM importacoes ORDER BY id DESC LIMIT 10").fetchall()
    hist = ""
    if imp:
        hist = "<h2>Últimas importações</h2>" + tabela("Últimas importações", ["Quando", "Arquivo", "Conta", "Formato", "Novas", "Repetidas"],
                                                         [[e(i["quando"]), e(i["arquivo"]), e(i["conta"]), e(i["formato"]), str(i["novas"]), str(i["repetidas"])] for i in imp], {4, 5})
    pend = fa.pendentes(DIR_DADOS)
    if pend:
        hist += "<h2>Arquivos para revisar</h2>" + tabela("Arquivos para revisar", ["Arquivo", "Motivo"], [[e(n), e(m)] for n, m in pend])
    corpo = ('<p>Aceita OFX (a maioria dos bancos oferece em "exportar extrato"), CSV com colunas de data, descrição e valor e PDF de extrato ou de fatura. '
             'O banco e o tipo (conta ou cartão) são identificados pelo conteúdo e pelo nome do arquivo; se você deixar o nome da conta em branco, uso o que eu identificar. '
             'Importar o mesmo arquivo de novo não duplica nada: lançamentos já vistos são pulados.</p>'
             f'<form method="post" action="/importar" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
             '<label for="arquivo">Arquivo do extrato ou da fatura</label><input id="arquivo" name="arquivo" type="file" accept=".ofx,.csv,.txt,.pdf" required>'
             '<label for="conta">Nome da conta ou do cartão (por exemplo: Itaú conta, Nubank cartão). Deixe em branco para eu identificar.</label><input id="conta" name="conta" type="text" maxlength="60">'
             '<label><input type="checkbox" name="inverter" value="1"> Neste CSV os gastos vêm com valor positivo (comum em fatura de cartão)</label>'
             '<label><input type="checkbox" name="forcar" value="1"> Importar o PDF mesmo que o total do documento não confira com os lançamentos (só depois de revisar)</label>'
             '<button type="submit">Importar</button></form>'
             '<p class="sub">Dica: extrato de conta e fatura de cartão devem ser importados com nomes de conta diferentes. O pagamento da fatura na conta vira "Pagamento de fatura" e não conta como despesa, porque os gastos já aparecem na fatura. '
             'Você também pode soltar os arquivos na pasta de entrada (heimdall finance --folder): o Heimdall importa sozinho o que conferir e separa o que deixar dúvida.</p>' + hist)
    return "Importar extrato", corpo


def pg_orcamentos(q: dict, sess: dict) -> tuple:
    visao = (q.get("visao") or [""])[0]
    visao = visao if visao in fn.VISOES else "competencia"
    ms = fn.meses(banco())
    if not ms:
        return "Orçamentos", "<p>Ainda não há lançamentos. Importe um extrato primeiro.</p>" + design.botao("/importar", "Importar extrato")
    mes = (q.get("mes") or [""])[0]
    if mes not in ms:
        mes = ms[0]
    o = fn.orcamentos(banco(), mes, visao)
    corpo = [seletor_mes(mes, "/orcamentos", f'<input type="hidden" name="visao" value="{e(visao)}">'), seletor_visao(visao, "/orcamentos", mes),
             "<p>Um orçamento é o limite de gasto por mês numa categoria. Quando o gasto chega a 80% do limite a situação vira \"perto do limite\", e quando passa dele, \"estourado\". "
             "Os gastos seguem a visão escolhida acima. Para tirar o limite de uma categoria, use o botão Remover limite.</p>"]
    if o["com_limite"]:
        corpo.append(f'<p>Em {e(fn.nome_mes(mes))}: {o["com_limite"]} categoria(s) com limite, somando {e(fn.brl(o["total_limite"]))} de limite e {e(fn.brl(o["total_gasto"]))} gastos. '
                     f'{o["estourados"]} estourada(s), {o["perto"]} perto do limite e {o["dentro"]} dentro do limite.</p>')
    else:
        corpo.append("<p>Você ainda não definiu nenhum limite. Digite um valor em reais em qualquer categoria abaixo e salve.</p>")
    linhas = []
    nomes_estado = {"dentro": "Dentro do limite", "perto": "Perto do limite", "estourado": "Estourado"}
    for x in o["linhas"]:
        cat = x["categoria"]
        elo = f'<a href="/transacoes?mes={e(mes)}&amp;cat={e(cat)}">{e(cat)}</a>'
        oculto = (f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><input type="hidden" name="categoria" value="{e(cat)}">'
                  f'<input type="hidden" name="mes" value="{e(mes)}"><input type="hidden" name="visao" value="{e(visao)}">')
        valor = "" if x["limite"] is None else f'{x["limite"] // 100},{x["limite"] % 100:02d}'
        form = (f'<form class="lim" method="post" action="/orcamentos">{oculto}'
                f'<input type="text" name="limite" inputmode="decimal" value="{e(valor)}" aria-label="Limite mensal de {e(cat)}, em reais" required>'
                f'<button type="submit" aria-label="Salvar limite de {e(cat)}">Salvar limite</button></form>')
        if x["limite"] is not None:
            form += (f'<form class="lim" method="post" action="/orcamentos/remover">{oculto}'
                     f'<button type="submit" aria-label="Remover limite de {e(cat)}">Remover limite</button></form>')
        if x["limite"] is None:
            linhas.append([elo, "Sem limite", e(fn.brl(x["gasto"])), "", "", form])
        else:
            resto = f'Faltam {fn.brl(x["restante"])}' if x["restante"] >= 0 else f'Passou {fn.brl(-x["restante"])}'
            linhas.append([elo, e(fn.brl(x["limite"])), e(fn.brl(x["gasto"])), e(resto), e(f'{nomes_estado[x["estado"]]} ({x["pct"]}%)'), form])
    corpo.append("<h2>Categorias</h2>" + tabela(f"Orçamento de {fn.nome_mes(mes)} por categoria", ["Categoria", "Limite", "Gasto", "Restante", "Situação", "Alterar"], linhas, {1, 2}))
    return "Orçamentos", "".join(corpo)


def _texto_em_html(texto: str) -> str:
    """Texto da análise em HTML simples: linha que termina em dois-pontos vira subtítulo, 'N. frase' vira item de lista numerada."""
    saida, lista = [], False
    for ln in texto.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", ln)
        if m:
            if not lista:
                saida.append("<ol>")
                lista = True
            saida.append(f"<li>{e(m.group(1))}</li>")
            continue
        if lista:
            saida.append("</ol>")
            lista = False
        saida.append(f"<h3>{e(ln.rstrip(':'))}</h3>" if ln.endswith(":") else f"<p>{e(ln)}</p>")
    if lista:
        saida.append("</ol>")
    return "".join(saida)


def _gerar_analise(tipo: str) -> int:
    """Roda em segundo plano, com conexão própria: calcula os fatos, pede ao modelo local (com conferência) e guarda."""
    con = fn.conectar(DIR_DADOS / "financas.db")
    try:
        f = fanal.fatos(con, tipo)
        r = fanal.com_modelo(f)
        cur = con.execute("INSERT INTO analises(tipo, mes, gerado_em, origem, texto, avisos) VALUES(?,?,?,?,?,?)",
                          (tipo, f["mes"], time.strftime("%Y-%m-%d %H:%M:%S"), r["origem"], r["texto"], " ".join(r["avisos"])))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def pg_analise(sess: dict) -> tuple:
    """A semana e o mês já vêm prontos: a última análise salva ou, se não houver, a calculada agora pelas regras. Os botões geram uma nova com os dados de agora."""
    csrf = f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
    corpo = ['<p>Análise no estilo de consultor, só com redução de gastos, datas de pagamento, o que subiu e baixou e pontos de atenção, sem dica de investimento. '
             'Os números são calculados pelo Heimdall; o modelo local só redige o texto, e se ele citar um valor que não está nos dados, vale o texto calculado. Nada sai do Mac. '
             'O botão de cada análise gera uma nova com os dados que o Finance tem até agora.</p>']
    pendentes = {t["info"] for t in perguntar.em_andamento(sess["csrf"], "analise") if t["estado"] == "pensando"}
    for t in perguntar.em_andamento(sess["csrf"], "analise"):
        if t["estado"] == "erro":
            corpo.append(f'<p class="erro" role="alert">Não consegui gerar a análise {"da semana" if t["info"] == "semana" else "do mês"}: {e(t["erro"])}</p>')
    for tipo, titulo in (("semana", "Análise da semana"), ("mes", "Análise do mês")):
        corpo.append(f'<section aria-labelledby="a-{tipo}"><h2 id="a-{tipo}">{titulo}</h2>')
        ult = banco().execute("SELECT * FROM analises WHERE tipo=? ORDER BY id DESC LIMIT 1", (tipo,)).fetchone()
        if tipo in pendentes:
            corpo.append('<p role="status">O modelo local está escrevendo uma nova análise. Pode levar alguns minutos; use o botão abaixo para conferir.</p>'
                         + design.botao("/analise", "Ver a análise"))
        if ult:
            corpo.append(f'<p class="sub">Gerada em {e(ult["gerado_em"])}, com os dados até então. Texto feito por {e(ult["origem"])}.</p>')
            if ult["avisos"]:
                corpo.append(f'<p role="status">{e(ult["avisos"])}</p>')
            corpo.append(_texto_em_html(ult["texto"]))
            corpo.append(f'<form class="lim" method="post" action="/analise/notas">{csrf}<input type="hidden" name="id" value="{ult["id"]}">'
                         f'<button type="submit" aria-label="Salvar a {titulo.lower()} no Notas">Salvar no Notas</button></form>')
        else:
            try:
                f = fanal.fatos(banco(), tipo)
                corpo.append('<p class="sub">Ainda não há análise gerada com o modelo. Esta foi calculada agora, pelas regras, com os dados atuais.</p>' + _texto_em_html(fanal.texto_fixo(f)))
            except fn.ErroFinance as ex:
                corpo.append(f"<p>{e(str(ex))}</p>")
        corpo.append(f'<form class="lim" method="post" action="/analise/gerar">{csrf}<input type="hidden" name="tipo" value="{tipo}">'
                     f'<button type="submit">Gerar nova {titulo.lower()}</button></form></section>')
    corpo.append('<p class="sub">O botão Salvar no Notas grava na pasta Heimdall Finanças. O Notas pode sincronizar com o iCloud: só salve se aceitar que a análise vá para lá.</p>')
    return "Análise", "".join(corpo)


_ROTAS_VOLTA = {u for u, _ in NAV} | {"/transacoes"}


def _volta_valida(v: str) -> str:
    """Caminho da própria página para voltar depois de perguntar: só rotas conhecidas, com consulta simples; senão, o resumo."""
    m = re.fullmatch(r"(/[a-z]*)(\?[A-Za-z0-9=&%._-]{0,200})?", v or "")
    return v if m and m.group(1) in _ROTAS_VOLTA else "/"


def _bloco_perguntar(sess: dict) -> str:
    """Campo Perguntar no fim de toda página, com as respostas logo abaixo, da mais recente para a mais antiga."""
    atual = _volta_valida(sess.get("atual", "/"))
    mes = (parse_qs(urlparse(atual).query).get("mes") or [""])[0]
    csrf = f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
    h = ('<section aria-labelledby="perguntar-t" class="perguntar"><h2 id="perguntar-t">Perguntar sobre os seus dados</h2>'
         '<p class="sub">Pergunte em português, por exemplo: quanto gastei com mercado neste mês? O modelo local responde só com base nos seus dados, que não saem do Mac. '
         'A resposta aparece logo abaixo, a mais recente primeiro.</p>'
         f'<form method="post" action="/perguntar">{csrf}<input type="hidden" name="volta" value="{e(atual)}"><input type="hidden" name="mes" value="{e(mes)}">'
         '<p><label for="pergunta">Sua pergunta</label><br><input type="text" id="pergunta" name="pergunta" autocomplete="off" maxlength="300" required></p>'
         '<button type="submit">Perguntar</button></form>')
    pend = perguntar.em_andamento(sess["csrf"], "pergunta")
    if any(t["estado"] == "pensando" for t in pend):
        h += '<p role="status">O modelo local está pensando. Quando achar que acabou, use o botão abaixo.</p>' + design.botao(atual.split("?")[0], "Atualizar respostas", {k: v[0] for k, v in parse_qs(urlparse(atual).query).items()})
    for t in pend:
        if t["estado"] == "erro":
            h += f'<p class="erro" role="alert">Não consegui responder a pergunta "{e(t["info"])}": {e(t["erro"])}</p>'
    try:
        linhas = banco().execute("SELECT * FROM perguntas ORDER BY id DESC LIMIT 10").fetchall()
    except Exception:  # noqa: BLE001
        linhas = []
    if linhas:
        h += "<h3>Respostas, da mais recente para a mais antiga</h3>"
        for r in linhas:
            h += (f'<article><h4>{e(r["pergunta"])}</h4><p class="sub">Perguntado em {e(r["quando"])}.</p>' + _texto_em_html(r["resposta"])
                  + (f'<p role="status">{e(r["avisos"])}</p>' if r["avisos"] else "") + "</article>")
    return h + "</section>"


def _responder_e_guardar(ctx: str, pergunta: str, pagina_: str) -> int:
    """Em segundo plano: pergunta ao modelo local e guarda a resposta no banco, para aparecer no fim de qualquer página."""
    r = perguntar.responder(ctx, pergunta)
    con = fn.conectar(DIR_DADOS / "financas.db")
    try:
        cur = con.execute("INSERT INTO perguntas(quando, pagina, pergunta, resposta, avisos) VALUES(?,?,?,?,?)",
                          (time.strftime("%Y-%m-%d %H:%M:%S"), pagina_, pergunta, r["texto"], " ".join(r["avisos"])))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def _token_agente() -> str:
    if os.environ.get("HEIMDALL_AGENTE_TOKEN"):
        return os.environ["HEIMDALL_AGENTE_TOKEN"]
    try:
        for ln in (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("HEIMDALL_AGENTE_TOKEN="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _salvar_nota(titulo: str, markdown: str) -> None:
    import json
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8003/notas/gravar", method="POST", data=json.dumps({"pasta": "Heimdall Finanças", "titulo": titulo, "markdown": markdown}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Heimdall-Token": _token_agente()})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()


def pg_futuros(sess: dict) -> tuple:
    csrf = f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
    f = fn.futuros(banco())
    corpo = ['<p>O que ainda vai sair ou entrar nos próximos meses: parcelas que faltam (lidas das faturas e extratos), contas recorrentes detectadas, '
             'pagamentos que você mesmo cadastrou e boletos em aberto. Boleto vencido entra no mês atual. Se algo detectado estiver errado, use Ignorar.</p>']
    origem = {"parcela": "Parcela", "recorrente": "Recorrente", "manual": "Cadastrado por você", "boleto": "Boleto"}
    for mes in f["meses"]:
        t = f'Saídas previstas {fn.brl(mes["saidas"])}, entradas previstas {fn.brl(mes["entradas"])}'
        if not mes["itens"]:
            corpo.append(f'<h2>{e(fn.nome_mes(mes["mes"]))}</h2><p>Nada previsto.</p>')
            continue
        linhas = []
        for x in mes["itens"]:
            if x["origem"] in ("parcela", "recorrente"):
                acao = (f'<form class="lim" method="post" action="/futuros/ignorar">{csrf}<input type="hidden" name="chave" value="{e(x["chave"])}"><input type="hidden" name="ignorar" value="1">'
                        f'<button type="submit" aria-label="Ignorar: {e(x["descricao"])}">Ignorar</button></form>')
            elif x["origem"] == "manual":
                acao = (f'<form class="lim" method="post" action="/futuros/remover">{csrf}<input type="hidden" name="id" value="{x["id"]}">'
                        f'<button type="submit" aria-label="Remover: {e(x["descricao"])}">Remover</button></form>')
            else:
                acao = design.botao("/boletos", "Ver boletos")
            linhas.append([e(fn.data_br(x["data"])), e(x["descricao"]), e(origem[x["origem"]]), e(fn.brl(x["valor"], True)), acao])
        corpo.append(f'<h2>{e(fn.nome_mes(mes["mes"]))}</h2><p>{e(t)}.</p>' + tabela(f'Previsto para {fn.nome_mes(mes["mes"])}', ["Dia", "Descrição", "Origem", "Valor", "Ação"], linhas, {3}))
    corpo.append('<h2>Cadastrar um pagamento ou entrada</h2><p>Para o que não aparece nos extratos, como um aluguel pago por fora. Deixe o mês final vazio se não tiver fim.</p>'
                 f'<form method="post" action="/futuros">{csrf}'
                 '<p><label for="fdesc">Descrição</label><br><input type="text" id="fdesc" name="descricao" required></p>'
                 '<p><label for="fval">Valor em reais</label><br><input type="text" id="fval" name="valor" inputmode="decimal" required></p>'
                 '<p><label for="fdia">Dia do mês, de 1 a 31</label><br><input type="text" id="fdia" name="dia" inputmode="numeric" required></p>'
                 '<p><label for="fini">Mês inicial, AAAA-MM (vazio = este mês)</label><br><input type="text" id="fini" name="inicio"></p>'
                 '<p><label for="ffim">Mês final, AAAA-MM (opcional)</label><br><input type="text" id="ffim" name="fim"></p>'
                 '<p><label for="ftipo">Tipo</label><br><select id="ftipo" name="tipo"><option value="saida">Saída</option><option value="entrada">Entrada</option></select></p>'
                 '<button type="submit">Cadastrar</button></form>')
    ign = [r["chave"] for r in banco().execute("SELECT chave FROM ignorados ORDER BY chave")]
    if ign:
        linhas = []
        for c in ign:
            nome = c.split(":", 1)[1].rsplit(":", 2)[0] if c.startswith("parcela:") else c.split(":", 1)[1]
            linhas.append([e(("Parcela: " if c.startswith("parcela:") else "Recorrente: ") + nome),
                           f'<form class="lim" method="post" action="/futuros/ignorar">{csrf}<input type="hidden" name="chave" value="{e(c)}"><input type="hidden" name="ignorar" value="0">'
                           f'<button type="submit" aria-label="Voltar a considerar: {e(nome)}">Voltar a considerar</button></form>'])
        corpo.append("<h2>Ignorados</h2>" + tabela("Itens que você mandou ignorar", ["Item", "Ação"], linhas))
    return "Pagamentos futuros", "".join(corpo)


def _bloco_pessoas(csrf: str) -> str:
    nomes = fb.pessoas(banco())
    html_ = ('<h2>Pessoas</h2><p>Cadastre as pessoas cujos boletos você paga, por exemplo sua noiva e sua filha, para agrupar os boletos e somar o que está em aberto de cada uma. '
             'Só o nome: o Heimdall não guarda CPF. Ao ler um PDF, ele procura o nome no campo Pagador.</p>'
             f'<form method="post" action="/boletos/pessoa">{csrf}<p><label for="npessoa">Nome da pessoa</label><br><input type="text" id="npessoa" name="nome" autocomplete="off" required></p>'
             '<button type="submit">Adicionar pessoa</button></form>')
    if nomes:
        linhas = [[e(n), f'<form class="lim" method="post" action="/boletos/pessoa/remover">{csrf}<input type="hidden" name="nome" value="{e(n)}">'
                         f'<button type="submit" aria-label="Remover pessoa: {e(n)}">Remover</button></form>'] for n in nomes]
        html_ += tabela("Pessoas cadastradas", ["Nome", "Ação"], linhas)
    return html_


def _opcoes_pessoas(atual: str) -> str:
    return '<option value="">Sem pessoa</option>' + "".join(f'<option value="{e(n)}"{" selected" if n == atual else ""}>{e(n)}</option>' for n in fb.pessoas(banco()))


def pg_boletos(sess: dict) -> tuple:
    csrf = f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
    corpo = ['<p>Aqui ficam os boletos como contas a pagar. O Heimdall lê a linha digitável, confere os dígitos verificadores e mostra valor e vencimento. '
             'Ele nunca paga nada: o pagamento é sempre com você, no app do banco. PDF de boleto solto na pasta de entrada também é registrado.</p>',
             '<h2>Registrar um boleto</h2>'
             f'<form method="post" action="/boletos">{csrf}<p><label for="linha">Linha digitável (47 ou 48 números, pontos e espaços podem ficar) ou Pix copia e cola</label><br>'
             '<input type="text" id="linha" name="linha" autocomplete="off" required></p>'
             '<p><label for="quem">Quem recebe (opcional)</label><br><input type="text" id="quem" name="quem" autocomplete="off"></p>'
             f'<p><label for="dono">De quem é este boleto</label><br><select id="dono" name="dono">{_opcoes_pessoas("")}</select></p>'
             '<button type="submit">Registrar boleto</button></form>']
    try:
        fb.conciliar(banco())  # o histórico pode ter mudado desde a última visita
    except Exception:  # noqa: BLE001
        pass
    lista = fb.listar(banco(), incluir_pagos=True)
    if not lista:
        corpo.append("<p>Nenhum boleto registrado ainda.</p>")
        return "Boletos", "".join(corpo) + _bloco_pessoas(csrf)
    totais = {}
    for b in lista:
        if b["estado"] not in ("pago", "programado"):
            totais[b["dono"] or "Sem pessoa"] = totais.get(b["dono"] or "Sem pessoa", 0) + (b["valor"] or 0)
    if totais and (len(totais) > 1 or "Sem pessoa" not in totais):
        corpo.append("<p>Total em aberto por pessoa: " + "; ".join(f"{e(k)} {e(fn.brl(v))}" for k, v in sorted(totais.items())) + ".</p>")
    estados = {"vencido": "Vencido", "vence hoje": "Vence hoje", "a vencer": "A vencer", "sem vencimento": "Sem vencimento no código", "pago": "Pago", "programado": "Já programado"}
    linhas = []
    for b in lista:
        quem = b["beneficiario"] or b["banco"] or b["segmento"] or "Sem identificação"
        valor = fn.brl(b["valor"]) if b["valor"] else "Em aberto (o pagador define)"
        venc = fn.data_br(b["vencimento"]) if b["vencimento"] else "Sem vencimento"
        sit = estados[b["estado"]]
        if b["dias"] is not None and b["estado"] not in ("pago", "programado"):
            sit += f' ({"há " + str(-b["dias"]) + " dia(s)" if b["dias"] < 0 else "em " + str(b["dias"]) + " dia(s)"})' if b["dias"] != 0 else ""
        if b.get("motivo"):
            sit += f". {b['motivo']}"
        if b["aviso"]:
            sit += f". Atenção: {b['aviso']}"
        if (b["arquivo"] or "").startswith("e-mail"):
            sit += f". Origem: {b['arquivo']}"
        oculto = f'{csrf}<input type="hidden" name="id" value="{b["id"]}">'
        fechado = b["estado"] in ("pago", "programado")
        rotulo = "É para pagar mesmo" if b["estado"] == "programado" else ("Reabrir" if b["estado"] == "pago" else "Marcar como pago")
        acoes = (f'<form class="lim" method="post" action="/boletos/situacao">{oculto}<input type="hidden" name="pago" value="{0 if fechado else 1}">'
                 f'<button type="submit" aria-label="{rotulo}: boleto de {e(quem)}">{rotulo}</button></form>'
                 f'<form class="lim" method="post" action="/boletos/remover">{oculto}<button type="submit" aria-label="Remover boleto de {e(quem)}">Remover</button></form>')
        pessoa = (f'<form class="lim" method="post" action="/boletos/dono">{oculto}'
                  f'<select name="dono" aria-label="Pessoa do boleto de {e(quem)}">{_opcoes_pessoas(b["dono"] or "")}</select><button type="submit" aria-label="Mudar a pessoa do boleto de {e(quem)}">Mudar pessoa</button></form>')
        linhas.append([e(quem), pessoa, e(valor), e(venc), e(sit), acoes])
    corpo.append("<h2>Boletos</h2>" + tabela("Boletos registrados, do vencimento mais próximo ao mais distante", ["Quem recebe", "Pessoa", "Valor", "Vencimento", "Situação", "Ações"], linhas, {2}))
    corpo.append('<p class="sub">Marcar como pago é só uma anotação sua; não envia nada ao banco.</p>')
    return "Boletos", "".join(corpo) + _bloco_pessoas(csrf)


def pg_recorrentes() -> tuple:
    r = fn.recorrentes(banco())
    if not r["series"]:
        return "Contas recorrentes", ("<p>Ainda não achei lançamentos que se repetem todo mês. É preciso ter pelo menos 3 meses de histórico "
                                      "(ou 2 meses seguidos com o mesmo valor) para uma conta aparecer aqui. Importe mais extratos e faturas.</p>"
                                      + design.botao("/importar", "Importar extrato"))
    corpo = [(f'<p>Achei {len([s for s in r["series"] if s["situacao"] != "encerrada"])} lançamento(s) que se repetem todo mês. Em média, saem {e(fn.brl(r["gasto_mensal"]))} '
              f'e entram {e(fn.brl(r["renda_mensal"]))} por mês nessas séries. Elas são deduzidas do seu histórico, não são cadastradas: o dia e o valor são os típicos.</p>')]
    titulos = {"atrasada": ("Esperadas neste mês e ainda não apareceram", "Passou do dia habitual e o lançamento não está no histórico. Pode estar atrasada ou o extrato mais recente ainda não foi importado."),
               "por_vir": ("Ainda por vir neste mês", "Estão dentro do prazo habitual."),
               "chegou": ("Já apareceram neste mês", ""), "encerrada": ("Possivelmente encerradas", "Não aparecem há mais de dois meses.")}
    for sit in ("atrasada", "por_vir", "chegou", "encerrada"):
        lista = [s for s in r["series"] if s["situacao"] == sit]
        if not lista:
            continue
        linhas = []
        for s in lista:
            nome = e(s["descricao"]) + (" (parcelada)" if s["parcelada"] else "") + (" (entrada)" if s["entrada"] else "")
            valor = fn.brl(abs(s["valor"])) + ("" if s["fixo"] else " (varia)")
            linhas.append([nome, e(s["categoria"]), e(valor), f'dia {s["dia"]}', f'{s["n"]} meses, último em {e(fn.nome_mes(s["ultimo"]))}'])
        t, aviso = titulos[sit]
        corpo.append(f"<h2>{e(t)}</h2>" + (f'<p class="sub">{e(aviso)}</p>' if aviso else "")
                     + tabela(t, ["Descrição", "Categoria", "Valor típico", "Dia típico", "Visto em"], linhas, {2}))
    return "Contas recorrentes", "".join(corpo)


def pg_regras(sess: dict) -> tuple:
    rs = banco().execute("SELECT * FROM regras ORDER BY (origem='usuario') DESC, categoria, padrao").fetchall()
    meu = [[e(r["padrao"]), e(r["categoria"]),
            f'<form method="post" action="/regras/apagar"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><input type="hidden" name="id" value="{r["id"]}">'
            f'<button type="submit" aria-label="Apagar a regra {e(r["padrao"])}">Apagar</button></form>'] for r in rs if r["origem"] == "usuario"]
    padrao = [[e(r["padrao"].strip()), e(r["categoria"])] for r in rs if r["origem"] != "usuario"]
    corpo = [('<p>Uma regra diz: se a descrição do lançamento tem este trecho (no início de uma palavra, sem acento e sem diferenciar maiúsculas), a categoria é esta. '
              'As suas regras vencem as padrão. Lançamentos que você categorizou à mão nunca são mudados por regras.</p>'
              f'<form method="post" action="/regras"><input type="hidden" name="csrf" value="{e(sess["csrf"])}">'
              '<label for="padrao">Trecho da descrição</label><input id="padrao" name="padrao" type="text" maxlength="60" required>'
              f'<label for="cat">Categoria</label><select id="cat" name="categoria">{opcoes_categoria()}</select><button type="submit">Adicionar regra</button></form>')]
    corpo.append("<h2>Suas regras</h2>" + (tabela("Suas regras", ["Trecho", "Categoria", "Ação"], meu) if meu else "<p>Você ainda não criou regras. Ao alterar a categoria de um lançamento, a regra nasce sozinha.</p>"))
    corpo.append("<h2>Regras padrão</h2>" + tabela("Regras padrão", ["Trecho", "Categoria"], padrao))
    return "Regras de categoria", "".join(corpo)


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


CSP_PAGINA = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"


class Finance(BaseHTTPRequestHandler):
    server_version = "HeimdallFinance"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # nunca registra parâmetros nem corpo
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP_PAGINA)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, nuvem.sessao_valida(token, "finance")

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        return nuvem.cabecalho_cookie(token, self.headers.get("Host", ""), self._https(), apagar)

    def _corpo(self, limite: int) -> bytes:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > limite:
            raise OverflowError
        return self.rfile.read(n)

    def do_GET(self):  # noqa: N802
        self._despachar("GET")

    def do_POST(self):  # noqa: N802
        self._despachar("POST")

    def do_HEAD(self):  # noqa: N802
        self._despachar("GET")

    def _despachar(self, metodo: str) -> None:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in HOSTS_OK:
            self._enviar(421, b"Host nao permitido", "text/plain; charset=utf-8")
            return
        u = urlparse(self.path)
        rota, q = u.path, parse_qs(u.query)
        if rota == "/saude":
            self._enviar(200, b"ok", "text/plain; charset=utf-8")
            return
        sess = None
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                self._ir("/entrar")
                return
            with _trava:
                if metodo == "POST":
                    self._post(rota, token, sess)
                else:
                    self._get(rota, q, sess)
        except OverflowError:
            self._enviar(413, pagina("Arquivo grande demais", f"<p>O limite é de {MAX_ENVIO // (1024 * 1024)} MB por arquivo.</p>", sess))
        except fn.ErroFinance as ex:
            if sess:
                sess["flash"] = ("erro", str(ex))
            self._ir("/importar" if rota == "/importar" else "/regras" if rota.startswith("/regras") else "/orcamentos" if rota.startswith("/orcamentos") else "/boletos" if rota.startswith("/boletos") else "/futuros" if rota.startswith("/futuros") else "/analise" if rota.startswith("/analise") else "/perguntar" if rota.startswith("/perguntar") else "/transacoes")
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    def _get(self, rota: str, q: dict, sess: dict) -> None:
        sess["atual"] = self.path
        if rota == "/":
            titulo, corpo = pg_resumo((q.get("mes") or [""])[0], (q.get("visao") or [""])[0])
        elif rota == "/transacoes":
            titulo, corpo = pg_transacoes(q, sess)
        elif rota == "/tendencias":
            titulo, corpo = pg_tendencias((q.get("visao") or [""])[0])
        elif rota == "/importar":
            titulo, corpo = pg_importar(sess)
        elif rota == "/orcamentos":
            titulo, corpo = pg_orcamentos(q, sess)
        elif rota == "/analise":
            titulo, corpo = pg_analise(sess)
        elif rota == "/perguntar":
            self._ir("/")
            return
        elif rota == "/futuros":
            titulo, corpo = pg_futuros(sess)
        elif rota == "/boletos":
            titulo, corpo = pg_boletos(sess)
        elif rota == "/recorrentes":
            titulo, corpo = pg_recorrentes()
        elif rota == "/regras":
            titulo, corpo = pg_regras(sess)
        elif rota == "/exportar.csv":
            self._enviar(200, fn.exportar_csv(banco()).encode("utf-8-sig"), "text/csv; charset=utf-8",
                         [("Content-Disposition", 'attachment; filename="heimdall-finance.csv"')])
            return
        else:
            m = re.fullmatch(r"/transacao/(\d{1,9})", rota)
            r = pg_transacao(int(m.group(1)), sess) if m else None
            if not r:
                self._enviar(404, pagina("Não encontrei", '<p><a href="/">Voltar ao resumo</a></p>', sess))
                return
            titulo, corpo = r
        self._enviar(200, pagina(titulo, corpo, sess))

    def _post(self, rota: str, token: str, sess: dict) -> None:
        tipo = self.headers.get("Content-Type", "")
        campos, arquivos = nuvem._formulario(self._corpo(MAX_ENVIO + 65536 if rota == "/importar" else 16384), tipo)
        if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
            self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
            return
        if rota == "/sair":
            nuvem.encerrar_sessao(token)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        if rota == "/importar":
            arq = arquivos.get("arquivo")
            if not arq or not arq[1]:
                raise fn.ErroFinance("Escolha o arquivo do extrato.")
            if len(arq[1]) > MAX_ENVIO:
                raise OverflowError
            r = fa.importar_arquivo(banco(), arq[1], arq[0], campos.get("conta", ""), campos.get("forcar") == "1",
                                    True if campos.get("inverter") == "1" else None)
            sess["flash"] = ("ok", f"Importado ({r['formato']}) na conta {r['conta']}: {r['lidas']} lançamentos lidos, {r['novas']} novos e {r['repetidas']} já existentes.")
            self._ir("/")
            return
        m = re.fullmatch(r"/transacao/(\d{1,9})", rota)
        if m:
            veio_da_lista = "volta" in campos
            n = fn.definir_categoria(banco(), int(m.group(1)), campos.get("categoria", ""), veio_da_lista or campos.get("regra") == "1")
            sess["flash"] = ("ok", f"Categoria salva. {n} lançamento(s) atualizado(s).")
            if veio_da_lista:
                mes = campos["volta"] if re.fullmatch(r"\d{4}-\d{2}", campos["volta"]) else ""
                self._ir("/transacoes?cat=Sem%20categoria" + (f"&mes={mes}" if mes else ""))
            else:
                self._ir("/transacoes")
            return
        if rota in ("/orcamentos", "/orcamentos/remover"):
            cat = campos.get("categoria", "")
            volta = "/orcamentos?" + "&".join(f"{k}={campos[k]}" for k in ("mes", "visao") if re.fullmatch(r"[0-9a-z-]{1,10}", campos.get(k, "")))
            if rota == "/orcamentos":
                v = fn.definir_orcamento(banco(), cat, campos.get("limite", ""))
                sess["flash"] = ("ok", f"Limite de {cat} salvo: {fn.brl(v)} por mês.")
            else:
                sess["flash"] = ("ok", f"Limite de {cat} removido." if fn.remover_orcamento(banco(), cat) else f"{cat} não tinha limite.")
            self._ir(volta)
            return
        if rota == "/analise/gerar":
            tipo = campos.get("tipo", "")
            if tipo not in ("semana", "mes"):
                raise fn.ErroFinance("Escolha analisar a semana ou o mês.")
            fanal.fatos(banco(), tipo)  # falha logo, com mensagem clara, se não houver lançamentos
            perguntar.iniciar(sess["csrf"], "analise" , lambda: _gerar_analise(tipo), tipo)
            sess["flash"] = ("ok", "Comecei a análise. O modelo local pode levar alguns minutos; use Ver a análise para conferir.")
            self._ir("/analise")
            return
        if rota == "/analise/notas":
            ult = banco().execute("SELECT * FROM analises WHERE id=?", (campos.get("id", "0") if campos.get("id", "0").isdigit() else 0,)).fetchone()
            if not ult:
                raise fn.ErroFinance("Não achei essa análise.")
            try:
                _salvar_nota(("Análise da semana " if ult["tipo"] == "semana" else "Análise de ") + (ult["gerado_em"][:10] if ult["tipo"] == "semana" else fn.nome_mes(ult["mes"])), ult["texto"])
                sess["flash"] = ("ok", "Análise salva na pasta Heimdall Finanças do Notas.")
            except Exception as ex:  # noqa: BLE001
                sess["flash"] = ("erro", f"Não consegui salvar no Notas ({type(ex).__name__}). O agente do Mac está de pé?")
            self._ir("/analise")
            return
        if rota == "/perguntar":
            q_ = " ".join(campos.get("pergunta", "").split())[:300]
            if len(q_) < 3:
                raise fn.ErroFinance("Digite a pergunta.")
            volta = _volta_valida(campos.get("volta", "/"))
            mes_p = campos.get("mes", "") if re.fullmatch(r"\d{4}-\d{2}", campos.get("mes", "")) else ""
            ctx = fanal.contexto_pergunta(banco(), q_, None, mes_p)
            perguntar.iniciar(sess["csrf"], "pergunta", lambda: _responder_e_guardar(ctx, q_, volta), q_)
            sess["flash"] = ("ok", "Pergunta enviada ao modelo local. A resposta aparece no fim da página; use Atualizar respostas para conferir.")
            self._ir(volta)
            return
        if rota == "/futuros":
            fn.adicionar_previsto(banco(), campos.get("descricao", ""), campos.get("valor", ""), campos.get("dia", ""), campos.get("inicio", ""), campos.get("fim", ""), campos.get("tipo") == "entrada")
            sess["flash"] = ("ok", "Cadastrado em pagamentos futuros.")
            self._ir("/futuros")
            return
        if rota == "/futuros/remover":
            try:
                ok = fn.remover_previsto(banco(), int(campos.get("id", "0")))
            except ValueError:
                ok = False
            sess["flash"] = ("ok", "Removido." if ok else "Não achei esse item.")
            self._ir("/futuros")
            return
        if rota == "/futuros/ignorar":
            chave = campos.get("chave", "")
            if re.fullmatch(r"(parcela|recorrente):[^\s].{0,150}", chave):
                fn.ignorar_detectado(banco(), chave, campos.get("ignorar") == "1")
                sess["flash"] = ("ok", "Ignorado: não entra mais nas previsões." if campos.get("ignorar") == "1" else "Voltou a entrar nas previsões.")
            self._ir("/futuros")
            return
        if rota == "/boletos":
            b = fb.completar_pix(fb.interpretar(campos.get("linha", "")))
            idb, novo = fb.registrar(banco(), b, campos.get("quem", ""), "", None, campos.get("dono", "") if campos.get("dono", "") in fb.pessoas(banco()) else "")
            sess["flash"] = ("ok", ("Boleto registrado: " if novo else "Esse boleto já estava registrado: ") + fb.frase({**b, "beneficiario": campos.get("quem", "").strip() or b.get("beneficiario", "")}) + ".")
            self._ir("/boletos")
            return
        if rota == "/boletos/pessoa":
            nome = fb.adicionar_pessoa(banco(), campos.get("nome", ""))
            sess["flash"] = ("ok", f"Pessoa cadastrada: {nome}.")
            self._ir("/boletos")
            return
        if rota == "/boletos/pessoa/remover":
            sess["flash"] = ("ok", "Pessoa removida; os boletos dela ficaram sem pessoa." if fb.remover_pessoa(banco(), campos.get("nome", "")) else "Não achei essa pessoa.")
            self._ir("/boletos")
            return
        if rota == "/boletos/dono":
            try:
                ok = fb.definir_dono(banco(), int(campos.get("id", "0")), campos.get("dono", ""))
            except ValueError:
                ok = False
            sess["flash"] = ("ok", "Pessoa do boleto atualizada." if ok else "Não achei esse boleto.")
            self._ir("/boletos")
            return
        if rota in ("/boletos/situacao", "/boletos/remover"):
            try:
                idb = int(campos.get("id", "0"))
            except ValueError:
                idb = 0
            if rota == "/boletos/remover":
                sess["flash"] = ("ok", "Boleto removido." if fb.remover(banco(), idb) else "Não achei esse boleto.")
            else:
                pago = campos.get("pago") == "1"
                sess["flash"] = ("ok", ("Boleto marcado como pago." if pago else "Boleto reaberto.") if fb.definir_situacao(banco(), idb, pago) else "Não achei esse boleto.")
            self._ir("/boletos")
            return
        if rota == "/regras":
            n = fn.adicionar_regra(banco(), campos.get("padrao", ""), campos.get("categoria", ""))
            sess["flash"] = ("ok", f"Regra salva. {n} lançamento(s) reclassificado(s).")
            self._ir("/regras")
            return
        if rota == "/regras/apagar":
            try:
                ok = fn.apagar_regra(banco(), int(campos.get("id", "0")))
            except ValueError:
                ok = False
            if ok:
                n = fn.reaplicar_regras(banco())
                sess["flash"] = ("ok", f"Regra apagada. {n} lançamento(s) reclassificado(s).")
            self._ir("/regras")
            return
        self._enviar(405, pagina("Não permitido", "<p>Pedido não reconhecido.</p>", sess))

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            via_access = nuvem.entrada_por_access(self.headers, "finance")  # aprovado no Cloudflare Access (Microsoft Authenticator), se ligado
            if via_access:
                self._enviar(200, nuvem.pagina_continuar(), extra=[self._cookie(via_access)])
                return
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if nuvem.login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
        senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
        passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
            nuvem.registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])


def _vigiar_entrada() -> None:
    """A cada minuto importa o que foi solto em dados_financas/entrada. Só registra o nome do arquivo, nunca os valores."""
    fa.preparar_pasta(DIR_DADOS)
    while True:
        try:
            with _trava:
                for r in fa.processar_entrada(banco(), DIR_DADOS):
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} entrada: {r['arquivo']} -> " + ("duplicado apagado" if r.get("duplicado") else "motivos antigos limpos" if r.get("limpeza") else f"{r['conta']} ({r['novas']} novos)" if r["ok"] else "para revisar") + "\n")
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} entrada: erro {type(ex).__name__}\n")
        time.sleep(60)


def _vigiar_email() -> None:
    """A cada 15 minutos lê o Gmail (somente leitura) atrás de boletos e Pix. Só roda com a senha de e-mail no .env; HEIMDALL_FINANCE_EMAIL=0 desliga."""
    if os.environ.get("HEIMDALL_FINANCE_EMAIL", "1") == "0":
        return
    cfg = femail.credenciais()
    if not cfg:
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} e-mail: sem senha de e-mail no .env; leitura de boletos por e-mail desligada\n")
        return
    while True:
        try:
            msgs = femail.buscar(cfg)  # rede fora da trava
            with _trava:
                estado_arq = DIR_DADOS / "email_estado.json"
                try:
                    estado = __import__("json").loads(estado_arq.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    estado = {}
                res = femail.processar(banco(), msgs, estado)
                try:
                    estado_arq.write_text(__import__("json").dumps(estado), encoding="utf-8")
                    estado_arq.chmod(0o600)
                except OSError:
                    pass
            for r in res:
                sys.stderr.write(f"{time.strftime('%H:%M:%S')} e-mail: boleto de {r['remetente']}: {r['novos']} novo(s)" + (" (remetente não autenticado)" if r["aviso"] else "") + "\n")
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} e-mail: erro {type(ex).__name__}\n")
        time.sleep(900)


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o Heimdall Finance não sobe. Rode: python3 heimdall_acesso.py --tudo")
    banco()
    threading.Thread(target=_vigiar_entrada, daemon=True).start()
    threading.Thread(target=_vigiar_email, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Finance)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Finance em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))}; dados em {DIR_DADOS})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
