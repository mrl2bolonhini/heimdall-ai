#!/usr/bin/env bash
# Exclui uma conta do Open WebUI, com as conversas e os dados dela, sem apagar o volume.
#
# Uso, na pasta do projeto:   bash scripts/excluir_usuario_webui.sh [email]
# Sem argumento, mostra a lista e pergunta o número. Pede para você digitar o e-mail para confirmar.
# Passos: cópia do volume em backups/ (permissão 600), para o Open WebUI por segundos, apaga a conta nas tabelas
# auth e user e os registros ligados a ela (tabelas com a coluna user_id), confere e liga de novo.
# Recusa apagar o último administrador.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
fail() { echo "Erro: $*" >&2; exit 1; }

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps -a --format '{{.Names}}' | grep -qx open-webui || fail "não existe o contêiner open-webui. Suba com: ./subir.sh --webui"
IMG="$(docker inspect -f '{{.Config.Image}}' open-webui)"

mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
ARQ="backups/open-webui-excluir-$STAMP.tgz"
echo "Parando o Open WebUI e copiando o volume para $ARQ ..."
docker stop open-webui > /dev/null || fail "não consegui parar o open-webui."
religar() { docker start open-webui > /dev/null 2>&1; }
docker run --rm -v open-webui:/data -v "$PROJECT_DIR/backups":/backup alpine \
    tar czf "/backup/open-webui-excluir-$STAMP.tgz" -C /data . 2> /dev/null || { religar; fail "não consegui fazer a cópia de segurança; nada foi alterado."; }
chmod 600 "$ARQ"
bash "$PROJECT_DIR/scripts/podar_backups.sh"

PY='
import sqlite3, sys
db = sys.argv[1]
alvo = sys.argv[2] if len(sys.argv) > 2 else ""
con = sqlite3.connect(db, timeout=30)
linhas = con.execute("SELECT id, email, role FROM user ORDER BY email").fetchall()
if not linhas:
    sys.exit("Não há usuários no banco.")
if not alvo:
    for i, (_, e, r) in enumerate(linhas, 1):
        print(f"{i}. {e} ({r})", file=sys.stderr)
    print("Digite o número da conta a excluir: ", end="", file=sys.stderr, flush=True)
    n = sys.stdin.readline().strip()
    if not n.isdigit() or not 1 <= int(n) <= len(linhas):
        sys.exit("Número inválido; nada foi alterado.")
    alvo = linhas[int(n) - 1][1]
achou = [l for l in linhas if l[1].lower() == alvo.lower()]
if len(achou) != 1:
    sys.exit(f"Não achei exatamente uma conta com o e-mail {alvo}; nada foi alterado.")
uid, email, role = achou[0]
if role == "admin" and sum(1 for l in linhas if l[2] == "admin") == 1:
    sys.exit("Essa é a única conta de administrador; não vou apagá-la.")
print(f"Vou excluir {email} ({role}) e os dados dela. Digite o e-mail para confirmar: ", end="", file=sys.stderr, flush=True)
if sys.stdin.readline().strip().lower() != email.lower():
    sys.exit("Confirmação diferente; nada foi alterado.")
apagados = {}
for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type=\"table\"").fetchall():
    if t in ("user", "auth"):
        continue
    cols = [c[1] for c in con.execute(f"PRAGMA table_info(\"{t}\")")]
    if "user_id" in cols:
        n = con.execute(f"DELETE FROM \"{t}\" WHERE user_id = ?", (uid,)).rowcount
        if n:
            apagados[t] = n
con.execute("DELETE FROM auth WHERE id = ?", (uid,))
if con.execute("DELETE FROM user WHERE id = ?", (uid,)).rowcount != 1:
    con.rollback()
    sys.exit("Não consegui apagar a conta; nada foi alterado.")
con.commit()
if con.execute("SELECT COUNT(*) FROM user WHERE id = ?", (uid,)).fetchone()[0]:
    sys.exit("A conferência falhou.")
extra = ", ".join(f"{t}: {n}" for t, n in apagados.items()) or "nenhum registro ligado"
print(f"Conta {email} excluída. Registros ligados apagados: {extra}.")
'
docker run --rm -i -v open-webui:/app/backend/data --entrypoint python3 "$IMG" -c "$PY" /app/backend/data/webui.db "${1:-}" < /dev/tty
RC=$?
religar
[ "$RC" = "0" ] || fail "a exclusão não foi concluída. A cópia de segurança está em $ARQ."
echo "Pronto. O Open WebUI voltou a subir. Cópia de segurança: $ARQ (apague quando não precisar mais)."
