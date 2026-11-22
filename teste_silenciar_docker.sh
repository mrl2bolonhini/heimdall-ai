#!/bin/bash
# Testa silenciar_docker.sh numa pasta falsa, sem tocar no Docker de verdade.
cd "$(dirname "$0")" || exit 1
T=$(mktemp -d); FALHAS=0
confere() { if [ "$2" = "ok" ]; then echo "ok   $1"; else echo "FALHOU $1"; FALHAS=$((FALHAS+1)); fi; }
echo '{"OpenUIOnStartupDisabled": false, "outra": 7}' > "$T/settings-store.json"
DOCKER_CONFIG_PASTA="$T" bash silenciar_docker.sh >/dev/null
python3 -c "import json,sys; d=json.load(open('$T/settings-store.json')); sys.exit(0 if d['OpenUIOnStartupDisabled'] is True and d['outra']==7 else 1)" && confere "liga a chave e preserva o resto" ok || confere "liga a chave e preserva o resto" no
[ -f "$T/settings-store.json.heimdall-bak" ] && confere "faz cópia de segurança" ok || confere "faz cópia de segurança" no
DOCKER_CONFIG_PASTA="$T" bash silenciar_docker.sh --desfazer >/dev/null
python3 -c "import json,sys; d=json.load(open('$T/settings-store.json')); sys.exit(0 if d['OpenUIOnStartupDisabled'] is False else 1)" && confere "--desfazer volta a chave" ok || confere "--desfazer volta a chave" no
DOCKER_CONFIG_PASTA="$T/nada" bash silenciar_docker.sh >/dev/null 2>&1 && confere "sem configuração: falha com aviso" no || confere "sem configuração: falha com aviso" ok
[ "$FALHAS" = 0 ] && echo "Tudo certo." || echo "FALHAS: $FALHAS"
exit $FALHAS
