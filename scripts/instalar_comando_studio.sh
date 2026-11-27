#!/bin/bash
# Instala o comando "studio" no zsh: tira do ~/.zshrc a função antiga (com cópia de segurança) e liga o studio.zsh deste projeto.
# Uso: bash scripts/instalar_comando_studio.sh      depois:  source ~/.zshrc
cd "$(dirname "$0")/.." || exit 1
PROJ="$(pwd)"
RC="$HOME/.zshrc"
[ -f "$RC" ] || touch "$RC"
cp "$RC" "$RC.antes-do-studio.$(date +%Y%m%d-%H%M%S)" && echo "Cópia de segurança do .zshrc criada."
python3 - "$RC" <<'PY'
import re, sys
rc = sys.argv[1]
linhas = open(rc, encoding="utf-8").read().split("\n")
saida, i, removido = [], 0, False
while i < len(linhas):
    l = linhas[i]
    if re.match(r"^heimdall\s*\(\s*\)\s*\{", l):
        # termina na primeira linha que é só "}" na coluna 0
        j = i
        while j < len(linhas) and linhas[j].rstrip() != "}":
            j += 1
        # descarta o comentário logo acima, se for o da função antiga
        while saida and saida[-1].startswith("# Ecossistema StudioLibre"):
            saida.pop()
        i, removido = j + 1, True
        continue
    saida.append(l)
    i += 1
open(rc, "w", encoding="utf-8").write("\n".join(saida))
print("Função antiga removida." if removido else "Não havia função antiga heimdall() no .zshrc.")
PY
grep -q "heimdall-comando" "$RC" || {
    {
        echo ""
        echo "# heimdall-comando: comando unificado do ecossistema StudioLibre"
        echo "export STUDIO_DIR=\"$PROJ\""
        echo "source \"\$STUDIO_DIR/studio.zsh\""
    } >> "$RC"
    echo "Linhas adicionadas ao .zshrc."
}
echo "Pronto. Rode: source ~/.zshrc   e depois: studio help"
