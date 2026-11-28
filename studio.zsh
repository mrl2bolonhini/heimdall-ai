# Comando unificado do ecossistema StudioLibre (zsh). Carregado pelo ~/.zshrc com:
#     source ~/StudioApps/studio.zsh
# Pasta do projeto: STUDIO_DIR (padrão ~/StudioApps). Digite "studio" sem nada para ver todos os comandos.

if [ -z "${STUDIO_DIR:-}" ]; then   # pasta do projeto: STUDIO_DIR, senão ~/StudioApps
  STUDIO_DIR="$HOME/StudioApps"
fi

# Migração única: o ~/.zshrc antigo carrega heimdall.zsh; troca para studio.zsh (com cópia de segurança do .zshrc).
if [ -f "$HOME/.zshrc" ] && grep -q 'heimdall\.zsh' "$HOME/.zshrc" 2>/dev/null; then
  cp "$HOME/.zshrc" "$HOME/.zshrc.antes-do-studio.$(date +%Y%m%d-%H%M%S)" && sed -i.tmp 's#heimdall\.zsh#studio.zsh#g' "$HOME/.zshrc" && rm -f "$HOME/.zshrc.tmp"
fi

_studio_py() {  # script Python do projeto, com o Python do venv, na pasta do projeto, sem mudar a pasta do seu terminal
  local py="$STUDIO_DIR/venv/bin/python"
  [ -x "$py" ] || py="$(command -v python3)"
  ( cd "$STUDIO_DIR" && "$py" "$@" )
}

_studio_sh() {  # script de shell do projeto
  local s="$1"; shift
  ( cd "$STUDIO_DIR" && bash "./$s" "$@" )
}

_studio_tr() {  # traduz as opções em inglês para as do programa. $1 = linhas "de=para" ("-" descarta); o resto são os argumentos. Resultado em _HA
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

_studio_open() {  # $1 = nome, $2 = endereço
  echo "$1: $2"
  open "$2" 2>/dev/null || echo "Abra o endereço acima no navegador."
}

_studio_web() {  # $1 nome, $2 chave (LAB, NEWS, SAUDE_PAINEL, JOGOS, FINANCE), $3 porta padrão, $4 subdomínio padrão, $5 caminho opcional
  # Abre o endereço público (passa pelo Cloudflare Access, com o Authenticator) ou, com --local, o endereço deste Mac (senha e código de 6 dígitos).
  local nome="$1" chave="$2" padrao="$3" sub="$4" caminho="$5" porta host lista h
  porta="$(_studio_port "STUDIO_${chave}_PORT" "$padrao")"
  if [ "${_HLOCAL:-0}" = 1 ]; then
    _studio_open "$nome (local)" "http://localhost:$porta$caminho"; return
  fi
  [ -f "$STUDIO_DIR/.env" ] && lista="$(grep -E "^STUDIO_${chave}_HOSTS=" "$STUDIO_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  for h in ${(s:,:)lista}; do
    h="${h// /}"
    case "$h" in ""|localhost|127.*|*.ts.net|[0-9]*) ;; *) host="$h"; break ;; esac
  done
  [ -z "$host" ] && host="$sub.studiolibre.io"
  echo "(Sem internet ou sem passar pelo Cloudflare: use --local, ou -L, para abrir o endereço deste Mac.)"
  _studio_open "$nome" "https://$host$caminho"
}

_studio_emulador() {  # studio lab --start|--stop: liga ou desliga o emulador de AWS (sob demanda, para poupar memória)
  local c achou="" i
  case "$1" in
    start)
      for c in localstack moto; do
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$c"; then achou="$c"; break; fi
      done
      if [ -z "$achou" ]; then
        echo "Ainda não existe emulador de AWS criado. Rode studio restart uma vez: na primeira subida ele é criado."
        return 1
      fi
      docker start "$achou" > /dev/null || { echo "Não consegui ligar o emulador de AWS ($achou). Confira se o Docker está no ar: studio containers"; return 1; }
      for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        if curl -s -o /dev/null -m 2 http://127.0.0.1:4566/ 2>/dev/null; then echo "Emulador de AWS ($achou) no ar em http://localhost:4566. Para desligar: studio lab --stop"; return 0; fi
        sleep 2
      done
      echo "O emulador de AWS ($achou) foi ligado, mas ainda não respondeu. Veja: docker logs --tail 30 $achou"; return 1 ;;
    stop)
      docker stop localstack moto > /dev/null 2>&1
      echo "Emulador de AWS desligado. Para ligar de novo: studio lab --start" ;;
  esac
}

_studio_envval() {  # valor do .env ($1), ou o padrão ($2)
  local v
  [ -f "$STUDIO_DIR/.env" ] && v="$(grep -E "^$1=" "$STUDIO_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  echo "${v:-$2}"
}

