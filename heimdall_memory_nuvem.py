#!/usr/bin/env python3
"""Studio Hub: conexão de cada pessoa com o próprio armazenamento em nuvem (Dropbox e OneDrive), com importação automática.

Fluxo: a pessoa toca em Conectar, autoriza no site do provedor (OAuth 2.0, código de autorização com PKCE) e informa a pasta a vigiar. A cada
STUDIO_NUVEM_INTERVALO segundos (padrão 900) o Hub lista a pasta, baixa só os arquivos novos ou alterados e os envia ao acervo da pessoa
(heimdall_memory_dados.adicionar: motor interno ou Paperless). Por padrão a conexão é só de leitura. Opções por pasta: incluir subpastas (até
MAX_PROFUNDIDADE níveis) e, só se a pessoa tiver autorizado a escrita, mover cada arquivo já importado para a pasta "Importados pelo Heimdall" dentro
da pasta vigiada. O Hub nunca apaga arquivos da nuvem e nunca importa de novo o que está na pasta Importados.

Privacidade: cada pessoa tem o seu arquivo de conexão (memory/nuvem.bin, cifrado com AES-GCM, permissão 600) e só a sincronização dela mexe nele.
O estado (`state`) do OAuth fica na memória do servidor, ligado à pessoa que iniciou, vale por 10 minutos e só uma vez.
Configuração do administrador (.env): STUDIO_NUVEM_<DROPBOX|ONEDRIVE>_ID e _SEGREDO; STUDIO_HUB_URL (padrão https://memory.heimdall-ai.tech)
para o endereço de retorno <URL>/nuvem/retorno, que precisa estar cadastrado no aplicativo do provedor. STUDIO_NUVEM=0 desliga a sincronização.
Usa a biblioteca padrão e `cryptography` (AESGCM, já usada nas cópias de segurança); sem ela, a conexão é recusada em vez de gravar token em texto aberto.
"""
import json
import os
import re
import time
import urllib.parse

import heimdall_conexoes as cx
import heimdall_memory_dados as base

ErroMemory = base.ErroMemory
MAX_POR_RODADA = 50
MAX_PROFUNDIDADE = 5      # níveis de subpasta abaixo da pasta vigiada
MAX_PASTAS = 200          # pastas percorridas por rodada (OneDrive lista pasta a pasta)
PASTA_IMPORTADOS = "Importados pelo Heimdall"
PROVEDORES = cx.PROVEDORES   # mesmo registro da base de conexões (os testes ajustam os endereços por aqui)
# a autorização (OAuth) é da base comum; estes nomes ficam aqui porque o Hub chama o módulo de nuvem
iniciar, concluir, desconectar = cx.iniciar, cx.concluir, cx.desconectar


def configurados() -> list:
    return cx.configurados("arquivos")


