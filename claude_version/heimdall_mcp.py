"""Servidor MCP unificado do Heimdall (HTTP, porta 8000, endpoint /mcp).

Registra todas as ferramentas do módulo de ferramentas (heimdall_tools.py ou
tools.py). O LiteLLM se conecta aqui e as repassa aos clientes (open-client)
pelo endpoint /mcp da porta 9000.
"""
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Aceita os dois nomes possíveis do módulo de ferramentas.
try:
    import heimdall_tools as tools_module
except ImportError:
    import tools as tools_module

mcp = FastMCP("Heimdall")

for _fn in tools_module.ALL_TOOLS:
    mcp.tool()(_fn)


# Rotas de saúde mantidas do antigo proxy_gateway.py, para quem as consultava.
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "database": "connected"})


for _path in ("/health", "/health/readiness", "/v1/health/readiness"):
    mcp.custom_route(_path, methods=["GET"])(health)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")
