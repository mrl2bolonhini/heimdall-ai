#!/bin/bash
# Testa a gravação em subpastas do app Notas: cria a nota "Teste de subpastas" em Heimdall-ai/Saúde.
# Rode na pasta do projeto, com o agente do Mac no ar. Depois apague a nota à mão, se quiser.
cd "$(dirname "$0")" || exit 1
TOKEN=$(grep '^HEIMDALL_AGENTE_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d "\"'")
[ -z "$TOKEN" ] && { echo "Não achei HEIMDALL_AGENTE_TOKEN no .env."; exit 1; }
for PASTA in "Saúde" "Digest" "geral"; do
  echo "== pasta: $PASTA"
  python3 - "$PASTA" "$TOKEN" <<'P'
import json, sys, urllib.request
pasta, token = sys.argv[1], sys.argv[2]
req = urllib.request.Request("http://127.0.0.1:8003/notas/gravar",
    data=json.dumps({"pasta": pasta, "titulo": "Teste de subpastas", "markdown": "Nota de teste das subpastas. Pode apagar."}).encode(),
    headers={"X-Heimdall-Token": token, "Content-Type": "application/json"})
try:
    print(urllib.request.urlopen(req, timeout=120).read().decode())
except Exception as e:
    print("ERRO:", getattr(e, "read", lambda: b"")().decode() or e)
P
done
echo "Agora abra o Notas: devem existir Heimdall-ai > Saúde, Heimdall-ai > Digest e Heimdall-ai > Estudos > geral."
