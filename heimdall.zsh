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

_heimdall_web() {  # $1 nome, $2 chave (CLOUD, NOTAS, NEWS, SAUDE_PAINEL, JOGOS, FINANCE), $3 porta padrão, $4 subdomínio padrão, $5 caminho opcional
  # Abre o endereço público (passa pelo Cloudflare Access, com o Authenticator) ou, com --local, o endereço deste Mac (senha e código de 6 dígitos).
  local nome="$1" chave="$2" padrao="$3" sub="$4" caminho="$5" porta host lista h
  porta="$(_heimdall_port "HEIMDALL_${chave}_PORT" "$padrao")"
  if [ "${_HLOCAL:-0}" = 1 ]; then
    _heimdall_open "$nome (local)" "http://localhost:$porta$caminho"; return
  fi
  [ -f "$HEIMDALL_DIR/.env" ] && lista="$(grep -E "^HEIMDALL_${chave}_HOSTS=" "$HEIMDALL_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  for h in ${(s:,:)lista}; do
    h="${h// /}"
    case "$h" in ""|localhost|127.*|*.ts.net|[0-9]*) ;; *) host="$h"; break ;; esac
  done
  [ -z "$host" ] && host="$sub.heimdall-ai.tech"
  echo "(Sem internet ou sem passar pelo Cloudflare: use --local, ou -L, para abrir o endereço deste Mac.)"
  _heimdall_open "$nome" "https://$host$caminho"
}

_heimdall_port() {  # porta de cada serviço (a do .env, se houver)
  local v
  [ -f "$HEIMDALL_DIR/.env" ] && v="$(grep -E "^$1=" "$HEIMDALL_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  echo "${v:-$2}"
}

_heimdall_stop_ports() {
  local p
  for p in 8000 8001 8002 8003 8004 8010 8011 8012 8013 8014 8016 8017 8099 9000; do
    lsof -ti:"$p" 2>/dev/null | xargs kill -9 2>/dev/null
  done
}

_heimdall_short() {  # opções curtas de cada comando -> opção longa em inglês
  case "$1" in
    up|restart) printf '%s\n' "-w=--webui" "-t=--terminal" "-n=--n8n" "-a=--agent" "-i=--ingest" "-d=--docling" "-u=--update" ;;
    logs) printf '%s\n' "-l=--list" "-c=--clean" "-s=--service" ;;
    containers) printf '%s\n' "-a=--all" ;;
    cloud) printf '%s\n' "-L=--local" ;;
    chat) printf '%s\n' "-d=--diagnose" "-p=--password" ;;
    news) printf '%s\n' "-t=--token" "-u=--urls" "-c=--copy" "-o=--opml" "-s=--sources" "-q=--queue" "-n=--now"  "-L=--local" ;;
    notes) printf '%s\n' "-m=--clean-mirrors" "-p=--clean-private" "-o=--move-old" "-r=--run" "-L=--local" ;;
    health) printf '%s\n' "-o=--open" "-t=--today" "-n=--now" "-w=--weekly" "-a=--anomalies" "-r=--report" "-s=--sleep" "-A=--activity" "-R=--recovery" "-T=--trends" "-W=--workouts" "-e=--ecg" "-f=--fc" "-i=--import" "-N=--import-n8n" "-L=--local" ;;
    controls) printf '%s\n' "-o=--open" "-L=--local" ;;
    games) printf '%s\n' "-p=--play" "-l=--list" "-L=--local" ;;
    finance) printf '%s\n' "-o=--open" "-i=--inspect" "-x=--explain" "-p=--preview" "-m=--import" "-b=--inbox" "-r=--retry" "-v=--values" "-f=--folder" "-l=--lines" "-a=--account" "-F=--force" "-B=--bill" "-D=--bills" "-P=--person" "-E=--read-email" "-S=--sync" "-L=--local" ;;
    triage) printf '%s\n' "-c=--complete-tests" ;;
    db) printf '%s\n' "-s=--sql" ;;
    doctor) printf '%s\n' "-m=--memory" "-c=--cpu" "-d=--disk" "-k=--docker" "-o=--ollama" "-s=--services" "-t=--top" ;;
    backup) printf '%s\n' "-p=--prepare" "-P=--password" "-r=--run" "-l=--list" "-v=--verify" "-R=--restore" ;;
    mail) printf '%s\n' "-t=--test-login" "-s=--simulate" "-d=--diagnose" ;;
    access) printf '%s\n' "-p=--password" "-c=--code" "-a=--all" "-v=--verify" ;;
    voice) printf '%s\n' "-i=--import" ;;
    listen) printf '%s\n' "-l=--list" "-n=--latest" ;;
    ingest) printf '%s\n' "-r=--reset" ;;
    env) printf '%s\n' "-s=--set" "-d=--defaults" ;;
    cloudflare) printf '%s\n' "-s=--set" "-t=--test" ;;
    mcp) printf '%s\n' "-v=--verify" ;;
    flows) printf '%s\n' "-a=--advanced" "-b=--basic" "-p=--privacy" "-e=--email" ;;
    hook) printf '%s\n' "-i=--install" "-r=--remove" ;;
    update) printf '%s\n' "-r=--restart" ;;
    docs) printf '%s\n' "-b=--brand" ;;
    test) printf '%s\n' "-l=--list" "-a=--all" "-r=--run" ;;
    help) printf '%s\n' "-d=--doc" ;;
  esac
  printf '%s\n' "-h=--help"
}

