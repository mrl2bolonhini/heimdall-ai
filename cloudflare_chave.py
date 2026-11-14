#!/usr/bin/env python3
"""Grava no .env a chave da Cloudflare que liga dois recursos do Heimdall News (só notícias públicas):
a reserva de resumos no Workers AI e a leitura de páginas com navegador (Browser Rendering).

    python3 cloudflare_chave.py

Antes, crie um token na Cloudflare (Meu perfil, Tokens de API, Criar token, token personalizado) com duas permissões
de conta: Workers AI (leitura) e Browser Rendering (edição). O token é pedido sem aparecer na tela e fica só no .env
(permissão 600). O número da conta é descoberto sozinho; se o token não puder listar contas, o script pede o número. Depois: ./subir.sh --reiniciar
"""
import getpass
import json
import re
import sys
import urllib.request

import heimdall_cloud as nuvem


def _get(caminho: str, token: str) -> dict:
    req = urllib.request.Request("https://api.cloudflare.com/client/v4" + caminho, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read(1_000_000))


def main() -> None:
    token = getpass.getpass("Token da Cloudflare (não aparece na tela): ").strip()
    if len(token) < 20:
        sys.exit("Token curto demais. Nada foi gravado.")
    try:
        status = _get("/user/tokens/verify", token).get("result", {}).get("status")
    except Exception as ex:  # noqa: BLE001
        sys.exit(f"A Cloudflare não aceitou o token ({type(ex).__name__}). Nada foi gravado.")
    if status != "active":
        sys.exit(f"O token não está ativo (estado: {status}). Nada foi gravado.")
    try:
        contas = _get("/accounts", token).get("result", [])
    except Exception:  # noqa: BLE001  (token só com as permissões do News: não lista contas)
        contas = []
    if len(contas) == 1:
        conta = contas[0]["id"]
    elif len(contas) > 1:
        sys.exit(f"O token enxerga {len(contas)} contas; o esperado é 1. Dê ao token permissão só na sua conta. Nada foi gravado.")
    else:
        print("O token não lista contas (normal quando ele só tem as permissões do News).")
        print("O número da conta são 32 letras e números que aparecem no endereço do painel: dash.cloudflare.com/<número>/...")
        conta = input("Número da conta: ").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", conta):
        sys.exit("O número da conta deve ter 32 caracteres (0 a 9 e a a f). Nada foi gravado.")
    nuvem.env_gravar({"CLOUDFLARE_API_TOKEN": token, "CLOUDFLARE_ACCOUNT_ID": conta})
    print("Gravado no .env (permissão 600). Reinicie para valer: ./subir.sh --reiniciar")
    print("Para desligar só a reserva de resumos: HEIMDALL_NEWS_RESERVA=0 no .env. Para ler uma fonte com navegador: \"renderizar\": true em noticias_fontes.json.")


if __name__ == "__main__":
    main()
