#!/usr/bin/env bash
# Sobe o Paperless-ngx (motor do Heimdall Library) em Docker, só em 127.0.0.1:8023, e liga o motor no .env.
# Gera a chave e a senha do Paperless na primeira vez (guardadas no .env, nunca mostradas). Funciona em macOS e Linux; no Windows, use o WSL.
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Não encontrei o .env nesta pasta."; exit 1; }
command -v docker > /dev/null 2>&1 || { echo "O Docker não está instalado ou não está no ar."; exit 1; }
cp .env .env.bak
python3 - <<'PY'
import secrets
linhas = open(".env", encoding="utf-8").read().splitlines()
tem = {l.split("=", 1)[0] for l in linhas if "=" in l}
novos = {"HEIMDALL_PAPERLESS_SECRET": secrets.token_urlsafe(48), "HEIMDALL_PAPERLESS_SENHA": secrets.token_urlsafe(24), "HEIMDALL_PAPERLESS_USER": "heimdall",
         "HEIMDALL_PAPERLESS_URL": "http://127.0.0.1:8023", "HEIMDALL_LIBRARY_MOTOR": "paperless"}
for k, v in novos.items():
    if k not in tem:
        linhas.append(f"{k}={v}")
    elif k == "HEIMDALL_LIBRARY_MOTOR":
        linhas = [f"{k}={v}" if l.startswith(k + "=") else l for l in linhas]
open(".env", "w", encoding="utf-8").write("\n".join(linhas) + "\n")
PY
mkdir -p paperless/data paperless/media paperless/export
docker compose -f paperless/docker-compose.yml --env-file .env up -d || { echo "Não consegui subir o Paperless-ngx; veja a mensagem acima."; exit 1; }
echo "Paperless-ngx no ar em 127.0.0.1:8023 (a primeira subida leva alguns minutos). Reinicie o Library: heimdall restart"
