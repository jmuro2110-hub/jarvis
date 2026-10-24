# Módulo Sistema

Control de la Mac: abrir/cerrar apps, buscar y organizar archivos, música, volumen, configuraciones.

- Lo simple se hace directo con `open -a "App"`, `osascript` o `bin/jv`.
- Comandos de voz sin IA: ver `comando_rapido()` en `voz/jarvis_voz.py`.
- Atajos (Hammerspoon, `hammerspoon/init.lua`): ⌃⌥J hablar, ⌃⌥Espacio escribir, ⌃⌥H panel, ⌃⌥. callar. Menú con un círculo en la barra superior.
- Arranque: `Jarvis.command` (elemento de inicio de sesión) levanta la voz y el reloj interno (`bin/agenda.py`).
- Estado privado y registros: `~/.jarvis/` (jarvis.log, historial.jsonl, secretos.env).
- Borrar archivos: preguntar antes.