_heimdall_ajuda_arquivo() { echo "$HEIMDALL_DIR/heimdall_ajuda.txt"; }

_heimdall_overview() {  # lista os comandos, um por linha
  echo "Uso: heimdall COMANDO [--opção ...]. Para as variações de um comando: heimdall COMANDO --help (ou -h)."
  echo "Todas as opções têm a forma curta de uma letra. Documento completo no navegador: heimdall help --doc"
  echo
  awk -F' [|] ' '/^@ /{sub(/^@ /,"",$1); printf "  %-12s %s\n",$1,$2}' "$(_heimdall_ajuda_arquivo)"
}

_heimdall_usage() {  # ajuda de um comando só
  local out
  out="$(awk -v n="$1" '/^@ /{split($0,a," [|] "); nm=substr(a[1],3); if(nm==n){p=1; print "heimdall " nm " - " a[2]; next} else p=0} p' "$(_heimdall_ajuda_arquivo)")"
  if [ -z "$out" ]; then echo "Sem ajuda para: $1. Veja os comandos com: heimdall help"; return 1; fi
  printf '%s\n' "$out"
}

_heimdall_doc() {  # o Safari recusa file:// fora da área permitida; por isso o documento é servido por um servidor local mínimo (porta 8099, só 127.0.0.1)
  local dir="$HEIMDALL_DIR/docs" porta=8099
  if [ ! -f "$dir/comando-heimdall.html" ]; then echo "Não achei $dir/comando-heimdall.html. Rode: heimdall update   (ou: heimdall docs)"; return 1; fi
  if ! nc -z 127.0.0.1 "$porta" > /dev/null 2>&1; then
    local py; py="$(command -v python3)"
    ( cd "$dir" && nohup "$py" -m http.server "$porta" --bind 127.0.0.1 > /dev/null 2>&1 & ) > /dev/null 2>&1
    sleep 1
  fi
  _heimdall_open "Documento do comando heimdall" "http://localhost:$porta/comando-heimdall.html"
}

heimdall() {
  local cmd="$1"
  [ $# -gt 0 ] && shift
  if [ ! -d "$HEIMDALL_DIR" ] && [ "$cmd" != "dir" ]; then
    echo "Não achei a pasta $HEIMDALL_DIR. Defina HEIMDALL_DIR no ~/.zshrc antes do source."; return 1
  fi
  local a pg
  case "$cmd" in
    ""|-h|--help) _heimdall_overview; return 0 ;;
    -d|--doc) _heimdall_doc; return $? ;;
  esac
  _heimdall_tr "$(_heimdall_short "$cmd")" "$@"
  set -- "${_HA[@]}"
  for a in "$@"; do
    if [ "$a" = "--help" ]; then _heimdall_usage "$cmd"; return $?; fi
  done
  _HLOCAL=0
  case "$cmd" in
    cloud|notes|news|health|games|finance|controls)
      local _x _n=()
      for _x in "$@"; do
        if [ "$_x" = "--local" ]; then _HLOCAL=1; else _n+=("$_x"); fi
      done
      set -- "${_n[@]}" ;;
  esac
  case "$cmd" in
    help)
      case "$1" in
        "") _heimdall_overview ;;
        --doc) _heimdall_doc ;;
        *) _heimdall_usage "$1" ;;
      esac ;;

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
            agent) a=agente ;; notes) a=notas ;; health) a=saude_painel ;; games) a=jogos ;; terminal) a=open_terminal ;; controls) a=controls_debug ;;
            finance) a=finance ;; mcp-public) a=mcp_public ;; mcp-data) a=mcp_dados ;; *) a="$2" ;;
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
        "") _heimdall_web "Heimdall Notas" NOTAS 8011 notes ;;
        --clean-mirrors) shift; _heimdall_py limpar_espelhos.py "$@" ;;
        --clean-private) shift; _heimdall_py limpar_privadas.py "$@" ;;
        --move-old) shift; _heimdall_tr "--run=--executar" "$@"; _heimdall_py mover_notas_antigas.py "${_HA[@]}" ;;
        *) echo "Use: heimdall notes [--clean-mirrors] [--clean-private] [--move-old [--run]]"; return 1 ;;
      esac ;;
    news)
      case "$1" in
        "") _heimdall_web "Heimdall News" NEWS 8012 news ;;
        *) _heimdall_tr "--copy=--copiar
