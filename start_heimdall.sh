#!/bin/bash
# Uso:  ./start_heimdall.sh            sobe tudo (Open WebUI só se STUDIO_WEBUI=1 no .env)
#       ./start_heimdall.sh --webui    sobe tudo, incluindo o Open WebUI (porta 3000)
#       ./start_heimdall.sh --terminal sobe também o Open Terminal (porta 8002); a chave vem de
#                                      OPEN_TERMINAL_API_KEY no .env (se faltar, o script gera uma)
#       ./start_heimdall.sh --ingest   antes de subir o LiteLLM, indexa só o que mudou em knowledge/ (ou STUDIO_INGEST=1)
#       ./start_heimdall.sh --docling  sobe também o Docling (extração de PDFs com OCR) na porta 5001 (ou STUDIO_DOCLING=1)
#       ./start_heimdall.sh --n8n      sobe também o n8n (automações e agendamentos) em http://localhost:5678 (ou STUDIO_N8N=1)
#       ./start_heimdall.sh --agente   sobe também o agente do Mac (ponte do n8n com o app Notas) na porta 8003; sobe sozinho
#                                      quando STUDIO_AGENTE_TOKEN existe no .env (o scripts/instalar_automacoes_avancadas.sh cria)
#       Aparência do Open WebUI (no .env): STUDIO_WEBUI_NAME="Heimdall-ai" (nome); arquivos em branding/
#       (favicon.png, logo.png, splash.png...) são copiados para dentro do contêiner a cada subida.
#       Extras (opcionais, no .env): STUDIO_MONITORING=0 desliga Uptime Kuma e Dozzle;
#       STUDIO_AWS_EMULATOR=auto|moto|localstack|off escolhe o emulador de AWS.
#       STUDIO_WEBUI_ENXUTO=1 (padrão) | 0: Open WebUI sem Notas, Automações, imagem, código e recursos automáticos (STUDIO_WEBUI_TITULOS=1 mantém os títulos; STUDIO_WEBUI_EMBEDDING=ollama poupa mais memória)
#       STUDIO_AWS_EMULATOR_INICIO=demanda (padrão) | auto: com "demanda", o emulador de AWS (LocalStack ou Moto) já criado não sobe
#       junto com o Heimdall, para poupar memória; ligue quando for usar: studio lab --start (e desligue com studio lab --stop).
#       ./start_heimdall.sh --update   antes de subir, atualiza as imagens Docker (SearXNG,
#                                      Qdrant e Open WebUI), com backup; também vale STUDIO_UPDATE=1 no .env

# A pasta do projeto é a pasta deste script, então funciona em qualquer lugar.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Todos os logs ficam em logs/. A cada subida, o log anterior de cada serviço vai para logs/historico/ (os 5 mais recentes).
LOGS_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOGS_DIR/historico"
nova_log() {  # uso: nova_log nome  -> devolve o caminho de logs/nome.log, já guardando o anterior no histórico
    local alvo="$LOGS_DIR/$1.log"
    if [ -s "$alvo" ]; then
        mv "$alvo" "$LOGS_DIR/historico/$1-$(date -r "$alvo" +%Y%m%d-%H%M%S 2>/dev/null || date +%Y%m%d-%H%M%S).log" 2>/dev/null
        ls -1t "$LOGS_DIR/historico/$1"-*.log 2>/dev/null | tail -n +6 | while read -r velho; do rm -f "$velho"; done
    fi
    : > "$alvo"
    echo "$alvo"
}

VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    VENV_PYTHON="$(command -v python3)"
    echo "Aviso: venv não encontrado em $PROJECT_DIR/venv; usando $VENV_PYTHON"
fi
CONFIG_FILE="$PROJECT_DIR/litellm_config.yaml"
MCP_PORT=8000
PUBLIC_MCP_PORT=8001
DADOS_MCP_PORT=8004
TERMINAL_PORT=8002
AGENTE_PORT="${STUDIO_AGENTE_PORT:-8003}"
LAB_PORT="${STUDIO_LAB_PORT:-8010}"
NOTAS_PORT="${STUDIO_NOTAS_PORT:-8011}"
NEWS_PORT="${STUDIO_NEWS_PORT:-8012}"
LEARN_PORT="${STUDIO_LEARN_PORT:-8019}"
TRADING_PORT="${STUDIO_TRADING_PORT:-8020}"
MEMORY_PORT="${STUDIO_HUB_PORT:-${STUDIO_HUB_PORT:-8021}}"   # STUDIO_HUB_PORT: nome antigo, ainda aceito
SAUDE_PAINEL_PORT="${STUDIO_SAUDE_PAINEL_PORT:-8013}"
CONTROLS_PORT="${STUDIO_CONTROLS_PORT:-8017}"
JOGOS_PORT="${STUDIO_JOGOS_PORT:-8014}"
ACCOUNT_PORT="${STUDIO_ACCOUNT_PORT:-8018}"
FINANCE_PORT="${STUDIO_FINANCE_PORT:-8016}"
LLM_PORT=9000
WEBUI_PORT=3000

WANT_WEBUI=0
WANT_UPDATE=0
WANT_TERMINAL=0
WANT_INGEST=0
WANT_DOCLING=0
WANT_N8N=0
WANT_AGENTE=0
for arg in "$@"; do
    [ "$arg" = "--n8n" ] && WANT_N8N=1
    [ "$arg" = "--agente" ] && WANT_AGENTE=1
    [ "$arg" = "--webui" ] && WANT_WEBUI=1
    [ "$arg" = "--update" ] && WANT_UPDATE=1
    [ "$arg" = "--terminal" ] && WANT_TERMINAL=1
    [ "$arg" = "--ingest" ] && WANT_INGEST=1
    [ "$arg" = "--docling" ] && WANT_DOCLING=1
done

echo "=== [Heimdall System Boot] ==="
echo "Projeto: $PROJECT_DIR"

# --- Chave mestra do LiteLLM (guardada em .env, nunca no YAML) ---
if [ -f .env ]; then
    # Troca no .env os nomes antigos de variável (HEIMDALL_*) pelos novos (STUDIO_*), com cópia em .env.bak
    "$VENV_PYTHON" -c "import heimdall_config as c; t = c.renomear_antigas(); print('Variáveis do .env com o nome novo:', ', '.join(t)) if t else None" 2>/dev/null
    set -a; source .env; set +a
    LAB_PORT="${STUDIO_LAB_PORT:-8010}"
fi
# Acrescenta uma linha ao .env sem colar na última (se o arquivo não terminar em quebra de linha).
env_append() {
    if [ -s .env ] && [ "$(tail -c1 .env | wc -l | tr -d ' ')" = "0" ]; then
        echo >> .env
    fi
    echo "$1" >> .env
}
if [ -z "$LITELLM_MASTER_KEY" ]; then
    LITELLM_MASTER_KEY="sk-$(openssl rand -hex 24)"
    env_append "LITELLM_MASTER_KEY=$LITELLM_MASTER_KEY"
    chmod 600 .env
    echo "Nova chave mestra gerada e salva em $PROJECT_DIR/.env"
