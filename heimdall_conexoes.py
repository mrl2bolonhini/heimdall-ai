#!/usr/bin/env python3
"""Heimdall Conexões: base comum das conexões de cada pessoa com serviços externos por conta (OAuth 2.0 com PKCE).

Usada pelo Library (arquivos em nuvem: heimdall_library_nuvem.py; notas, tarefas, agenda e contatos: heimdall_library_apps.py). Como tudo roda no
servidor e a pessoa só autoriza no navegador, funciona para quem usa Windows, Linux, macOS, Android ou iPhone.

O que esta base cuida (os módulos de cada grupo só dizem o que ler):
  - registro de provedores (PROVEDORES) e das credenciais do administrador no .env (HEIMDALL_NUVEM_<CHAVE>_ID e _SEGREDO);
  - armazenamento cifrado por pessoa (library/nuvem.bin, AES-GCM, permissão 600; sem o pacote cryptography a conexão é recusada);
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
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import heimdall_banco as banco
import heimdall_library_dados as base
import heimdall_pessoas as pessoas

ErroLibrary = base.ErroLibrary
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
                  "escopos_servico": {"notas": "Notes.Read", "tarefas": "Tasks.Read", "agenda": "Calendars.Read", "contatos": "Contacts.Read"},
                  "nomes_servico": {"notas": "OneNote", "tarefas": "Microsoft To Do", "agenda": "Calendário do Outlook", "contatos": "Contatos do Outlook"}},
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
    return [k for k, v in PROVEDORES.items() if (not grupo or v["grupo"] == grupo) and credenciais(k)[0]]


def url_retorno() -> str:
    return os.environ.get("HEIMDALL_LIBRARY_URL", "https://library.heimdall-ai.tech").rstrip("/") + "/nuvem/retorno"


def _aead():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise ErroLibrary("A conexão com a nuvem precisa do pacote cryptography instalado neste servidor.") from None
    segredo = os.environ.get("HEIMDALL_NUVEM_CHAVE") or os.environ.get("HEIMDALL_PAPERLESS_SECRET", "")
    if not segredo:
        raise ErroLibrary("Falta a chave de cifragem da conexão com a nuvem no .env (HEIMDALL_NUVEM_CHAVE).")
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
    except ErroLibrary:
        raise
    except Exception:  # noqa: BLE001
        raise ErroLibrary("Não consegui ler as conexões com a nuvem desta pessoa. Conecte de novo.") from None


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
        raise ErroLibrary("Endereço de provedor não permitido.")


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
                    raise ErroLibrary("Resposta grande demais.")
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
            raise ErroLibrary("O provedor não respondeu. Tente de novo em alguns minutos.") from None
    raise ErroLibrary("Redirecionamentos demais.")


def json_get(url: str, token: str, cab: dict = None) -> dict:
    """GET autenticado que devolve o JSON; erro do provedor vira ErroLibrary sem expor o corpo."""
    st, _, b = http("GET", url, {"Authorization": "Bearer " + token, "Accept": "application/json", **(cab or {})})
    if st == 429:
        raise ErroLibrary("O provedor pediu para esperar. Tentarei de novo na próxima rodada.")
    if st != 200:
        raise ErroLibrary(f"O provedor recusou a leitura (código {st}).")
    try:
        return json.loads(b or b"{}")
    except ValueError:
        raise ErroLibrary("Resposta inesperada do provedor.") from None


def _form(url: str, campos: dict) -> dict:
    st, _, b = http("POST", url, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, urllib.parse.urlencode(campos).encode())
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
        return " ".join(partes)
    return prov["escopo_escrita" if escrita else "escopo"]


def iniciar(chave: str, escrita: bool = False, servicos=None) -> str:
    """Endereço do provedor para a pessoa autorizar (com `escrita`, também a permissão de mover arquivos; `servicos` escolhe o que ler nos provedores de apps).
    Grava o state e o verificador PKCE na memória, ligados à pessoa de agora."""
    prov = PROVEDORES.get(chave)
    cid, _seg = credenciais(chave) if prov else ("", "")
    if not prov or not cid:
        raise ErroLibrary("Este provedor não está configurado pelo administrador.")
    if "escopos_servico" in prov:
        servicos = [s for s in dict.fromkeys(servicos or []) if s in prov["escopos_servico"]]
        if not servicos:
            raise ErroLibrary("Escolha pelo menos um serviço para conectar.")
    _aead()   # falha cedo se não houver como cifrar
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    agora = time.time()
    with _lock_pend:
        for k in [k for k, v in PENDENTES.items() if v["expira"] < agora]:
            del PENDENTES[k]
        if len(PENDENTES) > 500:
            raise ErroLibrary("Muitas conexões em andamento. Tente de novo em alguns minutos.")
        PENDENTES[state] = {"pessoa": pessoas.atual(), "provedor": chave, "verifier": verifier, "escrita": bool(escrita), "servicos": servicos or [], "expira": agora + 600}
    params = {"client_id": cid, "response_type": "code", "redirect_uri": url_retorno(), "state": state, "scope": escopo_de(chave, escrita, servicos),
              "code_challenge": desafio, "code_challenge_method": "S256", **prov["extra"]}
    return prov["auth"] + "?" + urllib.parse.urlencode(params)


def concluir(state: str, code: str, erro: str = "") -> tuple:
    """Fecha a autorização: (ok, mensagem). Funciona sem sessão (o retorno do provedor chega sem o cookie); quem vale é o state."""
    with _lock_pend:
        pend = PENDENTES.pop(state or "", None)
    if not pend or pend["expira"] < time.time():
        return False, "Esta autorização expirou ou já foi usada. Volte ao Library e conecte de novo."
    if erro or not code or len(code) > 2000:
        return False, "A autorização não foi concluída. Volte ao Library e tente de novo."
    chave = pend["provedor"]
    prov = PROVEDORES[chave]
    cid, seg = credenciais(chave)
    try:
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
    except ErroLibrary as ex:
        return False, str(ex)
    if prov["grupo"] == "apps":
        return True, f"{prov['nome']} conectado ({', '.join(prov['nomes_servico'][s] for s in pend['servicos'])}). A sincronização é automática."
    return True, f"{prov['nome']} conectado" + (" com permissão para mover arquivos" if escrita else " somente para leitura") + ". Informe a pasta a vigiar e toque em Sincronizar agora."


def acesso(chave: str, todos: dict) -> str:
    """Token de acesso válido da pessoa de agora; renova com o token de renovação e guarda o novo."""
    est = todos.get(chave)
    if not est or not est.get("renovacao"):
        raise ErroLibrary("Conecte o provedor antes de sincronizar.")
    if est.get("acesso") and est.get("expira", 0) > time.time() + 60:
        return est["acesso"]
    prov = PROVEDORES[chave]
    cid, seg = credenciais(chave)
    r = _form(prov["token"], {"grant_type": "refresh_token", "refresh_token": est["renovacao"], "client_id": cid, **({"client_secret": seg} if seg else {}),
                              **({"scope": escopo_de(chave, est.get("escrita", False), est.get("servicos"))} if "login.microsoftonline" in prov["token"] else {})})
    if "_erro" in r:
        if r["_erro"] in ("invalid_grant", "http 400", "http 401"):
            est.update({"acesso": "", "renovacao": "", "erro": "A autorização expirou ou foi revogada. Conecte de novo."})
            gravar(todos)
            raise ErroLibrary(est["erro"])
        raise ErroLibrary("Não consegui renovar o acesso agora. Tentarei de novo na próxima rodada.")
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
                    except (ErroLibrary, KeyError):
                        continue
                if conectados:
                    total["pessoas"] += 1
        except Exception:  # noqa: BLE001
            continue
    return total


def iniciar_sincronizador() -> None:
    """Thread de fundo do Library. HEIMDALL_NUVEM=0 desliga; sem provedor configurado, não faz nada."""
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
    threading.Thread(target=laco, daemon=True, name="library-conexoes").start()