--sources=--fontes
--queue=--fila
--now=--uma-vez" "$@"; _heimdall_py heimdall_news.py "${_HA[@]}" ;;
      esac ;;
    cloud) _heimdall_web "Heimdall Cloud" CLOUD 8010 cloud ;;
    health)
      case "$1" in
        "") _heimdall_web "Painel de saúde" SAUDE_PAINEL 8013 health ;;
        --open)
          case "$2" in
            anomalies) pg=anomalias ;; today) pg=hoje ;; week) pg=semana ;; sleep) pg=sono ;; activity) pg=atividade ;;
            recovery) pg=recuperacao ;; heart) pg=coracao ;; workouts) pg=treinos ;; events) pg=eventos ;; diary) pg=diario ;; labs) pg=exames ;; documents) pg=documentos ;; data) pg=dados ;;
            "") pg="" ;; *) pg="$2" ;;
          esac
          _heimdall_web "Painel de saúde" SAUDE_PAINEL 8013 health "${pg:+/$pg}" ;;
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
    labs)
      local _sub="$1"; [ $# -gt 0 ] && shift
      _heimdall_tr "--without=--sem
--date=--data
--time=--hora
--doctor=--medico
--specialty=--especialidade
--place=--local
--days=--dias" "$@"
      case "$_sub" in
        ""|summary) _heimdall_py heimdall_exames.py --resumo "${_HA[@]}" ;;
        pending) _heimdall_py heimdall_exames.py --pendentes ;;
        read) _heimdall_py heimdall_exames.py --ler "${_HA[@]}" ;;
        confirm) _heimdall_py heimdall_exames.py --confirmar "${_HA[@]}" ;;
        discard) _heimdall_py heimdall_exames.py --descartar "${_HA[@]}" ;;
        folder) _heimdall_py heimdall_exames.py --pasta ;;
        import) _heimdall_py heimdall_exames.py --importar "${_HA[@]}" ;;
        result) _heimdall_py heimdall_exames.py --exame "${_HA[@]}" ;;
        analysis) _heimdall_py heimdall_exames.py --analise "${_HA[@]}" ;;
        prescriptions) _heimdall_py heimdall_exames.py --receitas ;;
        referrals) _heimdall_py heimdall_exames.py --encaminhamentos ;;
        appointments) _heimdall_py heimdall_exames.py --consultas ;;
        appointment) _heimdall_py heimdall_exames.py --consulta-nova "${_HA[@]}" ;;
        calendar) _heimdall_py heimdall_exames.py --agenda ;;
        documents) _heimdall_py heimdall_exames.py --documentos ;;
        token) _heimdall_py heimdall_exames.py --gerar-token ;;
        --open) _heimdall_web "Painel de saúde" SAUDE_PAINEL 8013 health /exames ;;
        *) echo "Use: heimdall labs [summary|pending|read ID|confirm ID [--without 2,5] [--date AAAA-MM-DD]|discard ID|folder|import FILE...|result NAME|analysis [NAME]|prescriptions|referrals|appointments|appointment --date AAAA-MM-DD [--time HH:MM] [--doctor NAME] [--specialty NAME] [--place PLACE]|calendar|documents|token|--open]"; return 1 ;;
      esac ;;
    games)
      case "$1" in
        "") _heimdall_web "Heimdall Jogos" JOGOS 8014 games ;;
        --play) _heimdall_web "Jogo $2" JOGOS 8014 games "/jogo/$2" ;;
        --list) printf '%s\n' "2048 (heimdall games --play 2048)" "Arqueiro de áudio (heimdall games --play arqueiro)" "Bacará (heimdall games --play bacara)" "Batalha naval (heimdall games --play naval)" "Blackjack (heimdall games --play blackjack)" "Caça-níqueis (heimdall games --play cacaniqueis)" "Campo minado (heimdall games --play minas)" "A Caverna dos Ecos (heimdall games --play caverna)" "Cinco letras (heimdall games --play cincoletras)" "Estação Orion (heimdall games --play orion)" "O Farol Apagado (heimdall games --play aventura)" "Forca (heimdall games --play forca)" "Gramado (heimdall games --play gramado)" "Jogo da velha (heimdall games --play velha)" "Labirinto (heimdall games --play labirinto)" "A Mansão dos Relógios (heimdall games --play relogios)" "Número secreto (heimdall games --play numero)" "Paciência (heimdall games --play paciencia)" "Poker caribenho (heimdall games --play caribenho)" "Poker Texas hold'em (heimdall games --play poker)" "Roleta (heimdall games --play roleta)" "Senha (heimdall games --play senha)" "Sonar (heimdall games --play sonar)" "Sudoku (heimdall games --play sudoku)" "O Templo Submerso (heimdall games --play templo)" "A Travessia das Três Provas (heimdall games --play escolhas)" "Xadrez (heimdall games --play xadrez)" ;;
        *) echo "Use: heimdall games [--play JOGO] [--list]"; return 1 ;;
      esac ;;
    controls)
      case "$1" in
        ""|--open)
          case "$2" in terminal) pg=/terminal ;; services) pg=/servicos ;; maintenance) pg=/manutencao ;; settings) pg=/ajustes ;; "") pg="" ;; *) pg="/$2" ;; esac
          _heimdall_web "Heimdall Controls" CONTROLS 8017 controls "$pg" ;;
        *) echo "Use: heimdall controls [--open [terminal|services|settings|maintenance]] [--local]"; return 1 ;;
      esac ;;
    finance)
      case "$1" in
        ""|--open) _heimdall_web "Heimdall Finance" FINANCE 8016 finance ;;
        --folder) _heimdall_py financas_cli.py --pasta --abrir ;;
        *)
          _heimdall_tr "--inspect=--inspecionar
