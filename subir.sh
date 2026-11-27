#!/bin/bash
# Sobe o StudioLibre UMA vez só, guarda o log de cada subida e avisa quando tudo estiver no ar.
#
#   ./subir.sh                    sobe com --webui --terminal (o que você usa hoje)
#   ./subir.sh --update           sobe com os argumentos que você passar (os mesmos do start_studio.sh)
#   ./subir.sh --status           só confere agora o que está no ar, sem subir nada
#   ./subir.sh --log              mostra as últimas 40 linhas do log da subida atual
#   ./subir.sh --log lab          idem, do serviço indicado (mcp, mcp_public, mcp_dados, agente, lab, learn, trading, memory, news, saude_painel, jogos, account, finance, controls, open_terminal, ingest)
#   ./subir.sh --logs             lista os logs em logs/
#   ./subir.sh --limpar           apaga os logs antigos que ficavam soltos na pasta do projeto (agora ficam em logs/)
#   ./subir.sh --reiniciar [args] encerra a subida em andamento e sobe de novo
#
# O que ele faz:
#   1. Recusa subir se já houver uma subida em andamento (era isso que derrubava uma tentativa com a outra).
#   2. Grava o log em logs/studio-AAAAMMDD-HHMMSS.log e aponta studio.log para o da subida atual. Os logs anteriores
#      ficam guardados (os 15 mais recentes). Os logs de cada serviço também ficam em logs/ (o start_studio.sh guarda os 5
#      anteriores de cada um em logs/historico/).
#   3. Confere, de poucos em poucos segundos, cada serviço que deve estar no ar nesta subida e conta o que já subiu.
#   4. No fim avisa: "Tudo no ar" (com aviso do macOS e voz) ou lista o que ficou faltando e onde olhar no log.
#
# Opções no ambiente ou no .env: SUBIR_ESPERA=900 (segundos de espera máxima), SUBIR_SOM=0 (sem voz nem notificação),
# SUBIR_VOZ="Felipe (Aprimorada)" (voz do anúncio; SUBIR_VOZ_PPM=290 é a velocidade em palavras por minuto; aceita também "Felipe" ou "Felipe (Enhanced)"; sem isto usa a voz do sistema).

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
SCRIPT="${SUBIR_SCRIPT:-$PROJECT_DIR/start_studio.sh}"
LOGS="$PROJECT_DIR/logs"
ESPERA="${SUBIR_ESPERA:-900}"

# ---------------------------------------------------------------------------------------------------------------------
# Pedidos simples: --log, --status, --reiniciar
# ---------------------------------------------------------------------------------------------------------------------
MODO="subir"
case "$1" in
    --log)
        if [ -n "$2" ]; then
            alvo="$(ls -1 "$LOGS"/"$2"*.log 2> /dev/null | head -n 1)"
            [ -n "$alvo" ] && { echo "== $alvo"; tail -n 40 "$alvo"; exit 0; }
            echo "Não achei log para '$2'. Veja os nomes com: ./subir.sh --logs"; exit 1
        fi
        tail -n 40 "$PROJECT_DIR/studio.log" 2> /dev/null || echo "Ainda não há log. Rode ./subir.sh"; exit 0 ;;
    --logs) ls -lt "$LOGS" 2> /dev/null | tail -n +2 || echo "Ainda não há logs."; exit 0 ;;
    --limpar)
        n=0
        for f in mcp_debug mcp_public_debug mcp_dados_debug agente_debug lab_debug learn_debug trading_debug memory_debug open_terminal ingest; do
            if [ -f "$PROJECT_DIR/$f.log" ] && [ ! -L "$PROJECT_DIR/$f.log" ]; then rm -f "$PROJECT_DIR/$f.log" && n=$((n+1)) && echo "Apagado: $f.log"; fi
        done
        echo "$n arquivo(s) de log antigo apagado(s). Os logs atuais estão em logs/."
        exit 0 ;;
    --status) MODO="status"; shift ;;
    --reiniciar) MODO="reiniciar"; shift ;;
esac

