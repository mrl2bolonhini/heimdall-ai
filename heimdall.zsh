# Comando unificado do ecossistema Heimdall-ai (zsh). Carregado pelo ~/.zshrc com:
#     source ~/heimdall-ai/heimdall.zsh
# Pasta do projeto: HEIMDALL_DIR (padrão ~/heimdall-ai). Digite "heimdall" sem nada para ver todos os comandos.

: "${HEIMDALL_DIR:=$HOME/heimdall-ai}"

_heimdall_py() {  # script Python do projeto, com o Python do venv, na pasta do projeto, sem mudar a pasta do seu terminal
  local py="$HEIMDALL_DIR/venv/bin/python"
  [ -x "$py" ] || py="$(command -v python3)"
  ( cd "$HEIMDALL_DIR" && "$py" "$@" )
}

_heimdall_sh() {  # script de shell do projeto
  local s="$1"; shift
  ( cd "$HEIMDALL_DIR" && bash "./$s" "$@" )
}

_heimdall_tr() {  # traduz as opções em inglês para as do programa. $1 = linhas "de=para" ("-" descarta); o resto são os argumentos. Resultado em _HA
  local map="$1" a from to hit
  shift
  _HA=()
  for a in "$@"; do
    hit=0
    while IFS='=' read -r from to; do
      [ -z "$from" ] && continue
      if [ "$a" = "$from" ]; then
        hit=1
        [ "$to" != "-" ] && _HA+=("$to")
        break
      fi
    done <<< "$map"
    [ "$hit" = 0 ] && _HA+=("$a")
  done
}

_heimdall_open() {  # $1 = nome, $2 = endereço
  echo "$1: $2"
  open "$2" 2>/dev/null || echo "Abra o endereço acima no navegador."
}

_heimdall_port() {  # porta de cada serviço (a do .env, se houver)
  local v
  [ -f "$HEIMDALL_DIR/.env" ] && v="$(grep -E "^$1=" "$HEIMDALL_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  echo "${v:-$2}"
}

_heimdall_stop_ports() {
  local p
  for p in 8000 8001 8002 8003 8004 8010 8011 8012 8013 9000; do
    lsof -ti:"$p" 2>/dev/null | xargs kill -9 2>/dev/null
  done
}

_heimdall_help() {
  cat <<'AJUDA'
Uso: heimdall COMANDO [--opção ...]. O comando é sempre o serviço; o que ele faz vem depois, em opções com dois hífens.
Sem opção, os serviços com página abrem no navegador. Opções que levam valor: --report 30, --service agent.

Ligar, desligar e acompanhar
  up [--webui] [--terminal] [--n8n] [--agent] [--ingest] [--docling] [--update]    sobe tudo (padrão: --webui --terminal)
  restart [mesmas opções do up]            encerra a subida atual e sobe de novo
  stop                                     encerra os serviços do Mac (portas 8000 a 8004, 8010 a 8013 e 9000); o Docker fica
  status                                   confere o que está no ar
  logs [--list] [--clean] [--service NOME] sem opção, o log da subida atual; NOME: mcp mcp-public mcp-data agent cloud notes news health terminal ingest
  containers [opções do docker ps]         contêineres do Docker
  models [opções do ollama list]           modelos do Ollama

Serviços (abrem no navegador)
  chat [--diagnose] [--password]           Open WebUI; --diagnose mostra as últimas chamadas de ferramenta; --password troca a senha
  notes [--clean-mirrors] [--clean-private] [--move-old [--run]]   Heimdall Notas; as opções são manutenção do Second Brain e das pastas
  news                                     Heimdall News
  cloud                                    Heimdall Cloud (AWS local)
  health [--open PÁGINA]                   painel de saúde; PÁGINA: anomalies today week sleep activity recovery heart workouts events diary data
  n8n   kuma   dozzle                      automações, Uptime Kuma e logs dos contêineres
  urls                                     lista todos os endereços

Saúde no terminal (health com uma destas opções roda o relatório)
  health --today | --now | --weekly | --anomalies [AAAA-MM-DD] | --report [dias] | --sleep [dias] | --activity [dias]
         | --recovery [dias] | --trends [dias] | --workouts [dias] | --ecg [dias] | --fc [dias]
         | --import ARQUIVO.zip | --import-n8n

Dados e rotinas
  triage [--complete-tests]                estado da triagem de avisos; --complete-tests conclui os lembretes de teste
  db [--sql "SELECT ..."]                  banco pessoal
  backup --prepare | --password | --run | --list | --verify | --restore ORIGEM DESTINO     cópia de segurança criptografada
  mail [--test-login] [--simulate]         e-mail oficial
  access --password | --code | --all | --verify      senha e código de 6 dígitos de todos os serviços
  voice [TEXTO] | voice --import ARQUIVO.csv         dicionário de pronúncia
  listen [--list] [--latest N]             toca os áudios de estudo mais recentes
  ingest [--reset] [PASTAS]                indexa documentos na base de conhecimento
  env --set NOME                           grava no .env o que está na área de transferência
  cloudflare [--set] [--test]              grava ou testa a chave da Cloudflare
  mcp [--verify]                           verifica o MCP de dados

Instalar e manter
  flows [--advanced] [--basic] [--privacy] [--email]   instala fluxos no n8n (padrão: --advanced)
  hook [--install] [--remove] REPOSITÓRIO             liga ou desliga o GitOps num repositório git
  update [--restart]                       traz as novidades do GitHub (git pull) e diz se precisa reiniciar
  docs [--brand]                           regenera o site e o README; --brand regenera as imagens da marca
  test [--list] [--all] [--run NOME]       testes
  dir   cd                                 mostra a pasta do projeto; entra nela
AJUDA
}

