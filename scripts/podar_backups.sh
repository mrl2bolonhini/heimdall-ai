#!/bin/bash
# Mantém só as cópias mais recentes de cada tipo na pasta backups/ (cada cópia do Open WebUI tem cerca de 1 GB).
# Uso: bash scripts/podar_backups.sh [quantas_manter]     (padrão 3, ou HEIMDALL_BACKUPS_MANTER no .env)
# Tipos: open-webui (atualização), open-webui-senha, open-webui-email, open-webui-excluir, n8n_data e qdrant (também o nome antigo qdrant_storage).
# Só mexe em arquivos .tgz com esses nomes; nunca em outras coisas da pasta.
cd "$(dirname "$0")/.." || exit 1
[ -d backups ] || exit 0
N="${1:-}"
if [ -z "$N" ] && [ -f .env ]; then N="$(grep '^HEIMDALL_BACKUPS_MANTER=' .env | head -1 | cut -d= -f2- | tr -d "\"'")"; fi
case "$N" in ''|*[!0-9]*) N=3 ;; esac
[ "$N" -lt 1 ] && N=1
REMOVIDOS=0
for PADRAO in "open-webui-[0-9]*" "open-webui-senha-*" "open-webui-email-*" "open-webui-excluir-*" "n8n_data-*" "qdrant-*" "qdrant_storage-*"; do
    # os nomes levam a data e a hora, então a ordem alfabética é a ordem do tempo
    for ARQ in $(ls -1 backups/$PADRAO.tgz 2>/dev/null | sort -r | tail -n +$((N + 1))); do
        rm -f "$ARQ" && REMOVIDOS=$((REMOVIDOS + 1))
    done
done
[ "$REMOVIDOS" -gt 0 ] && echo "     Backups antigos removidos: $REMOVIDOS (ficam os $N mais recentes de cada tipo)."
exit 0
