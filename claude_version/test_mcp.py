"""Testa o MCP do Heimdall em dois pontos:

1. direto no servidor (porta 8000), sem autenticação;
2. pelo LiteLLM (porta 9000), com a chave mestra do .env.

Uso, dentro da pasta do projeto:
    venv/bin/python test.py                 # testa em localhost
    venv/bin/python test_mcp.py 100.106.3.26    # testa pelo IP do Tailscale
"""
import asyncio
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost"
EXPECTED = 13


def load_key() -> str:
    key = os.getenv("LITELLM_MASTER_KEY", "")
    env_file = Path(__file__).with_name(".env")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                key = line.split("=", 1)[1].strip()
    return key


async def check(label: str, url: str, headers: dict | None = None) -> None:
    print(f"\n=== {label}: {url}")
    try:
        transport = StreamableHttpTransport(url, headers=headers or {})
        async with Client(transport, timeout=20) as client:
            tools = await client.list_tools()
            names = sorted(t.name for t in tools)
            print(f"Ferramentas listadas: {len(names)} (esperado {EXPECTED})")
            for n in names:
                print(f"  - {n}")

            target = next((n for n in names if n.endswith("get_system_metrics")), None)
            if target is None:
                print("get_system_metrics não apareceu, não deu para testar uma chamada.")
                return
            result = await client.call_tool(target, {})
            print(f"Chamada de {target}: {result.content[0].text}")
    except Exception as e:
        print(f"FALHOU: {type(e).__name__}: {e}")


async def main() -> None:
    await check("Direto no servidor MCP", f"http://{HOST}:8000/mcp")

    key = load_key()
    if not key:
        print("\nLITELLM_MASTER_KEY não encontrada (.env ou variável de ambiente); pulei o teste do LiteLLM.")
        return
    headers = {"x-litellm-api-key": f"Bearer {key}", "Authorization": f"Bearer {key}"}
    await check("Via LiteLLM", f"http://{HOST}:9000/mcp", headers)

    print(
        "\nComo ler o resultado:\n"
        "- 8000 com 13 e 9000 com menos (ou falha): o problema está no LiteLLM (config, chave ou permissões).\n"
        "- As duas com 13: o MCP está certo e o problema está em como o app consulta.\n"
        "- 8000 falhou: o mcp.py não subiu; veja mcp_debug.log."
    )


if __name__ == "__main__":
    asyncio.run(main())
