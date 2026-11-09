#!/usr/bin/env bash
# Instala o vigia de e-mails de serviços públicos (INSS, gov.br, FGTS/Caixa, Receita, Serasa, Detran, tribunais etc.).
# Lê o seu Gmail por IMAP, em modo somente leitura, a cada hora. Confere se o remetente é de verdade (autenticação que
# o próprio Gmail registra), resume os verdadeiros com o modelo local, alerta sobre imitações (golpes) e nunca segue links.
#
# Antes: crie uma senha de aplicativo do Gmail (exige verificação em duas etapas ligada):
#   myaccount.google.com/apppasswords  (com o VoiceOver: campo "Nome do app", digite Heimdall, ative o botão Criar;
#   o Google mostra 16 letras; copie). Confirme também que o IMAP está ligado em Gmail > Configurações > Encaminhamento e POP/IMAP.
#
# Uso, na pasta do projeto:
#     bash instalar_email_oficial.sh              (instala; pede a senha com digitação oculta)
#     bash instalar_email_oficial.sh --testar     (confere login e mostra o que faria agora, sem enviar nada)
#     bash instalar_email_oficial.sh --remover    (desliga o agendamento e apaga a senha do .env)
#
# A senha fica só no .env (permissão 600, ignorado pelo git). Ela dá acesso ao Gmail inteiro: se quiser revogar,
# apague a senha de aplicativo "Heimdall" na página do Google.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
fail() { echo "Erro: $*" >&2; exit 1; }
umask 077

LABEL="ai.heimdall.email-oficial"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/heimdall-email-oficial.log"
PY="$PROJECT_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || fail "não encontrei o Python."
[ -f heimdall_email_oficial.py ] || fail "heimdall_email_oficial.py não está nesta pasta."

limpar_env() {
    [ -f .env ] || return 0
    "$PY" - .env <<'PYEOF'
import re, sys
p = sys.argv[1]
linhas = open(p, encoding="utf-8").read().splitlines()
novas = [l for l in linhas if not re.match(r"^HEIMDALL_EMAIL_(USUARIO|SENHA_APP)=", l)]
open(p, "w", encoding="utf-8").write("\n".join(novas) + ("\n" if novas else ""))
PYEOF
    chmod 600 .env
}

desligar_agendamento() {
    launchctl bootout "gui/$(id -u)/$LABEL" > /dev/null 2>&1 || launchctl unload "$PLIST" > /dev/null 2>&1
}

if [ "${1:-}" = "--remover" ]; then
    desligar_agendamento
    rm -f "$PLIST" .email_oficial_estado.json
    limpar_env
    echo "Vigia de e-mail desligado, memória apagada e senha removida do .env. Apague também a senha de aplicativo no Google."
    exit 0
fi

if [ "${1:-}" = "--testar" ]; then
    "$PY" heimdall_email_oficial.py --testar-login || exit 1
    "$PY" heimdall_email_oficial.py --simular
    exit 0
fi
[ -z "${1:-}" ] || fail "opção desconhecida: $1 (use --testar ou --remover)."

[ "$(uname)" = "Darwin" ] || fail "o agendamento usa o launchd do macOS. Em outro sistema, rode 'python3 heimdall_email_oficial.py' por cron a cada hora."
[ -f .env ] || fail "não achei o .env nesta pasta. Rode antes o start_heimdall.sh."

# .env guarda o resto (Bark, token, chave do LiteLLM); o vigia lê tudo de lá.
USUARIO_ATUAL="$(grep -E '^HEIMDALL_EMAIL_USUARIO=' .env | tail -1 | cut -d= -f2- | tr -d "'\"")"
read -r -p "Seu endereço do Gmail [Enter mantém: ${USUARIO_ATUAL:-mbolonhinic@gmail.com}] " USUARIO
USUARIO="${USUARIO:-${USUARIO_ATUAL:-mbolonhinic@gmail.com}}"
[[ "$USUARIO" =~ ^[A-Za-z0-9._%+-]+@gmail\.com$ ]] || fail "informe um endereço @gmail.com."

echo "Cole a senha de aplicativo do Gmail (16 letras, com ou sem espaços). Nada aparece na tela enquanto você cola."
read -r -s -p "Senha de aplicativo: " SENHA
echo
SENHA="$(printf '%s' "$SENHA" | tr -d ' \t\r\n')"
[[ "$SENHA" =~ ^[A-Za-z]{16}$ ]] || fail "a senha de aplicativo tem exatamente 16 letras. Se você colou a senha normal do Gmail, ela não funciona: gere uma senha de aplicativo."

limpar_env
{ [ -s .env ] && [ "$(tail -c1 .env | wc -l | tr -d ' ')" = "0" ] && echo; \
  echo "HEIMDALL_EMAIL_USUARIO='$USUARIO'"; echo "HEIMDALL_EMAIL_SENHA_APP='$SENHA'"; } >> .env
chmod 600 .env
unset SENHA

echo "Testando o login no Gmail..."
if ! "$PY" heimdall_email_oficial.py --testar-login; then
    limpar_env
    fail "o Gmail recusou o login. A senha foi apagada do .env. Confira a senha de aplicativo e se o IMAP está ligado, e rode de novo."
fi

# A memória e o .env nunca vão para o git.
if [ -f .gitignore ]; then
    grep -qxF ".email_oficial_estado.json" .gitignore || echo ".email_oficial_estado.json" >> .gitignore
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$LABEL</string>
<key>ProgramArguments</key><array><string>$PY</string><string>$PROJECT_DIR/heimdall_email_oficial.py</string></array>
<key>WorkingDirectory</key><string>$PROJECT_DIR</string>
<key>StartInterval</key><integer>3600</integer>
<key>RunAtLoad</key><true/>
<key>StandardOutPath</key><string>$LOG</string>
<key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLISTEOF
chmod 644 "$PLIST"
desligar_agendamento
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2> /dev/null || launchctl load "$PLIST" || fail "não consegui ativar o agendamento no launchd."

echo
echo "Pronto. O vigia roda agora e depois a cada hora (enquanto o Mac estiver ligado e acordado)."
echo "Primeiro aviso agora: pode listar e-mails dos últimos 3 dias. Depois só o que for novo."
echo "Log: $LOG"
echo "Teste sem enviar nada: bash instalar_email_oficial.sh --testar"
echo "Desligar: bash instalar_email_oficial.sh --remover"
