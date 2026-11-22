#!/usr/bin/env python3
"""Confere a configuração do LiteLLM com o interruptor da nuvem (heimdall_litellm.py). Sem rede e sem LiteLLM instalado."""
import os
import stat
import sys
import tempfile
from pathlib import Path

import yaml

import heimdall_litellm as hl

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


ENV = {"HEIMDALL_NUVEM": "1", "CLOUDFLARE_API_TOKEN": "segredo-de-teste", "CLOUDFLARE_ACCOUNT_ID": "a" * 32}
orig = yaml.safe_load(hl.ORIGINAL.read_text(encoding="utf-8"))
nomes_orig = [m["model_name"] for m in orig["model_list"]]
novo = hl.config_para_nuvem(orig, ENV)
por_nome = {m["model_name"]: m for m in novo["model_list"]}

confere("o original não foi alterado", [m["model_name"] for m in orig["model_list"]] == nomes_orig and "fallbacks" not in orig.get("litellm_settings", {}))
for n in ("qwen3-vl-instruct", "deepseek-coder-v2:16b"):
    p = por_nome[n]["litellm_params"]
    confere(n + " vai para o gateway da nuvem", p["model"] == "openai/workers-ai/@cf/openai/gpt-oss-120b" and p["api_base"] == "https://gateway.ai.cloudflare.com/v1/" + "a" * 32 + "/heimdall/compat", str(p))
    confere(n + " leva as duas autorizações e o User-Agent", p["api_key"] == "segredo-de-teste" and p["extra_headers"]["cf-aig-authorization"] == "Bearer segredo-de-teste" and p["extra_headers"]["User-Agent"] == "heimdall-ai/1.0")
    confere(n + " mantém o local como " + n + "-local", n + "-local" in por_nome and por_nome[n + "-local"]["litellm_params"]["model"].startswith("ollama_chat/"))
confere("o Conversas (gemma-4-uncensored) continua local por padrão", por_nome["gemma-4-uncensored"]["litellm_params"]["model"].startswith("ollama_chat/") and "gemma-4-uncensored-local" not in por_nome)
confere("os modelos de segurança e de resumo continuam locais", all(por_nome[n]["litellm_params"]["model"].startswith("ollama_chat/") for n in ("dolphin3-cyber-8b", "gemma3-4b", "llama-3.1-8b")))
confere("a nuvem volta ao local se falhar", {"qwen3-vl-instruct": ["qwen3-vl-instruct-local"]} in novo["litellm_settings"]["fallbacks"] and {"deepseek-coder-v2:16b": ["deepseek-coder-v2:16b-local"]} in novo["litellm_settings"]["fallbacks"])
confere("o gpt-oss declara ferramentas", por_nome["qwen3-vl-instruct"]["model_info"]["supports_function_calling"] is True)
confere("servidores MCP e pesquisa seguem iguais", novo["mcp_servers"] == orig["mcp_servers"] and novo["search_tools"] == orig["search_tools"] and novo["general_settings"] == orig["general_settings"])
confere("drop_params continua", novo["litellm_settings"]["drop_params"] is True)

todos = hl.config_para_nuvem(orig, {**ENV, "HEIMDALL_NUVEM_CHAT": "gemma-4-uncensored"})
confere("HEIMDALL_NUVEM_CHAT escolhe os modelos", {m["model_name"]: m for m in todos["model_list"]}["gemma-4-uncensored"]["litellm_params"]["model"].startswith("openai/")
        and {m["model_name"]: m for m in todos["model_list"]}["qwen3-vl-instruct"]["litellm_params"]["model"].startswith("ollama_chat/"))

# interruptor: desligada devolve o original e apaga o arquivo gerado; ligada grava com permissão 600
with tempfile.TemporaryDirectory() as d:
    hl.EFETIVO = Path(d) / "banco" / "efetivo.yaml"
    hl.nuvem._env = lambda: dict(ENV, HEIMDALL_NUVEM="0")
    hl._ler_extra = lambda: {}
    confere("desligada usa o litellm_config.yaml", hl.preparar() == hl.ORIGINAL and not hl.EFETIVO.exists())
    hl.nuvem._env = lambda: dict(ENV)
    c = hl.preparar()
    confere("ligada usa o arquivo gerado", c == hl.EFETIVO and c.exists())
    confere("o arquivo gerado tem permissão 600", stat.S_IMODE(os.stat(c).st_mode) == 0o600, oct(os.stat(c).st_mode))
    confere("o arquivo gerado é YAML válido com o fallback", "fallbacks" in yaml.safe_load(c.read_text(encoding="utf-8"))["litellm_settings"])
    hl.nuvem._env = lambda: dict(ENV, HEIMDALL_NUVEM="0")
    confere("desligar de novo apaga o arquivo com a chave", hl.preparar() == hl.ORIGINAL and not hl.EFETIVO.exists())
    hl.nuvem._env = lambda: {"HEIMDALL_NUVEM": "1"}
    confere("sem a chave da Cloudflare volta ao local", hl.preparar() == hl.ORIGINAL)

sys.exit(1 if falhas else 0)
