#!/usr/bin/env bash
# Instala no n8n o monitor de privacidade diário (fluxo 10, pasta n8n_flows_monitor/):
#   todos os dias às 9h pesquisa seus identificadores na web (SearXNG), lê as páginas novas, separa homônimos,
#   analisa menções, comentários, possíveis vazamentos e imagens, e entrega o relatório no app Notas
#   (pasta "Monitor de Privacidade") e um resumo no iPhone pelo Bark. O fluxo tem memória: não repete o que já
#   viu, avisa se uma página conhecida mudar e acompanha a tendência dos últimos dias.
#
# Uso, na pasta do projeto, com o n8n e o SearXNG no ar (start_heimdall.sh --n8n):
#     bash instalar_monitor_privacidade.sh                 (primeira vez: faz as perguntas)
#     bash instalar_monitor_privacidade.sh --reconfigurar  (muda nome, e-mails, usuários etc.)
#     bash instalar_monitor_privacidade.sh --remover       (apaga do .env o que você informou e desativa o fluxo)
#
# Seus identificadores ficam só no .env (que o git ignora) e dentro do n8n. Nunca vão para o repositório.
# Não informe CPF, senhas, números de documento ou cartão: pesquisar esses dados já os expõe aos buscadores.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

fail() { echo "Erro: $*" >&2; exit 1; }
umask 077

RECONF=0
REMOVER=0
case "${1:-}" in
    --reconfigurar) RECONF=1 ;;
    --remover) REMOVER=1 ;;
    "") ;;
    *) fail "opção desconhecida: $1 (use --reconfigurar ou --remover)." ;;
esac

PY="$PROJECT_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || fail "não encontrei o Python."

env_append() {
    if [ -s .env ] && [ "$(tail -c1 .env | wc -l | tr -d ' ')" = "0" ]; then
        echo >> .env
    fi
    echo "$1" >> .env
    chmod 600 .env
}

# Remove do .env as linhas HEIMDALL_MONITOR_* (usado ao reconfigurar e ao remover).
limpar_env_monitor() {
    [ -f .env ] || return 0
    "$PY" - .env <<'PYEOF'
import re, sys
p = sys.argv[1]
linhas = open(p, encoding="utf-8").read().splitlines()
novas = [l for l in linhas if not re.match(r"^HEIMDALL_MONITOR_[A-Z_]+=", l)]
open(p, "w", encoding="utf-8").write("\n".join(novas) + ("\n" if novas else ""))
PYEOF
    chmod 600 .env
}

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps --format '{{.Names}}' | grep -qx n8n || fail "o contêiner do n8n não está rodando. Suba com: bash start_heimdall.sh --n8n"

if [ "$REMOVER" = "1" ]; then
    for ID in hdMonitor00000001 hdDiario00000001 hdLembrete0000001; do
        docker exec n8n n8n update:workflow --id=$ID --active=false > /dev/null 2>&1 \
            && echo "Fluxo $ID desativado no n8n (continua importado; apague pela interface se quiser)."
    done
    limpar_env_monitor
    echo "Identificadores removidos do .env."
    exit 0
fi

docker ps --format '{{.Names}}' | grep -qx searxng || fail "o contêiner do SearXNG não está rodando. Rode: bash start_heimdall.sh --n8n"
[ -d n8n_flows_monitor ] || fail "a pasta n8n_flows_monitor/ não está ao lado deste script."
[ -n "${LITELLM_MASTER_KEY:-}" ] || fail "LITELLM_MASTER_KEY não está no .env (rode o start_heimdall.sh uma vez para gerá-la)."
[ -n "${HEIMDALL_AGENTE_TOKEN:-}" ] || fail "o token do agente do Mac não existe. Rode antes: bash instalar_automacoes_avancadas.sh"

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

