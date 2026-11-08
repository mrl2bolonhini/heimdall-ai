"""Testa o tool calling de cada modelo do litellm_config.yaml, um por um.

Para cada modelo ele faz duas etapas pelo LiteLLM (porta 9000):

1. CHAMADA: pergunta sobre a RAM do Mac com 3 ferramentas disponíveis e
   verifica se o modelo devolve uma chamada ESTRUTURADA (tool_calls) e escolhe
   a ferramenta certa. Chamada escrita como texto (<tool_call>...) é reprovada.
2. CICLO: executa a ferramenta de verdade, devolve o resultado ao modelo e
   verifica se a resposta final usa o número real.

Uso, na pasta do projeto, com o sistema no ar (heimdall claude up):
    python test_models_tools.py                     # todos os modelos
    python test_models_tools.py --only qwen         # só os que contêm "qwen" no nome
    python test_models_tools.py --host 100.106.3.26 # pelo IP do Tailscale

A primeira chamada de cada modelo demora, porque o Ollama precisa carregá-lo.
Ao terminar cada um, o script o descarrega da memória (use --keep-loaded para evitar).
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    import heimdall_tools as tools_module
except ImportError:
    import tools as tools_module

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
PROMPT = "Quanto da memória RAM do Mac está sendo usada agora? Use uma ferramenta para descobrir."


def _tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOLS = [
    _tool("get_system_metrics", "Retorna o uso atual de RAM, swap e CPU do Mac."),
    _tool("get_disk_usage", "Retorna o espaço total, usado e livre do disco do Mac."),
    _tool(
        "calculate_expression",
        "Calcula uma expressão matemática.",
        {"expression": {"type": "string", "description": "Expressão, por exemplo 2+2"}},
        ["expression"],
    ),
]
ALLOWED = {t["function"]["name"] for t in TOOLS}


def load_key() -> str:
    key = os.getenv("LITELLM_MASTER_KEY", "")
    env_file = BASE_DIR / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                key = line.split("=", 1)[1].strip()
    return key


def load_models():
    cfg = yaml.safe_load((BASE_DIR / "litellm_config.yaml").read_text())
    models = []
    for m in cfg["model_list"]:
        ollama_name = m["litellm_params"]["model"].split("/", 1)[1]
        models.append((m["model_name"], ollama_name))
    return models


def ollama_has_tools(ollama_name: str) -> str:
    """Pergunta ao Ollama se ele declara suporte a ferramentas para esse modelo."""
    try:
        r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": ollama_name}, timeout=20)
        r.raise_for_status()
        caps = r.json().get("capabilities")
        if caps is None:
            return "?"
        return "sim" if "tools" in caps else "não"
    except Exception:
        return "?"


def unload(ollama_name: str) -> None:
    try:
        requests.post(f"{OLLAMA_URL}/api/generate", json={"model": ollama_name, "keep_alive": 0}, timeout=30)
    except Exception:
        pass


def chat(base_url: str, key: str, model: str, messages: list, timeout: int) -> dict:
    r = requests.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0,
            "stream": False,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:250]}")
    return r.json()["choices"][0]["message"]


def mentions_number(text: str, num: str) -> bool:
    variants = {num, num.replace(".", ","), num.split(".")[0]}
    return any(re.search(rf"(?<![\d.,]){re.escape(v)}(?!\d)", text) for v in variants)


def test_model(base_url: str, key: str, name: str, ollama_name: str, timeout: int) -> dict:
    res = {
        "modelo": name,
        "tools_ollama": ollama_has_tools(ollama_name),
        "chamada": "",
        "ciclo": "-",
        "detalhe": "",
    }
    messages = [{"role": "user", "content": PROMPT}]

    # --- Etapa 1: o modelo pede a ferramenta? ---
    try:
        msg = chat(base_url, key, name, messages, timeout)
    except Exception as e:
        res["chamada"] = "ERRO"
        res["detalhe"] = str(e)
        return res

    calls = msg.get("tool_calls") or []
    content = msg.get("content") or ""
    if not calls:
        if "<tool_call>" in content or "get_system_metrics" in content:
            res["chamada"] = "TEXTO (tag no texto)"
        else:
            res["chamada"] = "SEM CHAMADA"
        res["detalhe"] = content.strip().replace("\n", " ")[:200]
        return res

    call = calls[0]
    fname = call["function"]["name"]
    res["chamada"] = "OK" if fname == "get_system_metrics" else f"OK, mas usou {fname}"

    # --- Etapa 2: executa a ferramenta e devolve o resultado ---
    raw_args = call["function"].get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except Exception:
        args = {}
    func = getattr(tools_module, fname, None)
    if fname not in ALLOWED or func is None:
        res["ciclo"] = "não testado"
        res["detalhe"] = f"ferramenta desconhecida: {fname}"
        return res
    try:
        result = func(**args)
    except Exception as e:
        result = f"Erro: {e}"

    messages.append({"role": "assistant", "content": content, "tool_calls": calls})
    messages.append({"role": "tool", "tool_call_id": call.get("id"), "name": fname, "content": result})
    try:
        final = chat(base_url, key, name, messages, timeout)
    except Exception as e:
        res["ciclo"] = "ERRO"
        res["detalhe"] = str(e)
        return res

    final_text = (final.get("content") or "").strip()
    if final.get("tool_calls") and not final_text:
        res["ciclo"] = "FALHOU (chamou outra ferramenta)"
    elif not final_text:
        res["ciclo"] = "FALHOU (resposta vazia)"
    elif fname == "get_system_metrics":
        m = re.search(r"RAM (\d+(?:\.\d+)?)%", result)
        if m and mentions_number(final_text, m.group(1)):
            res["ciclo"] = "OK"
        else:
            res["ciclo"] = "FALHOU (não usou o número)"
    else:
        res["ciclo"] = "OK (resposta dada)"
    res["detalhe"] = final_text.replace("\n", " ")[:200]
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description="Testa tool calling de todos os modelos do LiteLLM")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--only", default="", help="testa só os modelos cujo nome contém este texto")
    ap.add_argument("--timeout", type=int, default=300, help="segundos por chamada (inclui carregar o modelo)")
    ap.add_argument("--keep-loaded", action="store_true", help="não descarrega o modelo da memória depois do teste")
    args = ap.parse_args()

    key = load_key()
    if not key:
        sys.exit("LITELLM_MASTER_KEY não encontrada (.env ou variável de ambiente).")

    base_url = f"http://{args.host}:{args.port}"
    try:
        requests.get(f"{base_url}/health/readiness", timeout=10).raise_for_status()
    except Exception as e:
        sys.exit(f"LiteLLM não respondeu em {base_url}: {e}\nO sistema está no ar? (heimdall claude up)")

    models = [m for m in load_models() if args.only.lower() in m[0].lower()]
    if not models:
        sys.exit("Nenhum modelo encontrado com esse filtro.")

    results = []
    for i, (name, ollama_name) in enumerate(models, 1):
        print(f"[{i}/{len(models)}] {name} ...", flush=True)
        start = time.time()
        res = test_model(base_url, key, name, ollama_name, args.timeout)
        res["segundos"] = round(time.time() - start)
        print(f"    chamada: {res['chamada']} | ciclo: {res['ciclo']} ({res['segundos']}s)", flush=True)
        if res["detalhe"]:
            print(f"    detalhe: {res['detalhe']}", flush=True)
        results.append(res)
        if not args.keep_loaded:
            unload(ollama_name)

    print("\n" + "=" * 100)
    print(f"{'MODELO':34}{'TOOLS (OLLAMA)':16}{'CHAMADA':28}CICLO")
    print("-" * 100)
    for r in results:
        print(f"{r['modelo'][:33]:34}{r['tools_ollama']:16}{r['chamada'][:27]:28}{r['ciclo']}")
    print("=" * 100)

    good = [r["modelo"] for r in results if r["chamada"] == "OK" and r["ciclo"] == "OK"]
    partial = [r["modelo"] for r in results if r["chamada"].startswith("OK,") and r["ciclo"].startswith("OK")]
    bad = [r["modelo"] for r in results if r["modelo"] not in good and r["modelo"] not in partial]
    print(f"\nFuncionam com ferramentas: {', '.join(good) if good else 'nenhum'}")
    if partial:
        print(f"Chamam ferramentas, mas escolheram a errada: {', '.join(partial)}")
    if bad:
        print(f"Não funcionam: {', '.join(bad)}")
        print(
            "\nComo ler:\n"
            "- TEXTO ou SEM CHAMADA: o modelo não faz tool calling nativo neste template do Ollama.\n"
            "  Use outro modelo ou outro template para ferramentas.\n"
            "- TOOLS (OLLAMA) = não: o Ollama já declara que o modelo não suporta ferramentas.\n"
            "- ERRO: veja o detalhe acima (modelo inexistente, memória insuficiente, tempo esgotado).\n"
            "- CICLO FALHOU depois de CHAMADA OK: o modelo pede a ferramenta, mas se perde ao ler o resultado."
        )


if __name__ == "__main__":
    main()
