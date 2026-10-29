#!/bin/bash
# J.A.R.V.I.S. — arranque (upgrade 08). Lo llaman Jarvis.app (`app`, binario fijo que no se recompila) y
# Jarvis.command (`terminal`, respaldo). Prepara un entorno mínimo explícito y pasa el control al supervisor
# (bin/arranque.py: candado, hijos, reintentos, parada). Sin red y sin instalar nada (nunca voz/iniciar.sh).
#   prueba → repite la prueba de permisos de la etapa 1 (sin supervisor; no correr con Jarvis activo).
set -u
umask 077
MODO="${1:-}"
export HOME="${HOME:?}" PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="es_MX.UTF-8" UV_OFFLINE=1 HF_HUB_OFFLINE=1
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV
JARVIS="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
CASA="${JARVIS_CASA:-$HOME/.jarvis}"; mkdir -p "$CASA"
LOG="$CASA/arranque.log"                          # técnico: arranque, parada y fallos; nada de conversaciones
anota() {
  echo "$(date '+%F %T') $*" >>"$LOG"; chmod 600 "$LOG"
  [ "$MODO" = terminal ] && echo "$*" >&2
  return 0
}
anota "arranque $MODO (lanzador ${JARVIS_LANZADOR:-terminal}, micrófono según la app: ${JARVIS_MIC_APP:-no aplica})"
[ -n "$JARVIS" ] && cd "$JARVIS" || { anota "error: sin acceso a la carpeta de Jarvis ($0)"; exit 3; }
UV="$HOME/.local/bin/uv"
[ -x "$UV" ] || { anota "error: falta uv en $UV (no se instala solo; respaldo: Jarvis.command.pre08)"; exit 4; }
[ -x /usr/bin/python3 ] || { anota "error: falta /usr/bin/python3 (herramientas de línea de comandos)"; exit 4; }

case "$MODO" in
  app|terminal)
    exec /usr/bin/python3 -I "$JARVIS/bin/arranque.py" supervisar --lanzador "$MODO" ;;
  prueba)
    cd voz && exec "$UV" run --offline --script jarvis_voz.py --prueba-permisos >>"$LOG" 2>&1 ;;
  *)
    echo "uso: arranque.sh app|terminal|prueba"; exit 2 ;;
esac
