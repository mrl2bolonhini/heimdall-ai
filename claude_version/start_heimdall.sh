#!/bin/bash

# A pasta do projeto é a pasta deste script, então funciona em qualquer lugar.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    VENV_PYTHON="$(command -v python3)"
    echo "Aviso: venv não encontrado em $PROJECT_DIR/venv; usando $VENV_PYTHON"
fi
CONFIG_FILE="$PROJECT_DIR/litellm_config.yaml"
MCP_PORT=8000
LLM_PORT=9000

echo "=== [Heimdall System Boot] ==="
echo "Projeto: $PROJECT_DIR"

# --- Chave mestra do LiteLLM (guardada em .env, nunca no YAML) ---
if [ -f .env ]; then
    set -a; source .env; set +a
fi
if [ -z "$LITELLM_MASTER_KEY" ]; then
    LITELLM_MASTER_KEY="sk-$(openssl rand -hex 24)"
    echo "LITELLM_MASTER_KEY=$LITELLM_MASTER_KEY" >> .env
    chmod 600 .env
    echo "Nova chave mestra gerada e salva em $PROJECT_DIR/.env"
fi
export LITELLM_MASTER_KEY

echo "[0/5] Liberando portas em uso..."
lsof -ti:$LLM_PORT | xargs kill -9 2>/dev/null
lsof -ti:$MCP_PORT | xargs kill -9 2>/dev/null
sleep 1

# --- Docker + SearXNG ---
if ! docker info > /dev/null 2>&1; then
    echo "[1/5] Subindo o Docker Desktop..."
    open -a Docker
    while ! docker info > /dev/null 2>&1; do
        sleep 2
    done
fi
echo "[1/5] Docker pronto."

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
        -p 127.0.0.1:8080:8080 \
        -v "$PROJECT_DIR/searxng:/etc/searxng" \
        searxng/searxng > /dev/null
fi
echo "[2/5] SearXNG pronto (porta 8080)."

# --- Ollama ---
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[3/5] Iniciando o Ollama..."
    OLLAMA_CONTEXT_LENGTH=8192 ollama serve > /dev/null 2>&1 &
    sleep 3
else
    echo "[3/5] Ollama já estava rodando (o contexto vem do num_ctx do litellm_config.yaml)."
fi

# --- Servidor MCP unificado ---
echo "[4/5] Subindo o servidor MCP do Heimdall..."
"$VENV_PYTHON" heimdall_mcp.py > mcp_debug.log 2>&1 &
MCP_PID=$!
trap 'kill $MCP_PID 2>/dev/null' EXIT INT TERM

COUNTER=0
while ! nc -z localhost $MCP_PORT > /dev/null 2>&1; do
    sleep 1
    COUNTER=$((COUNTER+1))
    if [ $COUNTER -gt 15 ]; then
        echo "Erro: o servidor MCP demorou demais para subir. Veja mcp_debug.log:"
        tail -n 20 mcp_debug.log
        exit 1
    fi
done
echo "[4/5] Servidor MCP pronto em http://localhost:$MCP_PORT/mcp"

# --- Tailscale (informativo) ---
TS_BIN="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
TS_IP="$("$TS_BIN" ip -4 2>/dev/null | head -n1)"
if [ -n "$TS_IP" ]; then
    echo "Tailscale ativo. No iPhone use: http://$TS_IP:$LLM_PORT (sem /v1)"
else
    echo "Aviso: Tailscale não respondeu; o iPhone não alcançará o Mac."
fi

# --- LiteLLM ---
# Usa o executável oficial "litellm" do venv; rodar "python -m litellm.proxy.proxy_cli"
# importa o módulo duas vezes e quebrou a leitura do --config.
echo "[5/5] Subindo o LiteLLM Proxy..."
LITELLM_BIN="$(dirname "$VENV_PYTHON")/litellm"
if [ -x "$LITELLM_BIN" ]; then
    "$LITELLM_BIN" --config "$CONFIG_FILE" --host 0.0.0.0 --port $LLM_PORT
else
    echo "Aviso: executável litellm não encontrado no venv; usando o módulo."
    "$VENV_PYTHON" -m litellm.proxy.proxy_cli --config "$CONFIG_FILE" --host 0.0.0.0 --port $LLM_PORT
fi
