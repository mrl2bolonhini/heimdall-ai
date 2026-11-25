#!/usr/bin/env python3
"""Heimdall Library: apps conectados por conta (notas, tarefas, agenda e contatos), com leitura automática.

Provedores: Microsoft (OneNote, Microsoft To Do, Microsoft Planner, Calendário e Contatos do Outlook), pela Microsoft Graph, com permissões delegadas de leitura
(Notes.Read, Tasks.Read, Calendars.Read, Contacts.Read) pedidas só para os serviços que a pessoa marcar (o Planner só existe em conta de trabalho ou escola);
Notion (páginas que a pessoa compartilhar na autorização); Todoist (tarefas ativas, escopo data:read); Trello (cartões dos quadros abertos, escopo read). Funciona em qualquer sistema, porque a leitura é feita pelo
servidor: a pessoa só autoriza uma vez no navegador.

Cada nota, tarefa, cartão, evento ou contato vira um documento de texto (Markdown) no acervo da pessoa, pesquisável junto com os demais e disponível ao Perguntar.
O item é identificado por provedor, serviço e id: se mudar no app, o mesmo documento é atualizado, sem duplicar. Só leitura; nada é alterado no app.
A autorização, os tokens cifrados e a rodada de fundo vêm de heimdall_conexoes.py.
"""
import hashlib
import html
import html.parser
import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import heimdall_conexoes as cx
import heimdall_library_dados as base

ErroLibrary = base.ErroLibrary
MAX_POR_RODADA = 300      # itens novos ou alterados por rodada (o resto fica para a próxima)
MAX_PAGINAS = 10          # páginas de 100 itens por serviço
JANELA_AGENDA = (30, 180)  # dias para trás e para frente


# ---------------------------------------------------------------- texto
class _Texto(html.parser.HTMLParser):
    BLOCOS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self._pular = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._pular += 1
        elif tag in self.BLOCOS:
            self.partes.append("\n")
        if tag == "li":
            self.partes.append("- ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._pular = max(0, self._pular - 1)
        elif tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._pular:
            self.partes.append(data)


def html_para_texto(conteudo: str) -> str:
    p = _Texto()
    p.feed(conteudo or "")
    linhas = [" ".join(l.split()) for l in "".join(p.partes).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def _limpo(t, n=200) -> str:
    return " ".join(str(t or "").split())[:n]


def _nome_arquivo(prefixo: str, titulo: str, extra: str = "") -> str:
    base_ = re.sub(r"[^\w\- ().,]", "_", _limpo(f"{prefixo} - {titulo}{extra}", 90)).strip(" .") or prefixo
    return base_ + ".md"


def _data(x) -> str:
    """Data/hora da Graph ({"dateTime": ..., "timeZone": ...}) em texto simples."""
    if isinstance(x, dict):
        return f"{(x.get('dateTime') or '')[:16].replace('T', ' ')} ({x.get('timeZone') or 'UTC'})".strip() if x.get("dateTime") else ""
    return str(x or "")[:16].replace("T", " ")


# ---------------------------------------------------------------- leitura de cada serviço (Microsoft Graph)
def _paginar(url: str, token: str, cab: dict = None):
    for _ in range(MAX_PAGINAS):
        r = cx.json_get(url, token, cab)
        yield from r.get("value", [])
        url = r.get("@odata.nextLink")
        if not url:
            return


def _ler_notas(token: str, api: str, vistos: dict):
    for x in _paginar(api + "/me/onenote/pages?$top=100", token):
        if vistos.get(x["id"]) == x.get("lastModifiedDateTime") and x.get("lastModifiedDateTime"):
            yield {"id": x["id"], "marca": x["lastModifiedDateTime"], "nome": "", "texto": ""}   # sem mudança: não baixa o conteúdo de novo
            continue
        st, _, b = cx.http("GET", api + "/me/onenote/pages/" + urllib.parse.quote(x["id"]) + "/content", {"Authorization": "Bearer " + token, "Accept": "text/html"})
        if st != 200:
            continue   # página sem conteúdo legível: tenta de novo na próxima rodada
        titulo = _limpo(x.get("title")) or "Nota sem título"
        secao = _limpo((x.get("parentSection") or {}).get("displayName"))
        corpo = html_para_texto(b.decode("utf-8", "replace"))
        yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Nota", titulo),
               "texto": f"# {titulo}\n\nOrigem: OneNote{' · ' + secao if secao else ''}\nAtualizada em: {_data(x.get('lastModifiedDateTime'))}\n\n{corpo}\n"}


def _ler_tarefas(token: str, api: str, vistos: dict):
    for lista in _paginar(api + "/me/todo/lists", token):
        for x in _paginar(api + "/me/todo/lists/" + urllib.parse.quote(lista["id"]) + "/tasks?$top=100", token):
            titulo = _limpo(x.get("title")) or "Tarefa sem título"
            corpo = x.get("body") or {}
            detalhe = html_para_texto(corpo["content"]) if corpo.get("contentType") == "html" else (corpo.get("content") or "").strip()
            concluida = x.get("status") == "completed"
            yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Tarefa", titulo),
                   "texto": (f"# {titulo}\n\nOrigem: Microsoft To Do · lista {_limpo(lista.get('displayName'))}\nSituação: {'concluída' if concluida else 'a fazer'}\n"
                             + (f"Prazo: {_data(x.get('dueDateTime'))}\n" if x.get("dueDateTime") else "")
                             + (f"Importância: {x['importance']}\n" if x.get("importance") not in (None, "normal") else "") + (f"\n{detalhe}\n" if detalhe else ""))}


