#!/bin/bash
# Confere se o servidor MCP de dados (porta 8004) esta no ar e se o Open WebUI (no Docker) consegue alcança-lo.
if nc -z 127.0.0.1 8004 > /dev/null 2>&1; then
  echo "1. O servidor MCP de dados esta ouvindo na porta 8004 do Mac."
else
  echo "1. PROBLEMA: nada ouvindo na porta 8004. Reinicie o sistema (start_studio.sh) e veja mcp_dados_debug.log."
  exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -qx open-webui; then
  echo "2. PROBLEMA: o contêiner open-webui nao esta rodando. Suba o sistema com --webui."
  exit 1
fi
RES=$(docker exec open-webui python3 -c "
import urllib.request, urllib.error
try:
    r = urllib.request.urlopen('http://host.docker.internal:8004/mcp', timeout=8)
    print('HTTP', r.status)
except urllib.error.HTTPError as e:
    print('HTTP', e.code)
except Exception as e:
    print('ERRO', type(e).__name__, e)
" 2>&1)
echo "2. Resposta vista de dentro do Open WebUI: $RES"
case "$RES" in
  HTTP*) echo "O Open WebUI alcanca o servidor. Pode ligar a ferramenta em Configuracoes." ;;
  *) echo "O Open WebUI nao alcanca o servidor. Me mande esta saida." ;;
esac
