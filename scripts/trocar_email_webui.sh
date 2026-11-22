#!/usr/bin/env bash
# Troca o e-mail (que também é o nome de usuário) de uma conta do Open WebUI, mantendo conversas, modelos e configurações.
#
# Uso, na pasta do projeto:   bash scripts/trocar_email_webui.sh [novo@email]
# Se houver mais de um usuário, o script mostra a lista e pergunta qual trocar. Sem argumento, pergunta o novo e-mail.
# Passos: cópia do volume em backups/ (permissão 600), para o Open WebUI por alguns segundos, troca o e-mail nas
# tabelas auth e user do banco, confere e liga o Open WebUI de novo. A senha continua a mesma.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
fail() { echo "Erro: $*" >&2; exit 1; }

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps -a --format '{{.Names}}' | grep -qx open-webui || fail "não existe o contêiner open-webui. Suba com: ./subir.sh --webui"
IMG="$(docker inspect -f '{{.Config.Image}}' open-webui)"
DB=/app/backend/data/webui.db

NOVO="${1:-}"
if [ -z "$NOVO" ]; then read -r -p "Novo e-mail: " NOVO < /dev/tty; fi
NOVO="$(printf '%s' "$NOVO" | tr -d '[:space:]')"
case "$NOVO" in *?@?*.?*) ;; *) fail "e-mail inválido; nada foi alterado." ;; esac

mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
ARQ="backups/open-webui-email-$STAMP.tgz"
echo "Parando o Open WebUI e copiando o volume para $ARQ ..."
docker stop open-webui > /dev/null || fail "não consegui parar o open-webui."
religar() { docker start open-webui > /dev/null 2>&1; }
docker run --rm -v open-webui:/data -v "$PROJECT_DIR/backups":/backup alpine \
    tar czf "/backup/open-webui-email-$STAMP.tgz" -C /data . 2> /dev/null || { religar; fail "não consegui fazer a cópia de segurança; nada foi alterado."; }
chmod 600 "$ARQ"

PY='
import sqlite3, sys
novo = sys.argv[1]
con = sqlite3.connect("/app/backend/data/webui.db", timeout=30)
usuarios = [r[0] for r in con.execute("SELECT email FROM auth ORDER BY email")]
if not usuarios:
    sys.exit("Não há usuários no banco.")
if any(u.lower() == novo.lower() for u in usuarios):
    sys.exit("Já existe uma conta com esse e-mail; nada foi alterado.")
if len(usuarios) == 1:
    antigo = usuarios[0]
else:
    for i, u in enumerate(usuarios, 1):
        print(f"{i}. {u}", file=sys.stderr)
    print("Digite o número da conta a trocar: ", end="", file=sys.stderr, flush=True)
    n = sys.stdin.readline().strip()
    if not n.isdigit() or not 1 <= int(n) <= len(usuarios):
        sys.exit("Número inválido; nada foi alterado.")
    antigo = usuarios[int(n) - 1]
a = con.execute("UPDATE auth SET email = ? WHERE email = ?", (novo, antigo)).rowcount
u = con.execute("UPDATE user SET email = ? WHERE lower(email) = lower(?)", (novo, antigo)).rowcount
if a != 1 or u != 1:
    con.rollback()
    sys.exit(f"Esperava trocar 1 linha em cada tabela e troquei auth={a}, user={u}; nada foi alterado.")
con.commit()
ok = con.execute("SELECT COUNT(*) FROM auth WHERE email = ?", (novo,)).fetchone()[0] == 1 and \
     con.execute("SELECT COUNT(*) FROM user WHERE email = ?", (novo,)).fetchone()[0] == 1
print(f"E-mail trocado de {antigo} para {novo}." if ok else "A conferência falhou.")
sys.exit(0 if ok else 1)
'
# Uma lista de várias contas pede o número pela entrada padrão; com uma só conta nada é perguntado.
docker run --rm -i -v open-webui:/app/backend/data --entrypoint python3 "$IMG" -c "$PY" "$NOVO" < /dev/tty
RC=$?
religar
[ "$RC" = "0" ] || fail "a troca não foi concluída. A cópia de segurança está em $ARQ."
echo "Pronto. O Open WebUI voltou a subir; a senha continua a mesma. Cópia de segurança: $ARQ (apague quando não precisar mais)."
echo "Se for ligar o login pelo Access: HEIMDALL_WEBUI_ACCESS='1' em Ajustes, depois heimdall chat --check e heimdall update --restart."
