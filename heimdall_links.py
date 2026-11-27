#!/usr/bin/env python3
"""Endereço da tela de cada produto, para as notificações apontarem para ele (decisão do usuário em 26/11/2026).

Um só ponto define o domínio: STUDIO_DOMINIO (padrão heimdall-ai.tech até a troca para studiolibre.io; depois é só mudar o valor).
Cada produto tem um subdomínio (finance., health. e assim por diante). Se o .env definir os hosts do serviço (STUDIO_<X>_HOSTS ou
STUDIO_<X>_HOSTS), vale o primeiro host público dessa lista. Sem domínio válido, não há link: a notificação segue sem ele.
Desligar os links: STUDIO_NOTIFICACAO_LINK=0.
"""
import os
import re

DOMINIO_PADRAO = "heimdall-ai.tech"
# chave usada pelo código -> (subdomínio, variável de hosts, caminho da tela de avisos ou da página inicial)
PRODUTOS = {
    "saude": ("health", "SAUDE_PAINEL", "/avisos"), "health": ("health", "SAUDE_PAINEL", "/avisos"),
    "financas": ("finance", "FINANCE", "/avisos"), "finance": ("finance", "FINANCE", "/avisos"),
    "learn": ("learn", "LEARN", "/"), "news": ("news", "NEWS", "/"),
    "games": ("games", "JOGOS", "/"), "jogos": ("games", "JOGOS", "/"), "lab": ("lab", "LAB", "/"),
    "memory": ("memory", "MEMORY", "/"), "trading": ("trading", "TRADING", "/"),
    "controls": ("controls", "CONTROLS", "/"), "account": ("account", "ACCOUNT", "/"),
}
_HOST_OK = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get("STUDIO_" + nome) or padrao


def dominio() -> str:
    d = _env("DOMINIO", DOMINIO_PADRAO).strip().lower().strip(".")
    return d if _HOST_OK.match(d) else DOMINIO_PADRAO


def host_do(produto: str) -> str:
    """Host público do produto, ou vazio se o produto não é conhecido."""
    sub, chave, _ = PRODUTOS.get(str(produto).lower(), ("", "", ""))
    if not sub:
        return ""
    for h in _env(chave + "_HOSTS").split(","):
        h = h.strip().lower()
        if _HOST_OK.match(h) and not h.endswith(".ts.net"):
            return h
    return f"{sub}.{dominio()}"


def url_produto(produto: str, caminho: str = None) -> str:
    """Link https da tela do produto ('' se desligado ou desconhecido). `caminho` vazio usa a tela padrão do produto."""
    if _env("NOTIFICACAO_LINK", "1") == "0":
        return ""
    h = host_do(produto)
    if not h:
        return ""
    cam = PRODUTOS[str(produto).lower()][2] if caminho is None else caminho
    if not cam.startswith("/") or any(c in cam for c in " \r\n\\"):
        cam = "/"
    return f"https://{h}{cam}"


def com_link(payload: dict, produto: str, caminho: str = None) -> dict:
    """Cópia do aviso (formato Bark: title, body, group, level) com o campo url do produto, quando houver."""
    p = dict(payload)
    u = url_produto(produto, caminho)
    if u:
        p["url"] = u
    return p
