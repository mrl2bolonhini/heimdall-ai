# Comando unificado do ecossistema Heimdall-ai (zsh). Carregado pelo ~/.zshrc com:
#     source ~/heimdall-ai/heimdall.zsh
# Pasta do projeto: HEIMDALL_DIR (padrão ~/heimdall-ai). Digite "heimdall" sem nada para ver todos os comandos.

: "${HEIMDALL_DIR:=$HOME/heimdall-ai}"

_heimdall_py() {  # roda um script Python do projeto com o Python do venv, na pasta do projeto, sem mudar a pasta do seu terminal
  local py="$HEIMDALL_DIR/venv/bin/python"
  [ -x "$py" ] || py="$(command -v python3)"
  ( cd "$HEIMDALL_DIR" && "$py" "$@" )
}

_heimdall_sh() {
  local s="$1"; shift
  ( cd "$HEIMDALL_DIR" && bash "./$s" "$@" )
}

_heimdall_abrir() {  # $1 = nome, $2 = endereço
  echo "$1: $2"
  open "$2" 2>/dev/null || echo "Abra o endereço acima no navegador."
}

_heimdall_parar_portas() {
  local p
  for p in 8000 8001 8002 8003 8004 8010 8011 8012 8013 9000; do
    lsof -ti:"$p" 2>/dev/null | xargs kill -9 2>/dev/null
  done
}

_heimdall_legado() {  # versões antigas (claude_version e gemini_version), com o LaunchAgent
  local v="$1" a="$2" plist="$HOME/Library/LaunchAgents/com.bolonhini.ai-ecosystem.plist"
  local script
  case "$v" in
    claude) script="$HEIMDALL_DIR/claude_version/start_heimdall.sh" ;;
    gemini) script="$HEIMDALL_DIR/gemini_version/start_ecosystem.sh" ;;
    *) echo "Versão desconhecida."; return 1 ;;
  esac
  case "$a" in
    up)
      echo "Iniciando o ecossistema Heimdall-ai (versão $v)..."
      launchctl unload "$plist" 2>/dev/null
      lsof -ti:9000 | xargs kill -9 2>/dev/null; lsof -ti:8000 | xargs kill -9 2>/dev/null
      sleep 1
      bash "$script" ;;
    reload|restart)
      launchctl unload "$plist" 2>/dev/null
      lsof -ti:9000 | xargs kill -9 2>/dev/null; lsof -ti:8000 | xargs kill -9 2>/dev/null
      sleep 1
      launchctl load "$plist" && echo "Heimdall recarregado." ;;
    down|stop)
      launchctl unload "$plist" 2>/dev/null
      lsof -ti:9000 | xargs kill -9 2>/dev/null; lsof -ti:8000 | xargs kill -9 2>/dev/null
      echo "Heimdall parado." ;;
    status)
      launchctl list | grep com.bolonhini
      echo "Porta 9000:"; lsof -i :9000 ;;
    *) echo "Uso: heimdall $v {up|reload|down|status}" ;;
  esac
}

