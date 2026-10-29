#!/bin/bash
# J.A.R.V.I.S. — RESPALDO en Terminal (upgrade 08). El arranque normal es ~/Applications/Jarvis.app.
# Usa el mismo supervisor y el mismo candado que la app: si Jarvis ya está activo, lo dice y sale sin matar a
# nadie. En Terminal hereda los permisos de micrófono y Documentos de Terminal. Ctrl+C o cerrar la ventana
# lo apagan completo. Versión anterior (terminaba procesos por nombre): Jarvis.command.pre08, solo para emergencia.
printf '\033]0;J.A.R.V.I.S.\007'
exec /bin/bash "$HOME/Documents/Jarvis/bin/arranque.sh" terminal