fi
export LITELLM_MASTER_KEY
# O LiteLLM desliga servidores MCP stdio por padrão; o aws_docs precisa deste.
export LITELLM_ENABLE_MCP_STDIO=true
[ "$STUDIO_WEBUI" = "1" ] && WANT_WEBUI=1
[ "$STUDIO_UPDATE" = "1" ] && WANT_UPDATE=1
[ "$STUDIO_INGEST" = "1" ] && WANT_INGEST=1
[ "$STUDIO_DOCLING" = "1" ] && WANT_DOCLING=1
[ "$STUDIO_N8N" = "1" ] && WANT_N8N=1
# Open Terminal sobe se houver chave no .env ou se o script receber --terminal.
[ -n "$OPEN_TERMINAL_API_KEY" ] && WANT_TERMINAL=1
if [ "$WANT_TERMINAL" = "1" ] && [ -z "$OPEN_TERMINAL_API_KEY" ]; then
    OPEN_TERMINAL_API_KEY="$(openssl rand -hex 24)"
    env_append "OPEN_TERMINAL_API_KEY='$OPEN_TERMINAL_API_KEY'"
    chmod 600 .env
    echo "Nova chave do Open Terminal gerada e salva em $PROJECT_DIR/.env"
fi
export OPEN_TERMINAL_API_KEY
# Agente do Mac (ponte do n8n com o app Notas): sobe se houver token no .env ou se o script receber --agente.
[ -n "$STUDIO_AGENTE_TOKEN" ] && WANT_AGENTE=1
[ "$STUDIO_AGENTE" = "1" ] && WANT_AGENTE=1
if [ "$WANT_AGENTE" = "1" ] && [ -z "$STUDIO_AGENTE_TOKEN" ]; then
    STUDIO_AGENTE_TOKEN="$(openssl rand -hex 24)"
    env_append "STUDIO_AGENTE_TOKEN='$STUDIO_AGENTE_TOKEN'"
    chmod 600 .env
    echo "Novo token do agente do Mac gerado e salvo em $PROJECT_DIR/.env"
fi
export STUDIO_AGENTE_TOKEN

echo "[0/7] Liberando portas em uso..."
lsof -ti:$AGENTE_PORT | xargs kill -9 2>/dev/null
lsof -ti:$LAB_PORT | xargs kill -9 2>/dev/null
lsof -ti:$NOTAS_PORT | xargs kill -9 2>/dev/null
lsof -ti:$NEWS_PORT | xargs kill -9 2>/dev/null
lsof -ti:$LEARN_PORT | xargs kill -9 2>/dev/null
lsof -ti:$TRADING_PORT | xargs kill -9 2>/dev/null
lsof -ti:$MEMORY_PORT | xargs kill -9 2>/dev/null
lsof -ti:$SAUDE_PAINEL_PORT | xargs kill -9 2>/dev/null
lsof -ti:$CONTROLS_PORT | xargs kill -9 2>/dev/null
lsof -ti:$JOGOS_PORT | xargs kill -9 2>/dev/null
lsof -ti:$ACCOUNT_PORT | xargs kill -9 2>/dev/null
lsof -ti:$FINANCE_PORT | xargs kill -9 2>/dev/null
lsof -ti:$LLM_PORT | xargs kill -9 2>/dev/null
lsof -ti:$MCP_PORT | xargs kill -9 2>/dev/null
lsof -ti:$PUBLIC_MCP_PORT | xargs kill -9 2>/dev/null
lsof -ti:$DADOS_MCP_PORT | xargs kill -9 2>/dev/null
lsof -ti:$TERMINAL_PORT | xargs kill -9 2>/dev/null
sleep 1

# --- Docker ---
if ! docker info > /dev/null 2>&1; then
    echo "[1/7] Subindo o Docker Desktop..."
    open -g -j -a Docker   # em segundo plano e escondido: não rouba o foco nem abre a janela
    ESPERA=0
    while ! docker info > /dev/null 2>&1; do
        sleep 2
        ESPERA=$((ESPERA+2))
        if [ "$ESPERA" = 40 ]; then   # se o modo escondido não subiu o Docker, tenta o modo normal
            echo "O Docker não subiu escondido; abrindo do jeito normal..."
            open -a Docker
        fi
    done
fi
echo "[1/7] Docker pronto."

# Rede própria para os contêineres se enxergarem pelo nome.
docker network inspect heimdall > /dev/null 2>&1 || docker network create heimdall > /dev/null

# --- Pasta do Qdrant: qdrant_storage passou a se chamar qdrant ---
# O contêiner guarda o caminho antigo; por isso ele é removido (os dados ficam na pasta, no Mac) e recriado com o caminho novo mais abaixo.
# Se não der para renomear, tudo segue com qdrant_storage, sem perder nada.
QDRANT_DIR=qdrant
if [ -d qdrant_storage ] && [ ! -e qdrant ]; then
    docker rm -f qdrant > /dev/null 2>&1
    mv qdrant_storage qdrant || QDRANT_DIR=qdrant_storage
fi
[ -d qdrant_storage ] && [ ! -e qdrant ] && QDRANT_DIR=qdrant_storage

