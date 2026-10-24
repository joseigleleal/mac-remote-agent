#!/bin/bash
# Prender, apagar y ver el bot desde la Mac.
#   ./scripts/bot.sh prender     # lo arranca (y queda arrancando solo al iniciar sesión)
#   ./scripts/bot.sh apagar      # lo baja del todo (tampoco arranca al iniciar sesión) hasta «prender»
#   ./scripts/bot.sh reiniciar   # para tomar cambios del código o del .env
#   ./scripts/bot.sh estado      # si corre, cuánta CPU y RAM usa, y si está en pausa
#   ./scripts/bot.sh log         # sigue el log en vivo
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ETIQUETA="com.mac-remote-agent.bot"
SERVICIO="gui/$(id -u)/$ETIQUETA"

case "${1:-estado}" in
  prender)
    launchctl enable "$SERVICIO"
    if launchctl print "$SERVICIO" >/dev/null 2>&1; then
      launchctl kickstart "$SERVICIO"
      echo "Bot prendido."
    else
      "$ROOT/scripts/instalar_launchd.sh"
    fi
    ;;
  apagar)
    launchctl disable "$SERVICIO"
    launchctl bootout "$SERVICIO" 2>/dev/null || true
    echo "Bot apagado. Para volver: ./scripts/bot.sh prender"
    ;;
  reiniciar)
    launchctl kickstart -k "$SERVICIO" && echo "Bot reiniciado."
    ;;
  estado)
    pid="$(launchctl print "$SERVICIO" 2>/dev/null | awk '/pid =/{print $3; exit}' || true)"
    if [ -z "$pid" ]; then
      echo "Apagado."
    else
      ps -o pcpu=,rss=,etime= -p "$pid" | awk '{printf "Prendido · CPU %s %% · RAM %.0f MB · encendido hace %s\n", $1, $2/1024, $3}'
    fi
    [ -f "$ROOT/data/pausado" ] && echo "En pausa desde $(cat "$ROOT/data/pausado") (dile «prende» por Telegram)."
    true
    ;;
  log)
    tail -f "$ROOT/data/bot.log"
    ;;
  *)
    echo "Uso: $0 prender|apagar|reiniciar|estado|log"; exit 1
    ;;
esac