_studio_port() {  # porta de cada serviço (a do .env, se houver)
  local v
  [ -f "$STUDIO_DIR/.env" ] && v="$(grep -E "^$1=" "$STUDIO_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'")"
  echo "${v:-$2}"
}

_studio_stop_ports() {
  local p
  for p in 8000 8001 8002 8003 8004 8010 8012 8013 8014 8016 8017 8018 8019 8099 9000; do
    lsof -ti:"$p" 2>/dev/null | xargs kill -9 2>/dev/null
  done
}

_studio_short() {  # opções curtas de cada comando -> opção longa em inglês
  case "$1" in
    up|restart) printf '%s\n' "-w=--webui" "-t=--terminal" "-n=--n8n" "-a=--agent" "-i=--ingest" "-d=--docling" "-u=--update" ;;
    logs) printf '%s\n' "-l=--list" "-c=--clean" "-s=--service" ;;
    containers) printf '%s\n' "-a=--all" ;;
    lab) printf '%s\n' "-L=--local" "-s=--start" "-p=--stop" ;;
    chat) printf '%s\n' "-d=--diagnose" "-p=--password" "-e=--email" "-D=--delete-user" "-c=--check" "-m=--models" "-t=--tools" ;;
    news) printf '%s\n' "-t=--token" "-u=--urls" "-c=--copy" "-o=--opml" "-s=--sources" "-q=--queue" "-n=--now"  "-L=--local" ;;
    health) printf '%s\n' "-o=--open" "-t=--today" "-n=--now" "-w=--weekly" "-a=--anomalies" "-y=--analysis" "-r=--report" "-s=--sleep" "-A=--activity" "-R=--recovery" "-T=--trends" "-W=--workouts" "-e=--ecg" "-f=--fc" "-i=--import" "-N=--import-n8n" "-l=--labs" "-L=--local" ;;
    controls) printf '%s\n' "-o=--open" "-L=--local" ;;
    account) printf '%s\n' "-L=--local" ;;
    learn) printf '%s\n' "-L=--local" "-s=--sync" "-m=--migrate" "-a=--apply" ;;
    trading|miner) printf '%s\n' "-L=--local" ;;
    hub) printf '%s\n' "-L=--local" "-P=--paperless" "-m=--clean-mirrors" "-p=--clean-private" "-o=--copy-old" "-r=--run" ;;
    games) printf '%s\n' "-p=--play" "-l=--list" "-L=--local" ;;
    finance) printf '%s\n' "-o=--open" "-i=--inspect" "-x=--explain" "-p=--preview" "-m=--import" "-b=--inbox" "-r=--retry" "-v=--values" "-f=--folder" "-l=--lines" "-a=--account" "-F=--force" "-B=--bill" "-D=--bills" "-P=--person" "-E=--read-email" "-S=--sync" "-L=--local" ;;
    db) printf '%s\n' "-s=--sql" ;;
    notices) printf '%s\n' "-m=--migrate" ;;
    doctor) printf '%s\n' "-m=--memory" "-c=--cpu" "-d=--disk" "-k=--docker" "-o=--ollama" "-s=--services" "-v=--versions" "-t=--top" ;;
    backup) printf '%s\n' "-p=--prepare" "-P=--password" "-r=--run" "-l=--list" "-v=--verify" "-R=--restore" ;;
    continuity) printf '%s\n' "-p=--prepare" "-s=--send" "-t=--status" "-d=--deploy" "-o=--off" "-n=--on" "-k=--secrets" ;;
    mail) printf '%s\n' "-t=--test-login" "-s=--simulate" "-d=--diagnose" ;;
    access) printf '%s\n' "-p=--password" "-c=--code" "-a=--all" "-v=--verify" ;;
    voice) printf '%s\n' "-i=--import" ;;
    listen) printf '%s\n' "-l=--list" "-n=--latest" ;;
    ingest) printf '%s\n' "-r=--reset" ;;
    env) printf '%s\n' "-s=--set" "-d=--defaults" ;;
    cloudflare) printf '%s\n' "-s=--set" "-t=--test" ;;
    urls) printf '%s\n' "-p=--public" "-c=--check" ;;
    app) printf '%s\n' "-l=--login" "-r=--remove-login" ;;
    usage) printf '%s\n' "-d=--days" ;;
    support) printf '%s\n' "-l=--last" "-t=--test" "-k=--token" "-r=--reply" "-d=--documents" ;;
    ask) printf '%s\n' "-l=--local" "-c=--cloud" ;;
    mcp) printf '%s\n' "-v=--verify" ;;
    flows) printf '%s\n' "-a=--advanced" "-b=--basic" "-p=--privacy" "-e=--email" ;;
    hook) printf '%s\n' "-i=--install" "-r=--remove" ;;
    update) printf '%s\n' "-r=--restart" "-a=--app" ;;
    docs) printf '%s\n' "-b=--brand" ;;
    tests) printf '%s\n' "-l=--list" "-x=--stop" "-q=--quiet" "-v=--verbose" "-n=--lines" ;;
    help) printf '%s\n' "-d=--doc" ;;
  esac
  printf '%s\n' "-h=--help"
}