# Nomes antigos de variável (HEIMDALL_*) viram STUDIO_* no .env, com cópia em .env.bak (só quando há o que trocar)
if [ -f .env ]; then
    if [ -x venv/bin/python ]; then venv/bin/python -c "import studio_config as c; t = c.renomear_antigas(); print('Variáveis do .env com o nome novo:', ', '.join(t)) if t else None" 2>/dev/null || true; fi
fi

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env > /dev/null 2>&1
    set +a
fi

ARGS=("$@")
[ ${#ARGS[@]} -eq 0 ] && ARGS=(--webui --terminal)
tem_arg() { local a; for a in "${ARGS[@]}"; do [ "$a" = "$1" ] && return 0; done; return 1; }

# ---------------------------------------------------------------------------------------------------------------------
# O que deve estar no ar nesta subida (as mesmas condições do start_studio.sh)
# Cada linha: nome|tipo|alvo   (tipo: tcp = porta aberta; http = responde com sucesso)
# ---------------------------------------------------------------------------------------------------------------------
montar_lista() {
    LISTA=()
    LISTA+=("LiteLLM (modelos)|http|http://127.0.0.1:${LLM_PORT:-9000}/health/readiness")
    LISTA+=("Qdrant (base vetorial)|tcp|6333")
    LISTA+=("SearXNG (busca)|tcp|8080")
    LISTA+=("MCP do Mac|tcp|8000")
    LISTA+=("MCP público|tcp|8001")
    LISTA+=("MCP de dados|tcp|8004")
    [ -n "$STUDIO_AGENTE_TOKEN" ] || [ "$STUDIO_AGENTE" = "1" ] || tem_arg --agente && LISTA+=("Agente do Mac|tcp|${STUDIO_AGENTE_PORT:-8003}")
    if [ "$STUDIO_MONITORING" != "0" ]; then
        LISTA+=("Uptime Kuma (status)|tcp|3001")
        LISTA+=("Dozzle (logs)|tcp|8081")
    fi
    if [ "$STUDIO_N8N" = "1" ] || tem_arg --n8n; then LISTA+=("n8n (automações)|tcp|5678"); fi
    if [ "$STUDIO_WEBUI" = "1" ] || tem_arg --webui; then LISTA+=("Open WebUI (chat)|tcp|3000"); fi
    if [ -n "$OPEN_TERMINAL_API_KEY" ] || tem_arg --terminal; then LISTA+=("Open Terminal|tcp|8002"); fi
    # Sob demanda (padrão): se o contêiner do emulador já existe, ele não sobe junto e não entra na espera.
    EMU_SOB_DEMANDA=0
    if [ "${STUDIO_AWS_EMULATOR_INICIO:-demanda}" = "demanda" ] && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qE '^(localstack|moto)$'; then EMU_SOB_DEMANDA=1; fi
    case "${STUDIO_AWS_EMULATOR:-auto}" in off) ;; *) [ "$EMU_SOB_DEMANDA" = "1" ] || LISTA+=("Emulador de AWS|tcp|4566") ;; esac
    if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
        case "${STUDIO_AWS_EMULATOR:-auto}" in off) ;; *) LISTA+=("Studio Lab|http|http://127.0.0.1:${STUDIO_LAB_PORT:-8010}/saude") ;; esac
        [ "${STUDIO_LEARN:-0}" = "1" ] && LISTA+=("Studio Learn|http|http://127.0.0.1:${STUDIO_LEARN_PORT:-8019}/saude")
        [ "${STUDIO_TRADING:-0}" = "1" ] && LISTA+=("Studio Trading|http|http://127.0.0.1:${STUDIO_TRADING_PORT:-8020}/saude")
        [ "${STUDIO_HUB:-${STUDIO_HUB:-0}}" = "1" ] && LISTA+=("Studio Hub|http|http://127.0.0.1:${STUDIO_HUB_PORT:-${STUDIO_HUB_PORT:-8021}}/saude")
        LISTA+=("Studio News|http|http://127.0.0.1:${STUDIO_NEWS_PORT:-8012}/saude")
        LISTA+=("Studio Health|http|http://127.0.0.1:${STUDIO_SAUDE_PAINEL_PORT:-8013}/saude")
        LISTA+=("Studio Games|http|http://127.0.0.1:${STUDIO_JOGOS_PORT:-8014}/saude")
        LISTA+=("Studio Finance|http|http://127.0.0.1:${STUDIO_FINANCE_PORT:-8016}/saude")
        LISTA+=("Controls|http|http://127.0.0.1:${STUDIO_CONTROLS_PORT:-8017}/saude")
    fi
    [ -f studio_account.py ] && LISTA+=("Account|http|http://127.0.0.1:${STUDIO_ACCOUNT_PORT:-8018}/saude")
}

