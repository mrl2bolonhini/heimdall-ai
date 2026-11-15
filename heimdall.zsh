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
Uso: heimdall COMANDO [argumentos]. Os argumentos vão direto ao programa por trás de cada comando.

Ligar, desligar e acompanhar
  up [opções]       sobe tudo. Padrão: --webui --terminal. Opções: --webui --terminal --n8n --agente --ingest --docling --update
  restart           encerra a subida atual e sobe de novo; aceita as mesmas opções do up
  stop              encerra os serviços do Mac (portas 8000 a 8004, 8010 a 8013 e 9000); os contêineres do Docker ficam
  status            confere o que está no ar
  logs [serviço]    sem nome, lista os arquivos de log; com nome (mcp, agente, cloud, notas, news, ...), mostra as últimas linhas
  logs --clean      apaga os logs antigos soltos na pasta do projeto
  containers        contêineres do Docker (docker ps)
  models            modelos do Ollama

Abrir no navegador (sem argumento, abre a página inicial)
  chat              Open WebUI
  notes             Heimdall Notas
  news              Heimdall News
  cloud             Heimdall Cloud (AWS local)
  health [página]   painel de saúde; páginas: anomalias hoje semana sono atividade recuperacao coracao treinos eventos diario dados
  n8n               automações
  kuma              Uptime Kuma (status)
  dozzle            logs dos contêineres
  urls              lista todos os endereços

Saúde no terminal
  health --hoje | --agora | --semanal | --anomalias [AAAA-MM-DD] | --relatorio [dias] | --sono [dias] | --atividade [dias]
         | --recuperacao [dias] | --tendencias [dias] | --treinos [dias] | --ecg [dias] | --fc [dias] | --importar arquivo.zip

Dados e rotinas
  triagem [concluir-testes]       estado da triagem de avisos; concluir-testes conclui os lembretes de teste
  banco [--sql "SELECT ..."]      banco pessoal
  backup preparar|senha|fazer|listar|verificar|restaurar     cópia de segurança criptografada
  email [--testar-login] [--simular]    verificação do e-mail oficial
  acesso --senha|--codigo|--tudo|--verificar     senha e código de 6 dígitos de todos os serviços
  webui-password                  troca a senha do Open WebUI
  voz [texto] | voz --importar arquivo.csv       dicionário de pronúncia
  ouvir [N|--lista]               toca os áudios de estudo mais recentes
  ingest [pastas] [--reset]       indexa documentos na base de conhecimento
  env NOME                        grava no .env o que está na área de transferência
  cloudflare-key [--testar]       grava ou testa a chave da Cloudflare
  import-n8n-health               copia o histórico de saúde do n8n para o banco
  clean-mirrors | clean-private   limpezas do Second Brain
  move-notes [--executar]         move as notas antigas para as subpastas de Heimdall-ai
  mcp                             verifica o MCP de dados
  diagnostico                     diagnóstico do chat

Instalar e manter
  flows [basic|privacy|email]     instala os fluxos do n8n; sem nome, as automações avançadas
  hook REPO [--remover]           liga um repositório git ao GitOps
  update [--restart]              traz as novidades do GitHub (git pull) e diz se precisa reiniciar
  docs                            regenera o site e o README
  test [nome|all]                 roda um teste; sem nome, lista os testes
  brand                           regenera as imagens da marca
  dir                             mostra a pasta do projeto; cd entra nela
AJUDA
}

