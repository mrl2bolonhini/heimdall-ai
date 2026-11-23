#!/usr/bin/env bash
# Cria as políticas de gasto da Cloudflare (teto do projeto: US$ 15 por mês). Lê CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID do .env; nunca imprime o token.
# O token precisa da permissão Faturamento (Billing) com edição. Rode de novo sem medo: políticas que já existem com o mesmo nome são puladas.
# Uso: ./scripts/limites_gasto_cloudflare.sh [--ver]   (--ver só lista as políticas)
cd "$(dirname "$0")/.."
lerenv() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//"; }
TOKEN="$(lerenv CLOUDFLARE_API_TOKEN)"; CONTA="$(lerenv CLOUDFLARE_ACCOUNT_ID)"
[ -n "$TOKEN" ] && [ -n "$CONTA" ] || { echo "Faltam CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID no .env."; exit 1; }
EMAIL="${HEIMDALL_CF_ALERTA_EMAIL:-$(lerenv HEIMDALL_CF_ALERTA_EMAIL)}"; EMAIL="${EMAIL:-mbolonhinic@gmail.com}"
URL="https://api.cloudflare.com/client/v4/accounts/$CONTA/billing/spend-policies"
export TOKEN URL EMAIL VER="${1:-}"
python3 - <<'PY'
import json, os, sys, urllib.request, urllib.error
tok, url, email = os.environ["TOKEN"], os.environ["URL"], os.environ["EMAIL"]
def chamar(met, corpo=None):
    req = urllib.request.Request(url, method=met, data=json.dumps(corpo).encode() if corpo else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code, json.load(e)
        except Exception: return e.code, {}
st, ex = chamar("GET")
if st != 200:
    print(f"Não consegui ler as políticas (HTTP {st}). Confira se o token tem a permissão Faturamento com edição."); sys.exit(1)
existentes = {p["name"]: p for p in ex.get("result", [])}
for p in ex.get("result", []):
    print("existe:", p["name"], p["product_id"], p["action"], p["threshold_cents"] / 100, "USD", (p.get("current_state") or {}).get("status", ""))
if os.environ.get("VER") == "--ver": sys.exit(0)
# Teto total de US$ 15: Workers até 10 e Durable Objects (usados pelos Containers) até 5; avisos na metade de cada um.
politicas = [
    ("Heimdall: bloqueio Workers US$ 10", "workers", 1000, "usage_block"),
    ("Heimdall: bloqueio Durable Objects US$ 5", "durable_objects", 500, "usage_block"),
    ("Heimdall: aviso Workers US$ 5", "workers", 500, "notification"),
    ("Heimdall: aviso Durable Objects US$ 2,50", "durable_objects", 250, "notification"),
]
for nome, prod, cents, acao in politicas:
    if nome in existentes:
        print("pulada (já existe):", nome); continue
    corpo = {"name": nome, "product_id": prod, "enabled": True, "threshold_cents": cents, "action": acao}
    if acao == "notification": corpo["notification_email"] = email
    st, r = chamar("POST", corpo)
    print(("criada: " if st in (200, 201) else f"FALHOU (HTTP {st}): ") + nome, "" if st in (200, 201) else str(r.get("errors"))[:200])
PY