# ---------------------------------------------------------------- listagem e download por provedor
def _listar(chave: str, token: str, pasta: str, subpastas: bool = False):
    """Itens {id, nome, tamanho, marca} da pasta, em páginas; com `subpastas`, também as de dentro (até MAX_PROFUNDIDADE níveis).
    A pasta PASTA_IMPORTADOS nunca é percorrida."""
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token}
    ignora = PASTA_IMPORTADOS.lower()
    if chave == "dropbox":
        base_l = ("/" + pasta.strip("/")).lower() if pasta.strip("/") else ""
        caminho = "" if not base_l else "/" + pasta.strip("/")
        url, corpo = prov["api"] + "/2/files/list_folder", {"path": caminho, "recursive": bool(subpastas), "limit": 200}
        for _ in range(50):
            st, _, b = cx.http("POST", url, {**aut, "Content-Type": "application/json"}, json.dumps(corpo).encode())
            if st != 200:
                raise ErroMemory("Não consegui abrir a pasta no Dropbox. Confira o caminho informado.")
            r = json.loads(b)
            for x in r.get("entries", []):
                if x.get(".tag") != "file":
                    continue
                rel = (x.get("path_lower") or "")[len(base_l):].strip("/").split("/")[:-1] if x.get("path_lower") else []
                if ignora in rel or len(rel) > MAX_PROFUNDIDADE:
                    continue
                yield {"id": x["id"], "nome": x["name"], "tamanho": x.get("size", 0), "marca": x.get("content_hash") or x.get("server_modified", "")}
            if not r.get("has_more"):
                return
            url, corpo = prov["api"] + "/2/files/list_folder/continue", {"cursor": r["cursor"]}
    else:
        p = pasta.strip("/")
        url = prov["api"] + ("/me/drive/root:/" + urllib.parse.quote(p) + ":/children" if p else "/me/drive/root/children") + "?$top=200"
        fila, visitadas = [(url, 0)], 0
        while fila:
            url, nivel = fila.pop(0)
            visitadas += 1
            if visitadas > MAX_PASTAS:
                return
            for _ in range(50):
                st, _, b = cx.http("GET", url, aut)
                if st != 200:
                    raise ErroMemory("Não consegui abrir a pasta no OneDrive. Confira o caminho informado.")
                r = json.loads(b)
                for x in r.get("value", []):
                    if "file" in x:
                        yield {"id": x["id"], "nome": x["name"], "tamanho": x.get("size", 0), "marca": x.get("eTag") or x.get("lastModifiedDateTime", "")}
                    elif subpastas and "folder" in x and x["name"].lower() != ignora and nivel < MAX_PROFUNDIDADE:
                        fila.append((prov["api"] + "/me/drive/items/" + urllib.parse.quote(x["id"]) + "/children?$top=200", nivel + 1))
                url = r.get("@odata.nextLink")
                if not url:
                    break


def _destino(chave: str, token: str, pasta: str) -> str:
    """Prepara a pasta PASTA_IMPORTADOS dentro da pasta vigiada e devolve o que `_mover` precisa (caminho no Dropbox, id no OneDrive)."""
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    p = pasta.strip("/")
    if chave == "dropbox":
        caminho = ("/" + p if p else "") + "/" + PASTA_IMPORTADOS
        st, _, _ = cx.http("POST", prov["api"] + "/2/files/create_folder_v2", aut, json.dumps({"path": caminho, "autorename": False}).encode())
        if st not in (200, 409):   # 409: a pasta já existe
            raise ErroMemory("Não consegui preparar a pasta de importados no Dropbox.")
        return caminho
    caminho = (p + "/" if p else "") + PASTA_IMPORTADOS
    st, _, b = cx.http("GET", prov["api"] + "/me/drive/root:/" + urllib.parse.quote(caminho), aut)
    if st != 200:
        pai = prov["api"] + ("/me/drive/root:/" + urllib.parse.quote(p) + ":/children" if p else "/me/drive/root/children")
        st, _, b = cx.http("POST", pai, aut, json.dumps({"name": PASTA_IMPORTADOS, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}).encode())
    if st not in (200, 201):
        raise ErroMemory("Não consegui preparar a pasta de importados no OneDrive.")
    return json.loads(b)["id"]


def _mover(chave: str, token: str, item: dict, destino: str) -> bool:
    """Move o arquivo para a pasta de importados (nome repetido ganha sufixo). Nunca apaga. Falhar não desfaz a importação."""
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if chave == "dropbox":
        corpo = {"from_path": item["id"], "to_path": destino + "/" + item["nome"], "autorename": True}
        st, _, _ = cx.http("POST", prov["api"] + "/2/files/move_v2", aut, json.dumps(corpo).encode())
    else:
        corpo = {"parentReference": {"id": destino}, "@microsoft.graph.conflictBehavior": "rename"}
        st, _, _ = cx.http("PATCH", prov["api"] + "/me/drive/items/" + urllib.parse.quote(item["id"]), aut, json.dumps(corpo).encode())
    return st == 200