_studio_ajuda_arquivo() { echo "$STUDIO_DIR/guides/studio_ajuda.txt"; }

_studio_overview() {  # lista os comandos, um por linha
  echo "Uso: studio COMANDO [--opção ...]. Para as variações de um comando: studio COMANDO --help (ou -h)."
  echo "Todas as opções têm a forma curta de uma letra. Documento completo no navegador: studio help --doc"
  echo
  awk -F' [|] ' '/^@ /{sub(/^@ /,"",$1); printf "  %-12s %s\n",$1,$2}' "$(_studio_ajuda_arquivo)"
}

_studio_usage() {  # ajuda de um comando só
  local out
  out="$(awk -v n="$1" '/^@ /{split($0,a," [|] "); nm=substr(a[1],3); if(nm==n){p=1; print "studio " nm " - " a[2]; next} else p=0} p' "$(_studio_ajuda_arquivo)")"
  if [ -z "$out" ]; then echo "Sem ajuda para: $1. Veja os comandos com: studio help"; return 1; fi
  printf '%s\n' "$out"
}

_studio_doc() {  # o Safari recusa file:// fora da área permitida; por isso o documento é servido por um servidor local mínimo (porta 8099, só 127.0.0.1)
  local dir="$STUDIO_DIR/docs" porta=8099
  if [ ! -f "$dir/comando-studio.html" ]; then echo "Não achei $dir/comando-studio.html. Rode: studio update   (ou: studio docs)"; return 1; fi
  if ! nc -z 127.0.0.1 "$porta" > /dev/null 2>&1; then
    local py; py="$(command -v python3)"
    ( cd "$dir" && nohup "$py" -m http.server "$porta" --bind 127.0.0.1 > /dev/null 2>&1 & ) > /dev/null 2>&1
    sleep 1
  fi
  _studio_open "Documento do comando studio" "http://localhost:$porta/comando-studio.html"
}

_studio_labs() {  # studio health --labs: exames, receitas, encaminhamentos, atestados, laudos e consultas
  local _sub="$1"; [ $# -gt 0 ] && shift
  _studio_tr "--without=--sem
--date=--data
--time=--hora
--doctor=--medico
--specialty=--especialidade
--place=--local
--days=--dias" "$@"
  case "$_sub" in
    ""|summary) _studio_py studio_exames.py --resumo "${_HA[@]}" ;;
    pending) _studio_py studio_exames.py --pendentes ;;
    read) _studio_py studio_exames.py --ler "${_HA[@]}" ;;
    confirm) _studio_py studio_exames.py --confirmar "${_HA[@]}" ;;
    discard) _studio_py studio_exames.py --descartar "${_HA[@]}" ;;
    folder) _studio_py studio_exames.py --pasta ;;
    import) _studio_py studio_exames.py --importar "${_HA[@]}" ;;
    result) _studio_py studio_exames.py --exame "${_HA[@]}" ;;
    analysis) _studio_py studio_exames.py --analise "${_HA[@]}" ;;
    prescriptions) _studio_py studio_exames.py --receitas ;;
    referrals) _studio_py studio_exames.py --encaminhamentos ;;
    certificates) _studio_py studio_exames.py --atestados ;;
    reports) _studio_py studio_exames.py --laudos ;;
    requests) _studio_py studio_exames.py --pedidos ;;
    suggestions)   # sugestões de acompanhamento: nada vira lembrete ou evento sem accept
      case "${_HA[1]:-}" in
        refresh) _studio_py studio_clinico.py --atualizar ;;
        all) _studio_py studio_clinico.py --sugestoes --todas ;;
        accept)   # com --date (e --time) o compromisso já marcado vira evento no Calendário; sem data, conforme o caso: evento ou lembrete
          local _a=("${(@)_HA[3,-1]}") _o=() _i
          for ((_i=1; _i<=${#_a}; _i++)); do
            case "${_a[_i]}" in --date) _o+=(--data "${_a[_i+1]:-}"); ((_i++)) ;; --time) _o+=(--hora "${_a[_i+1]:-}"); ((_i++)) ;; esac
          done
          _studio_py studio_clinico.py --aceitar "${_HA[2]:-0}" "${_o[@]}" ;;
        dismiss) _studio_py studio_clinico.py --recusar "${_HA[2]:-0}" ;;
        snooze) _studio_py studio_clinico.py --adiar "${_HA[2]:-0}" --dias "${_HA[3]:-14}" ;;
        answer) _studio_py studio_clinico.py --responder "${_HA[2]:-0}" --texto "${(j: :)_HA[3,-1]}" ;;
        "") _studio_py studio_clinico.py --sugestoes ;;
        *) echo "Use: studio health --labs suggestions [refresh|all|accept ID [--date AAAA-MM-DD] [--time HH:MM]|dismiss ID|snooze ID DAYS|answer ID TEXT]" ;;
      esac ;;
    profile)   # perfil de saúde: condições, cirurgias, alergias, convênio
      case "${_HA[1]:-}" in
        add)
          local _t="${_HA[2]:-}"
          case "$_t" in condition) _t=condicao ;; surgery) _t=cirurgia ;; allergy) _t=alergia ;; insurance) _t=convenio ;; doctor) _t=medico ;; other) _t=outro ;; esac
          _studio_py studio_clinico.py --perfil-add "$_t" --texto "${(j: :)_HA[3,-1]}" ;;
        remove) _studio_py studio_clinico.py --perfil-rm "${_HA[2]:-0}" ;;
        done) _studio_py studio_clinico.py --perfil-concluir ;;
        "") _studio_py studio_clinico.py --perfil ;;
        *) echo "Use: studio health --labs profile [add condition|surgery|allergy|insurance|doctor|other TEXT|remove ID|done]" ;;
      esac ;;
    appointments) _studio_py studio_exames.py --consultas ;;
    appointment) _studio_py studio_exames.py --consulta-nova "${_HA[@]}" ;;
    calendar) _studio_py studio_exames.py --agenda ;;
    documents) _studio_py studio_exames.py --documentos ;;
    token) _studio_py studio_exames.py --gerar-token ;;
    --open) _studio_web "Painel de saúde" SAUDE_PAINEL 8013 health /exames ;;
    *) echo "Use: studio health --labs [summary|pending|read ID|confirm ID [--without 2,5] [--date AAAA-MM-DD]|discard ID|folder|import FILE...|result NAME|analysis [NAME]|prescriptions|referrals|certificates|reports|requests|suggestions|profile|appointments|appointment --date AAAA-MM-DD [--time HH:MM] [--doctor NAME] [--specialty NAME] [--place PLACE]|calendar|documents|token|--open]"; return 1 ;;
  esac
}

