#!/usr/bin/env python3
"""Integrações da conta: o que cada pessoa liga ao Heimdall a partir do menu Conta (account.heimdall-ai.tech/integracoes).

Hoje só a Saúde está pronta, e só para o dono: o app Health Auto Export do iPhone envia os dados à caixa de correio da Cloudflare
(endereço /v1/hae) com o token da pessoa; o Mac busca (heimdall mailbox pull) e importa para o banco de saúde. Notas, Lembretes e Calendário
(conta Apple ou Google) aparecem como "em preparação": falta o armazenamento por pessoa, e ninguém além do dono tem onde guardar esses dados.

O estado fica em banco/integracoes.json (permissão só do dono): quem ativou o quê e quando. O token nunca é guardado aqui; só a caixa guarda o hash.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

import heimdall_caixa as caixa

AQUI = Path(__file__).resolve().parent
ARQUIVO = AQUI / "banco" / "integracoes.json"
_SEGREDO = secrets.token_bytes(32)  # vale enquanto o Account roda; um reinício só invalida formulários abertos

# chave -> (nome, situação). "pronta" pode ser ativada; "em_preparacao" só informa.
INTEGRACOES = {
    "saude": ("Saúde", "pronta"),
    "notas": ("Notas", "em_preparacao"),
    "lembretes": ("Lembretes", "em_preparacao"),
    "calendario": ("Calendário", "em_preparacao"),
}


def usuario_de(p: dict, env=None) -> str:
    """Nome da pessoa na caixa. O dono usa o nome combinado (HEIMDALL_CAIXA_MEU_NOME, padrão "eu"); os demais, o e-mail reduzido a a-z, 0-9 e hífen."""
    env = caixa._env() if env is None else env
    if p.get("papel") == "dono":
        return re.sub(r"[^a-z0-9-]", "", (env.get("HEIMDALL_CAIXA_MEU_NOME") or "eu").lower())[:32] or "eu"
    base = re.sub(r"[^a-z0-9]+", "-", (p.get("email") or "").lower()).strip("-")
    if not base:
        return ""
    if len(base) > 32:
        base = base[:23] + "-" + hashlib.sha256(base.encode()).hexdigest()[:8]
    return base


def csrf(p: dict) -> str:
    """Token do formulário: assinado com um segredo do processo e preso à identidade de quem pediu a página."""
    ident = (p.get("email") or "local") + "\0integracoes"
    return hmac.new(_SEGREDO, ident.encode(), hashlib.sha256).hexdigest()[:32]


def csrf_ok(p: dict, recebido: str) -> bool:
    return hmac.compare_digest(csrf(p), recebido or "")


def _ler() -> dict:
    try:
        d = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(d: dict) -> None:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ARQUIVO)


def estado(p: dict, env=None) -> dict:
    """{chave: {nome, situacao, ativa, desde}} para a pessoa, mais "caixa" (ligada ou não) e "pode" (se ela pode ativar)."""
    env = caixa._env() if env is None else env
    u = usuario_de(p, env)
    meus = _ler().get(u, {}) if u else {}
    itens = {}
    for k, (nome, sit) in INTEGRACOES.items():
        itens[k] = {"nome": nome, "situacao": sit, "ativa": k in meus, "desde": meus.get(k, {}).get("desde", "")}
    return {"usuario": u, "caixa": caixa.ativa(env), "pode": p.get("papel") == "dono" and bool(u), "itens": itens}


def url_hae(env=None) -> str:
    env = caixa._env() if env is None else env
    return env.get("HEIMDALL_CAIXA_URL", caixa.URL_PADRAO).rstrip("/") + "/v1/hae"


def ativar_saude(p: dict, env=None, abrir=None) -> str:
    """Cria (ou troca) o token da pessoa e registra a ativação. Devolve o token, que só aparece agora. Levanta RuntimeError com mensagem clara."""
    env = caixa._env() if env is None else env
    st = estado(p, env)
    if not st["pode"]:
        raise RuntimeError("por enquanto só o dono pode ativar a Saúde; falta o armazenamento por pessoa")
    if not st["caixa"]:
        raise RuntimeError("a caixa de correio está desligada: rode heimdall mailbox start e depois heimdall env --set HEIMDALL_CAIXA 1")
    u = st["usuario"]
    try:
        caixa.revogar_pessoa(u, env, abrir)  # trocar o token: o antigo deixa de valer
    except RuntimeError:
        pass
    token = caixa.criar_pessoa(u, env, abrir)
    d = _ler()
    d.setdefault(u, {})["saude"] = {"desde": time.strftime("%Y-%m-%d %H:%M")}
    _gravar(d)
    return token


def desativar_saude(p: dict, env=None, abrir=None) -> None:
    env = caixa._env() if env is None else env
    st = estado(p, env)
    if not st["pode"]:
        raise RuntimeError("por enquanto só o dono pode mexer na Saúde")
    caixa.revogar_pessoa(st["usuario"], env, abrir)
    d = _ler()
    d.get(st["usuario"], {}).pop("saude", None)
    _gravar(d)