--explain=--explicar
--preview=--prever
--import=--importar
--inbox=--entrada
--retry=--reprocessar
--values=--valores
--lines=--linhas
--account=--conta
--force=--forcar
--bill=--boleto
--bills=--boletos
--person=--pessoa
--read-email=--ler-email
--days=--dias
--sync=--sincronizar
--save-pluggy=--guardar-pluggy
--since=--desde
--list=--listar
--name=--nomear
--rename-account=--renomear-conta
--standardize-names=--padronizar-nomes
--dedupe=--deduplicar
--simulate=--simular
--redo-from-pluggy=--refazer-pelo-pluggy
--now=--agora
--closing=--fechamento
--fixed-installment=--parcela-fixa
--diagnose-card=--diagnosticar-cartao
--balance=--saldo
--latest=--ultimos
--summary=--resumo
--month=--mes
--search=--buscar
--category=--categoria
--limit=--limite" "$@"
          _heimdall_py financas_cli.py "${_HA[@]}" ;;
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
      echo "games: http://localhost:$(_heimdall_port HEIMDALL_JOGOS_PORT 8014)"
      echo "finance: http://localhost:$(_heimdall_port HEIMDALL_FINANCE_PORT 8016)"
      echo "controls: http://localhost:$(_heimdall_port HEIMDALL_CONTROLS_PORT 8017)"
      echo "n8n: http://localhost:5678"
      echo "kuma: http://localhost:3001"
      echo "dozzle: http://localhost:8081" ;;

    triage)
      if [ "$1" = "--complete-tests" ]; then _heimdall_sh concluir_testes_triagem.sh; else _heimdall_sh consultar_triagem.sh "$@"; fi ;;
    db) _heimdall_py heimdall_banco.py "$@" ;;
    doctor)
      _heimdall_tr "--memory=--memoria
--disk=--disco
--services=--servicos
--top=--topo" "$@"
      _heimdall_py diagnostico.py "${_HA[@]}" ;;
    backup)
      _heimdall_tr "--prepare=preparar
--password=senha
--run=fazer
--list=listar
--verify=verificar
--restore=restaurar" "$@"
      _heimdall_py heimdall_backup.py "${_HA[@]}" ;;
    mail) _heimdall_tr "--test-login=--testar-login
