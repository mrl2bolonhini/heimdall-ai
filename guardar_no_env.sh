#!/bin/bash
# Grava no .env o texto que esta na area de transferencia (copiado com Command+C), sem mostrá-lo na tela.
# Uso: bash guardar_no_env.sh NOME_DA_VARIAVEL
cd "$(dirname "$0")" || exit 1
NOME="$1"
case "$NOME" in
  HEIMDALL_R2_KEY_ID|HEIMDALL_R2_SECRET|HEIMDALL_R2_ENDPOINT|HEIMDALL_R2_BUCKET|HEIMDALL_BACKUP_DESTINO) ;;
  *) echo "Nome de variavel nao permitido: $NOME"; exit 1 ;;
esac
VALOR=$(pbpaste | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
if [ -z "$VALOR" ]; then echo "A area de transferencia esta vazia."; exit 1; fi
case "$VALOR" in *"'"*) echo "O texto contem aspas simples; nada foi gravado."; exit 1 ;; esac
umask 077
grep -v "^${NOME}=" .env > .env.novo
echo "${NOME}='${VALOR}'" >> .env.novo
mv .env.novo .env
chmod 600 .env
echo "${NOME} gravado (${#VALOR} caracteres)."
