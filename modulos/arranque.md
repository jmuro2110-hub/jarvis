# Arranque — Jarvis en segundo plano (upgrade 08)

## Cómo arranca
- **Normal:** `~/Applications/Jarvis.app` (elemento de inicio de sesión). Sin ventana ni icono en el Dock.
  Binario nativo Intel, firma ad-hoc, `mx.jpmuro.jarvis`. Solo arranca `bin/arranque.sh app`, le reenvía la
  salida/SIGTERM/cierre de sesión y termina cuando termina el supervisor. Si sale con error, lo dice en una alerta.
- **Respaldo:** `Jarvis.command` (Terminal) → `bin/arranque.sh terminal`. Mismo supervisor, mismo candado.
- **Emergencia antigua:** `Jarvis.command.pre08` (la versión previa al 08, termina procesos por nombre).
- `bin/arranque.sh`: entorno mínimo explícito (PATH, `UV_OFFLINE=1`, `HF_HUB_OFFLINE=1`), sin red y sin instalar
  nada (nunca `voz/iniciar.sh`), y pasa a `/usr/bin/python3 -I bin/arranque.py supervisar`.
- `bin/arranque.py` (solo biblioteca estándar) es el ÚNICO dueño de voz, agenda y caffeinate:
  - Candado `~/.jarvis/jarvis.lock` (flock), heredado por voz y agenda: no se libera mientras viva un hijo.
    Segunda apertura → «Jarvis ya está activo», sin tocar a la primera.
  - Tubo vigía: si el supervisor muere (aun con SIGKILL), voz y agenda se apagan solas.
  - Hijos anotados por PID + hora de inicio; solo se terminan esos, por grupo. La voz calla sus reproductores
    de streaming (`streaming.limpiar_voces`) al recibir SIGTERM.
  - Caídas: reintentos a 5, 15, 30, 60 y 120 s; agotados = error visible. Códigos 3/4/5, micrófono denegado o
    entorno incompleto (`jarvis_voz.py --entorno`) = error sin reintentos.
  - Estados: iniciando, escuchando, integracion_pendiente (sin Hammerspoon), detenido, error. «Listo» = la voz
    escribió `~/.jarvis/voz_lista` (modelos cargados y oído abierto).
  - Registro técnico `~/.jarvis/arranque.log` (0600, se recorta a ~200 KB). Estado: `~/.jarvis/arranque_estado.json`.

## Controles (fuera del modo asistente: el guardia bloquea `jv arranque`)
- Menú J.A.R.V.I.S. de Hammerspoon: Estado de Jarvis, Detener Jarvis, Abrir Jarvis, Ver registro de arranque.
- Terminal: `~/Documents/Jarvis/bin/jv arranque estado|detener|abrir`
- Elemento de inicio: `bin/jv arranque inicio ver|app|terminal` (deja exactamente uno de Jarvis; Hammerspoon intacto).
- **Ruta de emergencia** (si la app o Hammerspoon no responden; no depende de uv):
  `/usr/bin/python3 ~/Documents/Jarvis/bin/arranque.py detener` — termina solo procesos verificados de Jarvis.

## Rollback a Terminal (exacto)
1. `~/Documents/Jarvis/bin/jv arranque detener` → debe decir «Jarvis detenido, señor. Micrófono libre.»
2. `~/Documents/Jarvis/bin/jv arranque inicio terminal` (quita Jarvis.app y registra Jarvis.command).
3. Abrir `~/Documents/Jarvis/Jarvis.command`.
4. Confirmar: `bin/jv arranque estado` dice «Desde terminal», una voz, micrófono y atajos.
Volver a la app: `bin/jv arranque detener`, `bin/jv arranque inicio app`, `bin/jv arranque abrir`.
No cambia recuerdos, historial, sesiones, configuración ni permisos.

## Permisos (etapa 1, 2026-10-29)
Micrófono, Archivos y carpetas (Documentos) y Automatización (Spotify) a nombre de **Jarvis**; Terminal conserva los
suyos. **No recompilar** `app/Jarvis.swift` sin necesidad: la firma ad-hoc cambia el cdhash y macOS puede volver a
pedir los permisos. Binario aprobado respaldado en `~/.jarvis/Jarvis.app.etapa1`. `app/construir.sh` se niega a
sobrescribir sin `--forzar`.