# --- Atualização opcional das imagens (SearXNG, Qdrant, Open WebUI e extras) ---
if [ "$WANT_UPDATE" = "1" ]; then
    echo "     Atualizando imagens Docker..."
    mkdir -p backups
    STAMP="$(date +%Y%m%d-%H%M%S)"
    if [ -d "$QDRANT_DIR" ]; then
        tar czf "backups/qdrant-$STAMP.tgz" "$QDRANT_DIR" && echo "     Backup: backups/qdrant-$STAMP.tgz"
    fi
    if docker volume inspect open-webui > /dev/null 2>&1; then
        docker run --rm -v open-webui:/data -v "$PROJECT_DIR/backups":/backup alpine \
            tar czf "/backup/open-webui-$STAMP.tgz" -C /data . 2>/dev/null \
            && echo "     Backup: backups/open-webui-$STAMP.tgz" \
            || echo "     Aviso: não consegui fazer o backup do volume open-webui."
    fi
    UPDATE_IMAGES="searxng/searxng qdrant/qdrant ghcr.io/open-webui/open-webui:main"
    if [ "$STUDIO_MONITORING" != "0" ]; then
        UPDATE_IMAGES="$UPDATE_IMAGES louislam/uptime-kuma:2 amir20/dozzle:latest"
    fi
    if [ "$WANT_DOCLING" = "1" ]; then
        UPDATE_IMAGES="$UPDATE_IMAGES quay.io/docling-project/docling-serve"
    fi
    if [ "$WANT_N8N" = "1" ]; then
        UPDATE_IMAGES="$UPDATE_IMAGES docker.n8n.io/n8nio/n8n:latest"
        # Backup do volume do n8n (fluxos e credenciais ficam lá dentro).
        if docker volume inspect n8n_data > /dev/null 2>&1; then
            docker run --rm -v n8n_data:/data -v "$PROJECT_DIR/backups":/backup alpine \
                tar czf "/backup/n8n_data-$STAMP.tgz" -C /data . 2>/dev/null \
                && echo "     Backup: backups/n8n_data-$STAMP.tgz" \
                || echo "     Aviso: não consegui fazer o backup do volume n8n_data."
        fi
    fi
    # Só ficam os últimos backups de cada tipo (STUDIO_BACKUPS_MANTER no .env muda; padrão 3). Cada cópia do Open WebUI tem cerca de 1 GB.
    bash "$PROJECT_DIR/scripts/podar_backups.sh"
    case "$STUDIO_AWS_EMULATOR" in
        off) ;;
        moto) UPDATE_IMAGES="$UPDATE_IMAGES motoserver/moto:latest" ;;
        localstack) UPDATE_IMAGES="$UPDATE_IMAGES localstack/localstack:latest" ;;
        *) if [ -n "$LOCALSTACK_AUTH_TOKEN" ]; then UPDATE_IMAGES="$UPDATE_IMAGES localstack/localstack:latest"; else UPDATE_IMAGES="$UPDATE_IMAGES motoserver/moto:latest"; fi ;;
    esac
    for IMG in $UPDATE_IMAGES; do
        if docker pull "$IMG" > /dev/null 2>&1; then
            echo "       atualizada: $IMG"
        else
            echo "       falhou (sem internet?): $IMG; segue com a versão que já existe"
        fi
    done
    # Recria os contêineres para usarem a imagem nova. Dados e configurações ficam
    # nas pastas montadas (searxng/ e qdrant/) e no volume open-webui.
    docker rm -f searxng qdrant uptime-kuma dozzle moto localstack docling n8n > /dev/null 2>&1
fi

# --- SearXNG ---
if [ ! -f searxng/settings.yml ]; then
    mkdir -p searxng
    cat > searxng/settings.yml <<EOF
use_default_settings: true
server:
  secret_key: "$(openssl rand -hex 32)"
  limiter: false
search:
  formats:
    - html
    - json
EOF
    echo "Criado searxng/settings.yml com o formato JSON habilitado."
fi

if docker ps -a --format '{{.Names}}' | grep -qx searxng; then
    docker start searxng > /dev/null
else
    docker run -d --name searxng --restart unless-stopped \
        --network heimdall \
        -p 127.0.0.1:8080:8080 \
        -v "$PROJECT_DIR/searxng:/etc/searxng" \
        searxng/searxng > /dev/null
fi
docker network connect heimdall searxng 2>/dev/null || true
echo "[2/7] SearXNG pronto (porta 8080)."

# --- Qdrant (base vetorial da ferramenta rag_search) ---
mkdir -p knowledge "$QDRANT_DIR"
if docker ps -a --format '{{.Names}}' | grep -qx qdrant; then
    docker start qdrant > /dev/null
else
    docker run -d --name qdrant --restart unless-stopped \
        --network heimdall \
        -p 127.0.0.1:6333:6333 \
        -v "$PROJECT_DIR/$QDRANT_DIR:/qdrant/storage" \
        qdrant/qdrant > /dev/null
fi
docker network connect heimdall qdrant 2>/dev/null || true
COUNTER=0
while ! curl -s http://localhost:6333/collections > /dev/null 2>&1; do
    sleep 1
    COUNTER=$((COUNTER+1))
    if [ $COUNTER -gt 30 ]; then
        echo "Aviso: o Qdrant não respondeu em 30s; rag_search não vai funcionar (docker logs qdrant)."
        break
    fi
done
echo "[3/7] Qdrant pronto (porta 6333, só local). Coloque documentos em knowledge/ e rode: python ingest_docs.py"

# --- Extras: monitoramento (Uptime Kuma e Dozzle) e emulador de AWS ---
# Tudo escuta só em 127.0.0.1. Desligue o monitoramento com STUDIO_MONITORING=0 no .env.
if [ "$STUDIO_MONITORING" != "0" ]; then
    if docker ps -a --format '{{.Names}}' | grep -qx uptime-kuma; then
        docker start uptime-kuma > /dev/null
    else
        docker run -d --name uptime-kuma --restart unless-stopped \
            --network heimdall \
            --add-host=host.docker.internal:host-gateway \
            -p 127.0.0.1:3001:3001 \
            -v uptime-kuma:/app/data \
            louislam/uptime-kuma:2 > /dev/null
    fi
    if docker ps -a --format '{{.Names}}' | grep -qx dozzle; then
        docker start dozzle > /dev/null
    else
        # Dozzle lê os logs pelo socket do Docker (montado somente leitura).
        docker run -d --name dozzle --restart unless-stopped \
            --network heimdall \
            -e DOZZLE_NO_ANALYTICS=true \
            -p 127.0.0.1:8081:8080 \
            -v /var/run/docker.sock:/var/run/docker.sock:ro \
            amir20/dozzle:latest > /dev/null
    fi
    echo "     Uptime Kuma em http://localhost:3001 e Dozzle (logs) em http://localhost:8081"
else
    docker stop uptime-kuma dozzle > /dev/null 2>&1
    echo "     Monitoramento desligado (STUDIO_MONITORING=0)."
fi

# --- n8n (opcional): automações e agendamentos. Ligue com --n8n ou STUDIO_N8N=1 no .env ---
# Escuta só em 127.0.0.1:5678. Fluxos e credenciais ficam no volume n8n_data (sobrevivem a atualizações).
# Os agendamentos só disparam com o Mac ligado, acordado e com o Docker rodando.
if [ "$WANT_N8N" = "1" ]; then
    # O contêiner é recriado a cada subida para valer as opções do .env (fluxos e credenciais ficam no volume n8n_data).
    docker rm -f n8n > /dev/null 2>&1
    N8N_TZ="${STUDIO_TZ:-America/Sao_Paulo}"
    # Sessão do login do n8n: padrão 8760 horas (1 ano), para o login próprio quase não aparecer atrás do Access.
    # STUDIO_N8N_SEM_LOGIN=1 tenta N8N_BASIC_AUTH_ACTIVE=false (opção antiga; as versões atuais do n8n costumam ignorá-la).
    docker run -d --name n8n --restart unless-stopped \
        --network heimdall \
        --add-host=host.docker.internal:host-gateway \
        -p 127.0.0.1:5678:5678 \
        -e TZ="$N8N_TZ" \
        -e GENERIC_TIMEZONE="$N8N_TZ" \
        -e N8N_SECURE_COOKIE=false \
        -e N8N_DIAGNOSTICS_ENABLED=false \
        -e N8N_USER_MANAGEMENT_JWT_DURATION_HOURS="${STUDIO_N8N_SESSAO_HORAS:-8760}" \
        ${STUDIO_N8N_SEM_LOGIN:+-e N8N_BASIC_AUTH_ACTIVE=false} \
        ${STUDIO_N8N_LOCALE:+-e N8N_DEFAULT_LOCALE=$STUDIO_N8N_LOCALE} \
        -v n8n_data:/home/node/.n8n \
        docker.n8n.io/n8nio/n8n:latest > /dev/null
    echo "     n8n em http://localhost:5678 (a primeira conta criada vira a dona)."