_heimdall_ajuda() {
  cat <<'AJUDA'
Uso: heimdall COMANDO [argumentos]

Ligar e desligar
  1. up [argumentos]        sobe tudo (padrão: --webui --terminal). Ex.: heimdall up --webui --terminal --n8n
  2. reiniciar              encerra a subida atual e sobe de novo (reload e restart também servem)
  3. parar                  encerra os serviços do Mac (portas 8000 a 8004, 8010 a 8013 e 9000); os contêineres do Docker ficam
  4. status                 confere o que está no ar
  5. log [serviço]          últimas linhas do log (mcp, agente, cloud, notas, news, saude_painel, ...); logs lista os arquivos

Abrir no navegador
  6. chat                   Open WebUI          7. notes ou notas    Heimdall Notas
  8. news                   Heimdall News       9. cloud             Heimdall Cloud (AWS local)
  10. painel ou health      painel de saúde, página inicial; também: heimdall painel anomalias | hoje | semana | sono | dados
  11. n8n                   automações          12. kuma             Uptime Kuma (status)
  13. dozzle                logs dos contêineres   14. urls          lista todos os endereços

Saúde
  15. saude [opções]        relatório no terminal. Ex.: heimdall saude --hoje | --agora | --sono | --semanal | --importar arquivo.zip
  16. anomalias [AAAA-MM-DD]  o que saiu do seu normal

Dados e rotinas
  17. triagem               estado da triagem de avisos       18. banco --sql "SELECT ..."   consulta o banco pessoal
  19. backup [comando]      cópia de segurança criptografada   20. email  verificação do e-mail oficial (--testar-login, --simular)
  21. acesso --senha|--codigo|--tudo|--verificar   senha e código de 6 dígitos de todos os serviços
  22. senha-webui           troca a senha do Open WebUI        23. voz  dicionário de pronúncia
  24. modelos               modelos do Ollama                   25. diagnostico  diagnóstico do chat
  26. mcp                   verifica o MCP de dados

Manutenção
  27. atualizar [--reiniciar]   traz as novidades do GitHub (git pull) e diz se precisa reiniciar
  28. fluxos                instala ou atualiza os fluxos do n8n (instalar_automacoes_avancadas.sh)
  29. docs                  regenera o site e o README (gerar_docs.py)
  30. teste [nome]          roda um teste (heimdall teste anomalias roda teste_anomalias.py); sem nome, lista os testes
  31. dir                   mostra a pasta do projeto

Versões antigas: heimdall claude|gemini up|reload|down|status
AJUDA
}