--diagnose=--diagnostico
--simulate=--simular
--balance=--saldo
--latest=--ultimos
--summary=--resumo
--month=--mes
--search=--buscar
--category=--categoria
--limit=--limite" "$@"; _heimdall_py heimdall_email_oficial.py "${_HA[@]}" ;;
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
    env)
      case "$1" in
        --defaults) _heimdall_py heimdall_config.py --gravar-padroes ;;
        *) _heimdall_tr "--set=-" "$@"; _heimdall_sh guardar_no_env.sh "${_HA[@]}" ;;
      esac ;;
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
      case "$1" in
        "") ;;
        --restart|-r) restart=1 ;;
        *) echo "Opção desconhecida: $1. Use: heimdall update [--restart]"; return 1 ;;
      esac
      branch="$(git -C "$HEIMDALL_DIR" rev-parse --abbrev-ref HEAD)"
      echo "Atualizando a branch $branch..."
      git -C "$HEIMDALL_DIR" pull --ff-only origin "$branch" || { echo "O pull falhou; veja a mensagem acima."; return 1; }
      source "$HEIMDALL_DIR/heimdall.zsh" && echo "Comandos do heimdall recarregados neste terminal."
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
    cmds=(up restart stop status logs containers models chat notes news cloud health labs games finance controls n8n kuma dozzle urls triage db doctor backup mail access voice listen ingest env cloudflare mcp flows hook update docs test dir cd help)
    if (( CURRENT == 2 )); then
      compadd -a cmds
      compadd -- --help --doc
      return
    fi
    case ${words[2]} in
      up|restart) compadd -- --webui --terminal --n8n --agent --ingest --docling --update ;;
      logs) if [[ ${words[CURRENT-1]} == --service ]]; then compadd -- mcp mcp-public mcp-data agent cloud notes news health games finance terminal ingest; else compadd -- --list --clean --service; fi ;;
      chat) compadd -- --diagnose --password ;;
      news) compadd -- --local --token --urls --copy --opml --sources --queue --now ;;
      notes) compadd -- --local --clean-mirrors --clean-private --move-old --run ;;
      health)
        if [[ ${words[CURRENT-1]} == --open ]]; then compadd -- anomalies today week sleep activity recovery heart workouts events diary labs documents data
        else compadd -- --local --open --today --now --weekly --anomalies --report --sleep --activity --recovery --trends --workouts --ecg --fc --import --import-n8n; fi ;;
      controls) if [[ ${words[CURRENT-1]} == --open ]]; then compadd -- terminal services maintenance; else compadd -- --open --local; fi ;;
      labs) compadd -- summary pending read confirm discard folder import result analysis prescriptions referrals appointments appointment calendar documents token --open --without --date --time --doctor --specialty --place ;;
      games) if [[ ${words[CURRENT-1]} == --play ]]; then compadd -- 2048 arqueiro bacara naval blackjack cacaniqueis minas caverna cincoletras orion aventura forca gramado velha labirinto relogios numero paciencia caribenho poker roleta senha sonar sudoku templo escolhas xadrez
        else compadd -- --local --play --list; fi ;;
      cloud) compadd -- --local ;;
      triage) compadd -- --complete-tests ;;
      db) compadd -- --sql ;;
      doctor) compadd -- --memory --cpu --disk --docker --ollama --services --top ;;
      backup) compadd -- --prepare --password --run --list --verify --restore ;;
      mail) compadd -- --test-login --diagnose --simulate ;;
      access) compadd -- --password --code --all --verify ;;
      finance) compadd -- --local --open --inspect --explain --preview --import --inbox --retry --values --folder --lines --account --force --bill --bills --person --read-email --days --sync --save-pluggy --since --list --name --rename-account --standardize-names --dedupe --simulate --now --redo-from-pluggy --diagnose-card --closing --fixed-installment --balance --latest --summary --month --search --category --limit ;;
      voice) compadd -- --import ;;
      listen) compadd -- --list --latest ;;
      ingest) compadd -- --reset ;;
      env) compadd -- --set --defaults ;;
      cloudflare) compadd -- --set --test ;;
      mcp) compadd -- --verify ;;
      flows) compadd -- --advanced --basic --privacy --email ;;
      hook) compadd -- --install --remove ;;
      update) compadd -- --restart ;;
      docs) compadd -- --brand ;;
      help) compadd -- --doc $cmds ;;
      test)
        if [[ ${words[CURRENT-1]} == --run ]]; then compadd -- $(cd "$HEIMDALL_DIR" 2>/dev/null && ls teste_*.py teste_*.sh test_*.py 2>/dev/null | sed 's/^teste_//; s/\.py$//; s/\.sh$//')
        else compadd -- --list --all --run; fi ;;
    esac
    compadd -- --help
  }
  compdef _heimdall_complete heimdall
fi
