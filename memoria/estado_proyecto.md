# Estado del proyecto Jarvis — el hilo conductor

> Este archivo es la memoria del PROYECTO (no de JP). Cualquier chat nuevo (Claude, ChatGPT o Jarvis) empieza leyendo esto.
> Se actualiza al cerrar cada paso: qué se hizo, qué se decidió, qué sigue.

**Última actualización:** 2026-11-17 (mudanza a Windows en curso)

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
- Arranque en segundo plano (upgrade 08, 2026-10-29): `~/Applications/Jarvis.app` (binario delgado, firma ad-hoc, no se recompila) como elemento de inicio → `bin/arranque.sh` → supervisor `bin/arranque.py` (candado flock, tubo vigía, hijos por PID+hora, reintentos 5–120 s, estados, registro `~/.jarvis/arranque.log`). Respaldo: Jarvis.command con el mismo supervisor. Controles en el menú de Hammerspoon y `jv arranque estado|detener|abrir|inicio`. Ver modulos/arranque.md.
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
- Memoria permanente (upgrade 07, 2026-10-27): «Jarvis, recuerda que…» (voz o ⌃⌥Espacio) guarda en local, sin Claude, en ~/.jarvis/recuerdos.jsonl (0600, registro de eventos, fsync). Corregir, olvidar (desactiva, no borra) y «¿qué recuerdas de…?». Claude recibe hasta 3 recuerdos relevantes como datos (búsqueda léxica con raíces, por ámbito; desarrollo solo si pregunta por Jarvis). Sin recuerdos: Codex, el resumen automático y el historial. Privacidad: no guarda secretos, datos médicos o financieros, terceros ni contenido de páginas. `jv memoria listar|buscar|estado`. Búsqueda con 500 recuerdos: p50 11 ms. Pruebas: 353 OK. Prueba física aprobada el 2026-10-28. Ver modulos/memoria.md.

## Pendientes conocidos
- [ ] JP: sacar llave de Groq y guardarla (`chmod +x ~/Documents/Jarvis/bin/jv && ~/Documents/Jarvis/bin/jv llave groq`), reiniciar Jarvis.
- [ ] Hammerspoon: confirmar permiso de Accesibilidad.
- [ ] iPhone: app ntfy suscrita al canal.
- [ ] Datos de JP: link app análisis facial, app de modos teclado/mouse (Logitech G HUB), ciudad para clima.
- [ ] Subir Jarvis a GitHub privado (jmuro2110-hub/jarvis) para que ChatGPT lea el código real.
- [x] Bug (2026-10-28): «Jarvis» desde IDLE no activaba (en seguimiento sí). No era la app de Claude: con ruido de fondo Whisper base tardaba hasta 24 s y `oido.vaciar()` tiraba lo dicho mientras tanto. Arreglado en 4c0f1d7 (cola conservada, base ve 3 s, telemetría `deteccion_base`, «qué horas»). Prueba física 2026-10-28 14:00–14:02 con la app de Claude al frente: 3/3 activaciones desde IDLE (base 576 / 504 / 602 ms), la tercera con Spotify sonando; «cállate» confirmado (paró en 2.15 s). Abierto: con música, base a veces tarda 2–9.6 s aun con 3 s de audio (probable reintento por temperatura de faster-whisper); ya no se pierde la orden pero llega tarde. Una orden salió mal transcrita («Corazón»).
- [ ] Correr Jarvis en segundo plano sin ventana de Terminal, sin perder el permiso del micrófono.
- [ ] Whisper base lento en IDLE con música: 2–9.6 s aun con solo 3 s de audio (`deteccion_base` motivo `lenta`). Causa probable: reintentos por temperatura de faster-whisper (fallback 0.2, 0.4…) cuando el audio es dudoso. La orden ya no se pierde (4c0f1d7), solo llega tarde. No se arregla en el 08; candidato: `temperature=0` solo para la detección de «Jarvis», medido antes/después. **Para el Upgrade 09.** También pesa en el barge-in: con música, base tardó 2.3–4.9 s en detectar mientras Jarvis hablaba (física del 08, 2026-10-29), contra 0.5–0.6 s sin música.
- [ ] **Upgrade 09:** «Jarvis, espera» no pausa mientras Jarvis habla. Física del 08 (2026-10-29 12:15, Jarvis.app, sin música): base oyó «Jarvis» en 0.57 s (igual que en Terminal), pero `voz/interrupciones.py` lo descartó con `jarvis_en_medio` (más de una palabra antes de «Jarvis», regla a del 06). Sin pausa, «sigue» entró como seguimiento a Claude (12.4 s) en vez de retomar. No es regresión del 08 (el archivo no cambia desde 19619f5) y App Nap quedó descartado. El texto no se registra, así que falta saber qué palabras quedan antes; candidato: telemetría solo del número de palabras previas y del pedazo de Jarvis, y revisar la regla a frente al eco.

