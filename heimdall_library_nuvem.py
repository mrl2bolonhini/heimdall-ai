#!/usr/bin/env python3
"""Heimdall Library: conexão de cada pessoa com o próprio armazenamento em nuvem (Dropbox e OneDrive), com importação automática.

Fluxo: a pessoa toca em Conectar, autoriza no site do provedor (OAuth 2.0, código de autorização com PKCE) e informa a pasta a vigiar. A cada
HEIMDALL_NUVEM_INTERVALO segundos (padrão 900) o Library lista a pasta, baixa só os arquivos novos ou alterados e os envia ao acervo da pessoa
(heimdall_library_dados.adicionar: motor interno ou Paperless). Só leitura: nada é alterado, movido nem apagado na nuvem.

Privacidade: cada pessoa tem o seu arquivo de conexão (library/nuvem.bin, cifrado com AES-GCM, permissão 600) e só a sincronização dela mexe nele.
O estado (`state`) do OAuth fica na memória do servidor, ligado à pessoa que iniciou, vale por 10 minutos e só uma vez.
Configuração do administrador (.env): HEIMDALL_NUVEM_<DROPBOX|ONEDRIVE>_ID e _SEGREDO; HEIMDALL_LIBRARY_URL (padrão https://library.heimdall-ai.tech)
para o endereço de retorno <URL>/nuvem/retorno, que precisa estar cadastrado no aplicativo do provedor. HEIMDALL_NUVEM=0 desliga a sincronização.
Usa a biblioteca padrão e `cryptography` (AESGCM, já usada nas cópias de segurança); sem ela, a conexão é recusada em vez de gravar token em texto aberto.
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
import heimdall_library_dados as base
import heimdall_pessoas as pessoas

ErroLibrary = base.ErroLibrary
_lock = threading.RLock()
_lock_pend = threading.Lock()   # só para o state do OAuth: nunca espera uma sincronização longa
_PENDENTES = {}          # state -> {pessoa, provedor, verifier, expira}
_PERMITE_HTTP = False    # só os testes ligam (servidor falso em 127.0.0.1)
MAX_POR_RODADA = 50

PROVEDORES = {
    "dropbox": {"nome": "Dropbox", "auth": "https://www.dropbox.com/oauth2/authorize", "token": "https://api.dropboxapi.com/oauth2/token",
                "escopo": "files.metadata.read files.content.read", "extra": {"token_access_type": "offline"},
                "api": "https://api.dropboxapi.com", "conteudo": "https://content.dropboxapi.com",
                "dica": "Caminho da pasta no Dropbox, por exemplo /Documentos (deixe em branco para a raiz)."},
    "onedrive": {"nome": "OneDrive", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                 "escopo": "Files.Read offline_access", "extra": {"response_mode": "query"}, "api": "https://graph.microsoft.com/v1.0", "conteudo": "",
                 "dica": "Caminho da pasta no OneDrive, por exemplo Documentos/Scans (deixe em branco para a raiz)."},
}


# ---------------------------------------------------------------- configuração e armazenamento cifrado
def _credenciais(chave: str) -> tuple:
    p = f"HEIMDALL_NUVEM_{chave.upper()}_"
    return os.environ.get(p + "ID", "").strip(), os.environ.get(p + "SEGREDO", "").strip()


def configurados() -> list:
    return [k for k in PROVEDORES if _credenciais(k)[0]]


def _url_retorno() -> str:
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


def _arquivo():
    return base.pasta_base() / "nuvem.bin"


def _carregar() -> dict:
    f = _arquivo()
    if not f.is_file():
        return {}
    try:
        b = f.read_bytes()
        return json.loads(_aead().decrypt(b[:12], b[12:], b"nuvem"))
    except ErroLibrary:
        raise
    except Exception:  # noqa: BLE001
        raise ErroLibrary("Não consegui ler as conexões com a nuvem desta pessoa. Conecte de novo.") from None


def _gravar(dados: dict) -> None:
    f = _arquivo()
    f.parent.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_bytes(12)
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(nonce + _aead().encrypt(nonce, json.dumps(dados).encode(), b"nuvem"))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


@contextlib.contextmanager
def _como(pessoa: str):
    """Roda como a pessoa indicada: dados (heimdall_banco) e identidade (heimdall_pessoas) mudam juntos."""
    with pessoas.definir(pessoa), (contextlib.nullcontext() if pessoas.e_dono(pessoa) else banco.da_pessoa(pessoa)):
        yield


# ---------------------------------------------------------------- HTTP
class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _checa_url(url: str) -> None:
    if not (url.startswith("https://") or (_PERMITE_HTTP and url.startswith("http://127.0.0.1"))):
        raise ErroLibrary("Endereço de provedor não permitido.")


def _http(metodo: str, url: str, cab: dict = None, corpo: bytes = None, limite: int = 2 * 1024 * 1024, seguir: bool = True, timeout: int = 40) -> tuple:
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


def _form(url: str, campos: dict) -> dict:
    st, _, b = _http("POST", url, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, urllib.parse.urlencode(campos).encode())
    try:
        r = json.loads(b or b"{}")
    except ValueError:
        r = {}
    if st != 200 or "access_token" not in r:
        r["_erro"] = r.get("error") or f"http {st}"
    return r


# ---------------------------------------------------------------- OAuth
def iniciar(chave: str) -> str:
    """Endereço do provedor para a pessoa autorizar. Grava o state e o verificador PKCE na memória, ligados à pessoa de agora."""
    prov = PROVEDORES.get(chave)
    cid, _seg = _credenciais(chave) if prov else ("", "")
    if not prov or not cid:
        raise ErroLibrary("Este provedor não está configurado pelo administrador.")
    _aead()   # falha cedo se não houver como cifrar
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    agora = time.time()
    with _lock_pend:
        for k in [k for k, v in _PENDENTES.items() if v["expira"] < agora]:
            del _PENDENTES[k]
        if len(_PENDENTES) > 500:
            raise ErroLibrary("Muitas conexões em andamento. Tente de novo em alguns minutos.")
        _PENDENTES[state] = {"pessoa": pessoas.atual(), "provedor": chave, "verifier": verifier, "expira": agora + 600}
    params = {"client_id": cid, "response_type": "code", "redirect_uri": _url_retorno(), "state": state, "scope": prov["escopo"],
              "code_challenge": desafio, "code_challenge_method": "S256", **prov["extra"]}
    return prov["auth"] + "?" + urllib.parse.urlencode(params)


def concluir(state: str, code: str, erro: str = "") -> tuple:
    """Fecha a autorização: (ok, mensagem). Funciona sem sessão (o retorno do provedor chega sem o cookie); quem vale é o state."""
    with _lock_pend:
        pend = _PENDENTES.pop(state or "", None)
    if not pend or pend["expira"] < time.time():
        return False, "Esta autorização expirou ou já foi usada. Volte ao Library e conecte de novo."
    if erro or not code or len(code) > 2000:
        return False, "A autorização não foi concluída. Volte ao Library e tente de novo."
    chave = pend["provedor"]
    prov = PROVEDORES[chave]
    cid, seg = _credenciais(chave)
    try:
        r = _form(prov["token"], {"grant_type": "authorization_code", "code": code, "redirect_uri": _url_retorno(), "client_id": cid,
                                  **({"client_secret": seg} if seg else {}), "code_verifier": pend["verifier"]})
        if "_erro" in r or not r.get("refresh_token"):
            return False, "O provedor não concluiu a autorização. Confira os dados do aplicativo com o administrador."
        with _como(pend["pessoa"]), _lock:
            todos = _carregar()
            antigo = todos.get(chave, {})
            todos[chave] = {"acesso": r["access_token"], "renovacao": r["refresh_token"], "expira": time.time() + int(r.get("expires_in", 3600)),
                            "pasta": antigo.get("pasta", ""), "vistos": antigo.get("vistos", {}), "ultimo": antigo.get("ultimo", ""), "resumo": antigo.get("resumo", ""), "erro": ""}
            _gravar(todos)
    except ErroLibrary as ex:
        return False, str(ex)
    return True, f"{prov['nome']} conectado. Informe a pasta a vigiar e toque em Sincronizar agora."


def _acesso(chave: str, todos: dict) -> str:
    """Token de acesso válido da pessoa de agora; renova com o token de renovação e guarda o novo."""
    est = todos.get(chave)
    if not est or not est.get("renovacao"):
        raise ErroLibrary("Conecte o provedor antes de sincronizar.")
    if est.get("acesso") and est.get("expira", 0) > time.time() + 60:
        return est["acesso"]
    prov = PROVEDORES[chave]
    cid, seg = _credenciais(chave)
    r = _form(prov["token"], {"grant_type": "refresh_token", "refresh_token": est["renovacao"], "client_id": cid, **({"client_secret": seg} if seg else {}),
                              **({"scope": prov["escopo"]} if chave == "onedrive" else {})})
    if "_erro" in r:
        if r["_erro"] in ("invalid_grant", "http 400", "http 401"):
            est.update({"acesso": "", "renovacao": "", "erro": "A autorização expirou ou foi revogada. Conecte de novo."})
            _gravar(todos)
            raise ErroLibrary(est["erro"])
        raise ErroLibrary("Não consegui renovar o acesso agora. Tentarei de novo na próxima rodada.")
    est["acesso"], est["expira"] = r["access_token"], time.time() + int(r.get("expires_in", 3600))
    if r.get("refresh_token"):
        est["renovacao"] = r["refresh_token"]   # o provedor pode trocar o token de renovação a cada uso
    est["erro"] = ""
    _gravar(todos)
    return est["acesso"]


# ---------------------------------------------------------------- listagem e download por provedor
def _listar(chave: str, token: str, pasta: str):
    """Itens {id, nome, tamanho, marca} da pasta (sem subpastas), em páginas."""
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token}
    if chave == "dropbox":
        caminho = "" if pasta.strip("/") == "" else "/" + pasta.strip("/")
        url, corpo = prov["api"] + "/2/files/list_folder", {"path": caminho, "recursive": False, "limit": 200}
        for _ in range(50):
            st, _, b = _http("POST", url, {**aut, "Content-Type": "application/json"}, json.dumps(corpo).encode())
            if st != 200:
                raise ErroLibrary("Não consegui abrir a pasta no Dropbox. Confira o caminho informado.")
            r = json.loads(b)
            for x in r.get("entries", []):
                if x.get(".tag") == "file":
                    yield {"id": x["id"], "nome": x["name"], "tamanho": x.get("size", 0), "marca": x.get("content_hash") or x.get("server_modified", "")}
            if not r.get("has_more"):
                return
            url, corpo = prov["api"] + "/2/files/list_folder/continue", {"cursor": r["cursor"]}
    else:
        p = pasta.strip("/")
        url = prov["api"] + ("/me/drive/root:/" + urllib.parse.quote(p) + ":/children" if p else "/me/drive/root/children") + "?$top=200"
        for _ in range(50):
            st, _, b = _http("GET", url, aut)
            if st != 200:
                raise ErroLibrary("Não consegui abrir a pasta no OneDrive. Confira o caminho informado.")
            r = json.loads(b)
            for x in r.get("value", []):
                if "file" in x:
                    yield {"id": x["id"], "nome": x["name"], "tamanho": x.get("size", 0), "marca": x.get("eTag") or x.get("lastModifiedDateTime", "")}
            url = r.get("@odata.nextLink")
            if not url:
                return


def _baixar(chave: str, token: str, item: dict) -> bytes:
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token}
    if chave == "dropbox":
        st, _, b = _http("POST", prov["conteudo"] + "/2/files/download", {**aut, "Dropbox-API-Arg": json.dumps({"path": item["id"]})}, b"", limite=base.LIMITE_BYTES, timeout=120)
    else:
        st, _, b = _http("GET", prov["api"] + "/me/drive/items/" + urllib.parse.quote(item["id"]) + "/content", aut, limite=base.LIMITE_BYTES, timeout=120)
    if st != 200:
        raise ErroLibrary("Não consegui baixar o arquivo.")
    return b


# ---------------------------------------------------------------- tela e sincronização
def situacao() -> list:
    todos = _carregar() if configurados() else {}
    saida = []
    for k in configurados():
        e = todos.get(k, {})
        saida.append({"chave": k, "nome": PROVEDORES[k]["nome"], "conectado": bool(e.get("renovacao")), "pasta": e.get("pasta", ""), "ultimo": e.get("ultimo", ""),
                      "resumo": e.get("resumo", ""), "erro": e.get("erro", ""), "dica": PROVEDORES[k]["dica"]})
    return saida


def definir_pasta(chave: str, pasta: str) -> None:
    pasta = " ".join((pasta or "").split())[:200]
    if re.search(r"[\x00-\x1f]|\.\./|^\.\.$", pasta):
        raise ErroLibrary("Caminho de pasta inválido.")
    with _lock:
        todos = _carregar()
        if not todos.get(chave, {}).get("renovacao"):
            raise ErroLibrary("Conecte o provedor antes de escolher a pasta.")
        if todos[chave].get("pasta") != pasta:
            todos[chave]["vistos"] = {}   # outra pasta: recomeça a lista de arquivos já importados
        todos[chave]["pasta"] = pasta
        _gravar(todos)


def desconectar(chave: str) -> None:
    with _lock:
        todos = _carregar()
        todos.pop(chave, None)
        _gravar(todos)


def sincronizar(chave: str, usar_ia: bool = True) -> dict:
    """Importa os arquivos novos ou alterados da pasta da pessoa de agora. Devolve as contagens."""
    if chave not in PROVEDORES or chave not in configurados():
        raise ErroLibrary("Este provedor não está configurado pelo administrador.")
    res = {"novos": 0, "repetidos": 0, "ignorados": 0, "erros": 0}
    with _lock:
        todos = _carregar()
        est = todos.get(chave)
        if not est:
            raise ErroLibrary("Conecte o provedor antes de sincronizar.")
        token = _acesso(chave, todos)
        vistos = est.setdefault("vistos", {})
        feitos = 0
        try:
            for item in _listar(chave, token, est.get("pasta", "")):
                ext = os.path.splitext(item["nome"])[1].lower()
                if ext not in base.EXT_OK or item["tamanho"] > base.LIMITE_BYTES or item["tamanho"] == 0:
                    res["ignorados"] += 1
                    continue
                if vistos.get(item["id"]) == item["marca"]:
                    continue
                if feitos >= MAX_POR_RODADA:
                    break
                feitos += 1
                try:
                    r = base.adicionar(item["nome"], _baixar(chave, token, item), "nuvem", usar_ia)
                    res["novos" if r.get("novo") else "repetidos"] += 1
                    vistos[item["id"]] = item["marca"]
                except ErroLibrary as ex:
                    if "Formato" in str(ex) or "vazio" in str(ex) or "passa de" in str(ex):
                        vistos[item["id"]] = item["marca"]   # não adianta tentar de novo
                        res["ignorados"] += 1
                    else:
                        res["erros"] += 1
            est["erro"] = ""
        except ErroLibrary as ex:
            est["erro"] = str(ex)
            res["erros"] += 1
        est["ultimo"] = time.strftime("%d/%m/%Y %H:%M")
        est["resumo"] = f"{res['novos']} novos, {res['repetidos']} repetidos, {res['erros']} com erro"
        _gravar(todos)
    return res


def _pessoas_com_conexao() -> list:
    saida = [pessoas.DONO]
    if pessoas.ativo():
        d = banco.pasta_pessoas()
        if d.is_dir():
            saida += sorted(x.name for x in d.iterdir() if x.is_dir() and not x.is_symlink() and pessoas.ID_RE.match(x.name))
    return saida


def sincronizar_todos() -> dict:
    """Uma rodada para todas as pessoas que têm conexão. Um erro de uma pessoa nunca interrompe as outras."""
    total = {"pessoas": 0, "novos": 0}
    for p in _pessoas_com_conexao():
        try:
            with _como(p):
                if not _arquivo().is_file():
                    continue
                conectados = [k for k, v in _carregar().items() if v.get("renovacao") and k in configurados()]
                for k in conectados:
                    total["novos"] += sincronizar(k)["novos"]
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
    threading.Thread(target=laco, daemon=True, name="library-nuvem").start()