def _ler_agenda(token: str, api: str, vistos: dict):
    agora = datetime.now(timezone.utc)
    de, ate = (agora - timedelta(days=JANELA_AGENDA[0])).strftime("%Y-%m-%dT%H:%M:%SZ"), (agora + timedelta(days=JANELA_AGENDA[1])).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (api + "/me/calendarView?" + urllib.parse.urlencode({"startDateTime": de, "endDateTime": ate, "$top": 100,
                                                                 "$select": "id,subject,start,end,location,bodyPreview,lastModifiedDateTime,isAllDay,organizer"}))
    for x in _paginar(url, token):
        titulo = _limpo(x.get("subject")) or "Evento sem título"
        local = _limpo((x.get("location") or {}).get("displayName"))
        org = _limpo(((x.get("organizer") or {}).get("emailAddress") or {}).get("name"))
        ini = _data(x.get("start"))
        yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Evento", titulo, f" {ini[:10]}"),
               "texto": (f"# {titulo}\n\nOrigem: Calendário do Outlook\nInício: {ini}{' (dia inteiro)' if x.get('isAllDay') else ''}\nFim: {_data(x.get('end'))}\n"
                         + (f"Local: {local}\n" if local else "") + (f"Organizador: {org}\n" if org else "") + (f"\n{_limpo(x.get('bodyPreview'), 2000)}\n" if x.get("bodyPreview") else ""))}


def _ler_contatos(token: str, api: str, vistos: dict):
    url = api + "/me/contacts?" + urllib.parse.urlencode({"$top": 100, "$select": "id,displayName,emailAddresses,mobilePhone,businessPhones,homePhones,companyName,jobTitle,lastModifiedDateTime,personalNotes"})
    for x in _paginar(url, token):
        nome = _limpo(x.get("displayName")) or "Contato sem nome"
        emails = ", ".join(_limpo(e.get("address")) for e in x.get("emailAddresses", []) if e.get("address"))
        fones = ", ".join(_limpo(t) for t in [x.get("mobilePhone")] + list(x.get("businessPhones") or []) + list(x.get("homePhones") or []) if t)
        yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Contato", nome),
               "texto": (f"# {nome}\n\nOrigem: Contatos do Outlook\n" + (f"Empresa: {_limpo(x.get('companyName'))}\n" if x.get("companyName") else "")
                         + (f"Cargo: {_limpo(x.get('jobTitle'))}\n" if x.get("jobTitle") else "") + (f"E-mail: {emails}\n" if emails else "")
                         + (f"Telefone: {fones}\n" if fones else "") + (f"\n{_limpo(x.get('personalNotes'), 2000)}\n" if x.get("personalNotes") else ""))}