studio() {
  local cmd="$1"
  [ $# -gt 0 ] && shift
  if [ ! -d "$STUDIO_DIR" ] && [ "$cmd" != "dir" ]; then
    echo "Não achei a pasta $STUDIO_DIR. Defina STUDIO_DIR no ~/.zshrc antes do source."; return 1
  fi
  local a pg
  case "$cmd" in
    ""|-h|--help) _studio_overview; return 0 ;;
    -d|--doc) _studio_doc; return $? ;;
  esac
  _studio_tr "$(_studio_short "$cmd")" "$@"
  set -- "${_HA[@]}"
  for a in "$@"; do
    if [ "$a" = "--help" ]; then _studio_usage "$cmd"; return $?; fi
  done
  _HLOCAL=0
  case "$cmd" in
    lab|learn|trading|miner|hub|news|health|games|finance|controls|account)
      local _x _n=()
      for _x in "$@"; do
        if [ "$_x" = "--local" ]; then _HLOCAL=1; else _n+=("$_x"); fi
      done
      set -- "${_n[@]}" ;;
  esac
  case "$cmd" in
    help)
      case "$1" in
        "") _studio_overview ;;
        --doc) _studio_doc ;;
        *) _studio_usage "$1" ;;
      esac ;;

    up) _studio_tr "--agent=--agente" "$@"; _studio_sh subir.sh "${_HA[@]}" ;;
    restart) _studio_tr "--agent=--agente" "$@"; _studio_sh subir.sh --reiniciar "${_HA[@]}" ;;
    stop)
      echo "Parando os serviços do Mac (o Docker continua)..."
      _studio_stop_ports
      echo "Parado. Para subir de novo: studio up" ;;
    status) _studio_sh subir.sh --status ;;
    logs)
      case "$1" in
        "") _studio_sh subir.sh --log ;;
        --list) _studio_sh subir.sh --logs ;;
        --clean) _studio_sh subir.sh --limpar ;;
        --service)
          case "$2" in
            agent) a=agente ;; learn) a=learn ;; health) a=saude_painel ;; games) a=jogos ;; terminal) a=open_terminal ;; controls) a=controls_debug ;; account) a=account_debug ;;
            finance) a=finance ;; mcp-public) a=mcp_public ;; mcp-data) a=mcp_dados ;; *) a="$2" ;;
          esac
          _studio_sh subir.sh --log "$a" ;;
        *) echo "Use: studio logs [--list] [--clean] [--service NOME]"; return 1 ;;
      esac ;;
    containers) docker ps "$@" ;;
    models) ollama list "$@" ;;

    chat)
      case "$1" in
        "") _studio_open "Open WebUI (chat)" "http://localhost:3000" ;;
        --diagnose) _studio_sh scripts/diagnostico_chat.sh ;;
        --check) _studio_py verificar_access.py "https://$(_studio_envval STUDIO_WEBUI_HOST chat.studiolibre.io)" ;;
        --password) shift; _studio_sh scripts/trocar_senha_webui.sh "$@" ;;
        --email) shift; _studio_sh scripts/trocar_email_webui.sh "$@" ;;
        --delete-user) shift; _studio_sh scripts/excluir_usuario_webui.sh "$@" ;;
        --models) shift; _studio_sh scripts/importar_modelos_webui.sh --models "$@" ;;
        --tools) shift; _studio_sh scripts/importar_modelos_webui.sh --tools "$@" ;;
        --import) shift; _studio_sh scripts/importar_modelos_webui.sh "$@" ;;
        *) echo "Use: studio chat [--diagnose] [--password] [--email] [--delete-user] [--tools] [--models] [--import] [--check]"; return 1 ;;
      esac ;;
    news)
      case "$1" in
        "") _studio_web "Studio News" NEWS 8012 news ;;
        *) _studio_tr "--copy=--copiar
