#!/usr/bin/env python3
"""Inicia o LiteLLM com a configuração certa para o interruptor da nuvem (STUDIO_NUVEM).

Com STUDIO_NUVEM=1 (e a chave da Cloudflare no .env), os modelos do chat (STUDIO_NUVEM_CHAT, padrão qwen3-vl-instruct e
deepseek-coder-v2:16b e conversas) passam a responder pelo gpt-oss-120b do gateway "heimdall" da Cloudflare (teto de gasto no gateway). O modelo
local continua na lista com o nome "<modelo>-local" e é o plano de volta: se a nuvem falhar ou o limite cortar, o LiteLLM tenta o local sozinho.
Com STUDIO_NUVEM diferente de 1, vale o litellm_config.yaml sem mudança nenhuma (como antes da migração).

O arquivo gerado (db/litellm_config_efetivo.yaml, fora do git, permissão 600) leva a chave lida do .env, por isso nunca é copiado.
O Conversas usa outro modelo da nuvem (Qwen3 30B, STUDIO_NUVEM_CONVERSAS_MODELO muda), porque o gpt-oss recusa o que o gemma local não recusa.
O gemma-4-uncensored continua disponível, só local, para quem quiser escolher à mão.

    python3 heimdall_litellm.py [opções do litellm]    gera a configuração e inicia o LiteLLM com ela
    python3 heimdall_litellm.py --so-gerar             só gera e mostra o caminho do arquivo que será usado
"""
import os
import heimdall_pastas
import sys
from pathlib import Path

import heimdall_nuvem as nuvem

AQUI = Path(__file__).resolve().parent
ORIGINAL = AQUI / "litellm_config.yaml"
EFETIVO = heimdall_pastas.db(AQUI) / "litellm_config_efetivo.yaml"
PADRAO_CHAT = "qwen3-vl-instruct,deepseek-coder-v2:16b,conversas"
# O Conversas tem modelo próprio na nuvem: o Qwen3 30B custa bem menos por token que o gpt-oss e o Mistral (confira os preços no Workers AI),
# aceita ferramentas e não recusa tanto. Outro modelo: studio env --set STUDIO_NUVEM_CONVERSAS_MODELO "workers-ai/@cf/mistralai/mistral-small-3.1-24b-instruct"
MODELO_CONVERSAS = "workers-ai/@cf/qwen/qwen3-30b-a3b-fp8"
CHAVES_EXTRA = ("STUDIO_NUVEM_CHAT", "STUDIO_NUVEM_CONVERSAS_MODELO")


def _ler_extra() -> dict:
    """STUDIO_NUVEM_CHAT do .env (o heimdall_nuvem só lê as chaves que ele conhece)."""
    out = {}
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("export "):
                ln = ln[7:]
            k, _, v = ln.partition("=")
            if k.strip() in CHAVES_EXTRA:
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    for k in CHAVES_EXTRA:
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def nomes_na_nuvem(env: dict) -> list:
    bruto = env.get("STUDIO_NUVEM_CHAT") or PADRAO_CHAT
    return [n.strip() for n in bruto.split(",") if n.strip()]


def config_para_nuvem(cfg: dict, env: dict) -> dict:
    """Devolve a configuração com os modelos escolhidos apontando para a nuvem e o local como volta. Não altera o original."""
    import copy
    novo = copy.deepcopy(cfg)
    token = env["CLOUDFLARE_API_TOKEN"]
    base = f"https://gateway.ai.cloudflare.com/v1/{env['CLOUDFLARE_ACCOUNT_ID']}/{nuvem.GATEWAY}/compat"
    modelo_padrao = env.get("STUDIO_NUVEM_MODELO") or nuvem.MODELO_PADRAO
    modelo_por_nome = {"conversas": env.get("STUDIO_NUVEM_CONVERSAS_MODELO") or MODELO_CONVERSAS}
    escolhidos = set(nomes_na_nuvem(env))
    lista, voltas = [], {}
    for item in novo.get("model_list", []):
        nome = item.get("model_name")
        if nome not in escolhidos:
            lista.append(item)
            continue
        local = copy.deepcopy(item)
        local["model_name"] = nome + "-local"
        lista.append(local)
        info = dict(item.get("model_info") or {})
        info["supports_function_calling"] = True  # o gpt-oss chama ferramentas
        lista.append({
            "model_name": nome,
            "litellm_params": {
                "model": "openai/" + modelo_por_nome.get(nome, modelo_padrao), "api_base": base, "api_key": token,
                "extra_headers": {"cf-aig-authorization": "Bearer " + token, "User-Agent": nuvem.USER_AGENT},
                "timeout": 120, "num_retries": 0,
            },
            "model_info": info,
        })
        voltas[nome] = [nome + "-local"]
    novo["model_list"] = lista
    ls = novo.setdefault("litellm_settings", {})
    ls["fallbacks"] = [{k: v} for k, v in voltas.items()]
    return novo


def preparar() -> Path:
    """Caminho da configuração a usar: o original (nuvem desligada) ou o gerado (nuvem ligada). Nunca falha: na dúvida, o original."""
    env = nuvem._env()
    env.update(_ler_extra())
    if not nuvem.ativo(env):
        _apagar_efetivo()
        return ORIGINAL
    try:
        import yaml
        cfg = yaml.safe_load(ORIGINAL.read_text(encoding="utf-8"))
        saida = config_para_nuvem(cfg, env)
        EFETIVO.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(EFETIVO, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(saida, f, allow_unicode=True, sort_keys=False)
        os.chmod(EFETIVO, 0o600)
        return EFETIVO
    except Exception as ex:  # noqa: BLE001
        print(f"[litellm] não consegui montar a configuração da nuvem ({type(ex).__name__}); usando só os modelos locais.", file=sys.stderr)
        _apagar_efetivo()
        return ORIGINAL


def _apagar_efetivo() -> None:
    try:
        EFETIVO.unlink()
    except OSError:
        pass


def main() -> None:
    args = sys.argv[1:]
    caminho = preparar()
    if args[:1] == ["--so-gerar"]:
        print(caminho)
        return
    nuvem_on = caminho == EFETIVO
    print("[litellm] chat na nuvem (" + ", ".join(nomes_na_nuvem({**nuvem._env(), **_ler_extra()})) + "), local como volta." if nuvem_on
          else "[litellm] nuvem desligada: só modelos locais.", file=sys.stderr)
    py = sys.executable or "python3"
    lit = str(Path(py).parent / "litellm")
    cmd = [lit] if os.path.exists(lit) else [py, "-m", "litellm.proxy.proxy_cli"]
    cmd += ["--config", str(caminho)] + args
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