heimdall() {
  local cmd="$1"
  [ $# -gt 0 ] && shift
  if [ ! -d "$HEIMDALL_DIR" ] && [ "$cmd" != "dir" ]; then
    echo "Não achei a pasta $HEIMDALL_DIR. Defina HEIMDALL_DIR no ~/.zshrc antes do source."; return 1
  fi
  local a pg
  case "$cmd" in
    ""|help|-h|--help) _heimdall_help ;;

    up) _heimdall_tr "--agent=--agente" "$@"; _heimdall_sh subir.sh "${_HA[@]}" ;;
    restart) _heimdall_tr "--agent=--agente" "$@"; _heimdall_sh subir.sh --reiniciar "${_HA[@]}" ;;
    stop)
      echo "Parando os serviços do Mac (o Docker continua)..."
      _heimdall_stop_ports
      echo "Parado. Para subir de novo: heimdall up" ;;
    status) _heimdall_sh subir.sh --status ;;
    logs)
      case "$1" in
        "") _heimdall_sh subir.sh --log ;;
        --list) _heimdall_sh subir.sh --logs ;;
        --clean) _heimdall_sh subir.sh --limpar ;;
        --service)
          case "$2" in
            agent) a=agente ;; notes) a=notas ;; health) a=saude_painel ;; terminal) a=open_terminal ;;
            mcp-public) a=mcp_public ;; mcp-data) a=mcp_dados ;; *) a="$2" ;;
          esac
          _heimdall_sh subir.sh --log "$a" ;;
        *) echo "Use: heimdall logs [--list] [--clean] [--service NOME]"; return 1 ;;
      esac ;;
    containers) docker ps "$@" ;;
    models) ollama list "$@" ;;

    chat)
      case "$1" in
        "") _heimdall_open "Open WebUI (chat)" "http://localhost:3000" ;;
        --diagnose) _heimdall_sh diagnostico_chat.sh ;;
        --password) shift; _heimdall_sh trocar_senha_webui.sh "$@" ;;
        *) echo "Use: heimdall chat [--diagnose] [--password]"; return 1 ;;
      esac ;;
    notes)
      case "$1" in
        "") _heimdall_open "Heimdall Notas" "http://localhost:$(_heimdall_port HEIMDALL_NOTAS_PORT 8011)" ;;
        --clean-mirrors) shift; _heimdall_py limpar_espelhos.py "$@" ;;
        --clean-private) shift; _heimdall_py limpar_privadas.py "$@" ;;
        --move-old) shift; _heimdall_tr "--run=--executar" "$@"; _heimdall_py mover_notas_antigas.py "${_HA[@]}" ;;
        *) echo "Use: heimdall notes [--clean-mirrors] [--clean-private] [--move-old [--run]]"; return 1 ;;
      esac ;;
    news) _heimdall_open "Heimdall News" "http://localhost:$(_heimdall_port HEIMDALL_NEWS_PORT 8012)" ;;
    cloud) _heimdall_open "Heimdall Cloud" "http://localhost:$(_heimdall_port HEIMDALL_CLOUD_PORT 8010)" ;;
    health)
      case "$1" in
        "") _heimdall_open "Painel de saúde" "http://localhost:$(_heimdall_port HEIMDALL_SAUDE_PAINEL_PORT 8013)" ;;
        --open)
          case "$2" in
            anomalies) pg=anomalias ;; today) pg=hoje ;; week) pg=semana ;; sleep) pg=sono ;; activity) pg=atividade ;;
            recovery) pg=recuperacao ;; heart) pg=coracao ;; workouts) pg=treinos ;; events) pg=eventos ;; diary) pg=diario ;; data) pg=dados ;;
            "") pg="" ;; *) pg="$2" ;;
          esac
          _heimdall_open "Painel de saúde" "http://localhost:$(_heimdall_port HEIMDALL_SAUDE_PAINEL_PORT 8013)${pg:+/$pg}" ;;
        --import-n8n) _heimdall_py importar_saude_n8n.py ;;
        *)
          _heimdall_tr "--today=--hoje
