#!/usr/bin/env bash
# Prepara jogos de terceiros para aparecerem no portal de jogos (heimdall games), ao lado dos jogos do próprio Heimdall.
#
# Uso, na pasta do projeto:
#     bash instalar_jogos_extras.sh --enigma        sobe o Enigma (quebra-cabeças de palavras, números e lógica) em Docker, na porta 8015
#     bash instalar_jogos_extras.sh --playaural     só põe no portal o link do PlayAural (jogos de áudio feitos para leitor de tela)
#     bash instalar_jogos_extras.sh --status        mostra o que está listado e se o contêiner do Enigma está rodando
#     bash instalar_jogos_extras.sh --remover       para o contêiner do Enigma (os dados ficam) e tira os dois do portal
#
# Avisos honestos:
#   1. Nada disso foi testado com o VoiceOver. O Enigma não declara acessibilidade; o PlayAural foi feito para leitor de tela.
#   2. O Enigma tem interface em inglês e espanhol, contas próprias e licença de uso pessoal. O PlayAural é um serviço de terceiros na internet,
#      fora do login do Heimdall: o que você digitar lá vai para esse serviço.
#   3. O portal só põe o link. O Enigma fica escutando só neste Mac (127.0.0.1:8015); para abrir de fora seria preciso outro nome no túnel Cloudflare.
# O segredo de sessão do Enigma é gerado aqui e guardado só no .env (que o git ignora); ele nunca aparece na tela.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
ENV_FILE="${HEIMDALL_ENV_FILE:-.env}"
CONTEINER="heimdall-enigma"
IMAGEM="boopboopboop/enigma:latest"
PORTA="${ENIGMA_PORT:-8015}"
VOLUME="heimdall-enigma-data"
ENIGMA_ITEM="Enigma|http://localhost:${PORTA}|Quebra-cabeças de palavras, números e lógica (de terceiros, em inglês ou espanhol, com conta própria)"
PLAYAURAL_ITEM="PlayAural|https://play.ddt.one|Jogos de áudio feitos para leitor de tela (serviço de terceiros na internet, com conta própria)"

fail() { echo "Erro: $*" >&2; exit 1; }
umask 077
PY="$PROJECT_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || fail "não encontrei o Python."
touch "$ENV_FILE" || fail "não consegui abrir o arquivo $ENV_FILE."

# extras_ajustar adicionar|remover NOME [ITEM]: edita HEIMDALL_JOGOS_EXTRAS no .env sem tocar em nenhuma outra linha.
extras_ajustar() {
    "$PY" - "$ENV_FILE" "$1" "$2" "${3:-}" <<'PYEOF'
import sys
caminho, acao, nome, item = sys.argv[1:5]
linhas = open(caminho, encoding="utf-8").read().splitlines()
atual, idx = [], None
for i, l in enumerate(linhas):
    if l.startswith("HEIMDALL_JOGOS_EXTRAS="):
        idx = i
        atual = [x for x in l.split("=", 1)[1].strip().strip('"').split(";") if x.strip()]
atual = [x for x in atual if x.split("|")[0].strip() != nome]
if acao == "adicionar":
    atual.append(item)
nova = "HEIMDALL_JOGOS_EXTRAS=\"" + ";".join(atual) + "\"" if atual else None
if idx is None and nova:
    linhas.append(nova)
elif idx is not None:
    if nova:
        linhas[idx] = nova
    else:
        del linhas[idx]
open(caminho, "w", encoding="utf-8").write("\n".join(linhas) + "\n")
PYEOF
}

valor_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'; }

docker_pronto() {
    command -v docker >/dev/null 2>&1 || fail "o Docker não está instalado. Instale o Docker Desktop, abra-o uma vez e rode este comando de novo."
    docker info >/dev/null 2>&1 || fail "o Docker está instalado mas não está rodando. Abra o Docker Desktop, espere ele iniciar e rode de novo."
}

case "${1:-}" in
    --enigma)
        docker_pronto
        SEGREDO="$(valor_env ENIGMA_SESSION_SECRET)"
        if [ -z "$SEGREDO" ]; then
            SEGREDO="$(openssl rand -hex 32 2>/dev/null || "$PY" -c 'import secrets;print(secrets.token_hex(32))')"
            printf 'ENIGMA_SESSION_SECRET="%s"\n' "$SEGREDO" >> "$ENV_FILE"
            echo "Segredo de sessão do Enigma criado e guardado no .env."
        fi
        docker rm -f "$CONTEINER" >/dev/null 2>&1
        echo "Baixando e iniciando o Enigma (a primeira vez demora)..."
        docker run -d --name "$CONTEINER" --restart unless-stopped \
            -p "127.0.0.1:${PORTA}:3000" \
            -e SESSION_SECRET="$SEGREDO" -e FRONTEND_URL="http://localhost:${PORTA}" \
            -v "${VOLUME}:/app/data" "$IMAGEM" >/dev/null || fail "o Docker não conseguiu iniciar o Enigma. Veja: docker logs $CONTEINER"
        extras_ajustar adicionar Enigma "$ENIGMA_ITEM"
        echo "Pronto. O Enigma deve responder em http://localhost:${PORTA} em alguns segundos (crie uma conta própria na primeira vez)."
        echo "Ele aparece no portal de jogos depois de: heimdall update --restart   (ou reiniciar o serviço de jogos)."
        echo "Lembrete: interface em inglês ou espanhol, sem garantia de acessibilidade. Teste com o VoiceOver e me diga o que ouviu."
        ;;
    --playaural)
        extras_ajustar adicionar PlayAural "$PLAYAURAL_ITEM"
        echo "PlayAural listado no portal de jogos (é só um link para o serviço de terceiros em play.ddt.one)."
        echo "Ele aparece depois de reiniciar o serviço de jogos. O que você digitar lá vai para esse serviço, fora do login do Heimdall."
        ;;
    --status)
        echo "No portal (HEIMDALL_JOGOS_EXTRAS): $(valor_env HEIMDALL_JOGOS_EXTRAS | tr ';' '\n' | cut -d'|' -f1 | paste -sd, - | sed 's/^$/nada/')"
        if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
            docker ps -a --filter "name=^${CONTEINER}\$" --format 'Enigma: {{.Status}}' | grep . || echo "Enigma: contêiner não existe."
        else
            echo "Docker: não está rodando ou não está instalado."
        fi
        ;;
    --remover)
        if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
            docker rm -f "$CONTEINER" >/dev/null 2>&1 && echo "Contêiner do Enigma parado e removido (os dados ficam no volume $VOLUME)."
        fi
        extras_ajustar remover Enigma
        extras_ajustar remover PlayAural
        echo "Enigma e PlayAural tirados do portal. Reinicie o serviço de jogos para valer."
        ;;
    *)
        sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
