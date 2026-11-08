#!/usr/bin/env bash
# Instala no n8n as três automações avançadas da pasta n8n_flows_avancados/:
#   6. GitOps inteligente   (webhook de git push -> análise com deepseek -> branch + PR em rascunho no GitHub)
#   7. Digest hiperpersonalizado (8h e 18h -> feeds -> triagem -> "por que importa para mim" -> Notas + Bark)
#   8. Second Brain         (app Notas -> conceitos, tags, conexões e lacunas -> nota espelho + base vetorial)
#
# Uso, na pasta do projeto, com o n8n no ar (start_heimdall.sh com --n8n ou HEIMDALL_N8N=1):
#     bash instalar_automacoes_avancadas.sh
#
# O que ele faz:
#   1. lê o .env; pede (com digitação oculta) o que faltar: chave do Bark, token do GitHub e a lista de
#      repositórios autorizados; gera sozinho o token do webhook do GitOps e o token do agente do Mac;
#   2. mede a dimensão dos embeddings no Ollama;
#   3. grava cópias temporárias dos fluxos com as chaves aplicadas (permissão 600), importa no n8n e ativa;
#   4. apaga as cópias temporárias, reinicia o n8n e confere o agente do Mac, o Ollama e o Qdrant.
# Rodar de novo atualiza os fluxos (mesmos identificadores), por exemplo depois de autorizar outro repositório.
#
# Opções no .env (todas opcionais):
#   HEIMDALL_BARK_KEY          chave do Bark (se faltar, o script pergunta)
#   HEIMDALL_GITHUB_TOKEN      token do GitHub com permissão de Contents e Pull requests (Read and write)
#   HEIMDALL_GITOPS_REPOS      repositórios autorizados, "dono/repo,dono/outro"
#   HEIMDALL_FLOW_MODEL        modelo do LiteLLM para digest e second brain (padrão: qwen3-vl-instruct)
#   HEIMDALL_CODE_MODEL        modelo do LiteLLM para o GitOps (padrão: deepseek-coder-v2:16b)
#   HEIMDALL_EMBED_MODEL       modelo de embeddings do Ollama (padrão: nomic-embed-text)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

fail() { echo "Erro: $*" >&2; exit 1; }

env_append() {
    if [ -s .env ] && [ "$(tail -c1 .env | wc -l | tr -d ' ')" = "0" ]; then
        echo >> .env
    fi
    echo "$1" >> .env
    chmod 600 .env
}

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps --format '{{.Names}}' | grep -qx n8n || fail "o contêiner do n8n não está rodando. Suba com: bash start_heimdall.sh --n8n"
[ -d n8n_flows_avancados ] || fail "a pasta n8n_flows_avancados/ não está ao lado deste script."
[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY não está no .env (rode o start_heimdall.sh uma vez para gerá-la)."

PY="$PROJECT_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || fail "não encontrei o Python."

# --- Bark ---
BARK_KEY="${HEIMDALL_BARK_KEY:-}"
if [ -z "$BARK_KEY" ]; then
    echo "Cole a chave do Bark (ou a URL completa do Bark). Nada aparece na tela enquanto você cola."
    read -r -s -p "Chave do Bark: " BARK_KEY
    echo
    ASK_SAVE_BARK=1
fi
case "$BARK_KEY" in
    http*) BARK_KEY="$(printf '%s' "$BARK_KEY" | sed -E 's#^https?://[^/]+/([^/?]+).*#\1#')" ;;
esac
[[ "$BARK_KEY" =~ ^[A-Za-z0-9_-]{6,}$ ]] || fail "a chave do Bark deve ter só letras, números, hífen ou sublinhado."
if [ "${ASK_SAVE_BARK:-0}" = "1" ]; then
    read -r -p "Guardar a chave do Bark no .env? [s/N] " ANS
    case "$ANS" in s|S|sim|SIM) env_append "HEIMDALL_BARK_KEY='$BARK_KEY'"; echo "Chave do Bark gravada no .env." ;; esac
fi

# --- GitHub (só para o GitOps; deixe em branco para instalar apenas o digest e o second brain) ---
SKIP_GIT=0
GH_TOKEN="${HEIMDALL_GITHUB_TOKEN:-}"
if [ -z "$GH_TOKEN" ]; then
    echo
    echo "GitOps: cole o token do GitHub (fine-grained, com Contents e Pull requests em 'Read and write'"
    echo "nos repositórios escolhidos). Aperte Enter sem colar nada para pular o GitOps por enquanto."
    read -r -s -p "Token do GitHub: " GH_TOKEN
    echo
    if [ -n "$GH_TOKEN" ]; then ASK_SAVE_GH=1; fi
fi
if [ -z "$GH_TOKEN" ]; then
    SKIP_GIT=1
    echo "GitOps pulado. Rode este script de novo quando tiver o token."