esta_no_ar() {  # $1 = tipo, $2 = alvo
    if [ "$1" = "tcp" ]; then
        nc -z 127.0.0.1 "$2" > /dev/null 2>&1
    else
        curl -fsS -m 3 -o /dev/null "$2" > /dev/null 2>&1
    fi
}

escolher_voz() {  # acha a voz pedida em SUBIR_VOZ na lista do sistema (qualquer variante Aprimorada/Aprimorado/Enhanced/Premium serve; a melhor ganha); vazio = voz do sistema
    VOZ_SUBIR=""
    [ -n "$SUBIR_VOZ" ] || return 0
    command -v say > /dev/null 2>&1 || return 0
    local base linha nome nivel melhor=0 lista
    base=$(printf '%s' "${SUBIR_VOZ%% (*}" | tr '[:upper:]' '[:lower:]')
    lista=$(say -v '?' 2> /dev/null)
    while IFS= read -r linha; do
        case "$linha" in *" pt_"*) ;; *) continue ;; esac
        nome=$(printf '%s' "$linha" | sed -E 's/[[:space:]]+[a-z]{2,3}_[A-Za-z]{2,3}[[:space:]]+#.*$//')
        [ "$(printf '%s' "${nome%% (*}" | tr '[:upper:]' '[:lower:]')" = "$base" ] || continue
        case "$nome" in *[Pp]remium*) nivel=3 ;; *[Aa]primorad*|*[Mm]elhorad*|*[Ee]nhanced*) nivel=2 ;; *) nivel=1 ;; esac
        if [ "$nivel" -gt "$melhor" ]; then melhor=$nivel; VOZ_SUBIR="$nome"; fi
    done <<< "$lista"
}

avisar() {  # $1 = texto curto para a notificação e a voz
    [ "$SUBIR_SOM" = "0" ] && return
    command -v osascript > /dev/null 2>&1 && osascript -e "display notification \"$1\" with title \"StudioLibre\"" > /dev/null 2>&1
    if command -v say > /dev/null 2>&1; then
        [ -z "${VOZ_ESCOLHIDA:-}" ] && { escolher_voz; VOZ_ESCOLHIDA=1; }
        local fala="Heimdall. $1"
        command -v python3 > /dev/null 2>&1 && fala=$(python3 "$PROJECT_DIR/studio_voz.py" "$fala" 2> /dev/null || printf '%s' "$fala")   # dicionário de pronúncia (pronuncias.txt)
        if [ -n "$VOZ_SUBIR" ]; then say -v "$VOZ_SUBIR" -r "${SUBIR_VOZ_PPM:-290}" "$fala" > /dev/null 2>&1 &
        else say -r "${SUBIR_VOZ_PPM:-290}" "$fala" > /dev/null 2>&1 &
        fi
    fi
}

subida_em_andamento() {
    pgrep -f "start_studio.sh" > /dev/null 2>&1 && return 0
    local p
    p="$(cat "$LOGS/subida.pid" 2> /dev/null)"
    [ -n "$p" ] && kill -0 "$p" 2> /dev/null
}

montar_lista

# ---------------------------------------------------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------------------------------------------------
if [ "$MODO" = "status" ]; then
    faltam=0
    for item in "${LISTA[@]}"; do
        IFS='|' read -r nome tipo alvo <<< "$item"
        if esta_no_ar "$tipo" "$alvo"; then echo "No ar:   $nome"; else echo "Parado:  $nome"; faltam=$((faltam+1)); fi
    done
    if subida_em_andamento; then echo "Há uma subida em andamento (start_studio.sh rodando)."; else echo "Nenhuma subida em andamento."; fi
    if [ "$faltam" -eq 0 ]; then echo "Tudo no ar: ${#LISTA[@]} serviços."; exit 0; fi
    echo "Faltam $faltam de ${#LISTA[@]} serviços."
    exit 1
