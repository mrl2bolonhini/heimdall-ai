"""Servidor MCP do Heimdall (HTTP, endpoint /mcp), em grupos de ferramentas.

Uso:
    python heimdall_mcp.py --group mac      # ferramentas do Mac (admin), porta 8000
    python heimdall_mcp.py --group public   # ferramentas seguras para convidados, porta 8001
    python heimdall_mcp.py                  # todas juntas, porta 8000 (comportamento antigo)

O start_heimdall.sh sobe os grupos "mac" e "public" em dois processos. O LiteLLM
se conecta aos dois e os repassa ao open-client pela porta 9000. O Open WebUI
dos convidados deve se conectar só ao grupo "public" (porta 8001).
"""
import argparse

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Aceita os dois nomes possíveis do módulo de ferramentas.
try:
    import heimdall_tools as tools_module
except ImportError:
    import tools as tools_module

GROUPS = {
    # nome: (título do servidor, porta, função que devolve a lista de ferramentas)
    "all": ("Heimdall", 8000, lambda m: m.ALL_TOOLS),
    "mac": ("Heimdall Mac", 8000, lambda m: m.MAC_TOOLS),
    "public": ("Heimdall Público", 8001, lambda m: m.PUBLIC_TOOLS),
}

parser = argparse.ArgumentParser(description="Servidor MCP do Heimdall")
parser.add_argument("--group", choices=sorted(GROUPS), default="all")
args = parser.parse_args()

title, port, pick = GROUPS[args.group]
mcp = FastMCP(title)

for _fn in pick(tools_module):
    mcp.tool()(_fn)


# Rotas de saúde mantidas do antigo proxy_gateway.py, para quem as consultava.
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "database": "connected"})


for _path in ("/health", "/health/readiness", "/v1/health/readiness"):
    mcp.custom_route(_path, methods=["GET"])(health)


# Métricas do Mac em JSON (RAM, swap, CPU, disco), usadas pelo fluxo de alerta do n8n.
# Só no grupo do Mac; não expõe nada além de números de uso.
async def metricas(request: Request) -> JSONResponse:
    import asyncio

    import psutil

    def coletar() -> dict:
        gb = 1024 ** 3
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disco = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / gb, 2),
            "ram_total_gb": round(ram.total / gb, 2),
            "swap_used_gb": round(swap.used / gb, 2),
            "disk_percent": disco.percent,
            "disk_free_gb": round(disco.free / gb, 2),
        }

    return JSONResponse(await asyncio.to_thread(coletar))


if args.group in ("mac", "all"):
    mcp.custom_route("/metricas", methods=["GET"])(metricas)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
