#!/usr/bin/env python3
"""Modelos grandes na nuvem (gpt-oss-120b no Workers AI) pelo gateway de IA "heimdall" da Cloudflare.

Interruptor: HEIMDALL_NUVEM=1 no .env liga; qualquer outro valor (ou ausente) desliga e tudo volta aos modelos locais, sem reiniciar
(o .env é lido a cada chamada). Se a nuvem falhar, quem chama cai para o modelo local (ver heimdall_perguntar.chamar_local).

O gateway exige autenticação, não guarda o conteúdo das conversas e corta em US$ 10 por mês. Usa a mesma chave do News
(CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID no .env), que precisa da permissão AI Gateway (Lido, Executar e Editar).

    python3 heimdall_nuvem.py            mostra o estado (ligada ou não) e faz uma pergunta de teste se estiver ligada
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
GATEWAY = "heimdall"
MODELO_PADRAO = "workers-ai/@cf/openai/gpt-oss-120b"
# Perguntar dos sites: modelo mais leve e barato, sem raciocínio (o /no_think vai no prompt). HEIMDALL_NUVEM_PERGUNTAR_MODELO troca.
MODELO_PERGUNTAR = "workers-ai/@cf/qwen/qwen3-30b-a3b-fp8"
USER_AGENT = "heimdall-ai/1.0"  # sem isto o endereço do gateway recusa o Python padrão (erro 1010)
CHAVES = ("HEIMDALL_NUVEM", "HEIMDALL_NUVEM_MODELO", "HEIMDALL_NUVEM_PERGUNTAR_MODELO", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
ultimo_erro = ""


def _env() -> dict:
    """Valores do .env, lidos na hora (o interruptor vale sem reiniciar). O ambiente do processo tem prioridade."""
    out = {}
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("export "):
                ln = ln[7:]
            k, _, v = ln.partition("=")
            if k.strip() in CHAVES:
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    for k in CHAVES:
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def ativo(env: dict = None) -> bool:
    e = env if env is not None else _env()
    return e.get("HEIMDALL_NUVEM") == "1" and bool(e.get("CLOUDFLARE_API_TOKEN")) and bool(e.get("CLOUDFLARE_ACCOUNT_ID"))


def _abrir(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def modelo_perguntar(env: dict = None) -> str:
    e = env if env is not None else _env()
    return e.get("HEIMDALL_NUVEM_PERGUNTAR_MODELO") or MODELO_PERGUNTAR


def chat(sistema: str, usuario: str, max_tokens: int = 700, timeout: int = 120, env: dict = None, abrir=None, forcar: bool = False, modelo: str = "", folga: int = 1000) -> str:
    """Resposta do modelo grande. Levanta exceção se a nuvem estiver desligada, falhar ou voltar vazia."""
    global ultimo_erro
    e = env if env is not None else _env()
    tem_chave = bool(e.get("CLOUDFLARE_API_TOKEN")) and bool(e.get("CLOUDFLARE_ACCOUNT_ID"))
    if not (ativo(e) or (forcar and tem_chave)):  # forcar: teste pontual, mesmo com o interruptor desligado
        raise RuntimeError("nuvem desligada" if tem_chave else "falta a chave da Cloudflare no .env")
    url = f"https://gateway.ai.cloudflare.com/v1/{e['CLOUDFLARE_ACCOUNT_ID']}/{GATEWAY}/compat/chat/completions"
    token = e["CLOUDFLARE_API_TOKEN"]
    # o gpt-oss gasta parte dos tokens raciocinando antes de responder: dá folga além do que o chamador pediu (modelo sem raciocínio usa folga menor)
    corpo = {"model": modelo or e.get("HEIMDALL_NUVEM_MODELO") or MODELO_PADRAO, "temperature": 0.2, "max_tokens": int(max_tokens) + int(folga),
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST", headers={
        "Authorization": "Bearer " + token, "cf-aig-authorization": "Bearer " + token,
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with (abrir or _abrir)(req, timeout) as r:
            d = json.loads(r.read(500000).decode("utf-8", "replace"))
        texto = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if not texto.strip():
            raise RuntimeError("resposta vazia")
        ultimo_erro = ""
        return texto.strip()
    except urllib.error.HTTPError as ex:
        ultimo_erro = f"HTTP {ex.code}"
        raise RuntimeError(ultimo_erro) from None
    except Exception as ex:  # noqa: BLE001
        ultimo_erro = type(ex).__name__ if not isinstance(ex, RuntimeError) else str(ex)
        raise RuntimeError(ultimo_erro) from None


def main() -> None:
    e = _env()
    if not ativo(e):
        print("Nuvem DESLIGADA (HEIMDALL_NUVEM não é 1, ou falta a chave da Cloudflare). Os modelos locais seguem em uso.")
        print("Para ligar: studio env --set HEIMDALL_NUVEM 1")
        return
    print("Nuvem LIGADA. Modelo:", e.get("HEIMDALL_NUVEM_MODELO") or MODELO_PADRAO)
    try:
        print("Teste:", chat("Responda em português, em uma frase curta.", "Diga que está funcionando.", max_tokens=60))
    except RuntimeError as ex:
        sys.exit(f"Teste falhou ({ex}). Se estava ligada, os apps usam o modelo local. Para desligar: studio env --set HEIMDALL_NUVEM 0")


if __name__ == "__main__":
    main()
