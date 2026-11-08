#!/usr/bin/env bash
# Instala no n8n os fluxos da pasta n8n_flows/ (resumo da AWS, pergunta de estudo, vigia de
# versões, alerta de saúde do Mac e relatório de disponibilidade).
#
# Uso, na pasta do projeto, com o n8n no ar (start_heimdall.sh com --n8n ou HEIMDALL_N8N=1):
#     bash instalar_fluxos_n8n.sh
#
# O que ele faz:
#   1. lê a chave do LiteLLM do .env e pede a chave do Bark (digitação oculta);
#   2. grava uma cópia temporária dos fluxos com as chaves aplicadas (permissão 600);
#   3. copia para dentro do contêiner, importa com o comando do próprio n8n e tenta ativar;
#   4. apaga as cópias temporárias e reinicia o n8n.
# As chaves não são mostradas na tela. Rodar de novo atualiza os fluxos (mesmos identificadores).
#
# Opções no .env (todas opcionais):
#   HEIMDALL_BARK_KEY      chave do Bark (se faltar, o script pergunta)
#   HEIMDALL_FLOW_MODEL    modelo do LiteLLM usado nos resumos (padrão: qwen3-vl-instruct)
#   HEIMDALL_KUMA_SLUG     nome (slug) da página de status do Uptime Kuma (padrão: heimdall)
#   HEIMDALL_ALERT_RAM / HEIMDALL_ALERT_SWAP / HEIMDALL_ALERT_DISK / HEIMDALL_ALERT_DISK_FREE
#                          limites do alerta do Mac: RAM %, swap em GB, disco %, livre em GB (95/8/90/20)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

fail() { echo "Erro: $*" >&2; exit 1; }

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps --format '{{.Names}}' | grep -qx n8n || fail "o contêiner do n8n não está rodando. Suba com: bash start_heimdall.sh --n8n"
[ -d n8n_flows ] || fail "a pasta n8n_flows/ não está ao lado deste script."
[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY não está no .env (rode o start_heimdall.sh uma vez para gerá-la)."

# --- Chave do Bark (aceita a chave pura ou a URL completa) ---
BARK_KEY="${HEIMDALL_BARK_KEY:-}"
if [ -z "$BARK_KEY" ]; then
    echo "Cole a chave do Bark (ou a URL completa do Bark). Nada aparece na tela enquanto você cola."
    read -r -s -p "Chave do Bark: " BARK_KEY
    echo
    ASK_SAVE=1
fi
case "$BARK_KEY" in
    http*) BARK_KEY="$(printf '%s' "$BARK_KEY" | sed -E 's#^https?://[^/]+/([^/?]+).*#\1#')" ;;
esac
[[ "$BARK_KEY" =~ ^[A-Za-z0-9_-]{6,}$ ]] || fail "a chave do Bark deve ter só letras, números, hífen ou sublinhado."
if [ "${ASK_SAVE:-0}" = "1" ]; then
    read -r -p "Guardar a chave no .env para as próximas vezes? [s/N] " ANS
    case "$ANS" in
        s|S|sim|SIM)
            printf "\nHEIMDALL_BARK_KEY='%s'\n" "$BARK_KEY" >> .env
            chmod 600 .env
            echo "Chave gravada no .env." ;;
    esac
fi

