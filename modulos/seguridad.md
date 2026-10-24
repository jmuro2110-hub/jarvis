# Módulo Seguridad (upgrade 02)

- **Dos contextos.** Desarrollo = JP abre `claude` a mano en esta carpeta: permisos de `.claude/settings.json`, sin guardia. Asistente = todo lo que pasa por `bin/pensar.py` (voz, ⌃⌥Espacio, resumen automático): `claude -p --restricted --strict-mcp-config --tools … --permission-mode dontAsk --settings seguridad/claude_asistente.json` con `JARVIS_MODO=asistente`. `--restricted` ignora los permisos de desarrollo del proyecto.
- **Guardia:** `bin/guardia.py`, hook PreToolUse (solo en `seguridad/claude_asistente.json`). Traduce cada herramienta o comando a una operación y la evalúa con `bin/politica.py`. Lo que no entiende, lo bloquea; si falla, bloquea.
- **Política:** `bin/politica.py` → permitido / confirmar / prohibido / bloqueado. Las prohibiciones (publicar en Instagram/TikTok/Snapchat, conectar Snapchat, cruzar mundos, tocar los controles) no admiten confirmación.
- **Autorizaciones:** de un solo uso, caducan a los 2 min y se ligan a la acción, el destino y el contenido exactos (`~/.jarvis/autorizaciones.json`, 0600). Hoy NINGUNA interfaz las crea: todo lo que requiere confirmación queda bloqueado (Parte B pendiente).
- **Codex de respaldo:** `--sandbox read-only`, sin plugins, apps, computer-use, navegador ni MCP. Solo conversa: no puede apuntar pendientes ni abrir nada.
- **Auditoría:** `~/.jarvis/seguridad.jsonl` (0600): fecha, contexto, origen, herramienta, tipo, decisión, motivo y dominio o app. Sin comandos, mensajes ni rutas privadas.
- **Asistente puede escribir solo** `memoria/pendientes.md`, `memoria/dinero.json` y `memoria/bitacora.md`.
- **Clasificar algo nuevo:** en modo desarrollo, agregar el caso en `guardia.py`/`politica.py` y su prueba en `tests/test_seguridad.py`.
- Pruebas: `uv run --python 3.11 --with numpy python -m unittest tests.test_latencia tests.test_seguridad`.
