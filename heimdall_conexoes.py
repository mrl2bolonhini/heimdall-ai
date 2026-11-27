#!/usr/bin/env python3
"""Heimdall Conexões: base comum das conexões de cada pessoa com serviços externos por conta (OAuth 2.0 com PKCE).

Usada pelo Hub (arquivos em nuvem: heimdall_memory_nuvem.py; notas, tarefas, agenda e contatos: heimdall_memory_apps.py). Como tudo roda no
servidor e a pessoa só autoriza no navegador, funciona para quem usa Windows, Linux, macOS, Android ou iPhone.

O que esta base cuida (os módulos de cada grupo só dizem o que ler):
  - registro de provedores (PROVEDORES) e das credenciais do administrador no .env (HEIMDALL_NUVEM_<CHAVE>_ID e _SEGREDO);
  - armazenamento cifrado por pessoa (memory/nuvem.bin, AES-GCM, permissão 600; sem o pacote cryptography a conexão é recusada);
  - OAuth: autorização com state de uso único (10 minutos, ligado à pessoa) e PKCE S256, troca do código, renovação do token com rotação,
    revogação detectada (pede nova conexão);
  - HTTP seguro (só https; redirecionamentos seguidos à mão e sem o token);
  - a rodada de fundo (HEIMDALL_NUVEM_INTERVALO, padrão 900 s; HEIMDALL_NUVEM=0 desliga) que chama o sincronizador registrado de cada grupo para cada
    pessoa conectada, sem que o erro de uma interrompa as outras.
Um provedor novo entra em PROVEDORES com "grupo" (que escolhe o sincronizador), endereços, escopos e, se for o caso, "escopos_servico" (um escopo por serviço).
Usa a biblioteca padrão e `cryptography`.
"""
import base64
import contextlib
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import heimdall_banco as banco
import heimdall_memory_dados as base
import heimdall_pessoas as pessoas

ErroMemory = base.ErroMemory
LOCK = threading.RLock()
_lock_pend = threading.Lock()   # só para o state do OAuth: nunca espera uma sincronização longa
PENDENTES = {}                  # state -> {pessoa, provedor, verifier, escrita, servicos, expira}
PERMITE_HTTP = False            # só os testes ligam (servidor falso em 127.0.0.1)
SINCRONIZADORES = {}            # grupo -> função(chave) que sincroniza a pessoa de agora