else
    docker stop n8n > /dev/null 2>&1
fi

# Emulador de AWS na porta 4566. STUDIO_AWS_EMULATOR=auto (padrão) | moto | localstack | off.
# auto: usa LocalStack se houver LOCALSTACK_AUTH_TOKEN no .env; senão, usa o Moto (livre, sem conta).
# STUDIO_AWS_EMULATOR_INICIO=demanda (padrão): se o contêiner do emulador já existe, ele fica desligado ao subir e é ligado
# só quando necessário (studio lab --start), porque ocupa de 300 a 700 MB de memória. Na primeira vez, sem contêiner, ele é criado.
AWS_EMU="${STUDIO_AWS_EMULATOR:-auto}"
if [ "$AWS_EMU" = "auto" ]; then
    if [ -n "$LOCALSTACK_AUTH_TOKEN" ]; then AWS_EMU=localstack; else AWS_EMU=moto; fi
fi
if [ "$AWS_EMU" = "localstack" ] && [ -z "$LOCALSTACK_AUTH_TOKEN" ]; then
    echo "Aviso: o LocalStack exige conta e LOCALSTACK_AUTH_TOKEN no .env; usando o Moto no lugar."
    AWS_EMU=moto
fi
if [ "$AWS_EMU" != "off" ] && [ "${STUDIO_AWS_EMULATOR_INICIO:-demanda}" = "demanda" ] \
    && docker ps -a --format '{{.Names}}' | grep -qE '^(localstack|moto)$'; then
    AWS_EMU=demanda
fi
case "$AWS_EMU" in
    demanda)
        docker stop moto localstack > /dev/null 2>&1
        echo "     Emulador de AWS sob demanda (desligado para poupar memória). Para ligar: studio lab --start; para desligar: studio lab --stop." ;;
    moto)
        docker rm -f localstack > /dev/null 2>&1
        if docker ps -a --format '{{.Names}}' | grep -qx moto; then
            docker start moto > /dev/null
        else
            docker run -d --name moto --network heimdall \
                -p 127.0.0.1:4566:5000 \
                motoserver/moto:latest > /dev/null
        fi
        echo "     Emulador de AWS (Moto) em http://localhost:4566 (use credenciais falsas)" ;;
    localstack)
        docker rm -f moto > /dev/null 2>&1
        # Lambda: o LocalStack executa as funções em contêineres, então precisa do socket do Docker (e da rede heimdall, para os
        # contêineres das funções acharem o LocalStack). Ligado por padrão; STUDIO_LOCALSTACK_DOCKER=0 no .env desliga.
        # Atenção: isso dá ao contêiner do LocalStack controle do Docker do Mac. Quem passa pelo painel Studio Lab (senha e
        # código de 6 dígitos) consegue executar código em contêineres.
        LS_DOCKER=()
        LS_QUER=0
        if [ "${STUDIO_LOCALSTACK_DOCKER:-1}" != "0" ]; then
            LS_QUER=1
            LS_DOCKER=(-v /var/run/docker.sock:/var/run/docker.sock -e LAMBDA_DOCKER_NETWORK=heimdall)
        fi
        if docker ps -a --format '{{.Names}}' | grep -qx localstack; then
            LS_TEM=0
            docker inspect localstack --format '{{range .Mounts}}{{.Destination}} {{end}}' 2>/dev/null | grep -q 'docker.sock' && LS_TEM=1
            if [ "$LS_TEM" != "$LS_QUER" ]; then
                echo "     Recriando o LocalStack para aplicar STUDIO_LOCALSTACK_DOCKER (o volume localstack é mantido)."
                docker rm -f localstack > /dev/null 2>&1
            fi
        fi
        if docker ps -a --format '{{.Names}}' | grep -qx localstack; then
            docker start localstack > /dev/null
        else
            docker run -d --name localstack --network heimdall \
                -p 127.0.0.1:4566:4566 \
                -e LOCALSTACK_AUTH_TOKEN="$LOCALSTACK_AUTH_TOKEN" \
                "${LS_DOCKER[@]}" \
                -v localstack:/var/lib/localstack \
                localstack/localstack:latest > /dev/null
        fi
        echo "     Emulador de AWS (LocalStack) em http://localhost:4566 (use credenciais falsas)" ;;
    *)
        docker stop moto localstack > /dev/null 2>&1
        echo "     Emulador de AWS desligado." ;;
esac
# Se o LocalStack parar logo ao subir (o caso comum é o LOCALSTACK_AUTH_TOKEN recusado, código de saída 55), cai para o Moto,
# para o painel Studio Lab e o código de estudo continuarem com um emulador no ar.
if [ "$AWS_EMU" = "localstack" ]; then
    LS_PAROU=0
    for _ in 1 2 3 4 5 6 7 8; do
        sleep 1
        [ "$(docker inspect -f '{{.State.Running}}' localstack 2>/dev/null)" = "true" ] || { LS_PAROU=1; break; }
    done
    if [ "$LS_PAROU" = "1" ]; then
        LS_SAIDA="$(docker inspect -f '{{.State.ExitCode}}' localstack 2>/dev/null)"
        if [ "$LS_SAIDA" = "55" ]; then
            echo "Aviso: o LocalStack recusou a licença (LOCALSTACK_AUTH_TOKEN inválido). Gere outra chave em app.localstack.cloud e grave no .env."
        else
            echo "Aviso: o LocalStack parou (código $LS_SAIDA). Veja: docker logs --tail 30 localstack"
        fi
        echo "     Usando o Moto no lugar, no mesmo endereço (Lambda, Glue e Athena ficam só simulados)."
        docker rm -f localstack > /dev/null 2>&1
        AWS_EMU=moto
        if docker ps -a --format '{{.Names}}' | grep -qx moto; then
            docker start moto > /dev/null
        else
            docker run -d --name moto --network heimdall -p 127.0.0.1:4566:5000 motoserver/moto:latest > /dev/null
        fi
    fi
fi

