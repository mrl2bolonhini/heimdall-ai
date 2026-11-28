#!/bin/bash
# Roda os testes do projeto (tests/<serviço>/ e cloudflare/) e mostra um resumo com o motivo de cada falha.
#   ./rodar_testes.sh                    roda tudo
#   ./rodar_testes.sh finance health     roda só as pastas tests/finance e tests/health
#   ./rodar_testes.sh agenda banco       roda os testes cujo caminho contém o texto (agenda, banco)
#   ./rodar_testes.sh -l [ALVO...]       lista as pastas (ou os testes dos alvos)
#   -x, --stop       para no primeiro teste que falhar
#   -q, --quiet      não mostra os testes que passaram
#   -v, --verbose    mostra a saída completa de todos os testes
#   Cada teste roda em ambiente limpo (sem o .env exportado no terminal; nuvem desligada, motor interno, agente numa porta morta).
#   -n, --lines N    linhas finais da saída de cada falha (padrão 40; 0 mostra tudo)
# Alguns testes (test_mcp.py, test_models_tools.py) precisam dos serviços no ar; os demais não usam rede.
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-}"
[ -z "$PY" ] && [ -x venv/bin/python ] && PY="venv/bin/python"   # o mesmo Python dos serviços, com as dependências instaladas
[ -z "$PY" ] && PY="python3"
LISTAR=0; PARAR=0; QUIETO=0; VERBOSO=0; LINHAS=40; ALVOS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -l|--list) LISTAR=1 ;;
    -x|--stop) PARAR=1 ;;
    -q|--quiet) QUIETO=1 ;;
    -v|--verbose) VERBOSO=1 ;;
    -n|--lines) shift; LINHAS="${1:-40}" ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Opção desconhecida: $1 (veja ./rodar_testes.sh --help)"; exit 2 ;;
    *) ALVOS+=("$1") ;;
  esac
  shift
done
case "$LINHAS" in ''|*[!0-9]*) echo "--lines pede um número."; exit 2 ;; esac

todos() {  # todos os arquivos de teste, em ordem
  ls tests/*/teste*.py tests/*/test_*.py tests/*/teste*.js tests/*/teste_silenciar_docker.sh cloudflare/teste*.mjs 2>/dev/null | grep -v "_util.py" | sort -u
}
SEL=()
if [ ${#ALVOS[@]} -eq 0 ]; then
  [ "$LISTAR" = 1 ] && { ls tests; exit 0; }
  while IFS= read -r f; do SEL+=("$f"); done < <(todos)
else
  for a in "${ALVOS[@]}"; do
    a="${a#tests/}"; a="${a%/}"
    ACHOU=0
    while IFS= read -r f; do
      if [ -d "tests/$a" ]; then case "$f" in tests/$a/*) ;; *) continue ;; esac
      else case "$f" in *"$a"*) ;; *) continue ;; esac; fi
      ACHOU=1; SEL+=("$f")
    done < <(todos)
    if [ "$ACHOU" = 0 ]; then echo "Nenhum teste combina com \"$a\". Pastas: $(ls tests | tr '\n' ' ')"; exit 2; fi
  done
  while IFS= read -r f; do UNI+=("$f"); done < <(printf '%s\n' "${SEL[@]}" | awk '!v[$0]++')
  SEL=("${UNI[@]}")
fi
if [ "$LISTAR" = 1 ]; then printf '%s\n' "${SEL[@]}"; exit 0; fi

AMBIENTE=(STUDIO_NUVEM=0 STUDIO_HUB_MOTOR=interno STUDIO_AGENTE_URL=http://127.0.0.1:9)
for v in PLAYWRIGHT_BROWSERS_PATH XDG_CACHE_HOME HOME PATH LANG LC_ALL TZ TMPDIR USER SHELL TERM SSL_CERT_FILE REQUESTS_CA_BUNDLE NODE_EXTRA_CA_CERTS HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
  [ -n "${!v:-}" ] && AMBIENTE+=("$v=${!v}")
done
SAIDA="$(mktemp)"; trap 'rm -f "$SAIDA"' EXIT
FALHAS=(); N=0
for t in "${SEL[@]}"; do
  case "$t" in *.js|*.mjs) CMD=(node "$t") ;; *.sh) CMD=(bash "$t") ;; *) CMD=("$PY" "$t") ;; esac
  # ambiente limpo: o terminal pode ter o .env exportado (agente, nuvem, motor do Hub), e o teste não pode falar com serviços reais
  CMD=(env -i "${AMBIENTE[@]}" "${CMD[@]}")
  N=$((N + 1))
  if timeout 300 "${CMD[@]}" >"$SAIDA" 2>&1; then
    [ "$QUIETO" = 0 ] && echo "ok      $t"
    [ "$VERBOSO" = 1 ] && cat "$SAIDA"
  else
    COD=$?; FALHAS+=("$t")
    echo "FALHOU  $t (código $COD$([ "$COD" = 124 ] && echo ', tempo esgotado'))"
    if [ "$LINHAS" = 0 ] || [ "$VERBOSO" = 1 ]; then sed 's/^/    | /' "$SAIDA"; else tail -n "$LINHAS" "$SAIDA" | sed 's/^/    | /'; fi
    [ "$PARAR" = 1 ] && break
  fi
done
echo; echo "$N testes rodados, ${#FALHAS[@]} com falha."
for f in "${FALHAS[@]}"; do echo "  falhou: $f"; done
[ ${#FALHAS[@]} -eq 0 ]
