#!/usr/bin/env python3
"""Avisos nativos no Mac: o StudioLibre grava o aviso completo numa pasta local e o app do Mac mostra como notificação do macOS.

O Bark entrega ao iPhone com texto genérico (o texto passa por um servidor de terceiros). No Mac não há esse limite: o aviso fica só em
`db/alerts/` (permissão 700) e é lido pelo app, que o apaga depois de mostrar. Campos no estilo do Bark: title, body, group, level.
Desligar: STUDIO_AVISOS_MAC=0.
"""
import json
import os
import time
import uuid
from pathlib import Path

import heimdall_banco as banco
import heimdall_pastas

NIVEIS = ("active", "timeSensitive", "critical", "passive")
MAX_TITULO, MAX_CORPO, MAX_FILA = 200, 4000, 200


def ligado() -> bool:
    return os.environ.get("STUDIO_AVISOS_MAC", "1").strip() != "0"


def pasta() -> Path:
    return heimdall_pastas.migrar(banco._RAIZ, "avisos_mac", "alerts")


def publicar(aviso: dict) -> bool:
    """Grava um aviso na fila do Mac. Devolve False se desligado, vazio ou sem espaço; nunca levanta erro (aviso não pode derrubar o fluxo)."""
    if not ligado() or not isinstance(aviso, dict):
        return False
    titulo = str(aviso.get("title") or aviso.get("titulo") or "").strip()[:MAX_TITULO]
    corpo = str(aviso.get("body") or aviso.get("corpo") or "").strip()[:MAX_CORPO]
    if not titulo and not corpo:
        return False
    nivel = str(aviso.get("level") or "active")
    item = {"titulo": titulo or "StudioLibre", "corpo": corpo, "grupo": str(aviso.get("group") or "heimdall")[:40],
            "nivel": nivel if nivel in NIVEIS else "active", "criado": time.time()}
    url = str(aviso.get("url") or "").strip()
    if url.startswith("https://") and len(url) <= 300:   # o app abre o endereço do produto ao clicar na notificação
        item["url"] = url
    try:
        p = pasta()
        p.mkdir(parents=True, exist_ok=True)
        os.chmod(p, 0o700)
        if len(list(p.glob("*.json"))) >= MAX_FILA:
            return False
        nome = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        tmp = p / f".{nome}.tmp"
        tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p / f"{nome}.json")
        return True
    except OSError:
        return False