MODELO="${HEIMDALL_FLOW_MODEL:-qwen3-vl-instruct}"
[[ "$MODELO" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "HEIMDALL_FLOW_MODEL tem caracteres inválidos."

# --- Identificadores a monitorar ---
pergunta() {  # pergunta "texto" VARIAVEL_ATUAL -> imprime o valor escolhido
    local texto="$1" atual="$2" resp
    if [ -n "$atual" ]; then
        read -r -p "$texto [Enter mantém: $atual] " resp
        [ -z "$resp" ] && resp="$atual"
    else
        read -r -p "$texto " resp
    fi
    printf '%s' "$resp"
}

if [ "$RECONF" = "1" ] || [ -z "${HEIMDALL_MONITOR_NOME:-}${HEIMDALL_MONITOR_EMAILS:-}${HEIMDALL_MONITOR_USUARIOS:-}" ]; then
    echo
    echo "Monitor de privacidade: o que devo procurar sobre você? Use só o que já é público ou que você quer vigiar."
    echo "NÃO informe CPF, senhas, documentos nem cartões. Várias respostas, separe por vírgula. Enter deixa em branco."
    echo
    N_NOME="$(pergunta "1. Seu nome completo (um só; as outras formas vão na pergunta 2):" "${HEIMDALL_MONITOR_NOME:-}")"
    N_VAR="$(pergunta "2. Outras grafias do nome (apelidos, sem acento, só sobrenome composto):" "${HEIMDALL_MONITOR_VARIACOES:-}")"
    N_EMAILS="$(pergunta "3. Seus e-mails:" "${HEIMDALL_MONITOR_EMAILS:-}")"
    N_USERS="$(pergunta "4. Seus usuários e apelidos em redes e sites (mínimo 5 letras para confirmar sozinho):" "${HEIMDALL_MONITOR_USUARIOS:-}")"
    N_CIDADE="$(pergunta "5. Sua cidade:" "${HEIMDALL_MONITOR_CIDADE:-}")"
    echo "6. Fatos que só combinam com você (empresa, profissão, faculdade, área). Eles separam você de homônimos:"
    N_SINAIS="$(pergunta "   Fatos:" "${HEIMDALL_MONITOR_SINAIS:-}")"
    N_IGN="$(pergunta "7. Sites seus a ignorar, só o domínio (por exemplo meusite.com.br):" "${HEIMDALL_MONITOR_IGNORAR:-}")"

    "$PY" - "$N_NOME" "$N_VAR" "$N_EMAILS" "$N_USERS" "$N_CIDADE" "$N_SINAIS" "$N_IGN" > "$(pwd)/.monitor_env.tmp" <<'PYEOF' || { rm -f .monitor_env.tmp; fail "dados inválidos (veja a mensagem acima)."; }
import re, shlex, sys
nome, var, emails, users, cidade, sinais, ign = [a.strip() for a in sys.argv[1:8]]
def lista(s): return [x.strip() for x in s.split(",") if x.strip()]
em = lista(emails); us = lista(users)
# Se o campo 1 veio com vários nomes separados por vírgula, o primeiro é o nome principal e o resto vira variação.
nomes1 = lista(nome)
if len(nomes1) > 1:
    print("Aviso: o campo 1 tinha vários nomes; '%s' ficou como nome principal e os outros foram para as variações." % nomes1[0], file=sys.stderr)
    nome = nomes1[0]
    vistos = []
    for x in lista(var) + nomes1[1:]:
        if x.lower() not in [v.lower() for v in vistos] and x.lower() != nome.lower():
            vistos.append(x)
    var = ",".join(vistos)
if not (nome or em or us):
    sys.exit("informe pelo menos o nome, um e-mail ou um usuário.")
for e in em:
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        sys.exit("e-mail inválido: " + e)
for u in us:
    if re.search(r"\s", u):
        sys.exit("usuário com espaço: " + u)
for d in lista(ign):
    if not re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", d):
        sys.exit("domínio inválido: " + d + " (use só o domínio, como meusite.com.br)")
if re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", " ".join(sys.argv[1:8])):
    sys.exit("parece haver um CPF nas respostas. Tire-o: pesquisar o CPF o expõe aos buscadores.")
for k, v in (("NOME", nome), ("VARIACOES", var), ("EMAILS", emails), ("USUARIOS", users), ("CIDADE", cidade), ("SINAIS", sinais), ("IGNORAR", ign)):
    print("HEIMDALL_MONITOR_%s=%s" % (k, shlex.quote(",".join(lista(v)) if k not in ("NOME", "CIDADE") else v)))
PYEOF
    limpar_env_monitor
    cat .monitor_env.tmp >> .env
    rm -f .monitor_env.tmp
    chmod 600 .env
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
    echo "Identificadores gravados no .env (arquivo ignorado pelo git)."
fi

# --- Prepara as cópias dos fluxos com as chaves e a configuração ---
TMP="$(mktemp -d)"
chmod 700 "$TMP"
cleanup() {
    rm -rf "$TMP"
    docker exec -u root n8n rm -rf /tmp/hd_flows_mon /tmp/hd_mon_export_hdMonitor00000001.json /tmp/hd_mon_export_hdDiario00000001.json > /dev/null 2>&1
}
trap cleanup EXIT

# Se o fluxo já existe, tenta levar a memória (páginas já vistas, histórico) para a nova versão.
for ID in hdMonitor00000001 hdDiario00000001 hdLembrete0000001; do
    docker exec n8n n8n export:workflow --id=$ID --output=/tmp/hd_mon_export_$ID.json > /dev/null 2>&1
    docker cp n8n:/tmp/hd_mon_export_$ID.json "$TMP/export_antigo_$ID.json" > /dev/null 2>&1
done

SUBS_LITELLM_KEY="$LITELLM_MASTER_KEY" SUBS_BARK_KEY="$BARK_KEY" SUBS_MODELO="$MODELO" SUBS_AGENTE="$HEIMDALL_AGENTE_TOKEN" \
M_NOME="${HEIMDALL_MONITOR_NOME:-}" M_VAR="${HEIMDALL_MONITOR_VARIACOES:-}" M_EMAILS="${HEIMDALL_MONITOR_EMAILS:-}" \
M_USERS="${HEIMDALL_MONITOR_USUARIOS:-}" M_CIDADE="${HEIMDALL_MONITOR_CIDADE:-}" M_SINAIS="${HEIMDALL_MONITOR_SINAIS:-}" \
M_IGN="${HEIMDALL_MONITOR_IGNORAR:-}" \
"$PY" - "$PROJECT_DIR/n8n_flows_monitor" "$TMP" <<'PYEOF' || fail "não consegui preparar os fluxos."
import json, os, pathlib, re, sys

src, dst = map(pathlib.Path, sys.argv[1:3])
E = os.environ

def lista(s):
    return [x.strip() for x in s.split(",") if x.strip()]

config = {
    "nome": E["M_NOME"], "variacoes": lista(E["M_VAR"]), "emails": lista(E["M_EMAILS"]), "usuarios": lista(E["M_USERS"]),
    "cidade": E["M_CIDADE"], "sinais": lista(E["M_SINAIS"]), "ignorar": lista(E["M_IGN"]),
}
if not (config["nome"] or config["emails"] or config["usuarios"]):
    sys.exit("nenhum identificador configurado. Rode: bash instalar_monitor_privacidade.sh --reconfigurar")
config_js = json.dumps(config, ensure_ascii=False)

subs = {
    "__LITELLM_KEY__": E["SUBS_LITELLM_KEY"], "__BARK_KEY__": E["SUBS_BARK_KEY"], "__MODELO__": E["SUBS_MODELO"],
    "__AGENTE_TOKEN__": E["SUBS_AGENTE"],
}

def fix(o, mapa):
    if isinstance(o, str):
        for k, v in mapa.items():
            o = o.replace(k, v)
        return o
    if isinstance(o, list):
        return [fix(x, mapa) for x in o]
    if isinstance(o, dict):
        return {k: fix(v, mapa) for k, v in o.items()}
    return o

# memória do fluxo anterior, se o n8n devolveu a exportação
memorias = {}
for wid in ("hdMonitor00000001", "hdDiario00000001"):
    try:
        antigo = json.loads((dst / ("export_antigo_%s.json" % wid)).read_text(encoding="utf-8"))
        antigo = antigo[0] if isinstance(antigo, list) else antigo
        sd = antigo.get("staticData")
        if isinstance(sd, str):
            sd = json.loads(sd)
        if isinstance(sd, dict) and sd.get("global"):
            memorias[wid] = sd
    except Exception:
        pass
    (dst / ("export_antigo_%s.json" % wid)).unlink(missing_ok=True)

ids = []
for f in sorted(src.glob("*.json")):
    wf = json.loads(f.read_text(encoding="utf-8"))
    wf = fix(wf, subs)
    texto = json.dumps(wf, ensure_ascii=False)
    sobra = re.search(r"__(?!MON_CONFIG__)[A-Z_]{3,}__", texto)
    if sobra:
        sys.exit("marcador sem valor em %s: %s" % (f.name, sobra.group(0)))
    wf = fix(wf, {"__MON_CONFIG__": config_js})
    if wf.get("id") in memorias:
        wf["staticData"] = memorias[wf["id"]]
        print("Memória anterior preservada em %s (já visto e histórico)." % f.name)
    out = dst / f.name
    out.write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(out, 0o600)
    ids.append(wf["id"])
PYEOF

# --- Importa no n8n ---
docker exec n8n mkdir -p /tmp/hd_flows_mon || fail "não consegui criar a pasta temporária no contêiner."
docker cp "$TMP/." n8n:/tmp/hd_flows_mon/ || fail "não consegui copiar os fluxos para o contêiner."
docker exec -u root n8n sh -c 'chown -R node:node /tmp/hd_flows_mon 2>/dev/null || chmod -R a+r /tmp/hd_flows_mon'
echo "Importando o monitor no n8n..."
if ! IMPORT_OUT="$(docker exec n8n n8n import:workflow --separate --input=/tmp/hd_flows_mon/ 2>&1)"; then
    # Segunda tentativa sem levar a memória antiga (o formato dela pode não ser aceito pela importação).
    for ARQ in 10-monitor-privacidade.json 11-diarios-oficiais.json 12-checagem-mensal.json; do
        "$PY" - "$TMP/$ARQ" <<'PYEOF2'
import json, sys
p = sys.argv[1]
w = json.load(open(p, encoding="utf-8"))
w.pop("staticData", None)
json.dump(w, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PYEOF2
        docker cp "$TMP/$ARQ" n8n:/tmp/hd_flows_mon/$ARQ
        docker exec -u root n8n chown node:node /tmp/hd_flows_mon/$ARQ 2>/dev/null
    done
    echo "A importação falhou; tentando de novo sem a memória antiga..."
    IMPORT_OUT="$(docker exec n8n n8n import:workflow --separate --input=/tmp/hd_flows_mon/ 2>&1)" || {
    echo "$IMPORT_OUT" | tail -n 15
    fail "a importação falhou. Você ainda pode importar n8n_flows_monitor/10-monitor-privacidade.json pela interface do n8n (os marcadores __CHAVE__ precisam ser trocados à mão)."
    }
fi
echo "$IMPORT_OUT" | tail -n 4

for ID in hdMonitor00000001 hdDiario00000001 hdLembrete0000001; do
    if docker exec n8n n8n update:workflow --id=$ID --active=true > /dev/null 2>&1 \
       || docker exec n8n n8n publish:workflow --id=$ID > /dev/null 2>&1; then
        echo "Fluxo $ID ativado (monitor às 9h, diários oficiais às 8h30)."
    else
        echo "O fluxo $ID foi importado, mas não consegui ativar. Ative-o na lista de fluxos do n8n (http://localhost:5678)."
    fi
done
docker restart n8n > /dev/null

# --- Conferências ---
echo
echo "Conferindo o que o monitor precisa:"
if docker exec n8n wget -q -T 15 -O - "http://searxng:8080/search?q=teste&format=json" 2>/dev/null | grep -q '"results"'; then
    echo " - O n8n alcança o SearXNG com resposta em JSON."
else
    echo " - AVISO: o n8n não recebeu JSON do SearXNG. Confira 'formats: - json' em searxng/settings.yml e rode o start_heimdall.sh de novo."
fi
if [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://localhost:8003/saude)" = "200" ]; then
    echo " - Agente do Mac no ar (o relatório vai para o app Notas, pasta Monitor de Privacidade)."
else
    echo " - AVISO: o agente do Mac está fora do ar. Sem ele o relatório não chega ao app Notas (o Bark ainda avisa). Rode o start_heimdall.sh."
fi
echo
echo "Para testar agora, sem esperar as 9h (o teste manual não guarda memória):"
echo "  docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=hdMonitor00000001 2>&1 | grep -E 'Execution was|rror'"
echo "Diários oficiais: docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=hdDiario00000001 2>&1 | grep -E 'Execution was|rror'"
echo "A memória só passa a valer nas execuções agendadas. A primeira execução agendada pode listar muita coisa antiga: é a linha de base."
echo
echo "Pronto."