heimdall() {
  local cmd="$1"
  [ $# -gt 0 ] && shift
  if [ ! -d "$HEIMDALL_DIR" ] && [ "$cmd" != "dir" ]; then
    echo "Não achei a pasta $HEIMDALL_DIR. Defina HEIMDALL_DIR no ~/.zshrc antes do source."; return 1
  fi
  case "$cmd" in
    ""|ajuda|help|-h|--help) _heimdall_ajuda ;;

    up|subir|iniciar) _heimdall_sh subir.sh "$@" ;;
    reiniciar|reload|restart) _heimdall_sh subir.sh --reiniciar "$@" ;;
    parar|down|stop)
      echo "Parando os serviços do Mac (o Docker continua)..."
      _heimdall_parar_portas
      echo "Parado. Para subir de novo: heimdall up" ;;
    status) _heimdall_sh subir.sh --status ;;
    log) _heimdall_sh subir.sh --log "$@" ;;
    logs) _heimdall_sh subir.sh --logs ;;

    chat|webui) _heimdall_abrir "Open WebUI (chat)" "http://localhost:3000" ;;
    notes|notas) _heimdall_abrir "Heimdall Notas" "http://localhost:${HEIMDALL_NOTAS_PORT:-8011}" ;;
    news) _heimdall_abrir "Heimdall News" "http://localhost:${HEIMDALL_NEWS_PORT:-8012}" ;;
    cloud) _heimdall_abrir "Heimdall Cloud" "http://localhost:${HEIMDALL_CLOUD_PORT:-8010}" ;;
    painel|health|painel-saude)
      local pg="${1:-}"
      _heimdall_abrir "Painel de saúde" "http://localhost:${HEIMDALL_SAUDE_PAINEL_PORT:-8013}${pg:+/$pg}" ;;
    n8n) _heimdall_abrir "n8n" "http://localhost:5678" ;;
    kuma|uptime) _heimdall_abrir "Uptime Kuma" "http://localhost:3001" ;;
    dozzle) _heimdall_abrir "Dozzle (logs)" "http://localhost:8081" ;;
    urls)
      echo "Chat: http://localhost:3000"
      echo "Notas: http://localhost:${HEIMDALL_NOTAS_PORT:-8011}"
      echo "News: http://localhost:${HEIMDALL_NEWS_PORT:-8012}"
      echo "Cloud: http://localhost:${HEIMDALL_CLOUD_PORT:-8010}"
      echo "Saúde: http://localhost:${HEIMDALL_SAUDE_PAINEL_PORT:-8013}"
      echo "n8n: http://localhost:5678"
      echo "Uptime Kuma: http://localhost:3001"
      echo "Dozzle: http://localhost:8081" ;;

    saude|saúde|health-cli) _heimdall_py heimdall_saude.py "${@:---hoje}" ;;
    anomalias) _heimdall_py heimdall_anomalias.py "$@" ;;

    triagem) _heimdall_sh consultar_triagem.sh "$@" ;;
    banco|db) _heimdall_py heimdall_banco.py "$@" ;;
    backup) _heimdall_py heimdall_backup.py "$@" ;;
    email|e-mail) _heimdall_py heimdall_email_oficial.py "$@" ;;
    acesso) _heimdall_py heimdall_acesso.py "$@" ;;
    senha-webui) _heimdall_sh trocar_senha_webui.sh "$@" ;;
    voz) _heimdall_py heimdall_voz.py "$@" ;;
    modelos) ollama list ;;
    diagnostico|diagnóstico) _heimdall_sh diagnostico_chat.sh "$@" ;;
    mcp) _heimdall_sh verificar_mcp_dados.sh "$@" ;;

    atualizar|update)
      local reiniciar=0 ramo
      [ "$1" = "--reiniciar" ] && reiniciar=1
      ramo="$(git -C "$HEIMDALL_DIR" rev-parse --abbrev-ref HEAD)"
      echo "Atualizando a branch $ramo..."
      git -C "$HEIMDALL_DIR" pull --ff-only origin "$ramo" || { echo "O pull falhou; veja a mensagem acima."; return 1; }
      if [ "$reiniciar" = 1 ]; then
        _heimdall_sh subir.sh --reiniciar
      else
        echo "Pronto. Se mudou código de serviço: heimdall reiniciar. Se mudou fluxo do n8n: heimdall fluxos."
      fi ;;
    fluxos) _heimdall_sh instalar_automacoes_avancadas.sh "$@" ;;
    docs) _heimdall_py gerar_docs.py "$@" ;;
    teste|test)
      if [ -z "$1" ]; then
        ( cd "$HEIMDALL_DIR" && ls teste_*.py teste_*.sh 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//' )
      elif [ -f "$HEIMDALL_DIR/teste_$1.py" ]; then
        local n="$1"; shift; _heimdall_py "teste_$n.py" "$@"
      elif [ -f "$HEIMDALL_DIR/teste_$1.sh" ]; then
        local n="$1"; shift; _heimdall_sh "teste_$n.sh" "$@"
      else
        echo "Teste desconhecido. Veja a lista com: heimdall teste"; return 1
      fi ;;
    dir) echo "$HEIMDALL_DIR" ;;

    claude|gemini) _heimdall_legado "$cmd" "$1" ;;
    *) echo "Comando desconhecido: $cmd. Veja os comandos com: heimdall ajuda"; return 1 ;;
  esac
}

# Completar com Tab (zsh)
if [ -n "$ZSH_VERSION" ] && whence compdef > /dev/null 2>&1; then
  _heimdall_completar() {
    local -a cmds
    cmds=(up reiniciar parar status log logs chat notes notas news cloud painel health n8n kuma dozzle urls saude anomalias triagem banco backup email acesso senha-webui voz modelos diagnostico mcp atualizar fluxos docs teste dir ajuda claude gemini)
    if (( CURRENT == 2 )); then
      compadd -a cmds
    elif [[ ${words[2]} == saude ]]; then
      compadd -- --hoje --agora --relatorio --sono --atividade --recuperacao --tendencias --treinos --ecg --fc --semanal --importar
    elif [[ ${words[2]} == painel || ${words[2]} == health ]]; then
      compadd -- anomalias hoje semana sono atividade recuperacao coracao treinos eventos diario dados
    elif [[ ${words[2]} == teste ]]; then
      compadd -- $(cd "$HEIMDALL_DIR" 2>/dev/null && ls teste_*.py teste_*.sh 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//')
    fi
  }
  compdef _heimdall_completar heimdall
fi
