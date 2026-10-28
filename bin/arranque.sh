#!/bin/bash
# J.A.R.V.I.S. — arranque (upgrade 08). Lo llama Jarvis.app (binario fijo, no se recompila); toda la lógica
# vive aquí y en el proyecto. Entorno mínimo explícito, sin red y sin instalar nada (nunca voz/iniciar.sh).
set -u
umask 077
export HOME="${HOME:?}" PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="es_MX.UTF-8" UV_OFFLINE=1 HF_HUB_OFFLINE=1
CASA="$HOME/.jarvis"; mkdir -p "$CASA"
LOG="$CASA/arranque.log"                          # técnico: arranque, parada y fallos; nada de conversaciones
if [ -f "$LOG" ] && [ "$(stat -f %z "$LOG")" -gt 204800 ]; then
  tail -c 102400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
exec >>"$LOG" 2>&1
chmod 600 "$LOG"
echo "$(date '+%F %T') arranque ${1:-?} (lanzador ${JARVIS_LANZADOR:-?}, micrófono según la app: ${JARVIS_MIC_APP:-?})"
cd "$HOME/Documents/Jarvis" || { echo "$(date '+%F %T') error: sin acceso a ~/Documents/Jarvis"; exit 3; }
UV="$HOME/.local/bin/uv"
[ -x "$UV" ] || { echo "$(date '+%F %T') error: falta uv en $UV (no se instala solo)"; exit 4; }

case "${1:-}" in
  app)  # Etapa 1 del 08: solo la prueba de permisos. La etapa 2 cambia esta línea por el supervisor.
    cd voz && exec "$UV" run --offline --script jarvis_voz.py --prueba-permisos ;;
  *)
    echo "uso: arranque.sh app"; exit 2 ;;
esac
