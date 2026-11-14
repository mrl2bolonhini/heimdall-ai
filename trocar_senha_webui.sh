#!/usr/bin/env bash
# Troca a senha de um usuário do Open WebUI SEM recriar o contêiner e sem perder conversas, modelos, ferramentas ou configurações.
#
# Uso, na pasta do projeto, com o Open WebUI no ar:
#     bash trocar_senha_webui.sh
#
# O que faz:
#   1. tira uma cópia de segurança do volume open-webui em backups/ (permissão 600);
#   2. mostra os usuários cadastrados e pergunta de quem é a senha (se só houver um, usa esse);
#   3. pede a nova senha duas vezes, sem mostrar na tela e sem gravá-la em arquivo nem no histórico do terminal;
#   4. dentro do contêiner, troca só o hash da senha desse usuário no banco do Open WebUI e confere o resultado.
# Com --stdin (usado pelo heimdall_acesso.py) a nova senha vem pela entrada padrão e não é perguntada de novo.
# Nada é reiniciado. As sessões já abertas em outros aparelhos continuam valendo até expirarem.
#
# Se algo der errado, o próprio script avisa e não altera mais nada. Para voltar à senha antiga, rode o script de novo e informe a antiga.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
fail() { echo "Erro: $*" >&2; exit 1; }

P1=""; P2=""
if [ "${1:-}" = "--stdin" ]; then
    IFS= read -r P1 || fail "não recebi a senha pela entrada padrão."
    P2="$P1"
fi

command -v docker > /dev/null 2>&1 || fail "o Docker não foi encontrado."
docker ps --format '{{.Names}}' | grep -qx open-webui || fail "o contêiner open-webui não está rodando. Suba com: ./subir.sh"
DB=/app/backend/data/webui.db
docker exec open-webui test -f "$DB" || fail "não achei o banco do Open WebUI em $DB (ele pode estar usando outro banco)."

mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
ARQ="backups/open-webui-senha-$STAMP.tgz"
echo "Copiando o volume do Open WebUI para $ARQ ..."
docker run --rm -v open-webui:/data -v "$PROJECT_DIR/backups":/backup alpine \
    tar czf "/backup/open-webui-senha-$STAMP.tgz" -C /data . 2> /dev/null || fail "não consegui fazer a cópia de segurança; nada foi alterado."
chmod 600 "$ARQ"
echo "Cópia feita."

USUARIOS="$(docker exec open-webui python3 -c "
import sqlite3
c = sqlite3.connect('$DB', timeout=30)
print('\n'.join(r[0] for r in c.execute('SELECT email FROM auth ORDER BY email')))
")" || fail "não consegui ler os usuários."
[ -n "$USUARIOS" ] || fail "não há usuários no banco."
TOTAL="$(printf '%s\n' "$USUARIOS" | wc -l | tr -d ' ')"
if [ "$TOTAL" = "1" ]; then
    EMAIL="$USUARIOS"
    echo "Usuário: $EMAIL"
else
    echo "Usuários cadastrados:"
    printf '%s\n' "$USUARIOS" | nl -w2 -s'. '
    read -r -p "Digite o número do usuário: " NUM < /dev/tty
    [[ "$NUM" =~ ^[0-9]+$ ]] && [ "$NUM" -ge 1 ] && [ "$NUM" -le "$TOTAL" ] || fail "número inválido; nada foi alterado."
    EMAIL="$(printf '%s\n' "$USUARIOS" | sed -n "${NUM}p")"
fi

if [ -z "$P1" ]; then
    read -r -s -p "Nova senha (mínimo 12 caracteres): " P1 < /dev/tty; echo
    read -r -s -p "Repita a nova senha: " P2 < /dev/tty; echo
fi
[ "$P1" = "$P2" ] || fail "as senhas não são iguais; nada foi alterado."
[ "${#P1}" -ge 12 ] || fail "a senha tem menos de 12 caracteres; nada foi alterado."

# A senha vai pela entrada padrão (printf é interno do shell: não aparece na lista de processos).
printf '%s\n%s\n' "$EMAIL" "$P1" | docker exec -i open-webui python3 -c "
import sqlite3, sys
import bcrypt
email = sys.stdin.readline().rstrip('\n')
senha = sys.stdin.readline().rstrip('\n')
if len(senha.encode()) > 72:
    sys.exit('A senha passa de 72 bytes (o bcrypt ignora o resto). Use uma menor.')
h = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
con = sqlite3.connect('$DB', timeout=30)
cur = con.execute('UPDATE auth SET password = ? WHERE lower(email) = lower(?)', (h, email))
if cur.rowcount != 1:
    con.rollback()
    sys.exit('Não achei exatamente um usuário com esse e-mail; nada foi alterado.')
con.commit()
guardado = con.execute('SELECT password FROM auth WHERE lower(email) = lower(?)', (email,)).fetchone()[0]
if not bcrypt.checkpw(senha.encode(), guardado.encode()):
    sys.exit('A conferência da senha gravada falhou.')
print('Senha trocada e conferida.')
" || { unset P1 P2; fail "a troca não foi concluída. A cópia de segurança está em $ARQ."; }
unset P1 P2
echo "Pronto. Entre no Open WebUI com a nova senha. Conversas e configurações continuam como estavam."
echo "Guarde a nova senha no app Senhas. A cópia de segurança ficou em $ARQ (apague quando não precisar mais)."