heimdall() {
  local cmd="$1"
  [ $# -gt 0 ] && shift
  if [ ! -d "$HEIMDALL_DIR" ] && [ "$cmd" != "dir" ]; then
    echo "Não achei a pasta $HEIMDALL_DIR. Defina HEIMDALL_DIR no ~/.zshrc antes do source."; return 1
  fi
  local n
  case "$cmd" in
    ""|help|-h|--help) _heimdall_help ;;

    up) _heimdall_sh subir.sh "$@" ;;
    restart) _heimdall_sh subir.sh --reiniciar "$@" ;;
    stop)
      echo "Parando os serviços do Mac (o Docker continua)..."
      _heimdall_stop_ports
      echo "Parado. Para subir de novo: heimdall up" ;;
    status) _heimdall_sh subir.sh --status "$@" ;;
    logs)
      if [ -z "$1" ]; then _heimdall_sh subir.sh --logs
      elif [ "$1" = "--clean" ]; then _heimdall_sh subir.sh --limpar
      else _heimdall_sh subir.sh --log "$@"; fi ;;
    containers) docker ps "$@" ;;
    models) ollama list "$@" ;;

    chat) _heimdall_open "Open WebUI (chat)" "http://localhost:3000" ;;
    notes) _heimdall_open "Heimdall Notas" "http://localhost:$(_heimdall_port HEIMDALL_NOTAS_PORT 8011)" ;;
    news) _heimdall_open "Heimdall News" "http://localhost:$(_heimdall_port HEIMDALL_NEWS_PORT 8012)" ;;
    cloud) _heimdall_open "Heimdall Cloud" "http://localhost:$(_heimdall_port HEIMDALL_CLOUD_PORT 8010)" ;;
    health)
      case "$1" in
        --*) _heimdall_py heimdall_saude.py "$@" ;;
        *) _heimdall_open "Painel de saúde" "http://localhost:$(_heimdall_port HEIMDALL_SAUDE_PAINEL_PORT 8013)${1:+/$1}" ;;
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

    triagem)
      if [ "$1" = "concluir-testes" ]; then _heimdall_sh concluir_testes_triagem.sh; else _heimdall_sh consultar_triagem.sh "$@"; fi ;;
    banco) _heimdall_py heimdall_banco.py "$@" ;;
    backup) _heimdall_py heimdall_backup.py "$@" ;;
    email) _heimdall_py heimdall_email_oficial.py "$@" ;;
    acesso) _heimdall_py heimdall_acesso.py "$@" ;;
    webui-password) _heimdall_sh trocar_senha_webui.sh "$@" ;;
    voz) _heimdall_py heimdall_voz.py "$@" ;;
    ouvir) _heimdall_sh ouvir_estudo.sh "$@" ;;
    ingest) _heimdall_py ingest_docs.py "$@" ;;
    env) _heimdall_sh guardar_no_env.sh "$@" ;;
    cloudflare-key) _heimdall_py cloudflare_chave.py "$@" ;;
    import-n8n-health) _heimdall_py importar_saude_n8n.py "$@" ;;
    clean-mirrors) _heimdall_py limpar_espelhos.py "$@" ;;
    clean-private) _heimdall_py limpar_privadas.py "$@" ;;
    move-notes) _heimdall_py mover_notas_antigas.py "$@" ;;
    mcp) _heimdall_sh verificar_mcp_dados.sh "$@" ;;
    diagnostico) _heimdall_sh diagnostico_chat.sh "$@" ;;

    flows)
      case "$1" in
        basic) shift; _heimdall_sh instalar_fluxos_n8n.sh "$@" ;;
        privacy) shift; _heimdall_sh instalar_monitor_privacidade.sh "$@" ;;
        email) shift; _heimdall_sh instalar_email_oficial.sh "$@" ;;
        *) _heimdall_sh instalar_automacoes_avancadas.sh "$@" ;;
      esac ;;
    hook) _heimdall_sh instalar_hook_gitops.sh "$@" ;;
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
    docs) _heimdall_py gerar_docs.py "$@" ;;
    brand) _heimdall_py gerar_marca_png.py "$@" ;;
    test)
      if [ -z "$1" ]; then
        ( cd "$HEIMDALL_DIR" && ls teste_*.py teste_*.sh test_*.py 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//' )
      elif [ "$1" = "all" ]; then
        local f falhas=0
        for f in "$HEIMDALL_DIR"/teste_*.py; do
          echo "== $(basename "$f")"
          _heimdall_py "$(basename "$f")" > /dev/null 2>&1 && echo "ok" || { echo "FALHOU"; falhas=$((falhas+1)); }
        done
        echo "Testes com falha: $falhas"
        [ "$falhas" = 0 ]
      else
        n="$1"; shift
        if [ -f "$HEIMDALL_DIR/teste_$n.py" ]; then _heimdall_py "teste_$n.py" "$@"
        elif [ -f "$HEIMDALL_DIR/teste_$n.sh" ]; then _heimdall_sh "teste_$n.sh" "$@"
        elif [ -f "$HEIMDALL_DIR/test_$n.py" ]; then _heimdall_py "test_$n.py" "$@"
        else echo "Teste desconhecido. Veja a lista com: heimdall test"; return 1; fi
      fi ;;
    dir) echo "$HEIMDALL_DIR" ;;
    cd) cd "$HEIMDALL_DIR" ;;

    *) echo "Comando desconhecido: $cmd. Veja os comandos com: heimdall help"; return 1 ;;
  esac
}

# Completar com Tab (zsh)
if [ -n "$ZSH_VERSION" ] && whence compdef > /dev/null 2>&1; then
  _heimdall_complete() {
    local -a cmds
    cmds=(up restart stop status logs containers models chat notes news cloud health n8n kuma dozzle urls triagem banco backup email acesso webui-password voz ouvir ingest env cloudflare-key import-n8n-health clean-mirrors clean-private move-notes mcp diagnostico flows hook update docs brand test dir cd help)
    if (( CURRENT == 2 )); then
      compadd -a cmds
      return
    fi
    case ${words[2]} in
      up|restart) compadd -- --webui --terminal --n8n --agente --ingest --docling --update ;;
      logs) compadd -- --clean mcp mcp_public mcp_dados agente cloud notas news saude_painel open_terminal ingest ;;
      health)
        if (( CURRENT == 3 )); then compadd -- anomalias hoje semana sono atividade recuperacao coracao treinos eventos diario dados --hoje --agora --semanal --anomalias --relatorio --sono --atividade --recuperacao --tendencias --treinos --ecg --fc --importar
        else compadd -- --hoje --agora --semanal --anomalias --relatorio --sono --atividade --recuperacao --tendencias --treinos --ecg --fc --importar; fi ;;
      triagem) compadd -- concluir-testes ;;
      banco) compadd -- --sql ;;
      backup) compadd -- preparar senha fazer listar verificar restaurar ;;
      email) compadd -- --testar-login --simular ;;
      acesso) compadd -- --senha --codigo --tudo --verificar ;;
      ouvir) compadd -- --lista ;;
      ingest) compadd -- --reset ;;
      cloudflare-key) compadd -- --testar ;;
      move-notes) compadd -- --executar ;;
      hook) compadd -- --remover ;;
      update) compadd -- --restart ;;
      flows) compadd -- basic privacy email ;;
      test) compadd -- all $(cd "$HEIMDALL_DIR" 2>/dev/null && ls teste_*.py teste_*.sh test_*.py 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//') ;;
    esac
  }
  compdef _heimdall_complete heimdall
fi