# --- Ollama ---
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[4/7] Iniciando o Ollama..."
    # OLLAMA_HOST do .env vale aqui; se não houver, o Ollama escuta só em 127.0.0.1.
    # Memória: no máximo 2 modelos carregados (um de chat e um de embeddings), 1 pedido por vez
    # (pedidos em paralelo multiplicam o cache de contexto) e cache de contexto quantizado.
    OLLAMA_CONTEXT_LENGTH=8192 \
    OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}" \
    OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}" \
    OLLAMA_FLASH_ATTENTION="${OLLAMA_FLASH_ATTENTION:-1}" \
    OLLAMA_KV_CACHE_TYPE="${OLLAMA_KV_CACHE_TYPE:-q8_0}" \
    ollama serve > /dev/null 2>&1 &
    sleep 3
else
    echo "[4/7] Ollama já estava rodando (o contexto vem do num_ctx do litellm_config.yaml)."
fi
OLLAMA_BIND="$(lsof -nP -iTCP:11434 -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $9}' | sort -u | tr '\n' ' ')"
case "$OLLAMA_BIND" in
    *"*:11434"*) echo "     Ollama escutando em todas as interfaces (*:11434), acessível pela rede/Tailscale." ;;
    *127.0.0.1:11434*|*"[::1]:11434"*) echo "     Ollama escutando só em localhost ($OLLAMA_BIND). Para abrir à rede: OLLAMA_HOST=0.0.0.0:11434 (veja as instruções)." ;;
    *) echo "     Não consegui confirmar onde o Ollama escuta ($OLLAMA_BIND)." ;;
esac

# --- Docling (opcional): extrai texto de PDFs complexos e escaneados, com OCR ---
# Pesado: o Docker Desktop precisa de uns 8 GB de RAM, e sem GPU o processamento é lento.
# Por isso fica desligado por padrão e sem reinício automático.
if [ "$WANT_DOCLING" = "1" ]; then
    if docker ps -a --format '{{.Names}}' | grep -qx docling; then
        docker start docling > /dev/null
    else
        docker run -d --name docling \
            --network heimdall \
            -p 127.0.0.1:5001:5001 \
            -e DOCLING_SERVE_ENABLE_UI=true \
            -e UVICORN_WORKERS=1 \
            -e DOCLING_SERVE_MAX_SYNC_WAIT=600 \
            quay.io/docling-project/docling-serve > /dev/null
    fi
    echo "     Docling em http://localhost:5001 (interface em /ui). No Open WebUI use http://docling:5001"
else
    docker stop docling > /dev/null 2>&1
fi