--sources=--fontes
--queue=--fila
--now=--uma-vez" "$@"; _studio_py studio_news.py "${_HA[@]}" ;;
      esac ;;
    lab)
      case "$1" in
        --start) _studio_emulador start ;;
        --stop) _studio_emulador stop ;;
        "") _studio_web "Studio Lab" LAB 8010 lab ;;
        *) echo "Use: studio lab [--local] [--start] [--stop]"; return 1 ;;
      esac ;;
    health)
      case "$1" in
        "") _studio_web "Painel de saúde" SAUDE_PAINEL 8013 health ;;
        --open)
          case "$2" in
            anomalies) pg=anomalias ;; today) pg=hoje ;; week) pg=semana ;; sleep) pg=sono ;; activity) pg=atividade ;;
            recovery) pg=recuperacao ;; heart) pg=coracao ;; workouts) pg=treinos ;; events) pg=eventos ;; diary) pg=diario ;; labs) pg=exames ;; documents) pg=documentos ;; data) pg=dados ;; notices) pg=avisos ;;
            "") pg="" ;; *) pg="$2" ;;
          esac
          _studio_web "Painel de saúde" SAUDE_PAINEL 8013 health "${pg:+/$pg}" ;;
        --labs) shift; _studio_labs "$@" ;;
        --import-n8n) _studio_py importar_saude_n8n.py ;;
        *)
          _studio_tr "--today=--hoje