## Roadmap de upgrade (diagnóstico de ChatGPT, 2026-10-24, aprobado)
1. **Conversación continua**: seguir la plática sin repetir "Jarvis" y entender "esa/la primera" ✅ (upgrade 04). Barge-in ✅ (upgrade 06).
2. **Velocidad**: medida, stdin resuelto (01/03) y stream-json con voz anticipada (05) ✅.
3. **Memoria que aprende**: permanente vs reciente vs recuerdos relevantes ✅ (upgrade 07, 2026-10-28).
4. **Iniciativa con criterio**: prioridades, silencio, no repetir avisos, contexto (modo, pendientes).
5. **Autonomía real en macOS** con candados por código (no solo instrucciones).
6. Después: voz premium (ElevenLabs), recordatorios con hora, Classroom.
- Idea reservada (después del 08, no implementada): memoria sugerida con confirmación. Jarvis detecta una posible preferencia y pregunta «¿Quiere que recuerde que…?»; solo un «sí» explícito de JP ligado a esa propuesta la guarda por el mecanismo local del 07. «No», silencio, vencimiento o ambigüedad no guardan nada. Misma validación de privacidad y ámbitos; nunca confirmaciones del modelo, páginas o herramientas.

## Paso actual
- **Mudanza a Windows en curso (2026-11-17).** Respaldo previo: repo privado `jmuro2110-hub/jarvis` en GitHub con todo el historial. Verificado antes de subir: `~/.jarvis/` (incluido `secretos.env`) vive fuera del repo y ninguno de sus valores aparece en archivos ni en el historial. En Windows hay que recrear `~/.jarvis/secretos.env` a mano. El upgrade 09 queda en pausa hasta terminar la mudanza.
- Upgrade 09 (naturalidad de la voz), revisión inicial aprobada. 09A implementado (medición del recorrido real, sin cambios funcionales; 419 pruebas OK), **pendiente de prueba física**. 09B–09H sin empezar.
- **Upgrade 08 terminado y aprobado (2026-10-29):** implementado (1196b0c, a229656, c8a954a; 394 pruebas OK). Física aprobada: A, B, D, E, F (cierre de sesión y reinicio: una instancia, sin Terminal, sin avisos dobles; listo en 10.8 / 8.5 s en frío), G (menú detener/abrir, bloqueo y reposo manual: dormida 14:40:40–14:41:51, mismo supervisor sin reinicio, «qué hora es» al despertar con detección de 0.48 s), H (rollback a Terminal y regreso), C «cállate» (14:43:09, detección 0.50 s, paró en 1.7 s). Fallaron y van al 09 por decisión de JP: «espera» (`jarvis_en_medio`) y base lento con música. Pendiente: Automatización de Minecraft (decisión de JP). Latencia sin regresión salvo barge-in con música. Arreglos durante la física: `ps` con LC_ALL=C (Detener del menú no paraba), menú de Hammerspoon global (se borraba el ◉), aviso al reabrir vía Hammerspoon, listado de elementos de inicio.
- Upgrade 07 terminado (2026-10-28): memoria permanente con 353 pruebas OK. Prueba física aprobada: guardar por voz y ⌃⌥Espacio, uso en Claude, 40 desde la memoria con sesión nueva, corregir a 50 por voz (local, 1.9 s), «¿cuánto deberían durar mis bloques?» → 50, consultar, olvidar y «cállate» a media respuesta (paró en 2.5 s). Arreglos durante la prueba: llamado mal transcrito («Jardis»), red de seguridad de la bitácora, intenciones sin acentos ni mayúsculas. Recuerdos activos: bloques de 50 minutos (escuela) y avanzar una mejora a la vez (desarrollo). Después del 07, aparte: eco del prompt de Groq descartado ✅ (bb5416e): 3+ palabras todas de VOCAB («Pendientes, tarea, rutina, panel.») → «No le entendí, señor.», sin Claude. 357 pruebas OK. Activación en IDLE arreglada (4c0f1d7, 367 pruebas OK, prueba física aprobada).
- Upgrade 06 terminado (2026-10-27): barge-in («cállate» ≈1.6 s, «espera» ≈2.2 s), cero falsas interrupciones con música, voz al result 0.39–0.52 s antes, pendientes solo personales.
- Límites abiertos (07): búsqueda léxica, sin semántica; dos recuerdos que se contradicen se pasan juntos; la validación de privacidad es por palabras (conservadora); reiniciar Jarvis no borra la sesión reciente (30 min).
- Límites abiertos (06 y antes): barge-in sin cancelación de eco y con piso de ruido propio: con música alta casi no hay candidatos; callarlo tarda ~1.5–2.2 s; «no, mejor X» con la voz sonando solo está probado en automático; la primera detección con Whisper base tras reiniciar tardó 6.2 s; la voz anticipada solo aplica a conocimiento general; sesiones del asistente y de desarrollo comparten carpeta de proyecto de Claude; WebFetch puede sacar datos en una URL; en Codex quedan `apply_patch`/recursos MCP dentro del modo código (falla cerrado); si se actualiza Codex el respaldo se apaga hasta volver a probar.

## Fase B — Negocio (después del upgrade)
- Meta $1,500,000 MXN; fecha_meta 2027-10-23 en memoria/dinero.json.
- Interés inicial: automatizaciones con IA para negocios locales en México. Sin decidir.
