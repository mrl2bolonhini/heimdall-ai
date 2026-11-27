#!/bin/bash
# Compatibilidade de nomes de variáveis (fase 3b da renomeação para StudioLibre). Use com: source scripts/studio_env.sh
# Depois do `source .env`, cada STUDIO_X exportada vale também como HEIMDALL_X (o nome que o código ainda lê). Se as duas existem, vale STUDIO_X.
# HEIMDALL_X sozinha continua funcionando. Não altera o .env.
_studio_espelhar_env() {
    local _linha _k
    while IFS= read -r _linha; do
        _k="${_linha%%=*}"
        case "$_k" in
            STUDIO_HUB|STUDIO_HUB_[A-Z0-9_]*) export "HEIMDALL_MEMORY${_k#STUDIO_HUB}=${!_k}" ;;   # Studio Hub é o antigo Memory
            STUDIO_[A-Z0-9_]*) export "HEIMDALL_${_k#STUDIO_}=${!_k}" ;;
        esac
    done < <(env)
}
_studio_espelhar_env
unset -f _studio_espelhar_env