--now=--agora
--weekly=--semanal
--anomalies=--anomalias
--analysis=--analise
--report=--relatorio
--sleep=--sono
--activity=--atividade
--recovery=--recuperacao
--trends=--tendencias
--workouts=--treinos
--import=--importar" "$@"
          _studio_py studio_saude.py "${_HA[@]}" ;;
      esac ;;
    account) _studio_web "Account" ACCOUNT 8018 account ;;
    trading) _studio_web "Studio Trading" TRADING 8020 trading ;;
    miner) _studio_web "Studio Miner" MINER 8022 miner ;;
    hub)
      case "$1" in
        -P|--paperless) bash "$STUDIO_DIR/scripts/iniciar_paperless.sh" ;;
        --clean-mirrors) shift; _studio_py limpar_espelhos.py "$@" ;;
        --clean-private) shift; _studio_py limpar_privadas.py "$@" ;;
        --copy-old) shift; _studio_tr "--run=--executar" "$@"; _studio_py mover_notas_antigas.py "${_HA[@]}" ;;
        -*) echo "Use: studio hub [--paperless] [--clean-mirrors] [--clean-private] [--copy-old [--run]] [--local]"; return 1 ;;
        *) _studio_web "Studio Hub" HUB "$(_studio_port STUDIO_HUB_PORT 8021)" memory ;;
      esac ;;
    learn)
      case "$1" in
        "") _studio_web "Studio Learn" LEARN 8019 learn ;;
        -s|--sync) _studio_py studio_learn_dados.py --sincronizar ;;
        -m|--migrate) shift; _studio_tr "--apply=--aplicar" "$@"; _studio_py studio_learn_migrar.py "${_HA[@]}" ;;
        *) echo "Use: studio learn [--sync] [--migrate [--apply]] [--local]"; return 1 ;;
      esac ;;
    games)
      case "$1" in
        "") _studio_web "Studio Games" JOGOS 8014 games ;;
        --play) _studio_web "Jogo $2" JOGOS 8014 games "/jogo/$2" ;;
        --list) printf '%s\n' "2048 (studio games --play 2048)" "Arqueiro de áudio (studio games --play arqueiro)" "Bacará (studio games --play bacara)" "Batalha naval (studio games --play naval)" "Blackjack (studio games --play blackjack)" "Caça-níqueis (studio games --play cacaniqueis)" "Campo minado (studio games --play minas)" "A Caverna dos Ecos (studio games --play caverna)" "Cinco letras (studio games --play cincoletras)" "Estação Orion (studio games --play orion)" "O Farol Apagado (studio games --play aventura)" "Forca (studio games --play forca)" "Gramado (studio games --play gramado)" "Jogo da velha (studio games --play velha)" "Labirinto (studio games --play labirinto)" "A Mansão dos Relógios (studio games --play relogios)" "Número secreto (studio games --play numero)" "Paciência (studio games --play paciencia)" "Poker caribenho (studio games --play caribenho)" "Poker Texas hold'em (studio games --play poker)" "Roleta (studio games --play roleta)" "Senha (studio games --play senha)" "Sonar (studio games --play sonar)" "Sudoku (studio games --play sudoku)" "O Templo Submerso (studio games --play templo)" "A Travessia das Três Provas (studio games --play escolhas)" "Vilarejo Sitiado (studio games --play vilarejo)" "Xadrez (studio games --play xadrez)" ;;
        *) echo "Use: studio games [--play JOGO] [--list]"; return 1 ;;
      esac ;;
    controls)
      case "$1" in
        ""|--open)
          case "$2" in terminal) pg=/terminal ;; services) pg=/servicos ;; maintenance) pg=/manutencao ;; settings) pg=/ajustes ;; "") pg="" ;; *) pg="/$2" ;; esac
          _studio_web "Controls" CONTROLS 8017 controls "$pg" ;;
        *) echo "Use: studio controls [--open [terminal|services|settings|maintenance]] [--local]"; return 1 ;;
      esac ;;
    finance)
      case "$1" in
        ""|--open) _studio_web "Studio Finance" FINANCE 8016 finance ;;
        --folder) _studio_py financas_cli.py --pasta --abrir ;;
        *)
          _studio_tr "--inspect=--inspecionar
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
          _studio_py financas_cli.py "${_HA[@]}" ;;
      esac ;;
    n8n) _studio_open "n8n" "http://localhost:5678" ;;
    kuma) _studio_open "Uptime Kuma" "http://localhost:3001" ;;
    dozzle) _studio_open "Dozzle (logs)" "http://localhost:8081" ;;
    urls)
      if [ "$1" = "--public" ]; then
        shift; _studio_tr "--check=--verificar" "$@"; _studio_py studio_conta.py --urls-publicas "${_HA[@]}"; return $?
      fi
      echo "chat: http://localhost:3000"
      echo "learn: http://localhost:$(_studio_port STUDIO_LEARN_PORT 8019)"
      echo "trading: http://localhost:$(_studio_port STUDIO_TRADING_PORT 8020)"
      echo "miner: http://localhost:$(_studio_port STUDIO_MINER_PORT 8022)"
      echo "hub: http://localhost:$(_studio_port STUDIO_HUB_PORT "$(_studio_port STUDIO_HUB_PORT 8021)")"
      echo "news: http://localhost:$(_studio_port STUDIO_NEWS_PORT 8012)"
      echo "lab: http://localhost:$(_studio_port STUDIO_LAB_PORT 8010)"
      echo "health: http://localhost:$(_studio_port STUDIO_SAUDE_PAINEL_PORT 8013)"
      echo "games: http://localhost:$(_studio_port STUDIO_JOGOS_PORT 8014)"
      echo "finance: http://localhost:$(_studio_port STUDIO_FINANCE_PORT 8016)"
      echo "controls: http://localhost:$(_studio_port STUDIO_CONTROLS_PORT 8017)"
      echo "account: http://localhost:$(_studio_port STUDIO_ACCOUNT_PORT 8018)"
      echo "n8n: http://localhost:5678"
      echo "kuma: http://localhost:3001"
      echo "dozzle: http://localhost:8081" ;;

    db) _studio_py studio_banco.py "$@" ;;
    notion) _studio_py studio_notion.py ;;
    cloudai) _studio_py studio_nuvem.py ;;
    mailbox) _studio_py studio_caixa.py "$@" ;;
    app) _studio_tr "--login=--entrar
--remove-login=--nao-entrar" "$@"; _studio_sh scripts/construir_app_mac.sh "${_HA[@]}" ;;
    ask) _studio_tr "--local=-
--cloud=-" "$@"; _studio_py studio_ask.py "${_HA[@]}" ;;
    usage) _studio_tr "--days=--dias" "$@"; _studio_py studio_cfmonitor.py "${_HA[@]}" ;;
    support) _studio_tr "--last=--ultimas
--test=--testar
--reply=--responder
--to=--para
--documents=--documentos" "$@"; _studio_py studio_ajuda.py "${_HA[@]}" ;;
    notices) _studio_tr "--migrate=--executar" "$@"; _studio_py migrar_avisos.py "${_HA[@]}" ;;
    doctor)
      _studio_tr "--memory=--memoria
