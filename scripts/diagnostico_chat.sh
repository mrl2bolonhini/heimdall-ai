#!/bin/bash
# Mostra o que o servidor de dados (porta 8004) e o Open WebUI registraram nas ultimas chamadas de ferramenta.
cd "$(dirname "$0")/.." || exit 1
echo "=== Servidor MCP de dados (ultimas 25 linhas) ==="
tail -n 25 mcp_dados_debug.log 2>/dev/null || echo "sem log"
echo
echo "=== Open WebUI: linhas recentes sobre ferramentas ou erros ==="
docker logs --since 30m open-webui 2>&1 | grep -i "tool\|mcp\|error\|timeout" | tail -n 25
