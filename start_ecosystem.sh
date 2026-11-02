#!/bin/bash

PROJECT_DIR="/Users/mrl2_bolonhini/heimdal-ai"
cd "$PROJECT_DIR" || exit 1

VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
CONFIG_FILE="$PROJECT_DIR/litellm_config.yaml"

echo "[0/4] Liberando portas em uso..."
lsof -ti:9000 | xargs kill -9 2>/dev/null
lsof -ti:8000 | xargs kill -9 2>/dev/null
sleep 1

echo "=== [Heimdall System Boot] ==="

if ! docker info > /dev/null 2>&1; then
    echo "[1/4] Subindo o Docker Desktop..."
    open -a Docker
    while ! docker info > /dev/null 2>&1; do
        sleep 2
    done
fi
echo "[1/4] Docker pronto."

if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[2/4] Iniciando o serviço do Ollama..."
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi
echo "[2/4] Ollama pronto."

echo "[3/4] Subindo o Gateway Heimdall..."
# Executa mantendo o log visível em arquivo temporário para depuração se travar
"$VENV_PYTHON" proxy_gateway.py > gateway_debug.log 2>&1 &

# Aguarda ativamente o endpoint de saúde do gateway responder
COUNTER=0
while ! curl -s http://localhost:8000/health > /dev/null 2>&1; do
    sleep 1
    COUNTER=$((COUNTER+1))
    if [ $COUNTER -gt 10 ]; then
        echo "Erro: O Gateway Heimdall demorou muito para responder. Veja gateway_debug.log:"
        tail -n 20 gateway_debug.log
        exit 1
    fi
done
echo "[3/4] Gateway Heimdall pronto."

echo "[4/4] Subindo o LiteLLM Proxy Oficial..."
exec "$VENV_PYTHON" -m litellm.proxy.proxy_cli --config "$CONFIG_FILE" --host 0.0.0.0 --port 9000