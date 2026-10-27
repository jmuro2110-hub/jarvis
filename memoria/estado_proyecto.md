# Estado del proyecto Jarvis — el hilo conductor

> Este archivo es la memoria del PROYECTO (no de JP). Cualquier chat nuevo (Claude, ChatGPT o Jarvis) empieza leyendo esto.
> Se actualiza al cerrar cada paso: qué se hizo, qué se decidió, qué sigue.

**Última actualización:** 2026-10-27 (upgrade 07: memoria permanente y recuerdos relevantes)

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
- Cerebro: `claude -p` con sesiones explícitas (upgrade 03): personal y auto, `--session-id` nueva o `--resume` del ID exacto si <30 min; nunca `--continue`. Respaldo automático con Codex (ChatGPT), aislado y autoverificado. Codex con sesión iniciada.
- Comandos rápidos sin IA: apps, Spotify, volumen, hora, modos (gamer/estudio/trabajo/dormir), rutina, panel.
- Dos mundos: páginas se abren en el perfil de Chrome correcto (Classroom/Meet → escuela; lo demás → personal jmuro2110). Probado OK.
- Iniciativa: resumen matutino 7:30, vigía (Minecraft 1/2/3 h, entregas), avisos Mac + iPhone (ntfy, canal en ~/.jarvis/secretos.env).
- Panel Jarvis HQ (Ctrl+Alt+H): meta del coche, pendientes, clima, juego, últimas pláticas.
- Hammerspoon: Ctrl+Alt+J hablar, Ctrl+Alt+Espacio escribir, Ctrl+Alt+H panel, Ctrl+Alt+. callar. (Teclado Windows: Alt = Opción.)
- Arranque automático (Jarvis.command, una sola instancia, se reinicia solo).
- Medición de latencia (upgrade 01, 2026-10-24): `bin/telemetria.py` registra cada etapa con ID por petición en ~/.jarvis/metricas_latencia.jsonl (sin contenido); `jv latencia` da p50/p90/mín/máx por etapa, origen y ruta. 19 pruebas con mocks en tests/. Primera muestra real: `claude -p` = 13.4 s para una respuesta trivial (texto).
- Seguridad (upgrade 02, 2026-10-24): modo asistente separado del de desarrollo. `claude -p` corre con `--restricted` + guardia PreToolUse (`bin/guardia.py` → `bin/politica.py`); Codex de respaldo en `read-only` sin plugins/computer-use/MCP. Bloquea antes de ejecutar: borrar, enviar, pagar (requieren aprobación y aún no hay interfaz: quedan bloqueados), publicar en IG/TikTok/Snapchat y conectar Snapchat (prohibido siempre), Classroom con cuenta personal, y cualquier comando no clasificado. Sin perfil escolar ya no cae al personal. Auditoría en ~/.jarvis/seguridad.jsonl. 24 pruebas nuevas (tests/test_seguridad.py) + las 19 del 01 = 43 OK. Ver modulos/seguridad.md.
- Arreglo: "desactiva/quita/apaga… el modo X" ya no activa el modo (lo resuelve el cerebro).
- Upgrade 03 (2026-10-26): `claude -p` con stdin cerrado (se acabó la espera de 3 s) y `--output-format json`. Respuesta trivial: 5.1–11.9 s → 2.0–3.9 s (n=4 antes, 9 después). Telemetría nueva: claude_duracion, claude_api (solo sesión nueva), claude_arranque_est (estimación ≈0.8–1.4 s) y sesión nueva/reanudada en `jv latencia`.
- Sesiones separadas (`bin/sesiones.py`, ~/.jarvis/sesiones.json 0600): personal (voz + texto) y auto (resumen matutino), con ID explícito (`--session-id` / `--resume`), 30 min de vigencia, nunca `--continue`. El historial lleva `origen`; a Codex solo le llega contexto personal.
- Codex de respaldo aislado: sin herramientas + perfil de permisos `jarvis_asistente` con ~/.jarvis denegado por Seatbelt (probado con `codex exec` real y canario). Autoverificación por versión (0.164.0) y canario; si falla, respaldo deshabilitado con aviso. 88 pruebas (43 viejas + 45 nuevas) OK.
- Conversación continua por voz (upgrade 04, 2026-10-27): tras «Jarvis» o ⌃⌥J, ventana de 15 s para seguir sin repetirlo (máx. 5 turnos / 3 min, en config.json). Máquina de estados en `voz/conversacion.py`, mismo hilo, sin procesos nuevos. Comandos rápidos en plática (con reglas para "siguiente"/"anterior"/"ya"/"para"), cierre manual con sonido, ⌃⌥. cierra, descarta otras voces de Jarvis, HUD verde discreto. Contexto por la sesión personal del 03. 61 pruebas nuevas + 88 previas = 149 OK.