--disk=--disco
--services=--servicos
--versions=--versoes
--top=--topo" "$@"
      _studio_py diagnostico.py "${_HA[@]}" ;;
    backup)
      _studio_tr "--prepare=preparar
--password=senha
--run=fazer
--list=listar
--verify=verificar
--restore=restaurar" "$@"
      _studio_py studio_backup.py "${_HA[@]}" ;;
    continuity)
      case "$1" in
        --deploy) "$STUDIO_DIR/scripts/continuidade_nuvem.sh" implantar ;;
        --off) "$STUDIO_DIR/scripts/continuidade_nuvem.sh" desligar ;;
        --on) "$STUDIO_DIR/scripts/continuidade_nuvem.sh" ligar ;;
        --secrets) "$STUDIO_DIR/scripts/continuidade_nuvem.sh" segredos ;;
        *) _studio_tr "--prepare=preparar
--send=enviar
--status=status" "$@"
           _studio_py studio_continuidade.py "${_HA[@]}" ;;
      esac ;;
    mail) _studio_tr "--test-login=--testar-login
--diagnose=--diagnostico
--simulate=--simular
--balance=--saldo
--latest=--ultimos
--summary=--resumo
--month=--mes
--search=--buscar
--category=--categoria
--limit=--limite" "$@"; _studio_py studio_email_oficial.py "${_HA[@]}" ;;
    access)
      _studio_tr "--password=--senha
--code=--codigo
--all=--tudo
--verify=--verificar" "$@"
      _studio_py studio_acesso.py "${_HA[@]}" ;;
    voice) _studio_tr "--import=--importar" "$@"; _studio_py studio_voz.py "${_HA[@]}" ;;
    listen) _studio_tr "--list=--lista
--latest=-" "$@"; _studio_sh scripts/ouvir_estudo.sh "${_HA[@]}" ;;
    ingest) _studio_py ingest_docs.py "$@" ;;
    env)
      case "$1" in
        --defaults) _studio_py studio_config.py --gravar-padroes ;;
        *) _studio_tr "--set=-" "$@"; _studio_sh scripts/guardar_no_env.sh "${_HA[@]}" ;;
      esac ;;
    cloudflare) _studio_tr "--set=-
--test=--testar" "$@"; _studio_py cloudflare_chave.py "${_HA[@]}" ;;
    mcp) _studio_tr "--verify=-" "$@"; _studio_sh scripts/verificar_mcp_dados.sh "${_HA[@]}" ;;

    flows)
      case "$1" in
        ""|--advanced) shift 2>/dev/null; _studio_sh scripts/instalar_automacoes_avancadas.sh "$@" ;;
        --basic) shift; _studio_sh scripts/instalar_fluxos_n8n.sh "$@" ;;
        --privacy) shift; _studio_sh scripts/instalar_monitor_privacidade.sh "$@" ;;
        --email) shift; _studio_sh scripts/instalar_email_oficial.sh "$@" ;;
        *) echo "Use: studio flows [--advanced] [--basic] [--privacy] [--email]"; return 1 ;;
      esac ;;
    hook) _studio_tr "--install=-
--remove=--remover" "$@"; _studio_sh scripts/instalar_hook_gitops.sh "${_HA[@]}" ;;
    update)
      local restart=0 forcar_app=0 branch antes
      case "$1" in
        "") ;;
        --restart|-r) restart=1 ;;
        --app|-a) restart=1; forcar_app=1 ;;
        *) echo "Opção desconhecida: $1. Use: studio update [--restart | --app]"; return 1 ;;
      esac
      branch="$(git -C "$STUDIO_DIR" rev-parse --abbrev-ref HEAD)"
      antes="$(git -C "$STUDIO_DIR" rev-parse HEAD)"
      echo "Atualizando a branch $branch..."
      git -C "$STUDIO_DIR" pull --ff-only origin "$branch" || { echo "O pull falhou; veja a mensagem acima."; return 1; }
      source "$STUDIO_DIR/studio.zsh" && echo "Comandos do studio recarregados neste terminal."
      if [ "$restart" = 1 ]; then
        _studio_sh subir.sh --reiniciar
        # O app de barra de menus só é compilado de novo quando a atualização mudou o app (macapp/ ou o script que o constrói), ou com --app.
        if [ "$forcar_app" = 1 ] || git -C "$STUDIO_DIR" diff --name-only "$antes" HEAD -- macapp scripts/construir_app_mac.sh | grep -q .; then
          echo "Compilando o app StudioLibre..."
          _studio_sh scripts/construir_app_mac.sh || echo "Não consegui compilar o app. Rode depois: studio app"
        fi
      else
        echo "Pronto. Se mudou código de serviço: studio restart. Se mudou fluxo do n8n: studio flows."
      fi ;;
    docs)
      case "$1" in
        "") _studio_py gerar_docs.py ;;
        --brand) _studio_py gerar_marca_png.py ;;
        *) echo "Use: studio docs [--brand]"; return 1 ;;
      esac ;;
    tests) _studio_sh rodar_testes.sh "$@" ;;
    dir) echo "$STUDIO_DIR" ;;
    cd) cd "$STUDIO_DIR" ;;

    *) echo "Comando desconhecido: $cmd. Veja os comandos com: studio help"; return 1 ;;
  esac
}

