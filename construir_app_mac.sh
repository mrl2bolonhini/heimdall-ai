#!/bin/bash
# Compila o app de barra de menus do Heimdall neste Mac e o instala em ~/Applications/Heimdall.app (assinatura local gratuita, sem conta de desenvolvedor).
# Uso: bash construir_app_mac.sh [--entrar | --nao-entrar]
#   --entrar       abre o app sozinho quando você entra no Mac
#   --nao-entrar   desfaz isso
# Precisa das ferramentas de linha de comando da Apple (swiftc): se faltarem, rode xcode-select --install e tente de novo.
cd "$(dirname "$0")" || exit 1
DESTINO="$HOME/Applications/Heimdall.app"
AGENTE="$HOME/Library/LaunchAgents/tech.heimdall.menu.plist"
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
  launchctl bootout "gui/$(id -u)/tech.heimdall.menu" 2>/dev/null
  rm -f "$AGENTE"
  echo "O app não abrirá mais sozinho ao entrar no Mac."
  exit 0
fi
if ! command -v swiftc >/dev/null 2>&1; then
  echo "Falta o compilador (swiftc). Rode: xcode-select --install, espere terminar e tente de novo."
  exit 1
fi
pkill -x Heimdall 2>/dev/null || true
set -e
mkdir -p "$DESTINO/Contents/MacOS" "$DESTINO/Contents/Resources"
# O alvo é fixado em macOS 12 para o programa abrir em qualquer Mac recente (sem isso o compilador pode exigir uma versão mais nova que a instalada: erro -10825).
swiftc -O -target "$(uname -m)-apple-macos12.0" -o "$DESTINO/Contents/MacOS/Heimdall" app_mac/Heimdall.swift
cp app_mac/Info.plist "$DESTINO/Contents/Info.plist"
codesign --force --deep --sign - "$DESTINO"
echo "App instalado em $DESTINO"
if [ "$ENTRAR" = "sim" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$AGENTE" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>tech.heimdall.menu</string>
<key>ProgramArguments</key><array><string>$DESTINO/Contents/MacOS/Heimdall</string></array>
<key>RunAtLoad</key><true/>
</dict></plist>
PLISTEOF
  launchctl bootout "gui/$(id -u)/tech.heimdall.menu" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTE"
  echo "O app abrirá sozinho quando você entrar no Mac."
fi
open "$DESTINO"
echo "Pronto. O Heimdall está na barra de menus (no canto direito, junto do relógio)."