def _ler_planner(token: str, api: str, vistos: dict):
    """Tarefas atribuídas à pessoa no Microsoft Planner. A Graph só permite com conta de trabalho ou escola; conta pessoal recebe recusa."""
    try:
        planos = {p["id"]: _limpo(p.get("title")) for p in _paginar(api + "/me/planner/plans", token)}
        tarefas = list(_paginar(api + "/me/planner/tasks", token))
    except ErroLibrary:
        raise ErroLibrary("O Planner só está disponível com conta Microsoft de trabalho ou escola.") from None
    for x in tarefas:
        marca = x.get("@odata.etag") or x.get("createdDateTime", "")
        titulo = _limpo(x.get("title")) or "Tarefa sem título"
        if vistos.get(x["id"]) == marca and marca:
            yield {"id": x["id"], "marca": marca, "nome": "", "texto": ""}
            continue
        detalhe, itens = "", []
        try:
            d = cx.json_get(api + "/planner/tasks/" + urllib.parse.quote(x["id"]) + "/details", token)
            detalhe = (d.get("description") or "").strip()
            itens = [(_limpo(v.get("title")), bool(v.get("isChecked"))) for v in (d.get("checklist") or {}).values() if v.get("title")]
        except ErroLibrary:
            pass   # sem detalhes agora: o título e o prazo já valem
        pct = int(x.get("percentComplete") or 0)
        yield {"id": x["id"], "marca": marca, "nome": _nome_arquivo("Tarefa", titulo),
               "texto": (f"# {titulo}\n\nOrigem: Microsoft Planner · plano {planos.get(x.get('planId'), '')}\nSituação: {'concluída' if pct == 100 else 'em andamento' if pct else 'a fazer'}\n"
                         + (f"Prazo: {_data(x.get('dueDateTime'))}\n" if x.get("dueDateTime") else "") + (f"\n{detalhe}\n" if detalhe else "")
                         + ("\nLista de verificação:\n" + "\n".join(f"- [{'x' if ok else ' '}] {t}" for t, ok in itens) + "\n" if itens else ""))}


# ---------------------------------------------------------------- Todoist
def _todoist_paginas(url: str, token: str):
    cursor = ""
    for _ in range(MAX_PAGINAS):
        r = cx.json_get(url + ("&" if "?" in url else "?") + "limit=200" + (("&cursor=" + urllib.parse.quote(cursor)) if cursor else ""), token)
        yield from r.get("results", [])
        cursor = r.get("next_cursor") or ""
        if not cursor:
            return


PRIORIDADE_TODOIST = {4: "urgente", 3: "alta", 2: "média"}


def _ler_todoist(token: str, api: str, vistos: dict):
    projetos = {p["id"]: _limpo(p.get("name")) for p in _todoist_paginas(api + "/projects", token)}
    for x in _todoist_paginas(api + "/tasks", token):
        titulo = _limpo(x.get("content")) or "Tarefa sem título"
        due = x.get("due") or {}
        prazo = _limpo(due.get("string") or due.get("date"), 80)
        marca = hashlib.sha256(json.dumps([x.get("content"), x.get("description"), due, x.get("project_id"), x.get("labels"), x.get("priority"), x.get("checked")], sort_keys=True).encode()).hexdigest()[:20]
        yield {"id": str(x["id"]), "marca": marca, "nome": _nome_arquivo("Tarefa", titulo),
               "texto": (f"# {titulo}\n\nOrigem: Todoist · projeto {projetos.get(x.get('project_id'), '')}\nSituação: {'concluída' if x.get('checked') else 'a fazer'}\n"
                         + (f"Prazo: {prazo}\n" if prazo else "") + (f"Prioridade: {PRIORIDADE_TODOIST[x['priority']]}\n" if x.get("priority") in PRIORIDADE_TODOIST else "")
                         + (f"Etiquetas: {', '.join(_limpo(l, 40) for l in x['labels'])}\n" if x.get("labels") else "") + (f"\n{(x.get('description') or '').strip()}\n" if (x.get("description") or "").strip() else ""))}


# ---------------------------------------------------------------- Trello
def _ler_trello(token: str, api: str, vistos: dict):
    cab = {"Authorization": cx.cab_trello(token)}
    quadros = cx.json_get(api + "/members/me/boards?" + urllib.parse.urlencode({"filter": "open", "fields": "name"}), "", cab)
    for q in quadros if isinstance(quadros, list) else []:
        listas = {l["id"]: _limpo(l.get("name")) for l in cx.json_get(api + f"/boards/{urllib.parse.quote(q['id'])}/lists?" + urllib.parse.urlencode({"filter": "open", "fields": "name"}), "", cab)}
        cartoes = cx.json_get(api + f"/boards/{urllib.parse.quote(q['id'])}/cards?" + urllib.parse.urlencode({"filter": "open", "fields": "name,desc,due,dueComplete,idList,dateLastActivity,labels"}), "", cab)
        for x in cartoes:
            titulo = _limpo(x.get("name")) or "Cartão sem título"
            etiquetas = ", ".join(_limpo(l.get("name") or l.get("color"), 40) for l in x.get("labels", []) if l.get("name") or l.get("color"))
            yield {"id": x["id"], "marca": x.get("dateLastActivity", ""), "nome": _nome_arquivo("Cartão", titulo),
                   "texto": (f"# {titulo}\n\nOrigem: Trello · quadro {_limpo(q.get('name'))} · lista {listas.get(x.get('idList'), '')}\n"
                             + (f"Prazo: {_data(x.get('due'))}{' (concluído)' if x.get('dueComplete') else ''}\n" if x.get("due") else "")
                             + (f"Etiquetas: {etiquetas}\n" if etiquetas else "") + (f"\n{(x.get('desc') or '').strip()[:5000]}\n" if (x.get("desc") or "").strip() else ""))}


