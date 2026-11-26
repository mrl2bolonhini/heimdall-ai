#!/usr/bin/env python3
"""Cliente mínimo do Notion para o Studio Notes: ideias, contatos e endereços vão para três bancos de dados do Notion.

Regra de privacidade (ROADMAP): o Notion só recebe notas comuns. Saúde e finanças nunca vão para lá (quem decide é heimdall_catalogo.py).
Configuração no .env (nunca colada em conversa; o comando `studio notion` grava e confere):
  HEIMDALL_NOTION_TOKEN           token da integração interna do Notion
  HEIMDALL_NOTION_DB_IDEIAS       id do banco de dados de ideias
  HEIMDALL_NOTION_DB_CONTATOS     id do banco de dados de contatos
  HEIMDALL_NOTION_DB_ENDERECOS    id do banco de dados de endereços
O título vai na propriedade de título do banco (qualquer nome) e os detalhes viram texto dentro da página; assim o banco pode ter as colunas que você quiser.
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
API = "https://api.notion.com/v1"
VERSAO = "2022-06-28"
BANCOS = {"ideia": "HEIMDALL_NOTION_DB_IDEIAS", "contato": "HEIMDALL_NOTION_DB_CONTATOS", "endereco": "HEIMDALL_NOTION_DB_ENDERECOS"}
ID_RE = re.compile(r"[0-9a-fA-F]{32}")


def _env(chave: str) -> str:
    v = os.environ.get(chave, "")
    if v:
        return v.strip()
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith(chave + "="):
                v = ln.split("=", 1)[1].strip()
                return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v
    except OSError:
        pass
    return ""


def id_do_banco(tipo: str) -> str:
    """Aceita o id puro ou o endereço do banco copiado do Notion; devolve só os 32 caracteres, ou ''."""
    bruto = _env(BANCOS[tipo]).replace("-", "")
    achados = ID_RE.findall(bruto)
    return achados[-1] if achados else ""


def configurado(tipo: str) -> bool:
    return bool(_env("HEIMDALL_NOTION_TOKEN") and id_do_banco(tipo))


def _chamar(metodo: str, caminho: str, corpo: dict = None, http=None) -> dict:
    """http(metodo, url, corpo, cabecalho) -> dict é para teste."""
    cab = {"Authorization": "Bearer " + _env("HEIMDALL_NOTION_TOKEN"), "Notion-Version": VERSAO, "Content-Type": "application/json"}
    if http:
        return http(metodo, API + caminho, corpo, cab)
    req = urllib.request.Request(API + caminho, data=json.dumps(corpo).encode("utf-8") if corpo is not None else None, headers=cab, method=metodo)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _titulo_do_banco(banco: str, http=None) -> str:
    r = _chamar("GET", f"/databases/{banco}", None, http)
    for nome, prop in (r.get("properties") or {}).items():
        if prop.get("type") == "title":
            return nome
    raise RuntimeError("o banco não tem coluna de título")


def _paragrafos(texto: str) -> list:
    blocos = []
    for p in [x.strip() for x in str(texto).split("\n") if x.strip()][:90]:
        blocos.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": p[:1900]}}]}})
    return blocos


def criar(tipo: str, titulo: str, texto: str, http=None) -> tuple:
    """Cria a página. Devolve (ok, id_da_pagina_ou_motivo). Nunca levanta erro."""
    if tipo not in BANCOS:
        return False, "tipo sem banco no Notion"
    if not configurado(tipo):
        return False, "o Notion não está configurado (rode: studio notion)"
    try:
        banco = id_do_banco(tipo)
        col = _titulo_do_banco(banco, http)
        r = _chamar("POST", "/pages", {"parent": {"database_id": banco},
                                       "properties": {col: {"title": [{"type": "text", "text": {"content": str(titulo)[:190]}}]}},
                                       "children": _paragrafos(texto)}, http)
        return True, str(r.get("id", ""))
    except urllib.error.HTTPError as e:
        return False, f"o Notion recusou ({e.code})"
    except Exception as e:  # noqa: BLE001
        return False, f"não consegui falar com o Notion ({type(e).__name__})"


def arquivar(pagina_id: str, http=None) -> tuple:
    """Desfazer: o Notion não apaga por API, arquiva a página (vai para a lixeira)."""
    try:
        _chamar("PATCH", f"/pages/{pagina_id}", {"archived": True}, http)
        return True, "arquivada"
    except Exception as e:  # noqa: BLE001
        return False, f"não consegui arquivar ({type(e).__name__})"


def verificar(http=None) -> list:
    """Para `studio notion`: uma linha por banco, dizendo se o token enxerga o banco."""
    out = []
    for tipo in BANCOS:
        if not _env("HEIMDALL_NOTION_TOKEN"):
            out.append(f"{tipo}: falta HEIMDALL_NOTION_TOKEN")
        elif not id_do_banco(tipo):
            out.append(f"{tipo}: falta {BANCOS[tipo]}")
        else:
            try:
                _titulo_do_banco(id_do_banco(tipo), http)
                out.append(f"{tipo}: ok")
            except Exception as e:  # noqa: BLE001
                out.append(f"{tipo}: não consegui abrir ({type(e).__name__}); compartilhe o banco com a integração")
    return out


if __name__ == "__main__":
    print("\n".join(verificar()))