# --- Parâmetros com valores padrão e validação ---
MODELO="${HEIMDALL_FLOW_MODEL:-qwen3-vl-instruct}"
SLUG="${HEIMDALL_KUMA_SLUG:-heimdall}"
A_RAM="${HEIMDALL_ALERT_RAM:-95}"
A_SWAP="${HEIMDALL_ALERT_SWAP:-8}"
A_DISCO="${HEIMDALL_ALERT_DISK:-90}"
A_LIVRE="${HEIMDALL_ALERT_DISK_FREE:-20}"
[[ "$MODELO" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "HEIMDALL_FLOW_MODEL tem caracteres inválidos."
[[ "$SLUG" =~ ^[A-Za-z0-9_-]+$ ]] || fail "HEIMDALL_KUMA_SLUG tem caracteres inválidos."
for v in "$A_RAM" "$A_SWAP" "$A_DISCO" "$A_LIVRE"; do
    [[ "$v" =~ ^[0-9]+$ ]] || fail "os limites do alerta devem ser números inteiros."
done

PY="$PROJECT_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || fail "não encontrei o Python."

TMP="$(mktemp -d)"
chmod 700 "$TMP"
cleanup() {
    rm -rf "$TMP"
    docker exec -u root n8n rm -rf /tmp/hd_flows > /dev/null 2>&1
}
trap cleanup EXIT

# --- Aplica as chaves e parâmetros (por variáveis de ambiente, fora da lista de processos) ---
SUBS_LITELLM_KEY="$LITELLM_MASTER_KEY" SUBS_BARK_KEY="$BARK_KEY" SUBS_MODELO="$MODELO" SUBS_SLUG="$SLUG" \
SUBS_RAM="$A_RAM" SUBS_SWAP="$A_SWAP" SUBS_DISCO="$A_DISCO" SUBS_LIVRE="$A_LIVRE" \
"$PY" - "$PROJECT_DIR/n8n_flows" "$TMP" <<'PYEOF' || fail "não consegui preparar os fluxos."
import json, os, pathlib, re, sys

src, dst = map(pathlib.Path, sys.argv[1:3])
subs = {
    "__LITELLM_KEY__": os.environ["SUBS_LITELLM_KEY"],
    "__BARK_KEY__": os.environ["SUBS_BARK_KEY"],
    "__MODELO__": os.environ["SUBS_MODELO"],
    "__KUMA_SLUG__": os.environ["SUBS_SLUG"],
    "__ALERTA_RAM__": os.environ["SUBS_RAM"],
    "__ALERTA_SWAP__": os.environ["SUBS_SWAP"],
    "__ALERTA_DISCO__": os.environ["SUBS_DISCO"],
    "__ALERTA_LIVRE__": os.environ["SUBS_LIVRE"],
}

def fix(o):
    if isinstance(o, str):
        for k, v in subs.items():
            o = o.replace(k, v)
        return o
    if isinstance(o, list):
        return [fix(x) for x in o]
    if isinstance(o, dict):
        return {k: fix(v) for k, v in o.items()}
    return o

files = sorted(src.glob("*.json"))
if not files:
    sys.exit("nenhum fluxo em n8n_flows/")
for f in files:
    wf = fix(json.loads(f.read_text(encoding="utf-8")))
    text = json.dumps(wf, ensure_ascii=False, indent=1)
    sobra = re.search(r"__[A-Z_]{3,}__", text)
    if sobra:
        sys.exit(f"marcador sem valor em {f.name}: {sobra.group(0)}")
    out = dst / f.name
    out.write_text(text, encoding="utf-8")
    os.chmod(out, 0o600)
PYEOF

IDS="$("$PY" - "$PROJECT_DIR/n8n_flows" <<'PYEOF'
import json, pathlib, sys
for f in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    print(json.loads(f.read_text(encoding="utf-8"))["id"])
PYEOF
)"

# --- Importa no n8n ---
docker exec n8n mkdir -p /tmp/hd_flows || fail "não consegui criar a pasta temporária no contêiner."
docker cp "$TMP/." n8n:/tmp/hd_flows/ || fail "não consegui copiar os fluxos para o contêiner."
# Os arquivos chegam com outro dono e permissão 600; o n8n roda como o usuário "node" e precisa lê-los.
docker exec -u root n8n sh -c 'chown -R node:node /tmp/hd_flows 2>/dev/null || chmod -R a+r /tmp/hd_flows'
echo "Importando os fluxos no n8n..."
if ! IMPORT_OUT="$(docker exec n8n n8n import:workflow --separate --input=/tmp/hd_flows/ 2>&1)"; then
    echo "$IMPORT_OUT" | tail -n 15
    fail "a importação falhou. Você ainda pode importar cada arquivo de n8n_flows/ pela interface do n8n."
fi
echo "$IMPORT_OUT" | tail -n 5

# --- Tenta ativar (o comando varia entre versões do n8n) ---
ATIVADOS=0
for id in $IDS; do
    if docker exec n8n n8n update:workflow --id="$id" --active=true > /dev/null 2>&1 \
       || docker exec n8n n8n publish:workflow --id="$id" > /dev/null 2>&1; then
        ATIVADOS=$((ATIVADOS + 1))
    fi
done
TOTAL="$(printf '%s\n' "$IDS" | wc -l | tr -d ' ')"
docker restart n8n > /dev/null
echo "Fluxos ativados: $ATIVADOS de $TOTAL."
if [ "$ATIVADOS" -lt "$TOTAL" ]; then
    echo "Os que não foram ativados estão importados, mas desligados. Ative-os na lista de fluxos do n8n"
    echo "(http://localhost:5678), pelo interruptor de cada um."
fi

# --- Avisos úteis ---
if [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://localhost:8000/metricas)" != "200" ]; then
    echo "Aviso: o MCP do Mac ainda não responde em /metricas (o alerta de saúde precisa dele)."
    echo "       Copie o heimdall_mcp.py novo e rode o start_heimdall.sh de novo."
fi
echo "Aviso: o relatório de disponibilidade precisa de uma página de status no Uptime Kuma com o nome (slug) '$SLUG'."
echo "Pronto."
