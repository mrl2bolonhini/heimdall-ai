#!/bin/bash
# Conclui no app Lembretes os lembretes de teste "Teste de triagem" da lista "Heimdall: Triagem".
osascript <<'APPLESCRIPT'
tell application "Reminders"
    if exists list "Heimdall: Triagem" then
        set completed of (every reminder of list "Heimdall: Triagem" whose name starts with "Teste de triagem") to true
    end if
end tell
APPLESCRIPT
echo "Lembretes de teste concluidos."
