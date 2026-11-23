#!/usr/bin/env bash
# Cria (ou atualiza) no Open WebUI, pela API, as conexões de ferramentas (openwebui/ferramentas/*.json, com o filtro de funções de
# openwebui/filtro_ID.txt) e os modelos personalizados com os prompts padrão (openwebui/modelos_importar.json).
#
# Uso, na pasta do projeto, com o Open WebUI no ar:
#     bash scripts/importar_modelos_webui.sh                 ferramentas e depois modelos
#     bash scripts/importar_modelos_webui.sh --tools         só as conexões de ferramentas
#     bash scripts/importar_modelos_webui.sh --models        só os modelos
#     bash scripts/importar_modelos_webui.sh --dry-run       só mostra o que faria (combina com os outros)
#
# A chave da API vem de HEIMDALL_WEBUI_API_KEY no .env; se não houver, o script pergunta sem mostrar na tela e não grava.
# Crie a chave no Open WebUI: Configurações, Conta, Chaves de API, Criar (conta administradora). A chave nunca é impressa.
# Conexão com o mesmo ID é atualizada no lugar (as outras conexões ficam como estão); modelo com o mesmo id é atualizado. Nada é apagado.
cd "$(dirname "$0")/.." || exit 1
python3 - "$@" <<'PY'
import getpass, json, os, sys, urllib.error, urllib.request
from pathlib import Path

DRY = "--dry-run" in sys.argv
FAZER_FERR = "--models" not in sys.argv
FAZER_MOD = "--tools" not in sys.argv
env = {}
arq = Path(".env")
if arq.exists():
    for linha in arq.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
base = os.environ.get("HEIMDALL_WEBUI_URL", env.get("HEIMDALL_WEBUI_URL", "http://localhost:3000")).rstrip("/")
chave = os.environ.get("HEIMDALL_WEBUI_API_KEY") or env.get("HEIMDALL_WEBUI_API_KEY", "")
modelos = json.loads(Path("openwebui/modelos_importar.json").read_text(encoding="utf-8")) if FAZER_MOD else []
conexoes = []
if FAZER_FERR:
    for arq_c in sorted(Path("openwebui/ferramentas").glob("*.json")):
        c = json.loads(arq_c.read_text(encoding="utf-8"))[0]
        filtro = Path("openwebui") / f"filtro_{c['info']['id']}.txt"
        c["config"] = {"enable": True, "function_name_filter_list": filtro.read_text(encoding="utf-8").strip() if filtro.exists() else "",
                       "access_grants": []}
        conexoes.append(c)
if DRY:
    for c in conexoes:
        print(f"Criaria ou atualizaria a conexão: {c['info']['id']} ({c['info']['name']}), {c['url']}, filtro {'sim' if c['config']['function_name_filter_list'] else 'não'}")
    for m in modelos:
        print(f"Criaria ou atualizaria o modelo: {m['id']} ({m['name']}), base {m['base_model_id']}")
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
if conexoes:
    st, atual = chamar("GET", "/api/v1/configs/tool_servers")
    if st in (401, 403):
        sys.exit("A chave foi recusada. Crie outra em Configurações, Conta, Chaves de API (a conta precisa ser administradora).")
    if st != 200 or not isinstance(atual, dict):
        sys.exit(f"Não consegui ler as conexões de ferramentas: HTTP {st} {atual}")
    lista = list(atual.get("TOOL_SERVER_CONNECTIONS") or [])
    for c in conexoes:
        cid = c["info"]["id"]
        for i, velha in enumerate(lista):
            if (velha.get("info") or {}).get("id") == cid:
                lista[i] = c
                print(f"conexão atualizada: {cid} ({c['info']['name']})")
                break
        else:
            lista.append(c)
            print(f"conexão criada: {cid} ({c['info']['name']})")
    st, r = chamar("POST", "/api/v1/configs/tool_servers", {"TOOL_SERVER_CONNECTIONS": lista})
    if st == 200:
        ok += len(conexoes)
    else:
        print(f"FALHOU ao gravar as conexões: HTTP {st} {r}")
        falhas += len(conexoes)
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
print(f"Itens criados ou atualizados: {ok}. Falhas: {falhas}.")
sys.exit(1 if falhas else 0)
PY
