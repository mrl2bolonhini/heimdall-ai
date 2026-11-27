#!/usr/bin/env bash
# Liga o Trading e o Hub no .env, acrescenta os dois identificadores do Cloudflare Access e, se você quiser, grava o token da brapi.
# Não mostra segredos na tela e faz cópia do .env em .env.bak antes de mudar.
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Não encontrei o .env nesta pasta."; exit 1; }
cp .env .env.bak
python3 - <<'PY'
import re
AUDS = ["c403d80d37f2c24ded70d49372beee0041ce474de916d4f4701a41bc6b97dcf4", "a176657c084cb84b2c82eb4415648daef5c066785ac7f1caf992244fe2abb149"]
linhas = open(".env", encoding="utf-8").read().splitlines()
def definir(nome, valor):
    for i, l in enumerate(linhas):
        if l.startswith(nome + "="):
            linhas[i] = f"{nome}={valor}"
            return
    linhas.append(f"{nome}={valor}")
definir("HEIMDALL_TRADING", "1")
definir("HEIMDALL_MEMORY", "1")
atual = next((l.split("=", 1)[1].strip().strip("\"'") for l in linhas if l.startswith("HEIMDALL_CFACCESS_AUD=")), "")
lista = [x for x in atual.split(",") if x]
for a in AUDS:
    if a not in lista:
        lista.append(a)
definir("HEIMDALL_CFACCESS_AUD", ",".join(lista))
open(".env", "w", encoding="utf-8").write("\n".join(linhas) + "\n")
print("Trading e Hub ligados e identificadores do Access gravados.")
PY
read -r -s -p "Token da brapi (opcional; Enter para pular): " T; echo
if [ -n "$T" ]; then
    grep -v '^HEIMDALL_TRADING_BRAPI_TOKEN=' .env > .env.tmp && mv .env.tmp .env
    echo "HEIMDALL_TRADING_BRAPI_TOKEN=$T" >> .env
    echo "Token da brapi gravado."
fi
unset T
echo "Pronto. Rode: studio restart"
