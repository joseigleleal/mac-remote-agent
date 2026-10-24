#!/bin/bash
# Deja el bot corriendo siempre en la Mac: arranca al iniciar sesión y launchd lo relanza si se cae.
#   ./scripts/instalar_launchd.sh              # instalar o actualizar
#   ./scripts/instalar_launchd.sh desinstalar  # quitarlo
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ETIQUETA="com.holamac.bot"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"

launchctl bootout "gui/$(id -u)/$ETIQUETA" 2>/dev/null || true
if [ "${1:-}" = "desinstalar" ]; then
  rm -f "$PLIST"
  echo "Bot desinstalado."
  exit 0
fi

[ -f "$ROOT/.env" ] || { echo "Falta $ROOT/.env (copiar .env.example y completarlo)"; exit 1; }
mkdir -p "$ROOT/data" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/python</string><string>-m</string><string>mac.bot</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$ROOT/data/bot.log</string>
  <key>StandardErrorPath</key><string>$ROOT/data/bot.log</string>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Bot instalado ($PLIST). Log: tail -f $ROOT/data/bot.log"
