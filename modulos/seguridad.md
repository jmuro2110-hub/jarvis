# Módulo Seguridad (upgrade 02)

- **Dos contextos.** Desarrollo = JP abre `claude` a mano en esta carpeta: permisos de `.claude/settings.json`, sin guardia. Asistente = todo lo que pasa por `bin/pensar.py` (voz, ⌃⌥Espacio, resumen automático): `claude -p --restricted --strict-mcp-config --tools … --permission-mode dontAsk --settings seguridad/claude_asistente.json` con `JARVIS_MODO=asistente`. `--restricted` ignora los permisos de desarrollo del proyecto.
- **Guardia:** `bin/guardia.py`, hook PreToolUse (solo en `seguridad/claude_asistente.json`). Traduce cada herramienta o comando a una operación y la evalúa con `bin/politica.py`. Lo que no entiende, lo bloquea; si falla, bloquea.
- **Política:** `bin/politica.py` → permitido / confirmar / prohibido / bloqueado. Las prohibiciones (publicar en Instagram/TikTok/Snapchat, conectar Snapchat, cruzar mundos, tocar los controles) no admiten confirmación.
- **Autorizaciones:** de un solo uso, caducan a los 2 min y se ligan a la acción, el destino y el contenido exactos (`~/.jarvis/autorizaciones.json`, 0600). Hoy NINGUNA interfaz las crea: todo lo que requiere confirmación queda bloqueado (Parte B pendiente).
- **Codex de respaldo (upgrade 03):** solo conversa, dos capas. (1) Sin herramientas: `--disable shell_tool/unified_exec/view_image/plugins/apps/computer_use/browser_use…`, `agents.enabled=false`, `code_mode_host` apagado (el modo código falla cerrado), `--ignore-user-config` (sin MCP ni config de JP), `--ignore-rules`, `--ephemeral`, sin web search. (2) Perfil de permisos `jarvis_asistente` (Seatbelt): lee solo `:minimal`, el proyecto, `~/.local/bin` y `~/.codex/packages`; **`~/.jarvis` = deny**; nada escribible; red apagada. Ya NO usa `--sandbox read-only`: `--sandbox` anula los perfiles. Entorno sin llaves ni tokens (`entorno_codex()`).
- **Autoverificación:** antes de usar Codex, `codex_aislado()` exige la versión probada (`CODEX_VERIFICADO` = 0.164.0) y comprueba en Seatbelt que `~/.jarvis/canario_upgrade03.txt` (contenido inventado, permanente) da "Operation not permitted". Si no, el respaldo queda deshabilitado y Jarvis lo dice. **Si se actualiza Codex**: correr `tests.test_upgrade03` (clase CodexReal) y, si pasa, subir `CODEX_VERIFICADO`.
- **Auditoría:** `~/.jarvis/seguridad.jsonl` (0600): fecha, contexto, origen, herramienta, tipo, decisión, motivo y dominio o app. Sin comandos, mensajes ni rutas privadas.
- **Asistente puede escribir solo** `memoria/pendientes.md`, `memoria/dinero.json` y `memoria/bitacora.md`.
- **Clasificar algo nuevo:** en modo desarrollo, agregar el caso en `guardia.py`/`politica.py` y su prueba en `tests/test_seguridad.py`.
- Pruebas: `uv run --python 3.11 --with numpy python -m unittest tests.test_latencia tests.test_seguridad`.

## Sesiones del asistente (upgrade 03)
- `bin/sesiones.py`: cada origen tiene su propio ID de Claude. **personal** = voz + ⌃⌥Espacio + terminal; **auto** = resumen matutino. Nunca `--continue`: sesión nueva con `--session-id <uuid>`, vigente (<30 min) con `--resume <id exacto>`. Se guarda el `session_id` que DEVUELVE Claude.
- `~/.jarvis/sesiones.json` (0600): solo id, origen, creada, ultima. Candado `fcntl.flock` + escritura atómica. Una consulta a la vez por origen (`sesion_<origen>.lock`).
- Si el ID ya no existe ("No conversation found") o el archivo está corrupto → sesión nueva del asistente, nunca la última global. Si Claude falla y responde Codex, la sesión se olvida (la próxima empieza limpia).
- El historial lleva `origen`; a Codex solo le llega contexto personal.
- **Límite abierto (no se arregla aquí):** las sesiones del asistente y las de desarrollo viven en la misma carpeta de proyecto de Claude (~/.claude/projects/…Jarvis). Si JP usa `claude --continue` o `/resume` a mano dentro de Jarvis, puede caer en una sesión del asistente (contexto de plática, no permisos: el modo desarrollo no carga el guardia). El asistente nunca cae en una de desarrollo.

## Conversación continua (upgrade 04)
- La ventana de seguimiento solo existe después de una activación legítima («Jarvis» o ⌃⌥J) y se cierra sola por tiempo, turnos, callar o modo dormir. Desde IDLE nada se manda a Groq sin «Jarvis».
- Una conversación NO autoriza nada: cada turno pasa por `pensar()` con los candados del 02 y la sesión personal del 03. Enviar, borrar, gastar y publicar siguen bloqueados.

## Modo asistente y barge-in (upgrade 06)
- Toda llamada personal (voz y ⌃⌥Espacio) lleva `INSTRUCCION_ASISTENTE`: la vida de JP sale de `memoria/` y `modulos/`, no de `upgrades/`, `tests/`, `hq/`, código ni git, salvo que pregunte por el desarrollo de Jarvis. El resumen automático no la lleva. CLAUDE.md y el modo desarrollo sin cambios.
- Interrumpir la voz nunca relanza a Claude ni repite herramientas; una orden nueva espera a que termine la anterior (una consulta por sesión a la vez). Lo sensible sigue pasando por el guardia del 02.
