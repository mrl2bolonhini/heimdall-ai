#!/usr/bin/env python3
"""Heimdall Library: apps conectados por conta (notas, tarefas, agenda e contatos), com leitura automática.

Primeiro provedor: Microsoft (OneNote, Microsoft To Do, Calendário e Contatos do Outlook), pela Microsoft Graph, com permissões delegadas de leitura
(Notes.Read, Tasks.Read, Calendars.Read, Contacts.Read) pedidas só para os serviços que a pessoa marcar. Funciona com conta pessoal e de trabalho ou escola,
em qualquer sistema, porque a leitura é feita pelo servidor: a pessoa só autoriza uma vez no navegador.

Cada nota, tarefa, evento ou contato vira um documento de texto (Markdown) no acervo da pessoa, pesquisável junto com os demais e disponível ao Perguntar.
O item é identificado por provedor, serviço e id: se mudar no app, o mesmo documento é atualizado, sem duplicar. Só leitura; nada é alterado no app.
A autorização, os tokens cifrados e a rodada de fundo vêm de heimdall_conexoes.py.
"""
import html
import html.parser
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


def _ler_notas(token: str, api: str):
    for x in _paginar(api + "/me/onenote/pages?$top=100", token):
        st, _, b = cx.http("GET", api + "/me/onenote/pages/" + urllib.parse.quote(x["id"]) + "/content", {"Authorization": "Bearer " + token, "Accept": "text/html"})
        if st != 200:
            continue   # página sem conteúdo legível: tenta de novo na próxima rodada
        titulo = _limpo(x.get("title")) or "Nota sem título"
        secao = _limpo((x.get("parentSection") or {}).get("displayName"))
        corpo = html_para_texto(b.decode("utf-8", "replace"))
        yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Nota", titulo),
               "texto": f"# {titulo}\n\nOrigem: OneNote{' · ' + secao if secao else ''}\nAtualizada em: {_data(x.get('lastModifiedDateTime'))}\n\n{corpo}\n"}


def _ler_tarefas(token: str, api: str):
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


def _ler_agenda(token: str, api: str):
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


def _ler_contatos(token: str, api: str):
    url = api + "/me/contacts?" + urllib.parse.urlencode({"$top": 100, "$select": "id,displayName,emailAddresses,mobilePhone,businessPhones,homePhones,companyName,jobTitle,lastModifiedDateTime,personalNotes"})
    for x in _paginar(url, token):
        nome = _limpo(x.get("displayName")) or "Contato sem nome"
        emails = ", ".join(_limpo(e.get("address")) for e in x.get("emailAddresses", []) if e.get("address"))
        fones = ", ".join(_limpo(t) for t in [x.get("mobilePhone")] + list(x.get("businessPhones") or []) + list(x.get("homePhones") or []) if t)
        yield {"id": x["id"], "marca": x.get("lastModifiedDateTime", ""), "nome": _nome_arquivo("Contato", nome),
               "texto": (f"# {nome}\n\nOrigem: Contatos do Outlook\n" + (f"Empresa: {_limpo(x.get('companyName'))}\n" if x.get("companyName") else "")
                         + (f"Cargo: {_limpo(x.get('jobTitle'))}\n" if x.get("jobTitle") else "") + (f"E-mail: {emails}\n" if emails else "")
                         + (f"Telefone: {fones}\n" if fones else "") + (f"\n{_limpo(x.get('personalNotes'), 2000)}\n" if x.get("personalNotes") else ""))}


LEITORES = {"notas": _ler_notas, "tarefas": _ler_tarefas, "agenda": _ler_agenda, "contatos": _ler_contatos}


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
                for it in LEITORES[serv](token, api):
                    if vistos.get(it["id"]) == it["marca"] and it["marca"]:
                        continue
                    if feitos >= MAX_POR_RODADA:
                        break
                    feitos += 1
                    try:
                        r = base.adicionar(it["nome"], it["texto"].encode("utf-8"), "microsoft-" + serv, usar_ia, chave=f"{chave}:{serv}:{it['id']}")
                        res["novos" if r.get("novo") else "atualizados" if r.get("atualizado") else "repetidos"] += 1
                        vistos[it["id"]] = it["marca"]
                    except ErroLibrary:
                        res["erros"] += 1
            except ErroLibrary as ex:
                res["erros"] += 1
                falhas.append(f"{cx.PROVEDORES[chave]['nomes_servico'][serv]}: {ex}")
        est["erro"] = " ".join(falhas)
        est["ultimo"] = time.strftime("%d/%m/%Y %H:%M")
        est["resumo"] = f"{res['novos']} novos, {res['atualizados']} atualizados, {res['erros']} com erro"
        cx.gravar(todos)
    return res


cx.registrar("apps", sincronizar)
