#!/usr/bin/env python3
"""Envio de notificação pelo Bark (iPhone): chave do .env e POST em api.day.app. Nunca levanta erro; devolve True se o Bark confirmou.

O texto que vai ao Bark passa por servidor de terceiros: use só texto genérico (studio_avisos.texto_bark) e, sempre que houver produto,
o campo url com o link dele (studio_links.com_link).
"""
import json
import os
import re
import urllib.request
from pathlib import Path


def chave_bark() -> str:
    v = (os.environ.get("STUDIO_BARK_KEY") or os.environ.get("STUDIO_BARK_KEY", "")).strip()
    if not v:
        try:
            for linha in (Path(__file__).resolve().parent / ".env").read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:export\s+)?(?:STUDIO|HEIMDALL)_BARK_KEY\s*=\s*(.*)$", linha)
                if m:
                    v = m.group(1).strip().strip("'\"")
        except OSError:
            pass
    return re.sub(r"^https?://[^/]+/([^/?]+).*", r"\1", v)


def enviar_bark(payload: dict) -> bool:
    chave = chave_bark()
    if not chave:
        return False
    req = urllib.request.Request("https://api.day.app/push", data=json.dumps({"device_key": chave, **payload}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return 200 <= r.status < 300
    except Exception:  # noqa: BLE001
        return False
