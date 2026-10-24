# Estado del proyecto Jarvis — el hilo conductor

> Este archivo es la memoria del PROYECTO (no de JP). Cualquier chat nuevo (Claude, ChatGPT o Jarvis) empieza leyendo esto.
> Se actualiza al cerrar cada paso: qué se hizo, qué se decidió, qué sigue.

**Última actualización:** 2026-10-24 (upgrade 02: seguridad)

## Visión
- Corto plazo: el Jarvis más cercano al de Iron Man posible en la Mac de JP, con lo que hay y máximo $200 MXN/mes extra.
- Mediano plazo: Jarvis como centro de control de un negocio con IA que genere $1,500,000 MXN en ~1 año (meta: coche). Modelo de negocio aún sin decidir.

## Equipo de trabajo (roles)
| Quién | Rol |
|---|---|
| Jarvis (Claude Code en ~/Documents/Jarvis) | Ejecuta. ÚNICO que edita código. |
| ChatGPT — proyecto "Jarvis HQ" (modo Chat, nube, GPT-6 Astra alto) | Arquitecto y estratega. Diseña y da prompts para Jarvis. |
| Claude (chat de la app) | Revisor y constructor: revisa propuestas de ChatGPT, arregla lo que se rompe. |
Flujo: ChatGPT propone → Claude revisa → JP pega el prompt en Jarvis → Jarvis lo hace → se prueba → se actualiza este archivo.

## Ya funciona (2026-10-23/24)
- Base: CLAUDE.md (personalidad estilo Jarvis/Tony, reglas), memoria, módulos, git local.
- Voz: "Jarvis, …" de un jalón o solo "Jarvis" + tin. Detección local Whisper base; orden con Groq whisper-large-v3-turbo (gratis); filtro de frases fantasma.
- Cerebro: `claude -p` (con --continue si <30 min) y respaldo automático con Codex (ChatGPT). Codex con sesión iniciada.
- Comandos rápidos sin IA: apps, Spotify, volumen, hora, modos (gamer/estudio/trabajo/dormir), rutina, panel.
- Dos mundos: páginas se abren en el perfil de Chrome correcto (Classroom/Meet → escuela; lo demás → personal jmuro2110). Probado OK.
- Iniciativa: resumen matutino 7:30, vigía (Minecraft 1/2/3 h, entregas), avisos Mac + iPhone (ntfy, canal en ~/.jarvis/secretos.env).
- Panel Jarvis HQ (Ctrl+Alt+H): meta del coche, pendientes, clima, juego, últimas pláticas.
- Hammerspoon: Ctrl+Alt+J hablar, Ctrl+Alt+Espacio escribir, Ctrl+Alt+H panel, Ctrl+Alt+. callar. (Teclado Windows: Alt = Opción.)
- Arranque automático (Jarvis.command, una sola instancia, se reinicia solo).
- Medición de latencia (upgrade 01, 2026-10-24): `bin/telemetria.py` registra cada etapa con ID por petición en ~/.jarvis/metricas_latencia.jsonl (sin contenido); `jv latencia` da p50/p90/mín/máx por etapa, origen y ruta. 19 pruebas con mocks en tests/. Primera muestra real: `claude -p` = 13.4 s para una respuesta trivial (texto).
- Seguridad (upgrade 02, 2026-10-24): modo asistente separado del de desarrollo. `claude -p` corre con `--restricted` + guardia PreToolUse (`bin/guardia.py` → `bin/politica.py`); Codex de respaldo en `read-only` sin plugins/computer-use/MCP. Bloquea antes de ejecutar: borrar, enviar, pagar (requieren aprobación y aún no hay interfaz: quedan bloqueados), publicar en IG/TikTok/Snapchat y conectar Snapchat (prohibido siempre), Classroom con cuenta personal, y cualquier comando no clasificado. Sin perfil escolar ya no cae al personal. Auditoría en ~/.jarvis/seguridad.jsonl. 24 pruebas nuevas (tests/test_seguridad.py) + las 19 del 01 = 43 OK. Ver modulos/seguridad.md.
- Arreglo: "desactiva/quita/apaga… el modo X" ya no activa el modo (lo resuelve el cerebro).

## Decisiones tomadas
- No IA pesada local (Mac Intel). Nube para lo pesado, local para lo simple.
- openWakeWord descartado (no reconoce el acento de JP). Detección con Whisper.
- Procesos dentro de Terminal (no launchd) por permisos de micrófono/Documentos.
- ElevenLabs se pospone: primero conversación y velocidad (acuerdo con ChatGPT).
- ChatGPT nunca edita archivos; sin carpeta local en su proyecto.

## Pendientes conocidos
- [ ] JP: sacar llave de Groq y guardarla (`chmod +x ~/Documents/Jarvis/bin/jv && ~/Documents/Jarvis/bin/jv llave groq`), reiniciar Jarvis.
- [ ] Hammerspoon: confirmar permiso de Accesibilidad.
- [ ] iPhone: app ntfy suscrita al canal.
- [ ] Datos de JP: link app análisis facial, app de modos teclado/mouse (Logitech G HUB), ciudad para clima.
- [ ] Subir Jarvis a GitHub privado (jmuro2110-hub/jarvis) para que ChatGPT lea el código real.

## Roadmap de upgrade (diagnóstico de ChatGPT, 2026-10-24, aprobado)
1. **Conversación continua**: seguir la plática sin repetir "Jarvis", entender "esa/la primera", barge-in (interrumpirlo). ← PRIORIDAD
2. **Velocidad**: medir latencia por etapa; el arranque en frío de `claude -p` es el sospechoso principal.
3. **Memoria que aprende**: permanente vs reciente vs recuerdos relevantes.
4. **Iniciativa con criterio**: prioridades, silencio, no repetir avisos, contexto (modo, pendientes).
5. **Autonomía real en macOS** con candados por código (no solo instrucciones).
6. Después: voz premium (ElevenLabs), recordatorios con hora, Classroom.

## Paso actual
- Upgrade 02 (seguridad) hecho y probado (Parte A completa + autorizaciones de un solo uso y auditoría). Falta de la Parte B: la interfaz local confiable que muestre la acción completa y cree la autorización; hasta entonces, todo lo que requiere confirmación queda bloqueado.
- Siguiente: Upgrade 03 = latencia (13.4 s de `claude -p`). Pista encontrada: `claude -p` hereda stdin y puede esperar 3 s ("no stdin data received in 3s") cuando no lo llama una terminal.
- Límites abiertos de seguridad: `--continue` puede retomar la última sesión de desarrollo (contexto, no permisos); WebFetch puede sacar datos en una URL; Codex en read-only puede LEER cualquier archivo (incluidas llaves) y mandarlo a OpenAI como contexto; el desarrollo interactivo sigue con permisos amplios a propósito.

## Fase B — Negocio (después del upgrade)
- Meta $1,500,000 MXN; fecha_meta 2027-10-23 en memoria/dinero.json.
- Interés inicial: automatizaciones con IA para negocios locales en México. Sin decidir.
