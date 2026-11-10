"""Confere a consulta ao Diário da Justiça (DJEN) e ao Querido Diário. Mostra só estrutura, nunca o conteúdo das publicações.
Uso: python3 teste_diario_justica.py [dias]   (lê HEIMDALL_OAB=NUMERO/UF do .env; dias padrão: 30)"""
import json, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

def oab_do_env():
    arq = Path(__file__).resolve().parent / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(?:export\s+)?HEIMDALL_OAB=['\"]?(\d{1,7})\s*[/-]?\s*([A-Za-z]{2})", linha)
            if m:
                return m.group(1), m.group(2).upper()
    return None

def pegar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) Heimdall", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:200]

DIAS = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
ok = True
st, corpo = pegar("https://api.queridodiario.org.br/gazettes?territory_ids=3550308&size=1")
print("Querido Diário (api.queridodiario.org.br):", "OK" if st == 200 else "FALHOU (%s %s)" % (st, corpo))
ok = ok and st == 200

oab = oab_do_env()
if not oab:
    print("Diário da Justiça: HEIMDALL_OAB não está no .env. Acrescente a linha HEIMDALL_OAB=NUMERO/UF e rode de novo.")
    sys.exit(1)
f = lambda d: d.strftime("%d/%m/%Y")
q = urllib.parse.urlencode({"numeroOab": oab[0], "ufOab": oab[1], "meio": "D", "itensPorPagina": 5,
                            "dataDisponibilizacaoInicio": f(date.today() - timedelta(days=DIAS)), "dataDisponibilizacaoFim": f(date.today())})
st, corpo = pegar("https://comunicaapi.pje.jus.br/api/v1/comunicacao?" + q)
print("Diário da Justiça (comunicaapi.pje.jus.br): HTTP", st)
if st == 200:
    try:
        d = json.loads(corpo)
        arr = d.get("items") or d.get("data") or d.get("results") or []
        print("  chaves da resposta:", ", ".join(sorted(d.keys())))
        print("  total informado:", d.get("count"), "| itens nesta página:", len(arr))
        if arr:
            print("  campos de cada item:", ", ".join(sorted(arr[0].keys())))
    except Exception as e:  # noqa: BLE001
        print("  resposta não é JSON:", str(e)[:100]); ok = False
else:
    ok = False
    print("  429 = espere 1 minuto; 403 = a API só atende o Brasil; 500 = data inválida ou instabilidade.")
sys.exit(0 if ok else 1)
