#!/usr/bin/env bash
# Cria (ou atualiza) no Open WebUI os modelos personalizados de openwebui/modelos_importar.json, com os prompts padrão, pela API.
#
# Uso, na pasta do projeto, com o Open WebUI no ar:
#     bash scripts/importar_modelos_webui.sh              importa os 7 modelos
#     bash scripts/importar_modelos_webui.sh --dry-run    só mostra o que faria
#
# A chave da API vem de HEIMDALL_WEBUI_API_KEY no .env; se não houver, o script pergunta sem mostrar na tela e não grava.
# Crie a chave no Open WebUI: Configurações, Conta, Chaves de API, Criar. A chave só é lida do .env, nunca é impressa.
# Modelo que já existe com o mesmo id é atualizado (nome, prompt e ferramentas); nada é apagado. As conexões de ferramentas (MCP)
# continuam sendo adicionadas à mão, como em guides/modelos_open_webui.txt.
cd "$(dirname "$0")/.." || exit 1
python3 - "$@" <<'PY'
import getpass, json, os, sys, urllib.error, urllib.request
from pathlib import Path

DRY = "--dry-run" in sys.argv
env = {}
arq = Path(".env")
if arq.exists():
    for linha in arq.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
base = os.environ.get("HEIMDALL_WEBUI_URL", env.get("HEIMDALL_WEBUI_URL", "http://localhost:3000")).rstrip("/")
chave = os.environ.get("HEIMDALL_WEBUI_API_KEY") or env.get("HEIMDALL_WEBUI_API_KEY", "")
modelos = json.loads(Path("openwebui/modelos_importar.json").read_text(encoding="utf-8"))
if DRY:
    for m in modelos:
        print(f"Criaria ou atualizaria: {m['id']} ({m['name']}), base {m['base_model_id']}")
    sys.exit(0)
if not chave:
    chave = getpass.getpass("Chave da API do Open WebUI (não aparece na tela): ").strip()
if not chave:
    sys.exit("Sem chave: nada foi feito.")


def chamar(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(base + caminho, data=dados, method=metodo, headers={
        "Authorization": "Bearer " + chave, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except OSError as e:
        sys.exit(f"Não consegui falar com {base}: {e}. O Open WebUI está no ar? (heimdall chat --diagnose)")


ok = falhas = 0
for m in modelos:
    existe, _ = chamar("GET", "/api/v1/models/model?id=" + m["id"])
    if existe == 200:
        st, r = chamar("POST", "/api/v1/models/model/update", m)
        acao = "atualizado"
    else:
        st, r = chamar("POST", "/api/v1/models/create", m)
        acao = "criado"
    if st == 200 and r:
        print(f"{acao}: {m['id']} ({m['name']})")
        ok += 1
    else:
        print(f"FALHOU {m['id']}: HTTP {st} {r}")
        falhas += 1
        if st in (401, 403):
            sys.exit("A chave foi recusada. Crie outra em Configurações, Conta, Chaves de API (a conta precisa ser administradora).")
print(f"Modelos criados ou atualizados: {ok}. Falhas: {falhas}.")
sys.exit(1 if falhas else 0)
PY
