#!/usr/bin/env bash
# Liga um repositório git local ao GitOps do Heimdall: instala o gancho pre-push, que avisa o n8n a cada git push.
#
# Uso:  bash instalar_hook_gitops.sh /caminho/do/repositorio
#       bash instalar_hook_gitops.sh --remover /caminho/do/repositorio
#
# O gancho roda em segundo plano, não atrasa nem bloqueia o push, e nunca faz o push falhar.
# Ele manda ao n8n só três coisas: dono/repositório, nome da branch e o hash do commit. O n8n busca o
# diff no próprio GitHub depois que o push termina. Só repositórios do GitHub são tratados.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail() { echo "Erro: $*" >&2; exit 1; }

REMOVER=0
if [ "$1" = "--remover" ]; then REMOVER=1; shift; fi
REPO_DIR="$1"
[ -n "$REPO_DIR" ] || fail "informe a pasta do repositório. Exemplo: bash instalar_hook_gitops.sh ~/projetos/meu-app"
REPO_DIR="$(cd "$REPO_DIR" 2>/dev/null && pwd)" || fail "a pasta não existe."
git -C "$REPO_DIR" rev-parse --git-dir > /dev/null 2>&1 || fail "esta pasta não é um repositório git."
HOOKS_DIR="$(cd "$REPO_DIR" && cd "$(git rev-parse --git-path hooks)" 2>/dev/null && pwd)" || fail "não achei a pasta de ganchos do repositório."
HOOK="$HOOKS_DIR/pre-push"
MARCA="# heimdall-gitops"

if [ "$REMOVER" = "1" ]; then
    if [ -f "$HOOK" ] && grep -q "$MARCA" "$HOOK"; then
        rm -f "$HOOK"
        [ -f "$HOOK.antes" ] && mv "$HOOK.antes" "$HOOK"
        echo "Gancho removido de $REPO_DIR."
    else
        echo "Nenhum gancho do Heimdall encontrado em $REPO_DIR."
    fi
    exit 0
fi

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi
[ -n "${HEIMDALL_GITOPS_TOKEN:-}" ] || fail "HEIMDALL_GITOPS_TOKEN não está no .env. Rode antes: bash instalar_automacoes_avancadas.sh"

REMOTE_URL="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null)"
[ -n "$REMOTE_URL" ] || fail "o repositório não tem remoto 'origin'."
SLUG="$(printf '%s' "$REMOTE_URL" | sed -E 's#^(git@github\.com:|ssh://git@github\.com/|https?://([^@/]+@)?github\.com/)##; s#\.git$##; s#/$##')"
[[ "$SLUG" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "o remoto 'origin' não parece ser do GitHub: $REMOTE_URL"

# Arquivo de configuração do gancho, só seu (fora do repositório).
CONF="$HOME/.heimdall_gitops"
umask 077
{
    echo "HEIMDALL_GITOPS_URL='http://localhost:5678/webhook/heimdall-gitops'"
    echo "HEIMDALL_GITOPS_TOKEN='$HEIMDALL_GITOPS_TOKEN'"
} > "$CONF"
chmod 600 "$CONF"

# Guarda um gancho pre-push anterior, se existir, e o chama depois.
if [ -f "$HOOK" ] && ! grep -q "$MARCA" "$HOOK"; then
    mv "$HOOK" "$HOOK.antes"
    echo "Havia um gancho pre-push: foi guardado como pre-push.antes e continua sendo executado."
fi

cat > "$HOOK" <<'HOOKEOF'
#!/bin/sh
# heimdall-gitops
# Avisa o n8n (em segundo plano) a cada push de branch para o GitHub. Nunca atrapalha o push.
HERE="$(cd "$(dirname "$0")" && pwd)"
ENTRADA="$(cat)"
if [ -x "$HERE/pre-push.antes" ]; then
    printf '%s\n' "$ENTRADA" | "$HERE/pre-push.antes" "$@" || exit $?
fi
CONF="$HOME/.heimdall_gitops"
[ -r "$CONF" ] || exit 0
# shellcheck disable=SC1090
. "$CONF"
URL_REMOTO="$2"
SLUG=$(printf '%s' "$URL_REMOTO" | sed -E 's#^(git@github\.com:|ssh://git@github\.com/|https?://([^@/]+@)?github\.com/)##; s#\.git$##; s#/$##')
case "$SLUG" in */*) ;; *) exit 0 ;; esac
printf '%s\n' "$ENTRADA" | while read -r LOCAL_REF LOCAL_SHA REMOTE_REF REMOTE_SHA; do
    case "$REMOTE_REF" in refs/heads/*) ;; *) continue ;; esac
    case "$LOCAL_SHA" in 0000000000000000000000000000000000000000|"") continue ;; esac
    RAMO="${REMOTE_REF#refs/heads/}"
    case "$RAMO" in fix/refactor-auto-*) continue ;; esac
    # Espera o push terminar (o n8n lê o commit no GitHub) e avisa, sem prender o terminal.
    ( sleep 20; curl -s -m 15 -X POST "$HEIMDALL_GITOPS_URL" \
        -H "X-Heimdall-Token: $HEIMDALL_GITOPS_TOKEN" -H 'Content-Type: application/json' \
        -d "{\"repo\":\"$SLUG\",\"branch\":\"$RAMO\",\"sha\":\"$LOCAL_SHA\"}" > /dev/null 2>&1 ) > /dev/null 2>&1 < /dev/null &
done
exit 0
HOOKEOF
chmod +x "$HOOK"

# Autoriza o repositório na lista do .env (o fluxo só age em repositórios autorizados).
NOVA_LISTA="$("$(command -v python3)" - "$PROJECT_DIR/.env" "$SLUG" <<'PYEOF'
import re, sys
caminho, slug = sys.argv[1], sys.argv[2]
try:
    linhas = open(caminho, encoding="utf-8").read().splitlines()
except FileNotFoundError:
    linhas = []
achou = False
mudou = False
for i, l in enumerate(linhas):
    m = re.match(r"^HEIMDALL_GITOPS_REPOS=(['\"]?)(.*?)\1\s*$", l)
    if m:
        achou = True
        itens = [x for x in m.group(2).split(",") if x]
        if slug.lower() not in [x.lower() for x in itens]:
            itens.append(slug)
            linhas[i] = "HEIMDALL_GITOPS_REPOS='%s'" % ",".join(itens)
            mudou = True
if not achou:
    linhas.append("HEIMDALL_GITOPS_REPOS='%s'" % slug)
    mudou = True
if mudou:
    open(caminho, "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    print("mudou")
PYEOF
)"
chmod 600 "$PROJECT_DIR/.env" 2>/dev/null

echo "Gancho instalado em $REPO_DIR (repositório do GitHub: $SLUG)."
if [ "$NOVA_LISTA" = "mudou" ]; then
    echo "O repositório foi adicionado à lista de autorizados no .env."
    echo "Para valer, rode de novo:  bash instalar_automacoes_avancadas.sh"
else
    echo "O repositório já estava na lista de autorizados."
fi
echo "Daqui para a frente, cada git push desta pasta avisa o n8n."