# ---------------------------------------------------------------- Notion
PAUSA_NOTION = 0.34          # o Notion aceita cerca de 3 pedidos por segundo
MAX_BLOCOS_NOTION = 800      # blocos lidos por página
PROFUNDIDADE_NOTION = 3
TEXTO_BLOCOS = {"paragraph": "", "heading_1": "# ", "heading_2": "## ", "heading_3": "### ", "bulleted_list_item": "- ", "numbered_list_item": "1. ", "quote": "> ",
                "callout": "", "toggle": "", "to_do": "- [ ] "}


def _rich(lista) -> str:
    return "".join((t.get("plain_text") or "") for t in (lista or []))


def _notion_chamar(metodo: str, url: str, token: str, corpo: dict = None) -> dict:
    time.sleep(PAUSA_NOTION)
    cab = {"Authorization": "Bearer " + token, "Accept": "application/json", **cx.PROVEDORES["notion"]["cab_api"]}
    dados_ = None
    if corpo is not None:
        cab["Content-Type"], dados_ = "application/json", json.dumps(corpo).encode()
    st, _, b = cx.http(metodo, url, cab, dados_)
    if st == 429:
        raise ErroLibrary("O Notion pediu para esperar. Tentarei de novo na próxima rodada.")
    if st != 200:
        raise ErroLibrary(f"O provedor recusou a leitura (código {st}).")
    try:
        return json.loads(b or b"{}")
    except ValueError:
        raise ErroLibrary("Resposta inesperada do provedor.") from None


def _blocos_notion(token: str, api: str, bloco: str, linhas: list, contador: list, nivel: int = 0) -> None:
    cursor = ""
    while contador[0] < MAX_BLOCOS_NOTION:
        r = _notion_chamar("GET", api + f"/blocks/{urllib.parse.quote(bloco)}/children?page_size=100" + (("&start_cursor=" + urllib.parse.quote(cursor)) if cursor else ""), token)
        for b in r.get("results", []):
            contador[0] += 1
            tipo = b.get("type", "")
            dado = b.get(tipo) or {}
            recuo = "  " * nivel
            if tipo in TEXTO_BLOCOS:
                texto = _rich(dado.get("rich_text"))
                prefixo = ("- [x] " if dado.get("checked") else "- [ ] ") if tipo == "to_do" else TEXTO_BLOCOS[tipo]
                if texto:
                    linhas.append(recuo + prefixo + texto)
            elif tipo == "code":
                linhas.append(recuo + _rich(dado.get("rich_text")))
            elif tipo == "table_row":
                linhas.append(recuo + " | ".join(_rich(c) for c in dado.get("cells", [])))
            elif tipo == "child_page":
                linhas.append(recuo + "Subpágina: " + _limpo(dado.get("title")))
            elif tipo in ("bookmark", "embed", "link_preview"):
                linhas.append(recuo + _limpo(dado.get("url"), 300))
            if b.get("has_children") and nivel < PROFUNDIDADE_NOTION and tipo != "child_page":
                _blocos_notion(token, api, b["id"], linhas, contador, nivel + 1)
        cursor = r.get("next_cursor") or ""
        if not (r.get("has_more") and cursor):
            return


def _titulo_notion(pagina: dict) -> str:
    for v in (pagina.get("properties") or {}).values():
        if v.get("type") == "title":
            return _limpo(_rich(v.get("title")))
    return ""