## Decisiones tomadas
- No IA pesada local (Mac Intel). Nube para lo pesado, local para lo simple.
- openWakeWord descartado (no reconoce el acento de JP). Detección con Whisper.
- Procesos dentro de Terminal (no launchd) por permisos de micrófono/Documentos.
- ElevenLabs se pospone: primero conversación y velocidad (acuerdo con ChatGPT).
- ChatGPT nunca edita archivos; sin carpeta local en su proyecto.
- Memoria permanente (upgrade 07, 2026-10-27): «Jarvis, recuerda que…» (voz o ⌃⌥Espacio) guarda en local, sin Claude, en ~/.jarvis/recuerdos.jsonl (0600, registro de eventos, fsync). Corregir, olvidar (desactiva, no borra) y «¿qué recuerdas de…?». Claude recibe hasta 3 recuerdos relevantes como datos (búsqueda léxica con raíces, por ámbito; desarrollo solo si pregunta por Jarvis). Sin recuerdos: Codex, el resumen automático y el historial. Privacidad: no guarda secretos, datos médicos o financieros, terceros ni contenido de páginas. `jv memoria listar|buscar|estado`. Búsqueda con 500 recuerdos: p50 11 ms. 63 pruebas nuevas + 275 previas = 338 OK. Ver modulos/memoria.md.

## Pendientes conocidos
- [ ] JP: sacar llave de Groq y guardarla (`chmod +x ~/Documents/Jarvis/bin/jv && ~/Documents/Jarvis/bin/jv llave groq`), reiniciar Jarvis.
- [ ] Hammerspoon: confirmar permiso de Accesibilidad.
- [ ] iPhone: app ntfy suscrita al canal.
- [ ] Datos de JP: link app análisis facial, app de modos teclado/mouse (Logitech G HUB), ciudad para clima.
- [ ] Subir Jarvis a GitHub privado (jmuro2110-hub/jarvis) para que ChatGPT lea el código real.

## Roadmap de upgrade (diagnóstico de ChatGPT, 2026-10-24, aprobado)
1. **Conversación continua**: seguir la plática sin repetir "Jarvis" y entender "esa/la primera" ✅ (upgrade 04). Barge-in ✅ (upgrade 06).
2. **Velocidad**: medida, stdin resuelto (01/03) y stream-json con voz anticipada (05) ✅.
3. **Memoria que aprende**: permanente vs reciente vs recuerdos relevantes (upgrade 07, código listo; ✅ cuando pase la prueba física).
4. **Iniciativa con criterio**: prioridades, silencio, no repetir avisos, contexto (modo, pendientes).
5. **Autonomía real en macOS** con candados por código (no solo instrucciones).
6. Después: voz premium (ElevenLabs), recordatorios con hora, Classroom.

## Paso actual
- Upgrade 07 (memoria): código y pruebas automáticas (348 OK). **Primera prueba física fallida (2026-10-27 15:00):** Groq oyó «Jardis, recuerda que…»; como el llamado no se reconoció, la frase llegó a Claude y Claude la anotó en bitacora.md. Arreglo: variantes del llamado en las primeras 3 palabras, «jardis» agregado a WAKE_RE, red de seguridad en la instrucción del asistente y línea de la bitácora quitada. «Cállate» sí cerró bien. **Falta repetir la prueba física desde el paso 1.**
- Upgrade 06 terminado (2026-10-27): barge-in («cállate» ≈1.6 s, «espera» ≈2.2 s), cero falsas interrupciones con música, voz al result 0.39–0.52 s antes, pendientes solo personales.
- Límites abiertos (07): búsqueda léxica, sin semántica; dos recuerdos que se contradicen se pasan juntos; la validación de privacidad es por palabras (conservadora); reiniciar Jarvis no borra la sesión reciente (30 min).
- Límites abiertos (06 y antes): barge-in sin cancelación de eco y con piso de ruido propio: con música alta casi no hay candidatos; callarlo tarda ~1.5–2.2 s; «no, mejor X» con la voz sonando solo está probado en automático; la primera detección con Whisper base tras reiniciar tardó 6.2 s; la voz anticipada solo aplica a conocimiento general; sesiones del asistente y de desarrollo comparten carpeta de proyecto de Claude; WebFetch puede sacar datos en una URL; en Codex quedan `apply_patch`/recursos MCP dentro del modo código (falla cerrado); si se actualiza Codex el respaldo se apaga hasta volver a probar.

## Fase B — Negocio (después del upgrade)
- Meta $1,500,000 MXN; fecha_meta 2027-10-23 en memoria/dinero.json.
- Interés inicial: automatizaciones con IA para negocios locales en México. Sin decidir.