else
    [[ "$GH_TOKEN" =~ ^[A-Za-z0-9_]{20,}$ ]] || fail "o token do GitHub tem caracteres inesperados (esperado: letras, números e sublinhado)."
    if [ "${ASK_SAVE_GH:-0}" = "1" ]; then
        read -r -p "Guardar o token do GitHub no .env? [s/N] " ANS
        case "$ANS" in s|S|sim|SIM) env_append "HEIMDALL_GITHUB_TOKEN='$GH_TOKEN'"; echo "Token do GitHub gravado no .env." ;; esac
    fi
    REPOS="${HEIMDALL_GITOPS_REPOS:-}"
    if [ -z "$REPOS" ]; then
        read -r -p "Repositórios autorizados (dono/repo, separados por vírgula): " REPOS
        [ -n "$REPOS" ] && env_append "HEIMDALL_GITOPS_REPOS='$REPOS'"
    fi
    REPOS="$(printf '%s' "$REPOS" | tr -d ' ')"
    [[ "$REPOS" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)*$ ]] \
        || fail "a lista de repositórios deve ser no formato dono/repo,dono/outro (sem espaços ou aspas)."
    if [ -z "${HEIMDALL_GITOPS_TOKEN:-}" ]; then
        HEIMDALL_GITOPS_TOKEN="$(openssl rand -hex 24)"
        env_append "HEIMDALL_GITOPS_TOKEN='$HEIMDALL_GITOPS_TOKEN'"
        echo "Token do webhook do GitOps gerado e gravado no .env."
    fi
fi

# --- Token do agente do Mac ---
if [ -z "${HEIMDALL_AGENTE_TOKEN:-}" ]; then
    HEIMDALL_AGENTE_TOKEN="$(openssl rand -hex 24)"
    env_append "HEIMDALL_AGENTE_TOKEN='$HEIMDALL_AGENTE_TOKEN'"
    echo "Token do agente do Mac gerado e gravado no .env."
    NOVO_AGENTE=1
fi