--now=--agora
--weekly=--semanal
--anomalies=--anomalias
--report=--relatorio
--sleep=--sono
--activity=--atividade
--recovery=--recuperacao
--trends=--tendencias
--workouts=--treinos
--import=--importar" "$@"
          _heimdall_py heimdall_saude.py "${_HA[@]}" ;;
      esac ;;
    n8n) _heimdall_open "n8n" "http://localhost:5678" ;;
    kuma) _heimdall_open "Uptime Kuma" "http://localhost:3001" ;;
    dozzle) _heimdall_open "Dozzle (logs)" "http://localhost:8081" ;;
    urls)
      echo "chat: http://localhost:3000"
      echo "notes: http://localhost:$(_heimdall_port HEIMDALL_NOTAS_PORT 8011)"
      echo "news: http://localhost:$(_heimdall_port HEIMDALL_NEWS_PORT 8012)"
      echo "cloud: http://localhost:$(_heimdall_port HEIMDALL_CLOUD_PORT 8010)"
      echo "health: http://localhost:$(_heimdall_port HEIMDALL_SAUDE_PAINEL_PORT 8013)"
      echo "n8n: http://localhost:5678"
      echo "kuma: http://localhost:3001"
      echo "dozzle: http://localhost:8081" ;;

    triage)
      if [ "$1" = "--complete-tests" ]; then _heimdall_sh concluir_testes_triagem.sh; else _heimdall_sh consultar_triagem.sh "$@"; fi ;;
    db) _heimdall_py heimdall_banco.py "$@" ;;
    backup)
      _heimdall_tr "--prepare=preparar
--password=senha
--run=fazer
--list=listar
--verify=verificar
--restore=restaurar" "$@"
      _heimdall_py heimdall_backup.py "${_HA[@]}" ;;
    mail) _heimdall_tr "--test-login=--testar-login
--simulate=--simular" "$@"; _heimdall_py heimdall_email_oficial.py "${_HA[@]}" ;;
    access)
      _heimdall_tr "--password=--senha
--code=--codigo
--all=--tudo
--verify=--verificar" "$@"
      _heimdall_py heimdall_acesso.py "${_HA[@]}" ;;
    voice) _heimdall_tr "--import=--importar" "$@"; _heimdall_py heimdall_voz.py "${_HA[@]}" ;;
    listen) _heimdall_tr "--list=--lista
--latest=-" "$@"; _heimdall_sh ouvir_estudo.sh "${_HA[@]}" ;;
    ingest) _heimdall_py ingest_docs.py "$@" ;;
    env) _heimdall_tr "--set=-" "$@"; _heimdall_sh guardar_no_env.sh "${_HA[@]}" ;;
    cloudflare) _heimdall_tr "--set=-
--test=--testar" "$@"; _heimdall_py cloudflare_chave.py "${_HA[@]}" ;;
    mcp) _heimdall_tr "--verify=-" "$@"; _heimdall_sh verificar_mcp_dados.sh "${_HA[@]}" ;;

    flows)
      case "$1" in
        ""|--advanced) shift 2>/dev/null; _heimdall_sh instalar_automacoes_avancadas.sh "$@" ;;
        --basic) shift; _heimdall_sh instalar_fluxos_n8n.sh "$@" ;;
        --privacy) shift; _heimdall_sh instalar_monitor_privacidade.sh "$@" ;;
        --email) shift; _heimdall_sh instalar_email_oficial.sh "$@" ;;
        *) echo "Use: heimdall flows [--advanced] [--basic] [--privacy] [--email]"; return 1 ;;
      esac ;;
    hook) _heimdall_tr "--install=-
