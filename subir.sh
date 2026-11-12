#!/bin/bash
# Sobe o Heimdall-ai UMA vez só, guarda o log de cada subida e avisa quando tudo estiver no ar.
#
#   ./subir.sh                    sobe com --webui --terminal (o que você usa hoje)
#   ./subir.sh --update           sobe com os argumentos que você passar (os mesmos do start_heimdall.sh)
#   ./subir.sh --status           só confere agora o que está no ar, sem subir nada
#   ./subir.sh --log              mostra as últimas 40 linhas do log da subida atual
#   ./subir.sh --reiniciar [args] encerra a subida em andamento e sobe de novo
#
# O que ele faz:
#   1. Recusa subir se já houver uma subida em andamento (era isso que derrubava uma tentativa com a outra).
#   2. Grava o log em logs/heimdall-AAAAMMDD-HHMMSS.log e aponta heimdall.log para o da subida atual. Os logs anteriores
#      ficam guardados (os 15 mais recentes).
#   3. Confere, de poucos em poucos segundos, cada serviço que deve estar no ar nesta subida e conta o que já subiu.
#   4. No fim avisa: "Tudo no ar" (com aviso do macOS e voz) ou lista o que ficou faltando e onde olhar no log.
#
# Opções no ambiente ou no .env: SUBIR_ESPERA=900 (segundos de espera máxima), SUBIR_SOM=0 (sem voz nem notificação).

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
SCRIPT="${SUBIR_SCRIPT:-$PROJECT_DIR/start_heimdall.sh}"
LOGS="$PROJECT_DIR/logs"
ESPERA="${SUBIR_ESPERA:-900}"

# ---------------------------------------------------------------------------------------------------------------------
# Pedidos simples: --log, --status, --reiniciar
# ---------------------------------------------------------------------------------------------------------------------
MODO="subir"
case "$1" in
    --log) tail -n 40 "$PROJECT_DIR/heimdall.log" 2>/dev/null || echo "Ainda não há log. Rode ./subir.sh"; exit 0 ;;
    --status) MODO="status"; shift ;;
    --reiniciar) MODO="reiniciar"; shift ;;
esac

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
# O que deve estar no ar nesta subida (as mesmas condições do start_heimdall.sh)
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
    [ -n "$HEIMDALL_AGENTE_TOKEN" ] || [ "$HEIMDALL_AGENTE" = "1" ] || tem_arg --agente && LISTA+=("Agente do Mac|tcp|${HEIMDALL_AGENTE_PORT:-8003}")
    if [ "$HEIMDALL_MONITORING" != "0" ]; then
        LISTA+=("Uptime Kuma (status)|tcp|3001")
        LISTA+=("Dozzle (logs)|tcp|8081")
    fi
    if [ "$HEIMDALL_N8N" = "1" ] || tem_arg --n8n; then LISTA+=("n8n (automações)|tcp|5678"); fi
    if [ "$HEIMDALL_WEBUI" = "1" ] || tem_arg --webui; then LISTA+=("Open WebUI (chat)|tcp|3000"); fi
    if [ -n "$OPEN_TERMINAL_API_KEY" ] || tem_arg --terminal; then LISTA+=("Open Terminal|tcp|8002"); fi
    case "${HEIMDALL_AWS_EMULATOR:-auto}" in off) ;; *) LISTA+=("Emulador de AWS|tcp|4566") ;; esac
    if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
        case "${HEIMDALL_AWS_EMULATOR:-auto}" in off) ;; *) LISTA+=("Heimdall Cloud|http|http://127.0.0.1:${HEIMDALL_CLOUD_PORT:-8010}/saude") ;; esac
        LISTA+=("Heimdall Notas|http|http://127.0.0.1:${HEIMDALL_NOTAS_PORT:-${HEIMDALL_BIBLIOTECA_PORT:-8011}}/saude")
    fi
}

esta_no_ar() {  # $1 = tipo, $2 = alvo
    if [ "$1" = "tcp" ]; then
        nc -z 127.0.0.1 "$2" > /dev/null 2>&1
    else
        curl -fsS -m 3 -o /dev/null "$2" > /dev/null 2>&1
    fi
}

avisar() {  # $1 = texto curto para a notificação e a voz
    [ "$SUBIR_SOM" = "0" ] && return
    command -v osascript > /dev/null 2>&1 && osascript -e "display notification \"$1\" with title \"Heimdall-ai\"" > /dev/null 2>&1
    command -v say > /dev/null 2>&1 && say "Heimdall. $1" > /dev/null 2>&1 &
}

subida_em_andamento() {
    pgrep -f "start_heimdall.sh" > /dev/null 2>&1 && return 0
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
    if subida_em_andamento; then echo "Há uma subida em andamento (start_heimdall.sh rodando)."; else echo "Nenhuma subida em andamento."; fi
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
        pkill -f "start_heimdall.sh"
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
# Um heimdall.log solto de antes vira parte do histórico, em vez de ser sobrescrito.
if [ -f heimdall.log ] && [ ! -L heimdall.log ]; then
    mv heimdall.log "$LOGS/heimdall-anterior-$(date -r heimdall.log +%Y%m%d-%H%M%S 2>/dev/null || date +%Y%m%d-%H%M%S).log"
fi
LOG="$LOGS/heimdall-$(date +%Y%m%d-%H%M%S).log"
ln -sfn "$LOG" heimdall.log
# Guarda só os 15 logs mais recentes.
ls -1t "$LOGS"/heimdall-*.log 2> /dev/null | tail -n +16 | while read -r velho; do rm -f "$velho"; done

nohup bash "$SCRIPT" "${ARGS[@]}" >> "$LOG" 2>&1 &
PID=$!
echo "$PID" > "$LOGS/subida.pid"
echo "Subindo o Heimdall-ai (argumentos: ${ARGS[*]}). Log: $LOG"
echo "Esperando até $((ESPERA / 60)) minutos. Vou avisar cada serviço que ficar no ar."

declare -a JA
ok_n=0
inicio=$SECONDS
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