# --- Modelos e dimensão dos embeddings ---
MODELO="${HEIMDALL_FLOW_MODEL:-qwen3-vl-instruct}"
MODELO_COD="${HEIMDALL_CODE_MODEL:-deepseek-coder-v2:16b}"
EMBED="${HEIMDALL_EMBED_MODEL:-nomic-embed-text}"
[[ "$MODELO" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "HEIMDALL_FLOW_MODEL tem caracteres inválidos."
[[ "$MODELO_COD" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "HEIMDALL_CODE_MODEL tem caracteres inválidos."
[[ "$EMBED" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "HEIMDALL_EMBED_MODEL tem caracteres inválidos."
DIM="$(curl -s -m 90 "http://localhost:11434/api/embed" -d "{\"model\":\"$EMBED\",\"input\":\"teste\"}" 2>/dev/null \
    | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)["embeddings"][0]))' 2>/dev/null)"
if ! [[ "$DIM" =~ ^[0-9]+$ ]]; then
    DIM=768
    echo "Aviso: não consegui medir os embeddings do modelo '$EMBED' (usando 768). Se ele não existir, rode: ollama pull $EMBED"
fi
echo "Embeddings: modelo $EMBED, $DIM dimensões."

TMP="$(mktemp -d)"
chmod 700 "$TMP"
cleanup() {
    rm -rf "$TMP"
    docker exec -u root n8n rm -rf /tmp/hd_flows_av > /dev/null 2>&1
}
trap cleanup EXIT

SUBS_LITELLM_KEY="$LITELLM_MASTER_KEY" SUBS_BARK_KEY="$BARK_KEY" SUBS_MODELO="$MODELO" SUBS_MODELO_COD="$MODELO_COD" \
SUBS_GH="${GH_TOKEN:-}" SUBS_GITOPS="${HEIMDALL_GITOPS_TOKEN:-}" SUBS_REPOS="${REPOS:-}" SUBS_AGENTE="$HEIMDALL_AGENTE_TOKEN" \
SUBS_EMBED="$EMBED" SUBS_DIM="$DIM" SUBS_SKIP_GIT="$SKIP_GIT" \
"$PY" - "$PROJECT_DIR/n8n_flows_avancados" "$TMP" <<'PYEOF' || fail "não consegui preparar os fluxos."
import json, os, pathlib, re, sys

src, dst = map(pathlib.Path, sys.argv[1:3])
E = os.environ
subs = {
    "__LITELLM_KEY__": E["SUBS_LITELLM_KEY"], "__BARK_KEY__": E["SUBS_BARK_KEY"], "__MODELO__": E["SUBS_MODELO"],
    "__MODELO_CODIGO__": E["SUBS_MODELO_COD"], "__GITHUB_TOKEN__": E["SUBS_GH"], "__GITOPS_TOKEN__": E["SUBS_GITOPS"],
    "__GITOPS_REPOS__": E["SUBS_REPOS"], "__AGENTE_TOKEN__": E["SUBS_AGENTE"], "__EMBED_MODELO__": E["SUBS_EMBED"],
    "__EMBED_DIM__": E["SUBS_DIM"],
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
if E["SUBS_SKIP_GIT"] == "1":
    files = [f for f in files if not f.name.startswith(("6-", "9-"))]
if not files:
    sys.exit("nenhum fluxo em n8n_flows_avancados/")
ids = []
for f in files:
    wf = fix(json.loads(f.read_text(encoding="utf-8")))
    text = json.dumps(wf, ensure_ascii=False, indent=1)
    sobra = re.search(r"__[A-Z_]{3,}__", text)
    if sobra:
        sys.exit(f"marcador sem valor em {f.name}: {sobra.group(0)}")
    out = dst / f.name
    out.write_text(text, encoding="utf-8")
    os.chmod(out, 0o600)
    if wf["id"] != "hdFalhaAviso0001":  # o aviso de falha só é chamado pelo n8n; não se ativa
        ids.append(wf["id"])
(dst / "ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
PYEOF

IDS="$(cat "$TMP/ids.txt")"
rm -f "$TMP/ids.txt"

# --- Importa no n8n ---
docker exec n8n mkdir -p /tmp/hd_flows_av || fail "não consegui criar a pasta temporária no contêiner."
docker cp "$TMP/." n8n:/tmp/hd_flows_av/ || fail "não consegui copiar os fluxos para o contêiner."
docker exec -u root n8n sh -c 'chown -R node:node /tmp/hd_flows_av 2>/dev/null || chmod -R a+r /tmp/hd_flows_av'
echo "Importando os fluxos no n8n..."
if ! IMPORT_OUT="$(docker exec n8n n8n import:workflow --separate --input=/tmp/hd_flows_av/ 2>&1)"; then
    echo "$IMPORT_OUT" | tail -n 15
    fail "a importação falhou. Você ainda pode importar cada arquivo de n8n_flows_avancados/ pela interface do n8n."
fi
echo "$IMPORT_OUT" | tail -n 5

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
    echo "Os que não foram ativados estão importados, mas desligados. Ative-os na lista de fluxos do n8n (http://localhost:5678)."
fi

# --- Conferências ---
echo
echo "Conferindo o que os fluxos precisam:"
if [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://localhost:8003/saude)" = "200" ]; then
    echo " - Agente do Mac: no ar na porta 8003."
    if docker exec n8n wget -q -T 5 -O - http://host.docker.internal:8003/saude > /dev/null 2>&1; then
        echo " - O n8n alcança o agente do Mac."
    else
        echo " - AVISO: o n8n não alcança o agente. Ponha HEIMDALL_AGENTE_HOST=0.0.0.0 no .env e rode o start_heimdall.sh de novo."
    fi
else
    echo " - Agente do Mac: FORA DO AR. Rode o start_heimdall.sh de novo (ele sobe o agente sozinho agora que o token existe)."
fi
if docker exec n8n wget -q -T 5 -O - http://host.docker.internal:11434/api/version > /dev/null 2>&1; then
    echo " - O n8n alcança o Ollama."
else
    echo " - AVISO: o n8n não alcança o Ollama (necessário para o Second Brain). Ele deve escutar em 0.0.0.0 (OLLAMA_HOST no .env)."
fi
if docker exec n8n wget -q -T 5 -O - http://qdrant:6333/collections > /dev/null 2>&1; then
    echo " - O n8n alcança o Qdrant."
else
    echo " - AVISO: o n8n não alcança o Qdrant (necessário para o Second Brain)."
fi
if command -v ollama > /dev/null 2>&1; then
    ollama list 2>/dev/null | grep -q "^${EMBED%%:*}" || echo " - AVISO: o modelo de embeddings '$EMBED' não está instalado. Rode: ollama pull $EMBED"
    if [ "$SKIP_GIT" = "0" ]; then
        ollama list 2>/dev/null | grep -q "^${MODELO_COD%%:*}" || echo " - AVISO: o modelo '$MODELO_COD' não está no Ollama."
    fi
fi
if [ "$SKIP_GIT" = "0" ]; then
    echo
    echo "GitOps: o endereço do webhook é http://localhost:5678/webhook/heimdall-gitops"
    echo "Para ligar um repositório, rode:  bash instalar_hook_gitops.sh /caminho/do/repositorio"
fi
if [ "${NOVO_AGENTE:-0}" = "1" ]; then
    echo
    echo "O token do agente é novo: rode o start_heimdall.sh de novo para o agente subir com ele."
fi
echo
echo "Pronto."