def _baixar(chave: str, token: str, item: dict) -> bytes:
    prov = PROVEDORES[chave]
    aut = {"Authorization": "Bearer " + token}
    if chave == "dropbox":
        st, _, b = cx.http("POST", prov["conteudo"] + "/2/files/download", {**aut, "Dropbox-API-Arg": json.dumps({"path": item["id"]})}, b"", limite=base.LIMITE_BYTES, timeout=120)
    else:
        st, _, b = cx.http("GET", prov["api"] + "/me/drive/items/" + urllib.parse.quote(item["id"]) + "/content", aut, limite=base.LIMITE_BYTES, timeout=120)
    if st != 200:
        raise ErroMemory("Não consegui baixar o arquivo.")
    return b


# ---------------------------------------------------------------- tela e sincronização
def situacao() -> list:
    todos = cx.carregar() if configurados() else {}
    saida = []
    for k in configurados():
        e = todos.get(k, {})
        saida.append({"chave": k, "nome": PROVEDORES[k]["nome"], "conectado": bool(e.get("renovacao")), "pasta": e.get("pasta", ""), "ultimo": e.get("ultimo", ""),
                      "resumo": e.get("resumo", ""), "erro": e.get("erro", ""), "subpastas": bool(e.get("subpastas")), "escrita": bool(e.get("escrita")),
                      "mover": bool(e.get("mover")) and bool(e.get("escrita")), "dica": PROVEDORES[k]["dica"]})
    return saida


def definir_pasta(chave: str, pasta: str, subpastas: bool = False, mover: bool = False) -> None:
    pasta = " ".join((pasta or "").split())[:200]
    if re.search(r"[\x00-\x1f]|\.\./|^\.\.$", pasta):
        raise ErroMemory("Caminho de pasta inválido.")
    with cx.LOCK:
        todos = cx.carregar()
        if not todos.get(chave, {}).get("renovacao"):
            raise ErroMemory("Conecte o provedor antes de escolher a pasta.")
        if mover and not todos[chave].get("escrita"):
            raise ErroMemory("Para mover arquivos, conecte com a permissão de organização.")
        if todos[chave].get("pasta") != pasta:
            todos[chave]["vistos"] = {}   # outra pasta: recomeça a lista de arquivos já importados
        todos[chave]["pasta"] = pasta
        todos[chave]["subpastas"], todos[chave]["mover"] = bool(subpastas), bool(mover)
        cx.gravar(todos)


def sincronizar(chave: str, usar_ia: bool = True) -> dict:
    """Importa os arquivos novos ou alterados da pasta da pessoa de agora. Devolve as contagens."""
    if chave not in PROVEDORES or chave not in configurados():
        raise ErroMemory("Este provedor não está configurado pelo administrador.")
    res = {"novos": 0, "repetidos": 0, "ignorados": 0, "erros": 0, "movidos": 0}
    with cx.LOCK:
        todos = cx.carregar()
        est = todos.get(chave)
        if not est:
            raise ErroMemory("Conecte o provedor antes de sincronizar.")
        token = cx.acesso(chave, todos)
        vistos = est.setdefault("vistos", {})
        feitos, destino = 0, None
        mover = bool(est.get("mover")) and bool(est.get("escrita"))
        try:
            for item in _listar(chave, token, est.get("pasta", ""), bool(est.get("subpastas"))):
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
                    if mover:
                        try:
                            destino = destino or _destino(chave, token, est.get("pasta", ""))
                            res["movidos"] += 1 if _mover(chave, token, item, destino) else 0
                        except ErroMemory:
                            pass   # o documento já está no acervo; só não foi movido
                except ErroMemory as ex:
                    if "Formato" in str(ex) or "vazio" in str(ex) or "passa de" in str(ex):
                        vistos[item["id"]] = item["marca"]   # não adianta tentar de novo
                        res["ignorados"] += 1
                    else:
                        res["erros"] += 1
            est["erro"] = ""
        except ErroMemory as ex:
            est["erro"] = str(ex)
            res["erros"] += 1
        est["ultimo"] = time.strftime("%d/%m/%Y %H:%M")
        est["resumo"] = f"{res['novos']} novos, {res['repetidos']} repetidos, {res['erros']} com erro" + (f", {res['movidos']} movidos" if mover else "")
        cx.gravar(todos)
    return res


cx.registrar("arquivos", sincronizar)
