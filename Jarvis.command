#!/bin/bash
# J.A.R.V.I.S. — arranque. Se abre solo al prender la Mac (elemento de inicio).
# Corre dentro de Terminal a propósito: así hereda los permisos de micrófono y de Documentos.
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$HOME/Documents/Jarvis" || exit 1
printf '\033]0;J.A.R.V.I.S.\007'
mkdir -p "$HOME/.jarvis"

# Si ya había un Jarvis corriendo, lo apaga (nunca dos escuchando a la vez).
# Primero sus bucles de arranque/agenda: si no, lo vuelven a levantar a los 5 s (upgrade 04).
for p in $(pgrep -f "Jarvis.command"); do
  [ "$p" != "$$" ] && kill "$p" 2>/dev/null
done
pkill -f "jarvis_voz.py" 2>/dev/null
pkill -f "bin/agenda.py" 2>/dev/null
sleep 1

# La Mac no se duerme mientras Jarvis esté encendido
caffeinate -i -w $$ &

# Reloj interno: resumen matutino, vigía y panel
( while true; do bin/jv agenda >> "$HOME/.jarvis/agenda.out" 2>&1; sleep 10; done ) &

# Oídos: si se cae, se levanta solo
while true; do
  bash voz/iniciar.sh
  echo "⚠️  La voz se detuvo. Reiniciando en 5 segundos (Ctrl+C dos veces para apagar Jarvis)..."
  sleep 5
done
