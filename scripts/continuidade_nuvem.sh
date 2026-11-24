#!/usr/bin/env bash
# Implanta, desliga e configura a continuidade do Heimdall na Cloudflare (Worker de entrada + contêiner). Lê os segredos do .env; nunca os imprime.
# Uso: ./scripts/continuidade_nuvem.sh segredos|implantar|desligar|ligar
#   segredos   envia ao Worker os segredos que o contêiner usa (senha da cópia, R2, login), lidos do .env
#   implantar  implanta o Worker e depois envia os segredos; só roda se já existir bloqueio de gasto em Workers e em Durable Objects (regra do projeto) e se a cópia dos bancos estiver no R2
#   desligar   interruptor: reimplanta com CONTINUIDADE=0 (o Worker só repassa ao Mac; o contêiner nunca liga). Os dados no R2 ficam.
#   ligar      reimplanta com CONTINUIDADE=1
cd "$(dirname "$0")/.."
CONFIG=wrangler.jsonc   # relativo à pasta cloudflare/continuity, onde o Wrangler roda (assim ele não lê o .env da raiz, que tem o CLOUDFLARE_API_TOKEN restrito)
NOMES="HEIMDALL_CONTINUIDADE_SENHA HEIMDALL_R2_ENDPOINT HEIMDALL_R2_BUCKET HEIMDALL_R2_KEY_ID HEIMDALL_R2_SECRET HEIMDALL_CLOUD_SENHA_HASH HEIMDALL_CLOUD_TOTP_SEGREDO HEIMDALL_CLOUD_SESSAO_HORAS HEIMDALL_CFACCESS_AUD HEIMDALL_CFACCESS_EMAILS HEIMDALL_CFACCESS_EQUIPE HEIMDALL_CFACCESS_CONVIDADOS HEIMDALL_CF_LEITURA_TOKEN CLOUDFLARE_ACCOUNT_ID"
lerenv() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//"; }
PY=venv/bin/python; [ -x "$PY" ] || PY=python3   # o mesmo Python do Heimdall (tem boto3 e cryptography)
# O Wrangler usa o login da sua conta (npx wrangler login). O CLOUDFLARE_API_TOKEN do shell é um token restrito (faturamento, análises) e não tem permissão de Workers, por isso é ignorado aqui.
# Quem preferir um token próprio para implantar: HEIMDALL_WRANGLER_USAR_TOKEN=1 mantém o do shell.
wr() { if [ "$HEIMDALL_WRANGLER_USAR_TOKEN" = "1" ]; then ( cd cloudflare/continuity && npx --yes wrangler "$@" ); else ( cd cloudflare/continuity && env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_API_KEY npx --yes wrangler "$@" ); fi; }
logado() { wr whoami 2>&1 | grep -qiE "not authenticated|not logged in" && { echo "O Wrangler não está logado. Rode: (cd ~ && env -u CLOUDFLARE_API_TOKEN npx wrangler login) (abre o navegador para você autorizar) e tente de novo."; return 1; }; return 0; }

segredos() {
  local n v enviados=0
  for n in $NOMES; do
    v="$(lerenv "$n")"
    [ -n "$v" ] || { echo "pulado (não está no .env): $n"; continue; }
    if printf '%s' "$v" | wr secret put "$n" --config "$CONFIG" >/dev/null 2>"${TMPDIR:-/tmp}/heimdall-wrangler.err"; then
      echo "enviado: $n"; enviados=$((enviados+1))
    else
      echo "Não consegui gravar o segredo $n."
      echo "Se o Worker ainda não foi implantado, rode antes: heimdall continuity --deploy (ele implanta e depois envia os segredos)."
      echo "Confira também o login do Wrangler: npx wrangler whoami (se não estiver logado: npx wrangler login). Detalhes em: ${TMPDIR:-/tmp}/heimdall-wrangler.err"
      return 1
    fi
  done
  echo "$enviados segredo(s) enviados ao Worker."
}

trava() {
  # Regra do projeto: nenhuma fase liga sem limite de gasto. Confere se há bloqueio de uso em Workers e em Durable Objects.
  local lista; lista="$(./scripts/limites_gasto_cloudflare.sh --ver 2>&1)"
  for p in workers durable_objects; do
    echo "$lista" | grep -q "$p usage_block" || { echo "Recusado: falta o bloqueio de gasto (usage_block) em $p. Rode ./scripts/limites_gasto_cloudflare.sh antes."; return 1; }
  done
  "$PY" heimdall_continuidade.py status >/dev/null 2>&1 || { echo "Recusado: não achei a cópia dos bancos no R2. Rode: heimdall continuity --send"; return 1; }
}

case "$1" in
  segredos) logado || exit 1; segredos ;;
  implantar) trava || exit 1; logado || exit 1; wr deploy --config "$CONFIG" && segredos ;;   # primeiro o Worker (os segredos só podem ser gravados em um Worker que já existe)
  desligar) logado || exit 1; wr deploy --config "$CONFIG" --var CONTINUIDADE:0 ;;
  ligar) trava || exit 1; logado || exit 1; wr deploy --config "$CONFIG" --var CONTINUIDADE:1 ;;
  *) sed -n 2,8p "$0"; exit 2 ;;
esac
