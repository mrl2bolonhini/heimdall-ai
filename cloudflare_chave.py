#!/usr/bin/env python3
"""Grava no .env a chave da Cloudflare que liga dois recursos do Heimdall News (só notícias públicas):
a reserva de resumos no Workers AI e a leitura de páginas com navegador (Browser Rendering).

    python3 cloudflare_chave.py            grava a chave no .env
    python3 cloudflare_chave.py --testar   testa a chave gravada: Workers AI e Browser Run, mostrando a resposta da Cloudflare

Antes, crie um token na Cloudflare (Meu perfil, Tokens de API, Criar token, token personalizado) com duas permissões
de conta: Workers AI (leitura) e Browser Rendering (edição). O token é pedido sem aparecer na tela e fica só no .env
(permissão 600). O número da conta é descoberto sozinho; se o token não puder listar contas, o script pede o número. Depois: ./subir.sh --reiniciar
"""
import getpass
import json
import re
import sys
import urllib.error
import urllib.request

import heimdall_cloud as nuvem


def _get(caminho: str, token: str) -> dict:
    req = urllib.request.Request("https://api.cloudflare.com/client/v4" + caminho, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read(1_000_000))


def _ler_env() -> dict:
    out = {}
    try:
        for l in (nuvem.PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if l.startswith("export "):
                l = l[7:]
            if "=" in l and l.startswith("CLOUDFLARE_"):
                k, v = l.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def _post(caminho: str, token: str, corpo: dict) -> str:
    req = urllib.request.Request("https://api.cloudflare.com/client/v4" + caminho, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return f"OK (HTTP {r.status})"
    except urllib.error.HTTPError as ex:
        try:
            msg = "; ".join(str(x.get("message", "")) for x in json.loads(ex.read(20000)).get("errors", []))
        except Exception:  # noqa: BLE001
            msg = ""
        return f"FALHOU: HTTP {ex.code} {msg[:160]}"
    except Exception as ex:  # noqa: BLE001
        return f"FALHOU: {type(ex).__name__}"


def testar() -> None:
    env = _ler_env()
    token, conta = env.get("CLOUDFLARE_API_TOKEN", ""), env.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not conta:
        sys.exit("Não há chave no .env. Rode python3 cloudflare_chave.py primeiro.")
    modelo = "@cf/google/gemma-3-12b-it"
    print("Workers AI (reserva de resumos):", _post(f"/accounts/{conta}/ai/run/{modelo}", token, {"messages": [{"role": "user", "content": "Responda só: ok"}], "max_tokens": 5}))
    print("Browser Run (leitura de páginas):", _post(f"/accounts/{conta}/browser-rendering/content", token, {"url": "https://example.com"}))


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--testar":
        testar()
        return
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
