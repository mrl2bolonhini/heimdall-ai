#!/usr/bin/env python3
"""Links do produto nas notificações: domínio base único, hosts do .env, desligar, Bark, aviso do Mac e texto genérico."""
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
falhas = 0


def confere(nome, cond):
    global falhas
    print(("ok   " if cond else "FALHA"), nome)
    if not cond:
        falhas += 1


for k in [k for k in os.environ if k.startswith(("STUDIO_", "HEIMDALL_"))]:
    del os.environ[k]
import heimdall_links as L

confere("padrão aponta para a aba Avisos do Health", L.url_produto("saude") == "https://health.heimdall-ai.tech/avisos")
confere("Finance usa financas ou finance", L.url_produto("financas") == L.url_produto("finance") == "https://finance.heimdall-ai.tech/avisos")
confere("Learn vai para a página inicial", L.url_produto("learn") == "https://learn.heimdall-ai.tech/")
confere("produto desconhecido não tem link", L.url_produto("xyz") == "" and L.com_link({"title": "t"}, "xyz") == {"title": "t"})
os.environ["STUDIO_DOMINIO"] = "studiolibre.io"
confere("STUDIO_DOMINIO muda todos os endereços", L.url_produto("saude") == "https://health.studiolibre.io/avisos" and L.url_produto("games") == "https://games.studiolibre.io/")
os.environ["HEIMDALL_DOMINIO"] = "antigo.tech"
confere("STUDIO_ vence HEIMDALL_", L.dominio() == "studiolibre.io")
os.environ["STUDIO_DOMINIO"] = "inválido/x"
confere("domínio inválido volta ao padrão", L.dominio() == "heimdall-ai.tech" or L.dominio() == "antigo.tech")
del os.environ["STUDIO_DOMINIO"], os.environ["HEIMDALL_DOMINIO"]
os.environ["HEIMDALL_FINANCE_HOSTS"] = "localhost,127.0.0.1,fin.exemplo.com"
confere("hosts do .env valem (primeiro público)", L.url_produto("finance") == "https://fin.exemplo.com/avisos")
os.environ["STUDIO_NOTIFICACAO_LINK"] = "0"
confere("interruptor desliga o link", L.url_produto("finance") == "" and "url" not in L.com_link({"title": "t"}, "finance"))
del os.environ["STUDIO_NOTIFICACAO_LINK"]
confere("caminho inseguro vira /", L.url_produto("learn", "avisos x") == "https://learn.heimdall-ai.tech/")
confere("com_link não altera o original", (lambda p: (L.com_link(p, "learn"), "url" not in p)[1])({"title": "t"}))

import heimdall_avisos as av
b = av.texto_bark("saude", 2)
confere("texto_bark leva o link do produto", b["url"] == "https://health.heimdall-ai.tech/avisos" and "2 avisos" in b["title"])
confere("texto_bark continua genérico", "Abra a aba Avisos" in b["body"])

import heimdall_avisos_mac as mac
with tempfile.TemporaryDirectory() as d:
    os.environ["HEIMDALL_ALERTAS_DIR"] = d
    mac.pasta = lambda: Path(d)
    confere("aviso do Mac com url https é gravado", mac.publicar({"title": "t", "body": "c", "url": "https://health.heimdall-ai.tech/avisos"}))
    import time as _t
    _t.sleep(0.01)
    confere("aviso do Mac com url não https ignora o link", mac.publicar({"title": "t2", "body": "c", "url": "javascript:alert(1)"}))
    itens = sorted((json.loads(p.read_text()) for p in Path(d).glob("*.json")), key=lambda x: x["criado"])
    confere("url https vai ao arquivo; outra não", itens[0].get("url", "").startswith("https://") and "url" not in itens[1])

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