PROVEDORES = {
    "dropbox": {"grupo": "arquivos", "nome": "Dropbox", "auth": "https://www.dropbox.com/oauth2/authorize", "token": "https://api.dropboxapi.com/oauth2/token",
                "escopo": "files.metadata.read files.content.read", "escopo_escrita": "files.metadata.read files.content.read files.content.write",
                "extra": {"token_access_type": "offline"}, "api": "https://api.dropboxapi.com", "conteudo": "https://content.dropboxapi.com",
                "dica": "Caminho da pasta no Dropbox, por exemplo /Documentos (deixe em branco para a raiz)."},
    "onedrive": {"grupo": "arquivos", "nome": "OneDrive", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                 "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token", "escopo": "Files.Read offline_access", "escopo_escrita": "Files.ReadWrite offline_access",
                 "extra": {"response_mode": "query"}, "api": "https://graph.microsoft.com/v1.0", "conteudo": "",
                 "dica": "Caminho da pasta no OneDrive, por exemplo Documentos/Scans (deixe em branco para a raiz)."},
    "microsoft": {"grupo": "apps", "nome": "Microsoft", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                  "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token", "escopo": "offline_access", "extra": {"response_mode": "query"},
                  "api": "https://graph.microsoft.com/v1.0", "credencial": "ONEDRIVE",   # o mesmo aplicativo registrado para o OneDrive
                  "escopos_servico": {"notas": "Notes.Read", "tarefas": "Tasks.Read", "planner": "Tasks.Read", "agenda": "Calendars.Read", "contatos": "Contacts.Read"},
                  "nomes_servico": {"notas": "OneNote", "tarefas": "Microsoft To Do", "planner": "Microsoft Planner (só conta de trabalho ou escola)", "agenda": "Calendário do Outlook",
                                    "contatos": "Contatos do Outlook"}},
    # Todoist: OAuth 2.0 sem PKCE, escopos separados por vírgula, token sem expiração e sem renovação (a pessoa revoga em Todoist > Configurações > Integrações)
    "todoist": {"grupo": "apps", "nome": "Todoist", "auth": "https://app.todoist.com/oauth/authorize", "token": "https://todoist.com/oauth/access_token", "escopo": "",
                "extra": {}, "api": "https://api.todoist.com/api/v1", "sep": ",", "simples": True, "sem_renovacao": True,
                "escopos_servico": {"tarefas": "data:read"}, "nomes_servico": {"tarefas": "Tarefas do Todoist"}},
    # iCloud: não há OAuth; a agenda e os contatos são lidos por CalDAV e CardDAV com o Apple ID e uma senha de aplicativo (gerada pela pessoa em account.apple.com, exige verificação em duas etapas)
    "icloud": {"grupo": "apps", "nome": "iCloud", "fluxo": "senha", "sem_credencial": True, "sem_renovacao": True, "auth": "", "token": "", "escopo": "", "extra": {}, "api": "",
               "bases": {"agenda": "https://caldav.icloud.com/", "contatos": "https://contacts.icloud.com/"},
               "escopos_servico": {"agenda": "", "contatos": ""}, "nomes_servico": {"agenda": "Calendário do iCloud", "contatos": "Contatos do iCloud"}},
    # Google: OAuth 2.0 com PKCE e acesso offline; escopos de leitura de Agenda, Tarefas e Contatos (a Agenda e os Contatos são escopos sensíveis: exigem verificação do Google antes de abrir para outras pessoas)
    "google": {"grupo": "apps", "nome": "Google", "auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token", "escopo": "",
               "extra": {"access_type": "offline", "prompt": "consent"}, "api": "https://www.googleapis.com",
               "bases": {"agenda": "https://www.googleapis.com/calendar/v3", "tarefas": "https://tasks.googleapis.com/tasks/v1", "contatos": "https://people.googleapis.com/v1"},
               "escopos_servico": {"agenda": "https://www.googleapis.com/auth/calendar.readonly", "tarefas": "https://www.googleapis.com/auth/tasks.readonly",
                                   "contatos": "https://www.googleapis.com/auth/contacts.readonly"},
               "nomes_servico": {"agenda": "Google Agenda (calendário principal)", "tarefas": "Google Tarefas", "contatos": "Google Contatos"}},
    # Notion: integração pública (OAuth 2.0 sem PKCE, sem escopos: a pessoa escolhe as páginas no seletor do Notion); troca de token com autenticação básica e corpo JSON
    "notion": {"grupo": "apps", "nome": "Notion", "auth": "https://api.notion.com/v1/oauth/authorize", "token": "https://api.notion.com/v1/oauth/token", "escopo": "",
               "extra": {"owner": "user"}, "api": "https://api.notion.com/v1", "sem_pkce": True, "basico": True, "sem_escopo": True, "sem_renovacao": True,
               "cab_api": {"Notion-Version": "2022-06-28"}, "escopos_servico": {"paginas": ""}, "nomes_servico": {"paginas": "Páginas do Notion que você compartilhar"}},
    # Trello: fluxo próprio (o token volta no fragmento do endereço; a página de retorno o entrega por POST), a chave de API do administrador vale como ID
    "trello": {"grupo": "apps", "nome": "Trello", "auth": "https://trello.com/1/authorize", "token": "", "escopo": "", "extra": {}, "api": "https://api.trello.com/1",
               "fluxo": "trello", "sem_renovacao": True, "escopos_servico": {"quadros": "read"}, "nomes_servico": {"quadros": "Cartões do Trello"}},
}


# ---------------------------------------------------------------- configuração e armazenamento cifrado
def credenciais(chave: str) -> tuple:
    p = f"HEIMDALL_NUVEM_{PROVEDORES[chave].get('credencial', chave).upper()}_"
    id_, seg = os.environ.get(p + "ID", "").strip(), os.environ.get(p + "SEGREDO", "").strip()
    if not id_:   # administrador pode registrar um aplicativo só para este provedor
        p = f"HEIMDALL_NUVEM_{chave.upper()}_"
        id_, seg = os.environ.get(p + "ID", "").strip() or id_, os.environ.get(p + "SEGREDO", "").strip() or seg
    return id_, seg