--remove=--remover" "$@"; _heimdall_sh instalar_hook_gitops.sh "${_HA[@]}" ;;
    update)
      local restart=0 branch
      [ "$1" = "--restart" ] && restart=1
      branch="$(git -C "$HEIMDALL_DIR" rev-parse --abbrev-ref HEAD)"
      echo "Atualizando a branch $branch..."
      git -C "$HEIMDALL_DIR" pull --ff-only origin "$branch" || { echo "O pull falhou; veja a mensagem acima."; return 1; }
      if [ "$restart" = 1 ]; then
        _heimdall_sh subir.sh --reiniciar
      else
        echo "Pronto. Se mudou código de serviço: heimdall restart. Se mudou fluxo do n8n: heimdall flows."
      fi ;;
    docs)
      case "$1" in
        "") _heimdall_py gerar_docs.py ;;
        --brand) _heimdall_py gerar_marca_png.py ;;
        *) echo "Use: heimdall docs [--brand]"; return 1 ;;
      esac ;;
    test)
      case "$1" in
        ""|--list) ( cd "$HEIMDALL_DIR" && ls teste_*.py teste_*.sh test_*.py 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//' ) ;;
        --all)
          local f falhas=0
          for f in "$HEIMDALL_DIR"/teste_*.py; do
            echo "== $(basename "$f")"
            _heimdall_py "$(basename "$f")" > /dev/null 2>&1 && echo "ok" || { echo "FALHOU"; falhas=$((falhas+1)); }
          done
          echo "Testes com falha: $falhas"
          [ "$falhas" = 0 ] ;;
        --run)
          a="$2"; shift 2 2>/dev/null
          if [ -f "$HEIMDALL_DIR/teste_$a.py" ]; then _heimdall_py "teste_$a.py" "$@"
          elif [ -f "$HEIMDALL_DIR/teste_$a.sh" ]; then _heimdall_sh "teste_$a.sh" "$@"
          elif [ -f "$HEIMDALL_DIR/test_$a.py" ]; then _heimdall_py "test_$a.py" "$@"
          else echo "Teste desconhecido. Veja a lista com: heimdall test --list"; return 1; fi ;;
        *) echo "Use: heimdall test [--list] [--all] [--run NOME]"; return 1 ;;
      esac ;;
    dir) echo "$HEIMDALL_DIR" ;;
    cd) cd "$HEIMDALL_DIR" ;;

    *) echo "Comando desconhecido: $cmd. Veja os comandos com: heimdall help"; return 1 ;;
  esac
}

# Completar com Tab (zsh)
if [ -n "$ZSH_VERSION" ] && whence compdef > /dev/null 2>&1; then
  _heimdall_complete() {
    local -a cmds
    cmds=(up restart stop status logs containers models chat notes news cloud health n8n kuma dozzle urls triage db backup mail access voice listen ingest env cloudflare mcp flows hook update docs test dir cd help)
    if (( CURRENT == 2 )); then
      compadd -a cmds
      return
    fi
    case ${words[2]} in
      up|restart) compadd -- --webui --terminal --n8n --agent --ingest --docling --update ;;
      logs) if [[ ${words[CURRENT-1]} == --service ]]; then compadd -- mcp mcp-public mcp-data agent cloud notes news health terminal ingest; else compadd -- --list --clean --service; fi ;;
      chat) compadd -- --diagnose --password ;;
      notes) compadd -- --clean-mirrors --clean-private --move-old --run ;;
      health)
        if [[ ${words[CURRENT-1]} == --open ]]; then compadd -- anomalies today week sleep activity recovery heart workouts events diary data
        else compadd -- --open --today --now --weekly --anomalies --report --sleep --activity --recovery --trends --workouts --ecg --fc --import --import-n8n; fi ;;
      triage) compadd -- --complete-tests ;;
      db) compadd -- --sql ;;
      backup) compadd -- --prepare --password --run --list --verify --restore ;;
      mail) compadd -- --test-login --simulate ;;
      access) compadd -- --password --code --all --verify ;;
      voice) compadd -- --import ;;
      listen) compadd -- --list --latest ;;
      ingest) compadd -- --reset ;;
      env) compadd -- --set ;;
      cloudflare) compadd -- --set --test ;;
      mcp) compadd -- --verify ;;
      flows) compadd -- --advanced --basic --privacy --email ;;
      hook) compadd -- --install --remove ;;
      update) compadd -- --restart ;;
      docs) compadd -- --brand ;;
      test)
        if [[ ${words[CURRENT-1]} == --run ]]; then compadd -- $(cd "$HEIMDALL_DIR" 2>/dev/null && ls teste_*.py teste_*.sh test_*.py 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//')
        else compadd -- --list --all --run; fi ;;
    esac
  }
  compdef _heimdall_complete heimdall
fi
