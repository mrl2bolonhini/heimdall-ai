#!/bin/bash
# Grava no .env o texto que esta na area de transferencia (copiado com Command+C), sem mostrá-lo na tela.
# Uso: bash scripts/guardar_no_env.sh NOME_DA_VARIAVEL            (le a area de transferencia; para segredos)
#      bash scripts/guardar_no_env.sh NOME_DO_ACCESS 'valor'       (so para as variaveis HEIMDALL_CFACCESS_*, que nao sao segredos)
cd "$(dirname "$0")/.." || exit 1
NOME="$1"
case "$NOME" in
  HEIMDALL_R2_KEY_ID|HEIMDALL_R2_SECRET|HEIMDALL_R2_ENDPOINT|HEIMDALL_R2_BUCKET|HEIMDALL_BACKUP_DESTINO|HEIMDALL_CLOUDFLARE_ACCESS_TOKEN|HEIMDALL_NOTION_TOKEN|HEIMDALL_NOTION_DB_IDEIAS|HEIMDALL_NOTION_DB_CONTATOS|HEIMDALL_NOTION_DB_ENDERECOS|HEIMDALL_WEBUI_API_KEY) ;;
  HEIMDALL_CFACCESS_EQUIPE|HEIMDALL_CFACCESS_AUD|HEIMDALL_CFACCESS_EMAILS|HEIMDALL_CFACCESS_CONVIDADOS) ;;
  HEIMDALL_NUVEM|HEIMDALL_CAIXA|HEIMDALL_LEARN|HEIMDALL_LEARN_AGENDA|HEIMDALL_LEARN_NOTIFICAR|HEIMDALL_DONO_NOME) ;;
  *) echo "Nome de variavel nao permitido: $NOME"; exit 1 ;;
esac
if [ -n "$2" ]; then
  # Valor passado na linha de comando: so para o Access (equipe, AUD e e-mails nao sao segredos).
  case "$NOME" in
    HEIMDALL_CFACCESS_*|HEIMDALL_NUVEM|HEIMDALL_CAIXA|HEIMDALL_LEARN|HEIMDALL_LEARN_AGENDA|HEIMDALL_LEARN_NOTIFICAR|HEIMDALL_DONO_NOME) ;;
    *) echo "Segredos nao se passam na linha de comando; copie com Command+C e rode sem o valor."; exit 1 ;;
  esac
  VALOR=$(printf '%s' "$2" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  case "$NOME" in
    HEIMDALL_CFACCESS_EQUIPE) PADRAO='^[a-z0-9][a-z0-9-]{0,62}(\.cloudflareaccess\.com)?$' ;;
    HEIMDALL_NUVEM|HEIMDALL_CAIXA|HEIMDALL_LEARN|HEIMDALL_LEARN_AGENDA|HEIMDALL_LEARN_NOTIFICAR) PADRAO='^[01]$' ;;
    HEIMDALL_DONO_NOME) PADRAO='^[[:alpha:]._-]{1,40}$' ;;
    HEIMDALL_CFACCESS_AUD) PADRAO='^[A-Za-z0-9,]+$' ;;
    HEIMDALL_CFACCESS_EMAILS) PADRAO='^[A-Za-z0-9@._+,-]+$' ;;
    *) PADRAO='^[A-Za-z0-9@._+,;=-]+$' ;;
  esac
  if ! printf '%s' "$VALOR" | grep -Eq "$PADRAO"; then echo "Valor com formato inesperado para $NOME; nada foi gravado."; exit 1; fi
else
  VALOR=$(pbpaste | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
fi
if [ -z "$VALOR" ]; then echo "A area de transferencia esta vazia."; exit 1; fi
case "$VALOR" in *"'"*) echo "O texto contem aspas simples; nada foi gravado."; exit 1 ;; esac
umask 077
grep -v "^${NOME}=" .env > .env.novo
echo "${NOME}='${VALOR}'" >> .env.novo
mv .env.novo .env
chmod 600 .env
echo "${NOME} gravado (${#VALOR} caracteres)."