fi

# ---------------------------------------------------------------------------------------------------------------------
# Subir
# ---------------------------------------------------------------------------------------------------------------------
if subida_em_andamento; then
    if [ "$MODO" = "reiniciar" ]; then
        echo "Encerrando a subida em andamento..."
        pkill -f "start_studio.sh"
        p="$(cat "$LOGS/subida.pid" 2> /dev/null)"
        [ -n "$p" ] && kill "$p" 2> /dev/null
        sleep 3
    else
        echo "Já há uma subida em andamento. Não vou iniciar outra, porque uma derrubaria a outra."
        echo "Veja o que já está no ar com: ./subir.sh --status"
        echo "Veja o log com: ./subir.sh --log"
        echo "Para encerrar e subir de novo: ./subir.sh --reiniciar"
        exit 1
    fi
fi

mkdir -p "$LOGS"
# Um studio.log solto de antes vira parte do histórico, em vez de ser sobrescrito.
if [ -f studio.log ] && [ ! -L studio.log ]; then
    mv studio.log "$LOGS/studio-anterior-$(date -r studio.log +%Y%m%d-%H%M%S 2>/dev/null || date +%Y%m%d-%H%M%S).log"
fi
LOG="$LOGS/studio-$(date +%Y%m%d-%H%M%S).log"
ln -sfn "$LOG" studio.log
# Guarda só os 15 logs mais recentes.
ls -1t "$LOGS"/studio-*.log 2> /dev/null | tail -n +16 | while read -r velho; do rm -f "$velho"; done

nohup bash "$SCRIPT" "${ARGS[@]}" >> "$LOG" 2>&1 &
PID=$!
echo "$PID" > "$LOGS/subida.pid"
echo "Subindo o StudioLibre (argumentos: ${ARGS[*]}). Log: $LOG"
echo "Esperando até $((ESPERA / 60)) minutos. Vou avisar cada serviço que ficar no ar."

declare -a JA
ok_n=0
inicio=$SECONDS
# Antes de contar serviços, espera o start_studio.sh terminar de liberar as portas (etapa 1). Assim, restos de uma
# subida anterior que ainda estejam de pé não contam como "no ar".
MARCA="${SUBIR_MARCA:-\[1/7\]}"
while ! grep -q "$MARCA" "$LOG" 2> /dev/null; do
    kill -0 "$PID" 2> /dev/null || break
    [ $((SECONDS - inicio)) -ge 180 ] && break
    sleep 1
done
while :; do
    ok_n=0
    for i in "${!LISTA[@]}"; do
        IFS='|' read -r nome tipo alvo <<< "${LISTA[$i]}"
        if esta_no_ar "$tipo" "$alvo"; then
            ok_n=$((ok_n+1))
            if [ -z "${JA[$i]}" ]; then
                JA[$i]=1
                printf 'No ar (%d de %d, %ds): %s\n' "$ok_n" "${#LISTA[@]}" $((SECONDS - inicio)) "$nome"
            fi
        fi
    done
    [ "$ok_n" -eq "${#LISTA[@]}" ] && break
    if ! kill -0 "$PID" 2> /dev/null; then
        echo "O script de subida terminou antes de tudo ficar no ar."
        break
    fi
    [ $((SECONDS - inicio)) -ge "$ESPERA" ] && break
    sleep 4
done

if [ "$ok_n" -eq "${#LISTA[@]}" ]; then
    echo "Tudo no ar: ${#LISTA[@]} serviços, em $((SECONDS - inicio)) segundos."
    avisar "Tudo no ar."
    exit 0
fi
echo "Ainda faltam serviços depois de $((SECONDS - inicio)) segundos:"
for i in "${!LISTA[@]}"; do
    [ -n "${JA[$i]}" ] && continue
    IFS='|' read -r nome tipo alvo <<< "${LISTA[$i]}"
    echo "  - $nome"
done
echo "A subida continua em segundo plano, se o script ainda estiver rodando. Veja: ./subir.sh --status e ./subir.sh --log"
echo "Log completo: $LOG"
avisar "Subida incompleta. Faltam serviços."
exit 1