# --- Indexação incremental da base de conhecimento (opcional) ---
# Só reprocessa arquivos novos ou alterados; os demais são pulados pelo hash.
if [ "$WANT_INGEST" = "1" ]; then
    if ls knowledge/* > /dev/null 2>&1; then
        ollama list 2>/dev/null | grep -q "nomic-embed-text" || ollama pull nomic-embed-text > /dev/null 2>&1
        echo "     Indexando knowledge/ em segundo plano (log em logs/ingest.log)..."
        "$VENV_PYTHON" ingest_docs.py > "$(nova_log ingest)" 2>&1 &
    else
        echo "     Nada em knowledge/ para indexar."
    fi
fi

# --- uv/uvx (servidor MCP de documentação da AWS) ---
if ! command -v uvx > /dev/null 2>&1; then
    echo "Aviso: 'uvx' não encontrado. A documentação da AWS (aws_docs) não carregará. Instale com: brew install uv"
fi

# --- Servidores MCP: grupo do Mac (admin, 8000) e grupo público (convidados, 8001) ---
echo "[5/7] Subindo os servidores MCP do Heimdall..."
"$VENV_PYTHON" heimdall_mcp.py --group mac > "$(nova_log mcp_debug)" 2>&1 &
MCP_PID=$!
"$VENV_PYTHON" heimdall_mcp.py --group public > "$(nova_log mcp_public_debug)" 2>&1 &
MCP_PUBLIC_PID=$!
"$VENV_PYTHON" heimdall_mcp.py --group dados > "$(nova_log mcp_dados_debug)" 2>&1 &
MCP_DADOS_PID=$!
TERMINAL_PID=""
AGENTE_PID=""
trap 'kill $MCP_PID $MCP_PUBLIC_PID $MCP_DADOS_PID $TERMINAL_PID $AGENTE_PID 2>/dev/null' EXIT INT TERM

for PORT in $MCP_PORT $PUBLIC_MCP_PORT $DADOS_MCP_PORT; do
    COUNTER=0
    while ! nc -z localhost $PORT > /dev/null 2>&1; do
        sleep 1
        COUNTER=$((COUNTER+1))
        if [ $COUNTER -gt 15 ]; then
            echo "Erro: o servidor MCP da porta $PORT demorou demais para subir. Veja logs/mcp_debug.log, logs/mcp_public_debug.log e logs/mcp_dados_debug.log:"
            tail -n 20 "$LOGS_DIR/mcp_debug.log" "$LOGS_DIR/mcp_public_debug.log" "$LOGS_DIR/mcp_dados_debug.log"
            exit 1
        fi
    done
done
echo "[5/7] MCP do Mac (admin) em http://localhost:$MCP_PORT/mcp e MCP público em http://localhost:$PUBLIC_MCP_PORT/mcp e MCP de dados (só o banco, só esta máquina) em http://127.0.0.1:$DADOS_MCP_PORT/mcp"

# --- Agente do Mac (opcional): lê o app Notas e grava notas/Markdown só em pastas "Heimdall*" ---
# Usa a biblioteca padrão do Python. Escuta em 127.0.0.1 (STUDIO_AGENTE_HOST=0.0.0.0 abre à rede) e exige o token.
if [ "$WANT_AGENTE" = "1" ]; then
    if [ -f heimdall_agente.py ]; then
        STUDIO_AGENTE_PORT="$AGENTE_PORT" "$VENV_PYTHON" heimdall_agente.py > "$(nova_log agente_debug)" 2>&1 &
        AGENTE_PID=$!
        COUNTER=0
        while ! nc -z localhost $AGENTE_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 15 ]; then
                echo "Aviso: o agente do Mac não respondeu em 15s. Veja logs/agente_debug.log."
                break
            fi
        done
        echo "     Agente do Mac na porta $AGENTE_PORT (Second Brain e Digest). Na primeira vez, autorize o acesso ao app Notas."
    else
        echo "Aviso: heimdall_agente.py não está na pasta do projeto; o agente do Mac não foi iniciado."
    fi
fi

# --- Studio Lab (painel web do emulador de AWS): sobe sozinho se houver senha e código no .env ---
# Para configurar: python3 heimdall_acesso.py --tudo. Escuta só em 127.0.0.1; o acesso público vem do túnel Cloudflare.
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ] && [ "$AWS_EMU" != "off" ]; then
    if [ -f heimdall_lab.py ]; then
        STUDIO_LAB_PORT="$LAB_PORT" "$VENV_PYTHON" heimdall_lab.py > "$(nova_log lab_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $LAB_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o painel Studio Lab não respondeu em 10s. Veja logs/lab_debug.log."
                break
            fi
        done
        echo "     Studio Lab (painel do emulador de AWS) em http://localhost:$LAB_PORT"
    fi
fi

# --- Studio Notes (site para ler as notas de estudo e ouvir os áudios): mesmo login do Studio Lab ---
# Escuta só em 127.0.0.1; o acesso público, se você quiser, vem do túnel Cloudflare (memory.heimdall-ai.tech).
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_notas.py ]; then
        STUDIO_NOTAS_PORT="$NOTAS_PORT" "$VENV_PYTHON" heimdall_notas.py > "$(nova_log notas_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $NOTAS_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Studio Notes não respondeu em 10s. Veja logs/notas_debug.log."
                break
            fi
        done
        echo "     Studio Notes (notas e áudios) em http://localhost:$NOTAS_PORT"
    fi
fi

# --- Studio Learn (plataforma de estudos; fase 1: pastas com categoria e tipo, importação de documentos) ---
# Desligado por padrão: ligue com STUDIO_LEARN=1 no .env (studio env --set STUDIO_LEARN 1). Mesmo login do Studio Lab.
if [ "${STUDIO_LEARN:-0}" = "1" ] && [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_learn.py ]; then
        STUDIO_LEARN_PORT="$LEARN_PORT" "$VENV_PYTHON" heimdall_learn.py > "$(nova_log learn_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $LEARN_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Studio Learn não respondeu em 10s. Veja logs/learn_debug.log."
                break
            fi
        done
        echo "     Studio Learn (estudos) em http://localhost:$LEARN_PORT"
    fi
fi

# --- Studio Trading (mesa de operações em simulação) ---
# Desligado por padrão: ligue com STUDIO_TRADING=1 no .env (studio env --set STUDIO_TRADING 1). Mesmo login do Studio Lab.
if [ "${STUDIO_TRADING:-0}" = "1" ] && [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_trading.py ]; then
        STUDIO_TRADING_PORT="$TRADING_PORT" "$VENV_PYTHON" heimdall_trading.py > "$(nova_log trading_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $TRADING_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Studio Trading não respondeu em 10s. Veja logs/trading_debug.log."
                break
            fi
        done
        echo "     Studio Trading (mesa de operações em simulação) em http://localhost:$TRADING_PORT"
    fi
fi

# --- Studio Hub (acervo pesquisável; antes se chamava Library) ---
# Desligado por padrão: ligue com STUDIO_HUB=1 no .env (studio env --set STUDIO_HUB 1; o nome antigo STUDIO_HUB=1 continua valendo). Mesmo login do Studio Lab.
if [ "${STUDIO_HUB:-${STUDIO_HUB:-0}}" = "1" ] && [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ "${STUDIO_HUB_MOTOR:-${STUDIO_HUB_MOTOR:-interno}}" = "paperless" ] && command -v docker > /dev/null 2>&1 && [ -f paperless/docker-compose.yml ]; then
        docker compose -f paperless/docker-compose.yml --env-file .env up -d > "$(nova_log paperless_debug)" 2>&1 || echo "Aviso: não consegui subir o Paperless-ngx (motor do Hub). Veja logs/paperless_debug.log."
    fi
    if [ -f heimdall_memory.py ]; then
        STUDIO_HUB_PORT="$MEMORY_PORT" "$VENV_PYTHON" heimdall_memory.py > "$(nova_log memory_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $MEMORY_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Studio Hub não respondeu em 10s. Veja logs/memory_debug.log."
                break
            fi
        done
        echo "     Studio Hub (acervo pesquisável) em http://localhost:$MEMORY_PORT"
    fi
fi

# --- Studio News (notícias das últimas 24 h com resumo de IA e feeds RSS): mesmo login do Studio Lab ---
# Atualiza sozinho de 30 em 30 minutos. Escuta só em 127.0.0.1; o acesso de fora, se você quiser, vem do túnel Cloudflare (news.heimdall-ai.tech).
# Os resumos usam o LiteLLM (porta $LLM_PORT): enquanto ele não estiver no ar, as matérias ficam na fila e o serviço tenta de novo na próxima atualização.
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_news.py ]; then
        STUDIO_NEWS_PORT="$NEWS_PORT" "$VENV_PYTHON" heimdall_news.py > "$(nova_log news_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $NEWS_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Studio News não respondeu em 10s. Veja logs/news_debug.log."
                break
            fi
        done
        echo "     Studio News (notícias e feeds RSS) em http://localhost:$NEWS_PORT"
        if [ -z "$STUDIO_NEWS_RSS_TOKEN" ]; then
            echo "     Feeds RSS desligados: rode  python3 heimdall_news.py --token  para criar a chave."
        fi
    fi
fi

# --- Studio Health (painel com as análises do app Saúde, somente leitura): mesmo login do Studio Lab ---
# Escuta só em 127.0.0.1; o acesso de fora, se você quiser, vem do túnel Cloudflare (health.heimdall-ai.tech).
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_painel_saude.py ]; then
        STUDIO_SAUDE_PAINEL_PORT="$SAUDE_PAINEL_PORT" "$VENV_PYTHON" heimdall_painel_saude.py > "$(nova_log saude_painel_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $SAUDE_PAINEL_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o painel Studio Health não respondeu em 10s. Veja logs/saude_painel_debug.log."
                break
            fi
        done
        echo "     Studio Health (painel de saúde) em http://localhost:$SAUDE_PAINEL_PORT"
    fi
fi

# --- Controls (terminal completo e painel de serviços): mesmo login do Studio Lab ---
# Escuta só em 127.0.0.1; o acesso de fora vem do túnel Cloudflare (controls.heimdall-ai.tech), atrás do Cloudflare Access. Quem entra manda no Mac.
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_controls.py ]; then
        if nc -z localhost $CONTROLS_PORT > /dev/null 2>&1; then
            echo "     Controls já estava no ar (foi ele quem pediu esta subida)."
        else
            STUDIO_CONTROLS_PORT="$CONTROLS_PORT" STUDIO_DIR="$(pwd)" "$VENV_PYTHON" heimdall_controls.py > "$(nova_log controls_debug)" 2>&1 &
        fi
        COUNTER=0
        while ! nc -z localhost $CONTROLS_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o Controls não respondeu em 10s. Veja logs/controls_debug.log."
                break
            fi
        done
        echo "     Controls em http://localhost:$CONTROLS_PORT"
    fi
fi

# --- Studio Games (jogos leves para leitor de tela, no navegador): mesmo login do Studio Lab ---
# Escuta só em 127.0.0.1; o acesso de fora, se você quiser, vem do túnel Cloudflare (games.heimdall-ai.tech).
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_jogos.py ]; then
        STUDIO_JOGOS_PORT="$JOGOS_PORT" "$VENV_PYTHON" heimdall_jogos.py > "$(nova_log jogos_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $JOGOS_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o servidor Studio Games não respondeu em 10s. Veja logs/jogos_debug.log."
                break
            fi
        done
        echo "     Studio Games em http://localhost:$JOGOS_PORT"
    fi
fi

# --- Account (account.heimdall-ai.tech): tour dos serviços de cada pessoa e a identidade que o site heimdall-ai.tech mostra ---
# Escuta só em 127.0.0.1; o acesso de fora vem do túnel Cloudflare, com o Access na frente. Não precisa de senha: só atende quem o Access aprovou.
if [ -f heimdall_account.py ]; then
    STUDIO_ACCOUNT_PORT="$ACCOUNT_PORT" "$VENV_PYTHON" heimdall_account.py > "$(nova_log account_debug)" 2>&1 &
    COUNTER=0
    while ! nc -z localhost $ACCOUNT_PORT > /dev/null 2>&1; do
        sleep 1
        COUNTER=$((COUNTER+1))
        if [ $COUNTER -gt 10 ]; then
            echo "Aviso: o servidor Account não respondeu em 10s. Veja logs/account_debug.log."
            break
        fi
    done
    echo "     Account em http://localhost:$ACCOUNT_PORT"
fi

# --- Studio Finance (extratos, categorias e tendências): mesmo login do Studio Lab ---
# Escuta só em 127.0.0.1; o acesso de fora, se você quiser, vem do túnel Cloudflare (finance.heimdall-ai.tech).
# Os dados ficam em finance/ (fora do git) e nunca saem do Mac.
if [ -n "$HEIMDALL_CLOUD_SENHA_HASH" ] && [ -n "$HEIMDALL_CLOUD_TOTP_SEGREDO" ]; then
    if [ -f heimdall_finance.py ]; then
        STUDIO_FINANCE_PORT="$FINANCE_PORT" "$VENV_PYTHON" heimdall_finance.py > "$(nova_log finance_debug)" 2>&1 &
        COUNTER=0
        while ! nc -z localhost $FINANCE_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 10 ]; then
                echo "Aviso: o servidor Studio Finance não respondeu em 10s. Veja logs/finance_debug.log."
                break
            fi
        done
        echo "     Studio Finance em http://localhost:$FINANCE_PORT"
    fi
fi

# --- Open Terminal (opcional): terminal que roda NO Mac, com as permissões do seu usuário ---
if [ "$WANT_TERMINAL" = "1" ]; then
    if command -v uvx > /dev/null 2>&1; then
        # A chave vai por variável de ambiente (não por argumento), para não aparecer no "ps".
        # O programa imprime a chave ao iniciar, então o log só pode ser lido por você.
        TERMINAL_LOG="$(nova_log open_terminal)"; chmod 600 "$TERMINAL_LOG"
        TERMINAL_ARGS=(run --host "${STUDIO_TERMINAL_HOST:-127.0.0.1}" --port $TERMINAL_PORT)
        [ -n "$OPEN_TERMINAL_CWD" ] && TERMINAL_ARGS+=(--cwd "$OPEN_TERMINAL_CWD")
        uvx open-terminal "${TERMINAL_ARGS[@]}" >> "$TERMINAL_LOG" 2>&1 &
        TERMINAL_PID=$!
        COUNTER=0
        while ! nc -z localhost $TERMINAL_PORT > /dev/null 2>&1; do
            sleep 1
            COUNTER=$((COUNTER+1))
            if [ $COUNTER -gt 60 ]; then
                echo "Aviso: o Open Terminal não respondeu em 60s (a primeira vez baixa pacotes). Veja logs/open_terminal.log."
                break
            fi
        done
        echo "     Open Terminal na porta $TERMINAL_PORT. No Open WebUI use http://host.docker.internal:$TERMINAL_PORT"
        echo "     Atenção: ele executa comandos no Mac com as permissões do seu usuário. Guarde a chave."
    else
        echo "Aviso: 'uvx' não encontrado; o Open Terminal não foi iniciado. Instale com: brew install uv"
    fi
fi

# --- Tailscale (informativo) ---
TS_BIN="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
TS_IP="$("$TS_BIN" ip -4 2>/dev/null | head -n1)"
if [ -n "$TS_IP" ]; then
    echo "Tailscale ativo. No iPhone use: http://$TS_IP:$LLM_PORT (sem /v1)"
else
    echo "Aviso: Tailscale não respondeu; o iPhone não alcançará o Mac."
fi

# --- Open WebUI (opcional) ---
if [ "$WANT_WEBUI" = "1" ]; then
    echo "[6/7] Subindo o Open WebUI..."
    docker rm -f open-webui > /dev/null 2>&1
    # Login pelo Cloudflare Access (STUDIO_WEBUI_ACCESS=1): o Open WebUI confia no e-mail que o Access manda no cabeçalho e entra sem senha.
    # Só liga se o endereço público (STUDIO_WEBUI_HOST, padrão chat.heimdall-ai.tech) estiver mesmo atrás do Access, porque qualquer um
    # que alcance o serviço sem passar pelo Access poderia inventar o cabeçalho. Nesse modo a porta fica só em 127.0.0.1 (sem Tailscale/rede local).
    WEBUI_BIND=""
    WEBUI_EXTRA=()
    if [ "$STUDIO_WEBUI_ACCESS" = "1" ]; then
        WEBUI_HOST_PUB="${STUDIO_WEBUI_HOST:-chat.heimdall-ai.tech}"
        "$VENV_PYTHON" verificar_access.py "https://$WEBUI_HOST_PUB" > /tmp/heimdall_access_webui.txt 2>&1
        ACC_RC=$?
        if [ "$ACC_RC" = "1" ]; then
            echo "     AVISO: $(cat /tmp/heimdall_access_webui.txt)"
            echo "     Login por cabeçalho NÃO ligado. Ponha o Cloudflare Access na frente de $WEBUI_HOST_PUB e suba de novo."
        else
            [ "$ACC_RC" = "2" ] && echo "     $(cat /tmp/heimdall_access_webui.txt) Seguindo: sem acesso de fora, o cabeçalho não pode ser falsificado."
            WEBUI_BIND="127.0.0.1:"
            WEBUI_EXTRA+=(-e "WEBUI_AUTH_TRUSTED_EMAIL_HEADER=${STUDIO_WEBUI_ACCESS_HEADER:-Cf-Access-Authenticated-User-Email}")
            # ENABLE_PASSWORD_AUTH=false faz esta versão do Open WebUI recusar (403) também o login pelo cabeçalho do Access; por isso é ignorada.
            [ "$STUDIO_WEBUI_SEM_SENHA" = "1" ] && echo "     Aviso: STUDIO_WEBUI_SEM_SENHA foi ignorada (desligar a senha derruba o login pelo Access nesta versão); pode apagá-la do .env."
            echo "     Open WebUI com login pelo Cloudflare Access (porta só em 127.0.0.1)."
        fi
    fi
    # Modo enxuto (STUDIO_WEBUI_ENXUTO=1, padrão): desliga o que o Open WebUI carrega ou executa sem que o chat precise (Notas,
    # Automações, geração de imagem, execução de código, títulos/etiquetas/sugestões/autocompletar gerados por modelo e voz local),
    # para poupar memória e chamadas de modelo em segundo plano. 0 devolve o comportamento anterior. Estas opções são gravadas pelo
    # Open WebUI na primeira subida: o que já foi alterado no painel de administração dele vale mais que o .env.
    # STUDIO_WEBUI_TITULOS=1 mantém os títulos automáticos das conversas.
    # STUDIO_WEBUI_EMBEDDING=ollama manda os embeddings dos documentos ao Ollama do Mac (poupa cerca de 500 MB); exige
    # ollama pull nomic-embed-text (ou o modelo de STUDIO_WEBUI_EMBEDDING_MODELO) e reindexar os documentos já enviados.
    WEBUI_ENXUTO=()
    if [ "${STUDIO_WEBUI_ENXUTO:-1}" != "0" ]; then
        WEBUI_ENXUTO+=(-e ENABLE_NOTES=False -e ENABLE_AUTOMATIONS=False -e ENABLE_IMAGE_GENERATION=False
            -e ENABLE_CODE_EXECUTION=False -e ENABLE_CODE_INTERPRETER=False -e ENABLE_AUTOCOMPLETE_GENERATION=False
            -e ENABLE_TAGS_GENERATION=False -e ENABLE_FOLLOW_UP_GENERATION=False -e AUDIO_STT_ENGINE=webapi)
        [ "${STUDIO_WEBUI_TITULOS:-0}" = "1" ] || WEBUI_ENXUTO+=(-e ENABLE_TITLE_GENERATION=False)
        if [ "${STUDIO_WEBUI_EMBEDDING:-}" = "ollama" ]; then
            WEBUI_ENXUTO+=(-e RAG_EMBEDDING_ENGINE=ollama -e RAG_OLLAMA_BASE_URL=http://host.docker.internal:11434
                -e RAG_EMBEDDING_MODEL="${STUDIO_WEBUI_EMBEDDING_MODELO:-nomic-embed-text}")
        fi
        echo "     Open WebUI em modo enxuto (sem Notas, Automações, imagem, código e recursos automáticos)."
    fi
    docker run -d --name open-webui \
        --network heimdall \
        --add-host=host.docker.internal:host-gateway \
        -p ${WEBUI_BIND}$WEBUI_PORT:8080 \
        ${WEBUI_EXTRA[@]+"${WEBUI_EXTRA[@]}"} \
        ${WEBUI_ENXUTO[@]+"${WEBUI_ENXUTO[@]}"} \
        -e OPENAI_API_BASE_URL="http://host.docker.internal:$LLM_PORT/v1" \
        -e OPENAI_API_KEY="$LITELLM_MASTER_KEY" \
        -e ENABLE_OLLAMA_API=false \
        -e WEBUI_NAME="${STUDIO_WEBUI_NAME:-Heimdall-ai}" \
        -v open-webui:/app/backend/data \
        ghcr.io/open-webui/open-webui:main > /dev/null
    # Opcional (STUDIO_WEBUI_STRIP_SUFFIX=1 no .env): tira o sufixo " (Open WebUI)" que o programa
    # acrescenta ao nome personalizado. Edita o env.py dentro do contêiner e reinicia; a edição se
    # perde quando a imagem é atualizada, mas esta etapa a refaz a cada subida. A licença do Open WebUI
    # restringe alterar a marca em instalações grandes; confira se o seu uso se enquadra.
    if [ "$STUDIO_WEBUI_STRIP_SUFFIX" = "1" ]; then
        sleep 2
        if docker exec open-webui sed -i "s/WEBUI_NAME += ' (Open WebUI)'/pass/" /app/backend/open_webui/env.py 2>/dev/null \
           && ! docker exec open-webui grep -q "WEBUI_NAME += ' (Open WebUI)'" /app/backend/open_webui/env.py 2>/dev/null; then
            docker restart open-webui > /dev/null
            echo "     Sufixo \" (Open WebUI)\" removido do nome."
        else
            echo "     Aviso: não consegui remover o sufixo do nome (a linha mudou nesta versão?)."
        fi
    fi
    # Aparência: copia o que estiver em branding/ (favicon.png, logo.png, splash.png, custom.css...)
    # para as pastas de arquivos estáticos do contêiner. Se uma pasta não existir nesta versão, é ignorada.
    if [ -d branding ]; then
        for f in branding/*; do
            [ -f "$f" ] || continue
            docker cp "$f" open-webui:/app/build/static/ > /dev/null 2>&1
            docker cp "$f" open-webui:/app/backend/open_webui/static/ > /dev/null 2>&1
        done
        echo "     Aparência: arquivos de branding/ aplicados (atualize o navegador com Ctrl/Cmd+Shift+R)."
    fi
    if [ -n "$WEBUI_BIND" ]; then
        echo "[6/7] Open WebUI em http://localhost:$WEBUI_PORT (e pelo endereço público, atrás do Access)"
    else
        echo "[6/7] Open WebUI em http://localhost:$WEBUI_PORT" "${TS_IP:+(Tailscale: http://$TS_IP:$WEBUI_PORT)}"
    fi
    echo "     A primeira conta criada vira administradora: crie a sua logo ao abrir."
else
    docker stop open-webui > /dev/null 2>&1
    echo "[6/7] Open WebUI desligado (use --webui ou STUDIO_WEBUI=1 no .env para ligar)."
fi

# --- LiteLLM ---
# Usa o executável oficial "litellm" do venv; rodar "python -m litellm.proxy.proxy_cli"
# importa o módulo duas vezes e quebrou a leitura do --config.
echo "[7/7] Subindo o LiteLLM Proxy..."
# O heimdall_litellm.py escolhe a configuração: com STUDIO_NUVEM=1 o chat responde pelo modelo da nuvem (e o local é a volta);
# com qualquer outro valor vale o litellm_config.yaml como sempre foi.
"$VENV_PYTHON" "$PROJECT_DIR/heimdall_litellm.py" --host 0.0.0.0 --port $LLM_PORT &
LITELLM_PID=$!
trap 'kill $MCP_PID $MCP_PUBLIC_PID $MCP_DADOS_PID $TERMINAL_PID $AGENTE_PID $LITELLM_PID 2>/dev/null' EXIT INT TERM
wait $LITELLM_PID
# Se o LiteLLM saiu (desligado de propósito no Controls, ou caiu), o script continua de pé: os outros serviços seguem no ar.
# "studio restart" e "studio stop" encerram este script do mesmo jeito.
echo "LiteLLM parou. Os demais serviços continuam no ar; religue o LiteLLM pelo Controls ou use: studio restart"
while true; do sleep 30; done
