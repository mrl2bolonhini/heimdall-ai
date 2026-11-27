#!/bin/bash
# Faz o Docker Desktop parar de abrir o painel (Dashboard) quando inicia. Com o StudioLibre abrindo o Docker em segundo plano, nada mais aparece na frente.
# Só mexe numa chave da configuração do Docker, com cópia de segurança ao lado do arquivo. Feche o Docker Desktop antes (ele regrava o arquivo ao sair).
# Uso: bash scripts/silenciar_docker.sh [--desfazer]
PASTA="${DOCKER_CONFIG_PASTA:-$HOME/Library/Group Containers/group.com.docker}"
DESFAZER=0
[ "$1" = "--desfazer" ] && DESFAZER=1
if [ -f "$PASTA/settings-store.json" ]; then ARQ="$PASTA/settings-store.json"; CHAVE="OpenUIOnStartupDisabled"
elif [ -f "$PASTA/settings.json" ]; then ARQ="$PASTA/settings.json"; CHAVE="openUIOnStartupDisabled"
else echo "Não achei a configuração do Docker Desktop em $PASTA. Abra o Docker uma vez e tente de novo."; exit 1; fi
if [ -z "$DOCKER_CONFIG_PASTA" ] && pgrep -x "Docker Desktop" >/dev/null 2>&1; then
  echo "O Docker Desktop está aberto. Feche-o (menu do Docker, Quit Docker Desktop), rode este comando e abra de novo com: studio up"; exit 1
fi
cp "$ARQ" "$ARQ.heimdall-bak" || exit 1
python3 - "$ARQ" "$CHAVE" "$DESFAZER" <<'PYEOF' || { echo "Não consegui alterar. A cópia está em $ARQ.heimdall-bak"; exit 1; }
import json, sys
arq, chave, desfazer = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
d = json.load(open(arq, encoding="utf-8"))
d[chave] = not desfazer
json.dump(d, open(arq, "w", encoding="utf-8"), indent=2)
PYEOF
if [ "$DESFAZER" = 1 ]; then echo "Pronto: o Docker volta a abrir o painel ao iniciar."
else echo "Pronto: o Docker Desktop não abrirá mais o painel ao iniciar. Cópia da configuração: $ARQ.heimdall-bak"; fi