def configurados(grupo: str = "") -> list:
    return [k for k, v in PROVEDORES.items() if (not grupo or v["grupo"] == grupo) and (credenciais(k)[0] or v.get("sem_credencial"))]


def url_retorno() -> str:
    return (os.environ.get("HEIMDALL_MEMORY_URL") or os.environ.get("HEIMDALL_LIBRARY_URL") or "https://memory.heimdall-ai.tech").rstrip("/") + "/nuvem/retorno"


def _aead():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise ErroMemory("A conexão com a nuvem precisa do pacote cryptography instalado neste servidor.") from None
    segredo = os.environ.get("HEIMDALL_NUVEM_CHAVE") or os.environ.get("HEIMDALL_PAPERLESS_SECRET", "")
    if not segredo:
        raise ErroMemory("Falta a chave de cifragem da conexão com a nuvem no .env (HEIMDALL_NUVEM_CHAVE).")
    return AESGCM(hashlib.sha256(b"heimdall-nuvem-v1\0" + segredo.encode()).digest())


def arquivo():
    return base.pasta_base() / "nuvem.bin"


def carregar() -> dict:
    f = arquivo()
    if not f.is_file():
        return {}
    try:
        b = f.read_bytes()
        return json.loads(_aead().decrypt(b[:12], b[12:], b"nuvem"))
    except ErroMemory:
        raise
    except Exception:  # noqa: BLE001
        raise ErroMemory("Não consegui ler as conexões com a nuvem desta pessoa. Conecte de novo.") from None


def gravar(dados: dict) -> None:
    f = arquivo()
    f.parent.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_bytes(12)
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(nonce + _aead().encrypt(nonce, json.dumps(dados).encode(), b"nuvem"))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


@contextlib.contextmanager
def como(pessoa: str):
    """Roda como a pessoa indicada: dados (heimdall_banco) e identidade (heimdall_pessoas) mudam juntos."""
    with pessoas.definir(pessoa), (contextlib.nullcontext() if pessoas.e_dono(pessoa) else banco.da_pessoa(pessoa)):
        yield


# ---------------------------------------------------------------- HTTP
class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _checa_url(url: str) -> None:
    if not (url.startswith("https://") or (PERMITE_HTTP and url.startswith("http://127.0.0.1"))):
        raise ErroMemory("Endereço de provedor não permitido.")


def http(metodo: str, url: str, cab: dict = None, corpo: bytes = None, limite: int = 2 * 1024 * 1024, seguir: bool = True, timeout: int = 40) -> tuple:
    """(status, cabeçalhos, bytes). Redirecionamentos de download são seguidos à mão e sem o token (o endereço pré-autorizado não precisa dele)."""
    _checa_url(url)
    cab = dict(cab or {})
    for _ in range(4):
        req = urllib.request.Request(url, data=corpo, headers=cab, method=metodo)
        try:
            with urllib.request.build_opener(_SemRedirecionar).open(req, timeout=timeout) as r:
                dados = r.read(limite + 1)
                if len(dados) > limite:
                    raise ErroMemory("Resposta grande demais.")
                return r.status, r.headers, dados
        except urllib.error.HTTPError as ex:
            if ex.code in (301, 302, 303, 307, 308) and seguir and ex.headers.get("Location"):
                url = urllib.parse.urljoin(url, ex.headers["Location"])
                _checa_url(url)
                cab.pop("Authorization", None)
                if ex.code == 303:
                    metodo, corpo = "GET", None
                continue
            return ex.code, ex.headers, ex.read(4096)
        except (urllib.error.URLError, OSError):
            raise ErroMemory("O provedor não respondeu. Tente de novo em alguns minutos.") from None
    raise ErroMemory("Redirecionamentos demais.")


def json_get(url: str, token: str, cab: dict = None) -> dict:
    """GET autenticado que devolve o JSON; erro do provedor vira ErroMemory sem expor o corpo."""
    st, _, b = http("GET", url, {"Authorization": "Bearer " + token, "Accept": "application/json", **(cab or {})})
    if st == 429:
        raise ErroMemory("O provedor pediu para esperar. Tentarei de novo na próxima rodada.")
    if st != 200:
        raise ErroMemory(f"O provedor recusou a leitura (código {st}).")
    try:
        return json.loads(b or b"{}")
    except ValueError:
        raise ErroMemory("Resposta inesperada do provedor.") from None


