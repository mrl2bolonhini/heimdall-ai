#!/usr/bin/env bash
# Toca no Mac o áudio de estudo mais recente (ou os N mais recentes, em sequência).
#   bash ouvir_estudo.sh        toca o mais recente
#   bash ouvir_estudo.sh 3      toca os 3 mais recentes, um depois do outro
#   bash ouvir_estudo.sh --lista  só mostra os 10 mais recentes
# Para parar: Control+C.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
COFRE="${HEIMDALL_VAULT_DIR:-./cerebro}"
LISTA="$(ls -t "$COFRE"/*/audio/*.m4a 2>/dev/null)"
[ -n "$LISTA" ] || { echo "Nenhum áudio de estudo encontrado em $COFRE/<tema>/audio/." >&2; exit 1; }
if [ "${1:-}" = "--lista" ]; then echo "$LISTA" | head -10; exit 0; fi
N="${1:-1}"
[[ "$N" =~ ^[0-9]+$ ]] || { echo "Use um número, por exemplo: bash ouvir_estudo.sh 3" >&2; exit 1; }
echo "$LISTA" | head -n "$N" | while IFS= read -r f; do
    echo "Tocando: $f"
    afplay "$f"
done
