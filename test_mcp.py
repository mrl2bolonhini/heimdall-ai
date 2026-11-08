"""Testa o MCP do Heimdall em dois pontos:

1. direto em cada grupo (8000 = ferramentas do Mac, 8001 = ferramentas públicas), sem autenticação;
2. pelo LiteLLM (porta 9000), com a chave mestra do .env, que junta os dois grupos e a AWS.

Uso, dentro da pasta do projeto:
    venv/bin/python test_mcp.py                 # testa em localhost
    venv/bin/python test_mcp.py 100.106.3.26    # testa pelo IP do Tailscale
"""
import asyncio
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost"


def load_key() -> str:
    key = os.getenv("LITELLM_MASTER_KEY", "")
    env_file = Path(__file__).with_name(".env")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                key = line.split("=", 1)[1].strip()
    return key


async def check(label: str, url: str, headers: dict | None = None, probe: str = "get_system_metrics") -> None:
    print(f"\n=== {label}: {url}")
    try:
        transport = StreamableHttpTransport(url, headers=headers or {})
        async with Client(transport, timeout=20) as client:
            tools = await client.list_tools()
            names = sorted(t.name for t in tools)
            print(f"Ferramentas listadas: {len(names)}")
            for n in names:
                print(f"  - {n}")

            target = next((n for n in names if n.endswith(probe)), None)
            if target is None:
                print(f"{probe} não apareceu, não deu para testar uma chamada.")
                return
            result = await client.call_tool(target, {})
            print(f"Chamada de {target}: {result.content[0].text}")
    except Exception as e:
        print(f"FALHOU: {type(e).__name__}: {e}")


async def main() -> None:
    await check("Grupo do Mac (admin)", f"http://{HOST}:8000/mcp")
    await check("Grupo público", f"http://{HOST}:8001/mcp", probe="get_system_timestamp")

    key = load_key()
    if not key:
        print("\nLITELLM_MASTER_KEY não encontrada (.env ou variável de ambiente); pulei o teste do LiteLLM.")
        return
    headers = {"x-litellm-api-key": f"Bearer {key}", "Authorization": f"Bearer {key}"}
    await check("Via LiteLLM", f"http://{HOST}:9000/mcp", headers)

    print(
        "\nComo ler o resultado:\n"
        "- Esperado: 8000 com 10 ferramentas, 8001 com 9, e o LiteLLM com as duas listas (19) mais as da AWS.\n"
        "- 8000 e 8001 certas e 9000 com menos (ou falha): o problema está no LiteLLM (config, chave ou permissões).\n"
        "- Tudo certo aqui, mas o app não vê: o problema está em como o app consulta.\n"
        "- 8000 ou 8001 falhou: o servidor não subiu; veja mcp_debug.log e mcp_public_debug.log."
    )


if __name__ == "__main__":
    asyncio.run(main())
