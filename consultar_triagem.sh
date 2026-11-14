#!/bin/bash
# Mostra o estado da triagem no agente do Mac, lendo o token direto do .env.
cd "$(dirname "$0")" || exit 1
TOKEN=$(grep '^HEIMDALL_AGENTE_TOKEN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
curl -s -H "X-Heimdall-Token: $TOKEN" http://127.0.0.1:8003/triagem/estado
echo