def _ler_notion(token: str, api: str, vistos: dict):
    """Páginas que a pessoa compartilhou com a integração (inclusive linhas de bancos de dados). O conteúdo só é baixado se a página mudou."""
    cursor = ""
    for _ in range(MAX_PAGINAS):
        r = _notion_chamar("POST", api + "/search", token, {"filter": {"property": "object", "value": "page"}, "page_size": 100, **({"start_cursor": cursor} if cursor else {})})
        for x in r.get("results", []):
            if x.get("archived") or x.get("in_trash"):
                continue
            marca = x.get("last_edited_time", "")
            if vistos.get(x["id"]) == marca and marca:
                yield {"id": x["id"], "marca": marca, "nome": "", "texto": ""}
                continue
            titulo = _titulo_notion(x) or "Página sem título"
            linhas = []
            try:
                _blocos_notion(token, api, x["id"], linhas, [0])
            except ErroLibrary:
                continue   # página sem conteúdo legível agora: tenta de novo na próxima rodada
            yield {"id": x["id"], "marca": marca, "nome": _nome_arquivo("Página", titulo),
                   "texto": f"# {titulo}\n\nOrigem: Notion\nEditada em: {_data(marca)}\n\n" + "\n".join(linhas) + "\n"}
        cursor = r.get("next_cursor") or ""
        if not (r.get("has_more") and cursor):
            return


LEITORES = {"microsoft": {"notas": _ler_notas, "tarefas": _ler_tarefas, "planner": _ler_planner, "agenda": _ler_agenda, "contatos": _ler_contatos},
            "todoist": {"tarefas": _ler_todoist}, "trello": {"quadros": _ler_trello}, "notion": {"paginas": _ler_notion}}


# ---------------------------------------------------------------- tela e sincronização
def disponiveis(chave: str) -> list:
    return list(cx.PROVEDORES[chave]["nomes_servico"].items())


def situacao() -> list:
    todos = cx.carregar() if cx.configurados("apps") else {}
    saida = []
    for k in cx.configurados("apps"):
        e = todos.get(k, {})
        nomes = cx.PROVEDORES[k]["nomes_servico"]
        saida.append({"chave": k, "nome": cx.PROVEDORES[k]["nome"], "conectado": bool(e.get("renovacao")), "servicos": list(e.get("servicos", [])),
                      "nomes": [nomes[s] for s in e.get("servicos", []) if s in nomes], "disponiveis": list(nomes.items()), "ultimo": e.get("ultimo", ""),
                      "resumo": e.get("resumo", ""), "erro": e.get("erro", "")})
    return saida


def sincronizar(chave: str, usar_ia: bool = False) -> dict:
    """Lê os serviços conectados da pessoa de agora e grava no acervo só o que é novo ou mudou. Devolve as contagens."""
    if chave not in cx.PROVEDORES or chave not in cx.configurados("apps"):
        raise ErroLibrary("Este provedor não está configurado pelo administrador.")
    res = {"novos": 0, "atualizados": 0, "repetidos": 0, "erros": 0}
    api = cx.PROVEDORES[chave]["api"]
    with cx.LOCK:
        todos = cx.carregar()
        est = todos.get(chave)
        if not est:
            raise ErroLibrary("Conecte o provedor antes de sincronizar.")
        token = cx.acesso(chave, todos)
        todos_vistos = est.setdefault("vistos_apps", {})
        falhas, feitos = [], 0
        for serv in est.get("servicos", []):
            vistos = todos_vistos.setdefault(serv, {})
            try:
                for it in LEITORES[chave][serv](token, api, vistos):
                    if vistos.get(it["id"]) == it["marca"] and it["marca"]:
                        continue
                    if feitos >= MAX_POR_RODADA:
                        break
                    feitos += 1
                    try:
                        r = base.adicionar(it["nome"], it["texto"].encode("utf-8"), f"{chave}-{serv}", usar_ia, chave=f"{chave}:{serv}:{it['id']}")
                        res["novos" if r.get("novo") else "atualizados" if r.get("atualizado") else "repetidos"] += 1
                        vistos[it["id"]] = it["marca"]
                    except ErroLibrary:
                        res["erros"] += 1
            except ErroLibrary as ex:
                res["erros"] += 1
                falhas.append(f"{cx.PROVEDORES[chave]['nomes_servico'][serv]}: {ex}")
        if cx.PROVEDORES[chave].get("sem_renovacao") and any("código 401" in f for f in falhas):   # token revogado pela pessoa no app: pede nova conexão
            est.update({"acesso": "", "renovacao": "", "erro": "A autorização foi revogada no app. Conecte de novo."})
            falhas = [est["erro"]]
        est["erro"] = " ".join(falhas)
        est["ultimo"] = time.strftime("%d/%m/%Y %H:%M")
        est["resumo"] = f"{res['novos']} novos, {res['atualizados']} atualizados, {res['erros']} com erro"
        cx.gravar(todos)
    return res


cx.registrar("apps", sincronizar)