def _form(url: str, campos: dict, basico: tuple = None, cab_extra: dict = None) -> dict:
    """POST do token. Com `basico` (id, segredo) usa autenticação básica e corpo JSON, como o Notion; senão, formulário."""
    if basico:
        cred = base64.b64encode(f"{basico[0]}:{basico[1]}".encode()).decode()
        st, _, b = http("POST", url, {"Content-Type": "application/json", "Accept": "application/json", "Authorization": "Basic " + cred, **(cab_extra or {})}, json.dumps(campos).encode())
    else:
        st, _, b = http("POST", url, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", **(cab_extra or {})}, urllib.parse.urlencode(campos).encode())
    try:
        r = json.loads(b or b"{}")
    except ValueError:
        r = {}
    if st != 200 or "access_token" not in r:
        r["_erro"] = r.get("error") or f"http {st}"
    return r


# ---------------------------------------------------------------- OAuth
def escopo_de(chave: str, escrita: bool = False, servicos=None) -> str:
    prov = PROVEDORES[chave]
    if "escopos_servico" in prov:
        partes = [prov["escopo"]] + [prov["escopos_servico"][s] for s in (servicos or []) if s in prov["escopos_servico"]]
        return prov.get("sep", " ").join(dict.fromkeys(x for x in partes if x))   # sem repetir (To Do e Planner usam o mesmo escopo)
    return prov["escopo_escrita" if escrita else "escopo"]


def iniciar(chave: str, escrita: bool = False, servicos=None) -> str:
    """Endereço do provedor para a pessoa autorizar (com `escrita`, também a permissão de mover arquivos; `servicos` escolhe o que ler nos provedores de apps).
    Grava o state e o verificador PKCE na memória, ligados à pessoa de agora."""
    prov = PROVEDORES.get(chave)
    if prov and prov.get("fluxo") == "senha":
        raise ErroMemory("Este provedor se conecta com o Apple ID e uma senha de aplicativo, não por autorização no site.")
    cid, _seg = credenciais(chave) if prov else ("", "")
    if not prov or not cid:
        raise ErroMemory("Este provedor não está configurado pelo administrador.")
    if "escopos_servico" in prov:
        servicos = [s for s in dict.fromkeys(servicos or []) if s in prov["escopos_servico"]]
        if not servicos:
            raise ErroMemory("Escolha pelo menos um serviço para conectar.")
    _aead()   # falha cedo se não houver como cifrar
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    agora = time.time()
    with _lock_pend:
        for k in [k for k, v in PENDENTES.items() if v["expira"] < agora]:
            del PENDENTES[k]
        if len(PENDENTES) > 500:
            raise ErroMemory("Muitas conexões em andamento. Tente de novo em alguns minutos.")
        PENDENTES[state] = {"pessoa": pessoas.atual(), "provedor": chave, "verifier": verifier, "escrita": bool(escrita), "servicos": servicos or [], "expira": agora + 600}
    if prov.get("fluxo") == "trello":   # o Trello não usa state nem código: o state vai no endereço de retorno e o token volta no fragmento
        params = {"key": cid, "name": "Studio Hub", "scope": escopo_de(chave, escrita, servicos), "expiration": "never", "response_type": "token",
                  "callback_method": "fragment", "return_url": url_retorno() + "?" + urllib.parse.urlencode({"state": state})}
        return prov["auth"] + "?" + urllib.parse.urlencode(params)
    if prov.get("simples"):
        params = {"client_id": cid, "state": state, "scope": escopo_de(chave, escrita, servicos), **prov["extra"]}
        return prov["auth"] + "?" + urllib.parse.urlencode(params, safe=":,")
    params = {"client_id": cid, "response_type": "code", "redirect_uri": url_retorno(), "state": state, **prov["extra"]}
    if not prov.get("sem_escopo"):
        params["scope"] = escopo_de(chave, escrita, servicos)
    if not prov.get("sem_pkce"):
        params.update({"code_challenge": desafio, "code_challenge_method": "S256"})
    return prov["auth"] + "?" + urllib.parse.urlencode(params)


def concluir(state: str, code: str, erro: str = "") -> tuple:
    """Fecha a autorização: (ok, mensagem). Funciona sem sessão (o retorno do provedor chega sem o cookie); quem vale é o state."""
    with _lock_pend:
        pend = PENDENTES.pop(state or "", None)
    if not pend or pend["expira"] < time.time():
        return False, "Esta autorização expirou ou já foi usada. Volte ao Hub e conecte de novo."
    if erro or not code or len(code) > 2000:
        return False, "A autorização não foi concluída. Volte ao Hub e tente de novo."
    chave = pend["provedor"]
    prov = PROVEDORES[chave]
    cid, seg = credenciais(chave)
    try:
        if prov.get("simples"):
            r = _form(prov["token"], {"client_id": cid, "client_secret": seg, "code": code})
            if "_erro" not in r and prov.get("sem_renovacao"):
                r.setdefault("refresh_token", "sem-renovacao")   # token sem expiração: o marcador só diz que há conexão
                r.setdefault("expires_in", 10 * 365 * 86400)
        elif prov.get("basico"):
            r = _form(prov["token"], {"grant_type": "authorization_code", "code": code, "redirect_uri": url_retorno()}, (cid, seg), prov.get("cab_api"))
            if "_erro" not in r and prov.get("sem_renovacao"):
                r.setdefault("refresh_token", "sem-renovacao")   # integração sem expiração: o marcador só diz que há conexão
                r.setdefault("expires_in", 10 * 365 * 86400)
        else:
            r = _form(prov["token"], {"grant_type": "authorization_code", "code": code, "redirect_uri": url_retorno(), "client_id": cid,
                                      **({"client_secret": seg} if seg else {}), "code_verifier": pend["verifier"]})
        if "_erro" in r or not r.get("refresh_token"):
            return False, "O provedor não concluiu a autorização. Confira os dados do aplicativo com o administrador."
        # a escrita só vale se o provedor confirmou o escopo (quando ele informa os escopos concedidos)
        escrita = bool(pend.get("escrita")) and (not r.get("scope") or "content.write" in r["scope"] or "ReadWrite" in r["scope"])
        with como(pend["pessoa"]), LOCK:
            todos = carregar()
            novo = {**todos.get(chave, {}), "acesso": r["access_token"], "renovacao": r["refresh_token"], "expira": time.time() + int(r.get("expires_in", 3600)),
                    "escrita": escrita, "erro": ""}
            novo["mover"] = bool(novo.get("mover")) and escrita
            if pend.get("servicos"):
                novo["servicos"] = pend["servicos"]
            todos[chave] = novo
            gravar(todos)
    except ErroMemory as ex:
        return False, str(ex)
    if prov["grupo"] == "apps":
        return True, f"{prov['nome']} conectado ({', '.join(prov['nomes_servico'][s] for s in pend['servicos'])}). A sincronização é automática."
    return True, f"{prov['nome']} conectado" + (" com permissão para mover arquivos" if escrita else " somente para leitura") + ". Informe a pasta a vigiar e toque em Sincronizar agora."


def provedor_do_state(state: str) -> str:
    """Provedor de uma autorização em andamento (sem consumir o state); vazio se não existir ou tiver expirado."""
    with _lock_pend:
        pend = PENDENTES.get(state or "")
    return pend["provedor"] if pend and pend["expira"] >= time.time() else ""


def concluir_token(state: str, token: str) -> tuple:
    """Fecha a autorização dos provedores em que o token volta direto (Trello): (ok, mensagem). O state de uso único é a credencial; o token é conferido no provedor antes de ser guardado."""
    with _lock_pend:
        pend = PENDENTES.pop(state or "", None)
    if not pend or pend["expira"] < time.time() or PROVEDORES.get(pend["provedor"], {}).get("fluxo") != "trello":
        return False, "Esta autorização expirou ou já foi usada. Volte ao Hub e conecte de novo."
    token = (token or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16,200}", token):
        return False, "A autorização não foi concluída. Volte ao Hub e tente de novo."
    chave = pend["provedor"]
    prov = PROVEDORES[chave]
    try:
        st, _, _b = http("GET", prov["api"] + "/members/me?fields=id", {"Authorization": cab_trello(token), "Accept": "application/json"})
        if st != 200:
            return False, "O Trello não confirmou a autorização. Volte ao Hub e tente de novo."
        with como(pend["pessoa"]), LOCK:
            todos = carregar()
            todos[chave] = {**todos.get(chave, {}), "acesso": token, "renovacao": "sem-renovacao", "expira": time.time() + 10 * 365 * 86400, "escrita": False,
                            "servicos": pend["servicos"], "erro": ""}
            gravar(todos)
    except ErroMemory as ex:
        return False, str(ex)
    return True, f"{prov['nome']} conectado ({', '.join(prov['nomes_servico'][s] for s in pend['servicos'])}). A sincronização é automática."


def cab_trello(token: str) -> str:
    """Cabeçalho de autenticação do Trello (a chave de API do administrador e o token da pessoa, sem pôr o token no endereço)."""
    return f'OAuth oauth_consumer_key="{credenciais("trello")[0]}", oauth_token="{token}"'


def acesso(chave: str, todos: dict) -> str:
    """Token de acesso válido da pessoa de agora; renova com o token de renovação e guarda o novo."""
    est = todos.get(chave)
    if not est or not est.get("renovacao"):
        raise ErroMemory("Conecte o provedor antes de sincronizar.")
    if est.get("acesso") and est.get("expira", 0) > time.time() + 60:
        return est["acesso"]
    prov = PROVEDORES[chave]
    cid, seg = credenciais(chave)
    if prov.get("basico"):
        r = _form(prov["token"], {"grant_type": "refresh_token", "refresh_token": est["renovacao"]}, (cid, seg), prov.get("cab_api"))
    else:
        r = _form(prov["token"], {"grant_type": "refresh_token", "refresh_token": est["renovacao"], "client_id": cid, **({"client_secret": seg} if seg else {}),
                                  **({"scope": escopo_de(chave, est.get("escrita", False), est.get("servicos"))} if "login.microsoftonline" in prov["token"] else {})})
    if "_erro" in r:
        if r["_erro"] in ("invalid_grant", "http 400", "http 401"):
            est.update({"acesso": "", "renovacao": "", "erro": "A autorização expirou ou foi revogada. Conecte de novo."})
            gravar(todos)
            raise ErroMemory(est["erro"])
        raise ErroMemory("Não consegui renovar o acesso agora. Tentarei de novo na próxima rodada.")
    est["acesso"], est["expira"] = r["access_token"], time.time() + int(r.get("expires_in", 3600))
    if r.get("refresh_token"):
        est["renovacao"] = r["refresh_token"]   # o provedor pode trocar o token de renovação a cada uso
    est["erro"] = ""
    gravar(todos)
    return est["acesso"]


def desconectar(chave: str) -> None:
    with LOCK:
        todos = carregar()
        todos.pop(chave, None)
        gravar(todos)


# ---------------------------------------------------------------- rodada de fundo
def registrar(grupo: str, sincronizador) -> None:
    SINCRONIZADORES[grupo] = sincronizador


def _pessoas_com_conexao() -> list:
    saida = [pessoas.DONO]
    if pessoas.ativo():
        d = banco.pasta_pessoas()
        if d.is_dir():
            saida += sorted(x.name for x in d.iterdir() if x.is_dir() and not x.is_symlink() and pessoas.ID_RE.match(x.name))
    return saida


def sincronizar_todos() -> dict:
    """Uma rodada para todas as pessoas que têm conexão. Um erro de uma pessoa ou de um provedor nunca interrompe os outros."""
    total = {"pessoas": 0, "novos": 0}
    for p in _pessoas_com_conexao():
        try:
            with como(p):
                if not arquivo().is_file():
                    continue
                conectados = [k for k, v in carregar().items() if k in PROVEDORES and v.get("renovacao") and k in configurados()]
                for k in conectados:
                    try:
                        total["novos"] += SINCRONIZADORES[PROVEDORES[k]["grupo"]](k).get("novos", 0)
                    except (ErroMemory, KeyError):
                        continue
                if conectados:
                    total["pessoas"] += 1
        except Exception:  # noqa: BLE001
            continue
    return total


def iniciar_sincronizador() -> None:
    """Thread de fundo do Hub. HEIMDALL_NUVEM=0 desliga; sem provedor configurado, não faz nada."""
    if os.environ.get("HEIMDALL_NUVEM", "1") == "0" or not configurados():
        return
    intervalo = max(60, int(os.environ.get("HEIMDALL_NUVEM_INTERVALO", "900") or 900))

    def laco():
        time.sleep(30)
        while True:
            try:
                sincronizar_todos()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(intervalo)
    threading.Thread(target=laco, daemon=True, name="memory-conexoes").start()
