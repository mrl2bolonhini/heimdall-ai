#!/bin/bash
# Compila o app de barra de menus do StudioLibre neste Mac e o instala em ~/Applications/StudioLibre.app (assinatura local gratuita, sem conta de desenvolvedor).
# Uso: bash scripts/construir_app_mac.sh [--entrar | --nao-entrar]
#   --entrar       abre o app sozinho quando você entra no Mac
#   --nao-entrar   desfaz isso
# Precisa das ferramentas de linha de comando da Apple (swiftc): se faltarem, rode xcode-select --install e tente de novo.
cd "$(dirname "$0")/.." || exit 1
DESTINO="$HOME/Applications/StudioLibre.app"
AGENTE="$HOME/Library/LaunchAgents/io.studiolibre.menu.plist"
# App antigo (nome StudioLibre): é removido; o nome antigo deixa de existir (decisão do usuário em 26/11/2026).
ANTIGO_APP="$HOME/Applications/Heimdall.app"
ANTIGO_AGENTE="$HOME/Library/LaunchAgents/tech.heimdall.menu.plist"
ENTRAR=""
for a in "$@"; do
  case "$a" in
    --entrar) ENTRAR=sim ;;
    --nao-entrar) ENTRAR=nao ;;
    *) echo "Opção desconhecida: $a"; exit 1 ;;
  esac
done
if [ "$(uname)" != "Darwin" ]; then echo "Este app é só para o Mac."; exit 1; fi
if [ "$ENTRAR" = "nao" ]; then
  launchctl bootout "gui/$(id -u)/io.studiolibre.menu" 2>/dev/null
  rm -f "$AGENTE"
  echo "O app não abrirá mais sozinho ao entrar no Mac."
  exit 0
fi
if ! command -v swiftc >/dev/null 2>&1; then
  echo "Falta o compilador (swiftc). Rode: xcode-select --install, espere terminar e tente de novo."
  exit 1
fi
pkill -x StudioLibre 2>/dev/null || true
pkill -x StudioLibre 2>/dev/null || true
launchctl bootout "gui/$(id -u)/tech.heimdall.menu" 2>/dev/null || true
if [ -e "$ANTIGO_AGENTE" ] || [ -d "$ANTIGO_APP" ]; then
  # o app antigo ligava ao entrar no Mac: o novo religa se ele estava ligado
  [ -e "$ANTIGO_AGENTE" ] && [ -z "$ENTRAR" ] && ENTRAR=sim
  rm -f "$ANTIGO_AGENTE"
  rm -rf "$ANTIGO_APP"
  echo "App antigo (StudioLibre) removido."
fi
set -e
mkdir -p "$DESTINO/Contents/MacOS" "$DESTINO/Contents/Resources"
# O alvo é fixado em macOS 12 para o programa abrir em qualquer Mac recente (sem isso o compilador pode exigir uma versão mais nova que a instalada: erro -10825).
swiftc -O -target "$(uname -m)-apple-macos12.0" -o "$DESTINO/Contents/MacOS/StudioLibre" macapp/StudioLibre.swift
cp macapp/Info.plist "$DESTINO/Contents/Info.plist"
# Sem uma localização em português dentro do pacote, o macOS mostra em inglês os itens que ele mesmo acrescenta aos menus (ditado, emojis, mover e redimensionar...).
mkdir -p "$DESTINO/Contents/Resources/pt-BR.lproj"
printf '"CFBundleName" = "StudioLibre";\n"CFBundleDisplayName" = "StudioLibre";\n' > "$DESTINO/Contents/Resources/pt-BR.lproj/InfoPlist.strings"
codesign --force --deep --sign - "$DESTINO"
echo "App instalado em $DESTINO"
if [ "$ENTRAR" = "sim" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$AGENTE" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>io.studiolibre.menu</string>
<key>ProgramArguments</key><array><string>$DESTINO/Contents/MacOS/StudioLibre</string></array>
<key>RunAtLoad</key><true/>
</dict></plist>
PLISTEOF
  launchctl bootout "gui/$(id -u)/io.studiolibre.menu" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTE"
  echo "O app abrirá sozinho quando você entrar no Mac."
fi
open "$DESTINO"
echo "Pronto. O StudioLibre está na barra de menus (no canto direito, junto do relógio)."