# Completar com Tab (zsh)
if [ -n "$ZSH_VERSION" ] && whence compdef > /dev/null 2>&1; then
  _studio_complete() {
    local -a cmds
    cmds=(up restart stop status logs containers models chat learn trading miner hub news lab health games finance controls account n8n kuma dozzle urls notices notion cloudai mailbox app ask usage support db doctor backup continuity mail access voice listen ingest env cloudflare mcp flows hook update docs tests dir cd help)
    if (( CURRENT == 2 )); then
      compadd -a cmds
      compadd -- --help --doc
      return
    fi
    case ${words[2]} in
      up|restart) compadd -- --webui --terminal --n8n --agent --ingest --docling --update ;;
      logs) if [[ ${words[CURRENT-1]} == --service ]]; then compadd -- mcp mcp-public mcp-data agent lab learn trading miner hub news health games finance terminal ingest; else compadd -- --list --clean --service; fi ;;
      chat) compadd -- --diagnose --password --email --delete-user --tools --models --import --check ;;
      news) compadd -- --local --token --urls --copy --opml --sources --queue --now ;;
      health)
        if [[ ${words[CURRENT-1]} == --open ]]; then compadd -- anomalies today week sleep activity recovery heart workouts events diary labs documents data notices
        elif [[ ${words[CURRENT-1]} == --labs ]]; then compadd -- summary pending read confirm discard folder import result analysis prescriptions referrals requests suggestions profile certificates reports appointments appointment calendar documents token --open
        elif (( ${words[(Ie)--labs]} )); then compadd -- --without --date --time --doctor --specialty --place
        else compadd -- --local --labs --open --today --now --weekly --anomalies --analysis --report --sleep --activity --recovery --trends --workouts --ecg --fc --import --import-n8n; fi ;;
      controls) if [[ ${words[CURRENT-1]} == --open ]]; then compadd -- terminal services maintenance; else compadd -- --open --local; fi ;;
      games) if [[ ${words[CURRENT-1]} == --play ]]; then compadd -- 2048 arqueiro bacara naval blackjack cacaniqueis minas caverna cincoletras orion aventura forca gramado velha labirinto relogios numero paciencia caribenho poker roleta senha sonar sudoku templo escolhas vilarejo xadrez
        else compadd -- --local --play --list; fi ;;
      lab) compadd -- --local --start --stop ;;
      notices) compadd -- --migrate ;;
      db) compadd -- --sql ;;
      doctor) compadd -- --memory --cpu --disk --docker --ollama --services --versions --top ;;
      backup) compadd -- --prepare --password --run --list --verify --restore ;;
      continuity) compadd -- --prepare --send --status --deploy --off --on --secrets ;;
      mail) compadd -- --test-login --diagnose --simulate ;;
      access) compadd -- --password --code --all --verify ;;
      finance) compadd -- --local --open --inspect --explain --preview --import --inbox --retry --values --folder --lines --account --force --bill --bills --person --read-email --days --sync --save-pluggy --since --list --name --rename-account --standardize-names --dedupe --simulate --now --redo-from-pluggy --diagnose-card --closing --fixed-installment --balance --latest --summary --month --search --category --limit ;;
      voice) compadd -- --import ;;
      listen) compadd -- --list --latest ;;
      ingest) compadd -- --reset ;;
      env) compadd -- --set --defaults ;;
      cloudflare) compadd -- --set --test ;;
      mailbox) compadd -- status start add remove pull ;;
      urls) compadd -- --public --check ;;
      app) compadd -- --login --remove-login ;;
      usage) compadd -- --days ;;
      support) compadd -- --last --test --token --reply --to --documents ;;
      ask) compadd -- --local --cloud ;;
      mcp) compadd -- --verify ;;
      flows) compadd -- --advanced --basic --privacy --email ;;
      hook) compadd -- --install --remove ;;
      update) compadd -- --restart --app ;;
      docs) compadd -- --brand ;;
      help) compadd -- --doc $cmds ;;
      tests)
        if [[ ${words[CURRENT-1]} == --lines ]]; then :
        else compadd -- --list --stop --quiet --verbose --lines $(cd "$STUDIO_DIR" 2>/dev/null && ls tests 2>/dev/null); fi ;;
    esac
    compadd -- --help
  }
  compdef _studio_complete studio
fi

