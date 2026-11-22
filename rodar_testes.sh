#!/bin/bash
# Roda todos os testes do projeto (tests/<serviço>/ e cloudflare/) e mostra um resumo.
#   ./rodar_testes.sh              roda tudo
#   ./rodar_testes.sh finance      roda só a pasta tests/finance
#   ./rodar_testes.sh -l           lista as pastas de testes
# Alguns testes (test_mcp.py, test_models_tools.py) precisam dos serviços no ar; os demais não usam rede.
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
if [ "$1" = "-l" ]; then ls tests; exit 0; fi
ALVO="${1:-}"
if [ -n "$ALVO" ] && [ ! -d "tests/$ALVO" ]; then echo "Não existe tests/$ALVO. Pastas: $(ls tests | tr '\n' ' ')"; exit 2; fi
FALHAS=(); N=0
rodar() {
  N=$((N + 1))
  if ! timeout 300 "$@" >/tmp/heimdall_teste.$$ 2>&1; then FALHAS+=("$*"); echo "FALHOU  $*"; else echo "ok      $*"; fi
}
if [ -n "$ALVO" ]; then PASTAS="tests/$ALVO"; else PASTAS="tests/*"; fi
for t in $(ls $PASTAS/teste*.py $PASTAS/test_*.py 2>/dev/null | grep -v "_util.py"); do rodar "$PY" "$t"; done
for t in $(ls $PASTAS/teste*.js 2>/dev/null); do rodar node "$t"; done
for t in $(ls $PASTAS/teste_silenciar_docker.sh 2>/dev/null); do rodar bash "$t"; done
if [ -z "$ALVO" ]; then for t in $(ls cloudflare/teste*.mjs 2>/dev/null); do rodar node "$t"; done; fi
rm -f /tmp/heimdall_teste.$$
echo; echo "$N testes rodados, ${#FALHAS[@]} com falha."
for f in "${FALHAS[@]}"; do echo "  falhou: $f"; done
[ ${#FALHAS[@]} -eq 0 ]
