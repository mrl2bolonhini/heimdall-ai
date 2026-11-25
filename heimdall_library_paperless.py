#!/usr/bin/env python3
"""Heimdall Library com o Paperless-ngx como motor (HEIMDALL_LIBRARY_MOTOR=paperless).

O Paperless-ngx roda em Docker neste Mac, escutando só em 127.0.0.1, sem login exposto: o Library é a única tela e fala com ele pela API REST (token).
O Paperless faz o OCR, guarda os arquivos, lê e-mails (regras IMAP) e classifica; a classificação aprende com as correções que a pessoa grava em "A revisar".
Estas funções têm os mesmos nomes e formatos de heimdall_library_dados.py, que as chama no lugar das internas quando o motor é o Paperless (para todos:
cada convidado ganha um usuário próprio no Paperless e o Library filtra tudo por dono; o e-mail é só do dono).

Convenções: a etiqueta "A revisar" marca o que ainda não foi confirmado; a etiqueta "Lixeira" marca o que foi excluído pelo Library (nada é apagado do Paperless).
Variáveis: HEIMDALL_PAPERLESS_URL (http://127.0.0.1:8023), HEIMDALL_PAPERLESS_USER (heimdall), HEIMDALL_PAPERLESS_SENHA, HEIMDALL_LIBRARY_EMAIL_SENHA (senha de aplicativo do e-mail).
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import heimdall_library_dados as base

ErroLibrary = base.ErroLibrary
PROJECT_DIR = Path(__file__).resolve().parent
TAG_REVISAR, TAG_LIXEIRA = "A revisar", "Lixeira"
SISTEMA = (TAG_REVISAR, TAG_LIXEIRA)
_estado = {"tokens": {}, "ids": {}}   # token e id de usuário por nome de usuário do Paperless
PERMISSOES_CONVIDADO = [f"{a}_{o}" for o in ("document", "tag", "documenttype", "correspondent") for a in ("view", "add", "change")]   # sem exclusão e sem e-mail


def _pessoa() -> str:
    """Nome do convidado em atendimento (vazio para o dono)."""
    d = base.banco._PESSOA_DIR.get()
    return d.name if d else ""


def _usuario() -> str:
    p = _pessoa()
    return f"heimdall-{p}" if p else os.environ.get("HEIMDALL_PAPERLESS_USER", "heimdall")


def _senha_convidado(pessoa: str) -> str:
    """Senha derivada da chave do Paperless: não precisa ser guardada em lugar nenhum."""
    import hashlib
    import hmac
    return hmac.new(os.environ.get("HEIMDALL_PAPERLESS_SECRET", "").encode(), f"convidado:{pessoa}".encode(), hashlib.sha256).hexdigest()[:40]


def _url() -> str:
    return os.environ.get("HEIMDALL_PAPERLESS_URL", "http://127.0.0.1:8023").rstrip("/")


def pasta_entrada() -> Path:
    if _pessoa():
        return base.ORIGINAIS["pasta_entrada"]()   # convidado: pasta própria; o Library envia os arquivos ao Paperless
    return PROJECT_DIR / "paperless" / "consume"


def _login(usuario: str, senha: str) -> str:
    corpo = json.dumps({"username": usuario, "password": senha}).encode()
    with urllib.request.urlopen(urllib.request.Request(_url() + "/api/token/", data=corpo, headers={"Content-Type": "application/json", "Accept": "application/json"}), timeout=15) as r:
        return json.loads(r.read())["token"]


def _token(renovar: bool = False, dono: bool = False) -> str:
    """Token do usuário em atendimento: o dono usa a conta do .env; cada convidado, a sua, criada na primeira vez (com a senha derivada)."""
    pessoa = "" if dono else _pessoa()
    usuario = os.environ.get("HEIMDALL_PAPERLESS_USER", "heimdall") if not pessoa else f"heimdall-{pessoa}"
    if _estado["tokens"].get(usuario) and not renovar:
        return _estado["tokens"][usuario]
    senha = os.environ.get("HEIMDALL_PAPERLESS_SENHA", "") if not pessoa else _senha_convidado(pessoa)
    if not senha or (pessoa and not os.environ.get("HEIMDALL_PAPERLESS_SECRET")):
        raise ErroLibrary("Faltam a senha ou a chave do Paperless-ngx no .env (HEIMDALL_PAPERLESS_SENHA, HEIMDALL_PAPERLESS_SECRET).")
    try:
        try:
            _estado["tokens"][usuario] = _login(usuario, senha)
        except urllib.error.HTTPError:
            if not pessoa:
                raise
            _req("POST", "/api/users/", corpo={"username": usuario, "password": senha, "is_active": True, "is_staff": False, "is_superuser": False,
                                              "user_permissions": PERMISSOES_CONVIDADO}, dono=True)
            _estado["tokens"][usuario] = _login(usuario, senha)
    except urllib.error.HTTPError:
        raise ErroLibrary("O Paperless-ngx recusou o usuário ou a senha configurados no .env.") from None
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        raise ErroLibrary("O Paperless-ngx não respondeu. Confira se ele está ligado.") from None
    return _estado["tokens"][usuario]


def _meu_id() -> int:
    """Id do usuário em atendimento no Paperless. Tudo que o Library mostra ou grava leva esse dono: o dono (superusuário) vê tudo no Paperless, então o filtro é do Library."""
    usuario = _usuario()
    if usuario not in _estado["ids"]:
        _token()   # cria o usuário do convidado na primeira vez
        r = _req("GET", "/api/users/", {"username": usuario}, dono=True)
        achado = [u for u in (r.get("results", []) if isinstance(r, dict) else []) if u.get("username") == usuario]
        if not achado:
            raise ErroLibrary("O Paperless-ngx não encontrou o usuário do Library.")
        _estado["ids"][usuario] = achado[0]["id"]
    return _estado["ids"][usuario]


def _req(metodo: str, caminho: str, params: dict = None, corpo=None, bruto: bytes = None, tipo: str = "", timeout: int = 40, _de_novo: bool = True, dono: bool = False):
    url = _url() + caminho + (("?" + urllib.parse.urlencode(params, doseq=True)) if params else "")
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
    cab = {"Authorization": "Token " + _token(dono=dono), "Accept": "application/json"}
    if dados is not None:
        cab["Content-Type"] = tipo or "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=dados, headers=cab, method=metodo), timeout=timeout) as r:
            b = r.read()
            return json.loads(b) if "json" in (r.headers.get("Content-Type") or "") else b
    except urllib.error.HTTPError as ex:
        if ex.code == 401 and _de_novo:
            _token(renovar=True, dono=dono)
            return _req(metodo, caminho, params, corpo, bruto, tipo, timeout, False, dono)
        raise ErroLibrary(f"O Paperless-ngx recusou o pedido ({ex.code}).") from None
    except (urllib.error.URLError, OSError):
        raise ErroLibrary("O Paperless-ngx não respondeu. Confira se ele está ligado.") from None


def _todos(caminho: str, params: dict = None) -> list:
    out, pag = [], 1
    while pag < 50:
        r = _req("GET", caminho, {**(params or {}), "page": pag, "page_size": 500})
        out += r.get("results", [])
        if not r.get("next"):
            break
        pag += 1
    return out


def _mapa(endpoint: str) -> dict:
    meu = _meu_id()
    return {x["id"]: x for x in _todos(f"/api/{endpoint}/") if x.get("owner") in (None, meu)}   # nunca usa etiqueta, tipo ou emissor de outra pessoa


def _id_por_nome(endpoint: str, nome: str, criar: bool = True):
    nome = (nome or "").strip()
    if not nome:
        return None
    for x in _mapa(endpoint).values():
        if x["name"].lower() == nome.lower():
            return x["id"]
    if not criar:
        return None
    return _req("POST", f"/api/{endpoint}/", corpo={"name": nome, "owner": _meu_id()})["id"]


def _doc(d: dict, tags: dict, tipos: dict, corr: dict) -> dict:
    nomes = [tags[i]["name"] for i in (d.get("tags") or []) if i in tags]
    texto = d.get("content") or ""
    return {"id": d["id"], "titulo": d.get("title") or "Documento", "nome_arquivo": d.get("original_file_name") or "", "sha256": "", "tamanho": 0, "texto": texto,
            "por_ocr": 0, "data_doc": (d.get("created_date") or d.get("created") or "")[:10], "tipo": (tipos.get(d.get("document_type")) or {}).get("name") or "Outros",
            "emissor": (corr.get(d.get("correspondent")) or {}).get("name", ""), "criado": d.get("added") or "", "revisado": 0 if TAG_REVISAR in nomes else 1,
            "lixeira": 1 if TAG_LIXEIRA in nomes else 0, "origem": "paperless", "etiquetas": sorted(n for n in nomes if n not in SISTEMA), "previa": texto[:400]}


def _tres() -> tuple:
    return _mapa("tags"), _mapa("document_types"), _mapa("correspondents")


# ---------------------------------------------------------------- consulta
def _consulta(q: str, ou: bool) -> str:
    palavras = re.findall(r"[\wÀ-ÿ]{2,}" if not ou else r"[\wÀ-ÿ]{4,}", q or "")[:10]
    return (" OR " if ou else " ").join(p + "*" for p in palavras)


def listar(q: str = "", tipo: str = "", etiqueta: str = "", so_revisar: bool = False, lixeira: bool = False, pagina: int = 1, por_pagina: int = 20, ou: bool = False) -> tuple:
    tags, tipos, corr = _tres()
    ids = {x["name"]: i for i, x in tags.items()}
    p = {"page": max(1, pagina), "page_size": por_pagina, "owner__id": _meu_id()}
    todos = []
    if lixeira:
        todos.append(ids.get(TAG_LIXEIRA, -1))
    elif TAG_LIXEIRA in ids:
        p["tags__id__none"] = ids[TAG_LIXEIRA]
    if so_revisar:
        todos.append(ids.get(TAG_REVISAR, -1))
    if etiqueta:
        todos.append(ids.get(etiqueta, -1))
    if todos:
        p["tags__id__all"] = ",".join(str(i) for i in todos)
    if tipo:
        p["document_type__id"] = next((i for i, x in tipos.items() if x["name"] == tipo), -1)
    termo = _consulta(q, ou)
    if termo:
        p["query"] = termo
    else:
        p["ordering"] = "-created"
    try:
        r = _req("GET", "/api/documents/", p)
    except ErroLibrary as ex:
        if "404" in str(ex):   # página além do fim
            return [], 0
        raise
    return [_doc(d, tags, tipos, corr) for d in r.get("results", []) if d.get("owner") == _meu_id()], r.get("count", 0)


def obter(did) -> dict:
    if not str(did).isdigit():
        return {}
    try:
        d = _req("GET", f"/api/documents/{int(did)}/")
    except ErroLibrary:
        return {}
    if d.get("owner") != _meu_id():
        return {}   # documento de outra pessoa
    return _doc(d, *_tres())


def arquivo(did) -> tuple:
    d = obter(did)
    if not d:
        return "", b""
    try:
        return d["nome_arquivo"] or f"documento-{d['id']}", _req("GET", f"/api/documents/{d['id']}/download/", {"original": "true"}, timeout=120)
    except ErroLibrary:
        return "", b""


# ---------------------------------------------------------------- escrita
def adicionar(nome: str, dados: bytes, origem: str = "envio", usar_ia: bool = True) -> dict:
    nome = Path(nome or "documento").name[:150]
    ext = Path(nome).suffix.lower()
    if ext not in base.EXT_OK:
        raise ErroLibrary(f"Formato não aceito ({ext or 'sem extensão'}). Envie PDF, foto (JPG, PNG, HEIC, TIFF, WEBP), DOCX, TXT, MD ou CSV.")
    if not dados:
        raise ErroLibrary("O arquivo está vazio.")
    if len(dados) > base.LIMITE_BYTES:
        raise ErroLibrary(f"O arquivo passa de {base.LIMITE_BYTES // (1024 * 1024)} MB.")
    rid = _id_por_nome("tags", TAG_REVISAR)
    lim = uuid.uuid4().hex
    seguro = nome.replace('"', "_").replace("\r", "_").replace("\n", "_")
    corpo = (f'--{lim}\r\nContent-Disposition: form-data; name="tags"\r\n\r\n{rid}\r\n'.encode()
             + f'--{lim}\r\nContent-Disposition: form-data; name="document"; filename="{seguro}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
             + dados + f"\r\n--{lim}--\r\n".encode())
    tarefa = _req("POST", "/api/documents/post_document/", bruto=corpo, tipo=f"multipart/form-data; boundary={lim}", timeout=120)
    tarefa = tarefa if isinstance(tarefa, str) else str(tarefa)
    titulo = Path(nome).stem
    for _ in range(40):   # até uns 60 s para o Paperless ler e classificar
        r = _req("GET", "/api/tasks/", {"task_id": tarefa})
        t = (r if isinstance(r, list) else r.get("results", [])) or [{}]
        t = t[0]
        st = (t.get("status") or "").upper()
        if st == "SUCCESS":
            did = int(t.get("related_document") or 0)
            return {"id": did, "novo": True, "titulo": (obter(did) or {}).get("titulo", titulo) if did else titulo}
        if st in ("FAILURE", "REVOKED"):
            if "duplicate" in str(t.get("result") or "").lower():
                return {"id": 0, "novo": False, "titulo": titulo}
            raise ErroLibrary("O Paperless-ngx não conseguiu ler este arquivo.")
        time.sleep(1.5)
    return {"id": 0, "novo": True, "titulo": titulo}   # ainda processando: aparece em A revisar quando terminar


def processar_entrada(usar_ia: bool = True) -> dict:
    if _pessoa():
        return base.ORIGINAIS["processar_entrada"](usar_ia)
    return {"novos": 0, "repetidos": 0, "recusados": 0}   # o Paperless acompanha a pasta do dono sozinho


def _tags_do(did: int) -> list:
    return list(_req("GET", f"/api/documents/{int(did)}/").get("tags") or []) if obter(did) else []


def atualizar(did, titulo: str, tipo: str, data_doc: str, emissor: str, etiquetas: str) -> None:
    titulo = " ".join((titulo or "").split())[:100]
    if len(titulo) < 2:
        raise ErroLibrary("O título precisa de pelo menos 2 caracteres.")
    tipo = " ".join((tipo or "").split())[:60]
    data_doc = (data_doc or "").strip()
    if data_doc and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_doc):
        raise ErroLibrary("Use a data no formato AAAA-MM-DD, por exemplo 2026-11-25.")
    atual = obter(did)
    if not atual:
        raise ErroLibrary("Documento não encontrado.")
    tags = _mapa("tags")
    sistema = [i for i, x in tags.items() if x["name"] == TAG_LIXEIRA and i in _tags_do(did)]   # salvar confirma (tira A revisar), como no acervo interno; não restaura da lixeira
    ids = []
    for n in [x for x in re.split(r"[,;]", etiquetas or "") if x.strip()][:10]:
        ids.append(_id_por_nome("tags", base.validar_etiqueta(n)))
    corpo = {"title": titulo, "tags": sorted(set(ids + sistema)), "document_type": _id_por_nome("document_types", tipo) if tipo and tipo != "Outros" else None,
             "correspondent": _id_por_nome("correspondents", " ".join((emissor or "").split())[:80])}
    if data_doc:
        corpo["created"] = data_doc
    _req("PATCH", f"/api/documents/{int(did)}/", corpo=corpo)   # a correção é o que ensina o classificador do Paperless


def _mudar_tag(did, nome: str, adicionar_: bool) -> None:
    if not obter(did):
        raise ErroLibrary("Documento não encontrado.")
    tid = _id_por_nome("tags", nome)
    atuais = set(_tags_do(did))
    atuais = atuais | {tid} if adicionar_ else atuais - {tid}
    _req("PATCH", f"/api/documents/{int(did)}/", corpo={"tags": sorted(atuais)})


def confirmar(did) -> None:
    _mudar_tag(did, TAG_REVISAR, False)


def lixeira(did, restaurar: bool = False) -> None:
    _mudar_tag(did, TAG_LIXEIRA, not restaurar)


def etiquetas_com_contagem() -> list:
    return sorted(({"nome": x["name"], "n": x.get("document_count", 0)} for x in _mapa("tags").values() if x["name"] not in SISTEMA and x.get("document_count", 0)), key=lambda e: e["nome"].lower())


def tipos_com_contagem() -> list:
    cont = {x["name"]: x.get("document_count", 0) for x in _mapa("document_types").values()}
    nomes = list(base.TIPOS) + sorted(n for n in cont if n not in base.TIPOS)
    return [(n, cont.get(n, 0)) for n in nomes]


def _contar(**p) -> int:
    return _req("GET", "/api/documents/", {"page_size": 1, "owner__id": _meu_id(), **p}).get("count", 0)


def estado() -> dict:
    ids = {x["name"]: i for i, x in _mapa("tags").items()}
    lix, rev = ids.get(TAG_LIXEIRA), ids.get(TAG_REVISAR)
    return {"documentos": _contar(**({"tags__id__none": lix} if lix else {})), "bytes": 0, "a_revisar": _contar(tags__id__all=rev) if rev else 0,
            "sem_texto": 0, "lixeira": _contar(tags__id__all=lix) if lix else 0, "tesseract": True, "entrada": str(pasta_entrada()), "motor": "Paperless-ngx"}


# ---------------------------------------------------------------- e-mail
def email_disponivel() -> bool:
    return not _pessoa()   # a senha de e-mail do .env é do dono


def email_estado() -> dict:
    contas = [x["name"] for x in _todos("/api/mail_accounts/")]
    regras = [{"nome": x["name"], "pasta": x.get("folder", ""), "ativa": bool(x.get("enabled", True))} for x in _todos("/api/mail_rules/")]
    return {"contas": contas, "regras": regras}


def email_configurar(servidor: str, usuario: str, pasta: str, remetente: str = "") -> str:
    """Cria (ou atualiza) a conta IMAP e a regra que lê só os anexos da pasta indicada. A senha vem do .env, nunca do formulário."""
    if _pessoa():
        raise ErroLibrary("A leitura de e-mail está disponível só para o dono por enquanto.")
    servidor, usuario, pasta, remetente = servidor.strip().lower(), usuario.strip(), (pasta or "Heimdall").strip(), remetente.strip()
    if not re.fullmatch(r"[a-z0-9.-]{3,100}", servidor) or "@" not in usuario or len(usuario) > 120 or not re.fullmatch(r"[\w .\-/À-ÿ]{1,60}", pasta):
        raise ErroLibrary("Confira o servidor IMAP (por exemplo imap.exemplo.com), o endereço de e-mail e o nome da pasta.")
    senha = os.environ.get("HEIMDALL_LIBRARY_EMAIL_SENHA", "")
    if not senha:
        raise ErroLibrary("Falta a senha de aplicativo do e-mail no .env. A Ajuda do Library explica como gravá-la.")
    nome_conta = f"Heimdall {usuario}"
    conta = {"name": nome_conta, "imap_server": servidor, "imap_port": 993, "imap_security": 2, "username": usuario, "password": senha, "character_set": "UTF-8", "account_type": 1}
    conta["owner"] = _meu_id()
    existente = next((x for x in _todos("/api/mail_accounts/") if x["name"] == nome_conta), None)
    cid = (_req("PATCH", f"/api/mail_accounts/{existente['id']}/", corpo=conta) if existente else _req("POST", "/api/mail_accounts/", corpo=conta))["id"]
    regra = {"name": "Heimdall: documentos por e-mail", "account": cid, "enabled": True, "folder": pasta, "filter_from": remetente or None, "maximum_age": 30, "action": 3,
             "attachment_type": 1, "consumption_scope": 1, "order": 1, "owner": _meu_id(), "assign_title_from": 2, "assign_tags": [_id_por_nome("tags", TAG_REVISAR)]}
    r = next((x for x in _todos("/api/mail_rules/") if x["name"] == regra["name"]), None)
    _req("PATCH", f"/api/mail_rules/{r['id']}/", corpo=regra) if r else _req("POST", "/api/mail_rules/", corpo=regra)
    return f"E-mail configurado: os anexos da pasta {pasta} de {usuario} serão importados e ficarão em A revisar."
