# JARVIS — Upgrade 04: Conversación continua por voz
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-26)

Eres el ingeniero principal de JARVIS, ubicado en `~/Documents/Jarvis`.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

**OBJETIVO:** Permitir que JP mantenga una conversación natural de varios turnos con JARVIS sin repetir la palabra de activación, conservando contexto, privacidad y controles de seguridad.

Este upgrade debe costar $0 adicionales, funcionar en la Mac mini Intel y respetar toda la arquitectura existente.

## 1. Inspección obligatoria

Antes de editar:

- Lee `CLAUDE.md`, `estado_proyecto.md` y `modulos/voz.md`.
- Lee `modulos/seguridad.md`.
- Ejecuta `git status`.
- Inspecciona el funcionamiento real de `voz/jarvis_voz.py`, `voz/oido.py`, `bin/pensar.py`, `bin/decir.py`, `bin/telemetria.py`, `config.json` y el HUD de Hammerspoon.
- Revisa el gestor de sesiones creado durante el Upgrade 03.
- Ejecuta las 88 pruebas existentes o establece una línea base equivalente.

No modifiques archivos innecesarios.

## 2. Crear un gestor de conversación

Implementa un gestor de estados, preferentemente en `voz/conversacion.py`.

Estados:

**IDLE** — Jarvis espera normalmente su palabra de activación. No transcribe continuamente conversaciones ambientales mediante Groq.

**ACTIVATED** — Detectó «Jarvis». Captura la instrucción mediante el mecanismo actual.

**PROCESSING** — Procesa un comando rápido o consulta a Claude. Evita procesar nuevas consultas simultáneas por accidente.

**SPEAKING** — Jarvis reproduce su respuesta. No interpreta su propia voz como una nueva instrucción. Mantiene el comportamiento actual de no aceptar interrupciones por voz mientras habla.

**FOLLOW_UP** — Después de terminar de hablar, abre una ventana temporal para escuchar otra intervención sin repetir «Jarvis». Si detecta voz válida, transcribe y procesa la siguiente intervención. Puede responder y regresar nuevamente a FOLLOW_UP.

**CLOSED** — Termina la conversación. Limpia los buffers de audio pendientes. Vuelve a IDLE.

Implementa transiciones explícitas y comprobables. Evita condiciones de carrera entre micrófono, reproducción de voz y procesamiento del cerebro.

## 3. Ventana de conversación

Agrega en `config.json`, respetando la estructura existente:

- `conversacion_continua`: activada.
- `timeout_seguimiento_seg`: 15.
- `max_turnos`: 5.
- `duracion_maxima_seg`: 180.

Las configuraciones deben poder ajustarse sin editar Python.

Reglas:

1. JP dice «Jarvis» para iniciar.
2. Jarvis recibe y ejecuta la primera instrucción.
3. Después de terminar completamente su respuesta de voz, empieza el contador de 15 segundos.
4. Durante esa ventana, JP puede hablar sin repetir «Jarvis».
5. Cuando JP comienza una intervención válida, deja de correr el timeout mientras se captura y procesa ese turno.
6. Terminada la siguiente respuesta, se abre otra ventana.
7. Después de 15 segundos de inactividad, regresa a IDLE.
8. Después de cinco intervenciones del usuario o tres minutos desde la activación inicial, cierra la conversación sin procesar nuevos turnos.
9. Si JP dice «Jarvis» de nuevo durante la conversación, no debe ocasionar una segunda sesión ni duplicar la orden.
10. Los plazos se miden con reloj monotónico, no con tiempo de pared.

No agregues una frase automática como «¿Algo más, señor?» después de cada respuesta. No necesitamos que Jarvis esté hablando innecesariamente.

## 4. Transcripción de seguimiento

Hoy faster-whisper base identifica «Jarvis» y Groq transcribe la instrucción.

Durante FOLLOW_UP:

- No exijas la palabra «Jarvis».
- No ejecutes Whisper base únicamente para buscar la palabra de activación.
- Usa el mecanismo actual de detección de voz por energía.
- Si hay una intervención válida, usa Groq para transcribirla.
- Conserva faster-whisper small como respaldo.
- Mantén los filtros de transcripciones fantasma.
- Reutiliza el audio capturado sin volver a grabarlo.
- No envíes silencios ni audio ambiental a Groq.
- Evita múltiples solicitudes para una misma intervención.
- No agregues bibliotecas pesadas ni modelos adicionales.

Umbrales razonables para distinguir voz de ruido, sin perder respuestas cortas como «sí», «no», «el segundo» o «mañana».

Si falla la transcripción, no inventes la orden ni ejecutes acciones. Política predecible, sin ciclo de errores.

## 5. Contexto entre turnos

Reutiliza las sesiones explícitas del Upgrade 03 (`--session-id` / `--resume`).

Ejemplo: «Jarvis, ¿qué tengo mañana?» → «Dos pendientes, señor. Matemáticas e Historia». → «¿Cuál vence primero?» — debe entender la referencia.

No reenvíes manualmente el historial si la sesión de Claude ya lo conserva.

Cerrar la ventana de voz NO destruye la sesión personal de Claude. Se conserva la expiración de 30 minutos del contexto del cerebro. Las sesiones automática, personal y de desarrollo siguen aisladas. Si el fallback Codex está activo, conserva exclusivamente las capacidades y restricciones que pasaron las pruebas del Upgrade 03.

## 6. Comandos rápidos en conversación

En FOLLOW_UP funcionan los comandos rápidos sin llamar a Claude.

Ejemplo: «Jarvis, abre Spotify» → abre. «Ponle pausa» → pausa sin «Jarvis» ni Claude. «Siguiente canción» → cambia.

No rompas: Spotify, volumen, apertura de apps, modos gamer/estudio/trabajo/dormir, «desactiva el modo X», el panel HQ, los perfiles de Chrome.

Si un comando rápido no produce respuesta hablada, abre la siguiente ventana al terminar la acción, sin esperar una reproducción inexistente.

Una acción rápida no interrumpe ni invalida la sesión personal de Claude.

## 7. Cierre manual

Reconoce localmente comandos inequívocos: «Terminamos, Jarvis», «Cierra la conversación», «Eso es todo, Jarvis». Cierran la ventana sin llamar al cerebro.

No uses palabras ambiguas como «no» o «gracias» como cierre automático.

Conserva el atajo para callar a Jarvis: callar detiene la reproducción actual y cierra la ventana activa.

No implementes todavía interrupciones por voz durante la reproducción.

## 8. Evitar que Jarvis se escuche a sí mismo (crítico)

Hoy el micrófono sigue capturando mientras Jarvis habla, pero el audio se descarta. Conserva esa protección.

- FOLLOW_UP solo comienza después de que la reproducción realmente terminó.
- Descarta el audio acumulado durante SPEAKING.
- El final de la respuesta hablada no se interpreta como instrucción.
- Maneja errores o cancelaciones de `say` y del backend de voz instalado.
- No dependas de un temporizador que estime cuánto durará la frase.
- Una reproducción vieja no puede abrir una ventana de una conversación ya cerrada.

No implementes barge-in; eso es otro upgrade.

## 9. Privacidad y seguridad

- FOLLOW_UP solo se activa después de una activación legítima («Jarvis» o el atajo autorizado).
- La conversación se cierra sola al agotarse sus límites.
- Cambios de modo e interrupciones externas se manejan explícitamente.
- Si Jarvis está dormido o en un estado sin escucha, no puede quedar conversación abierta.
- La detección de audio no abre por sí sola una conversación desde IDLE.
- No guardes audio en disco.
- No agregues transcripciones a la telemetría.
- No agregues accesos a secretos o credenciales.
- No envíes a Groq audio fuera de una sesión autorizada.

Conserva el Upgrade 02 completo. Una conversación continua NO autoriza enviar mensajes, borrar, gastar ni publicar. Lo que requiere aprobación sigue bloqueado hasta que exista una interfaz local confiable. Lo prohibido sigue prohibido. No relajes los hooks de seguridad ni el aislamiento de Codex.

## 10. Indicador visual

Integra el estado de conversación en el HUD de Hammerspoon existente (reutiliza la barra luminosa). Sin interfaz paralela.

Indicación discreta y distinta para: escuchando activación, procesando, hablando, esperando seguimiento.

Sin animaciones pesadas. No cambies la estética del panel HQ. Si Hammerspoon no está, Jarvis sigue funcionando y respetando los límites.

## 11. Telemetría

Registra eventos técnicos: activación de conversación, inicio/fin de FOLLOW_UP, seguimiento detectado, cierre por timeout, cierre manual, cierre por límite de turnos, seguimiento descartado por ruido o reconocimiento inválido, tiempo entre fin de respuesta y nueva intervención, latencia agregada por el gestor.

No guardes lo que dice JP. No infles `metricas_latencia.jsonl`.

## 12. Pruebas automatizadas

En `tests/test_conversacion.py`, como mínimo:

- T1. Sin palabra de activación, permanece en IDLE.
- T2. «Jarvis» abre una conversación.
- T3. La primera instrucción se procesa.
- T4. Al terminar la respuesta hablada se abre FOLLOW_UP.
- T5. Una segunda pregunta dentro del plazo no necesita «Jarvis».
- T6. Esa pregunta conserva el contexto de la sesión personal de Claude.
- T7. Una tercera pregunta también funciona.
- T8. Tras 15 s de silencio vuelve a IDLE.
- T9. Después del cierre, hablar sin «Jarvis» no ejecuta nada.
- T10. Cinco turnos provocan el cierre.
- T11. Tres minutos provocan el cierre.
- T12. Decir «Jarvis» en FOLLOW_UP no duplica solicitudes.
- T13. Un comando rápido funciona sin llamar al modelo.
- T14. El audio de Jarvis no se procesa como instrucción.
- T15. Los buffers se limpian al cerrar.
- T16. Errores de transcripción no ejecutan comandos inventados.
- T17. Un error de TTS no deja abierto el micrófono conversacional.
- T18. Una activación mientras se procesa otra orden no inicia dos consultas concurrentes.
- T19. Los cierres manuales funcionan localmente.
- T20. Las operaciones sensibles siguen sujetas al Upgrade 02.
- T21. Codex mantiene el aislamiento del Upgrade 03.
- T22. La separación personal/automática/desarrollo sigue.
- T23. La telemetría no guarda audio ni transcripciones.
- T24. Funciona sin HUD.
- T25. La expiración del contexto de Claude es independiente de la ventana de voz.

Mocks para reloj, voz, Groq, Claude y micrófono. Ejecuta también las 88 pruebas anteriores.

## 13. Prueba real en la Mac

Tras pasar las pruebas automáticas, prueba controlada con el micrófono PD100X. JP dirá:

1. «Jarvis, ¿qué hora es?»
2. Esperar a que termine la respuesta.
3. «Abre Spotify» (sin «Jarvis»).
4. Esperar a que complete la acción.
5. «Ponle pausa».
6. «Cierra la conversación».
7. Esperar unos segundos.
8. «Abre Spotify» (sin «Jarvis»).

Esperado: 1, 3 y 5 funcionan; 6 cierra; 8 NO se ejecuta.

Prueba de contexto: «Jarvis, dime tres planetas del sistema solar» → «¿Cuál de esos es el más grande?» — debe entender la referencia.

Pide a JP participar solo cuando las pruebas automáticas estén aprobadas. No simules una prueba humana que JP no hizo.

## 14. Restricciones

- Mac Intel 2018, 16 GB RAM. Sin hardware ni facturación API nueva.
- Mantener Claude Pro y Codex existentes, la arquitectura restringida del 02 y las sesiones separadas del 03.
- Sin streaming del modelo. Sin barge-in. Sin motores de voz nuevos. Sin ElevenLabs.
- No tocar memoria a largo plazo ni módulos ajenos a la conversación.
- Sin procesos permanentes nuevos salvo justificación técnica imprescindible.
- No afectar las cuentas escolar y personal. Nada destructivo.
- Compatibilidad con el arranque y reinicio actuales.

## 15. Cierre

Reporte con:

1. Archivos creados/modificados.
2. Máquina de estados final.
3. Tiempos y límites.
4. Cómo se conservó el contexto de Claude.
5. Qué pasa en reproducción de voz, silencio y errores.
6. Resultados de las pruebas nuevas.
7. Resultado de las 88 anteriores.
8. Prueba real con JP: realizada o pendiente.
9. Impacto en rendimiento y consumo de Groq.
10. Limitaciones y rollback.

Actualiza `estado_proyecto.md`. Commit cuando las pruebas automáticas pasen sin regresiones; indica si la validación física sigue pendiente.

**Detente al terminar este upgrade. No implementes streaming ni interrupciones por voz.**

---

## Ajustes de Claude (revisor) — obligatorios

Revisados contra el código real (voz/jarvis_voz.py, voz/oido.py, bin/decir.py, hammerspoon/init.lua).

1. **Respaldo primero.** Antes de tocar nada: commit "Respaldo antes de upgrade 04" incluyendo `hq/index.html` (está modificado). NO agregues `.claude/settings.local.json` a git, ni en este commit ni en los siguientes.

2. **Un solo hilo, cero procesos nuevos.** El ciclo de `voz/jarvis_voz.py` hoy es síncrono: `oido.frase()` bloquea, `procesar()` bloquea y `decir()` regresa cuando `say`/`afplay` de verdad terminó. Construye encima de eso: la máquina de estados corre en el mismo hilo del ciclo principal. Nada de threads, asyncio ni temporizadores paralelos. "Terminó de hablar" = `decir()` regresó. Después de cada `decir()` siempre `oido.vaciar()` antes de abrir FOLLOW_UP. `voz/conversacion.py` debe ser lógica pura (sin micrófono, sin `say`, reloj inyectable) para probarla con mocks; `jarvis_voz.py` solo la conecta.

3. **Reloj monotónico en el oído.** `oido.frase()` usa `time.time()` para `espera_inicio`: cámbialo a `time.monotonic()` (cambio mínimo, misma conducta). Los 15 s empiezan cuando `decir()` regresa (o cuando acaba una acción rápida sin voz). `espera_inicio` ya deja de contar en cuanto empieza la voz: reutilízalo, no lo reimplementes. FOLLOW_UP usa los mismos parámetros de captura que `pedir_comando` (fin_silencio 1.3, max_dur 25). No subas el mínimo de 0.3 s de voz (`con_voz < 3`): "sí" y "no" deben pasar.

4. **Otras voces de Jarvis (crítico; el diseño original no lo cubre).** No solo habla el ciclo de voz: el vigía (`avisar.py --hablar`), el resumen (`jv resumen`, que el comando rápido lanza con `Popen` y NO espera) y `modo.py` también llaman `decir()`, que toma `~/.jarvis/voz.lock`. Si cualquiera habla durante FOLLOW_UP, el micrófono lo oye y lo mandaría a Groq como orden. Regla: antes de transcribir un audio de FOLLOW_UP, comprueba `voz.lock` con flock no bloqueante (LOCK_EX|LOCK_NB, y suéltalo en seguida) y que `estado.json` no diga "hablando". Si otra voz está sonando o sonó durante la captura: descarta el audio, vacía la cola y sigue esperando sin reiniciar el contador. Además, el comando rápido "resumen" cierra la conversación. Prueba para esto.

5. **Comandos rápidos ambiguos, solo en FOLLOW_UP (IDLE queda igual).** En plática, "¿y la siguiente?" o "¿y el anterior?" son preguntas, no Spotify. En FOLLOW_UP:
   - "siguiente" / "anterior" solo cambian canción si dice "canción" (siguiente canción, canción anterior, salta/cambia/regresa la canción) o si la frase es exactamente "siguiente"/"anterior" Y el turno anterior fue un comando de Spotify (guarda solo la categoría "spotify", nunca el texto). Si no, va al cerebro.
   - "ya" y "para" solos van al cerebro (pueden ser respuestas).
   - Una prueba por cada caso.

6. **«Jarvis» y atajos dentro de la conversación.** Si en FOLLOW_UP la transcripción trae «Jarvis», quítalo con `separar()` y procesa el resto como un turno más de la misma conversación (una sola llamada a Groq, una sola al cerebro). Si solo dijo «Jarvis»: suena Tink, la ventana sigue y no cuenta turno. ⌃⌥J durante FOLLOW_UP = capturar el siguiente turno de la misma conversación. El camino "solo Jarvis + tin" (`pedir_comando`) y ⌃⌥J desde IDLE también abren conversación. ⌃⌥Espacio (texto, `bin/pensar.py`) NO abre ni toca la conversación de voz.

7. **Turnos y tiempo sin ambigüedad.** La primera orden es el turno 1. Tras responder el turno 5 no se abre ventana: CLOSED. Los 180 s cuentan desde la activación; si se cumplen mientras se procesa o habla un turno, ese turno termina normal y luego se cierra (no se corta a la mitad). Ruido descartado o frase fantasma: no cuenta turno ni reinicia los 15 s. Si la transcripción falla o sale vacía dos veces seguidas en la misma conversación → CLOSED. Nunca se procesa texto vacío.

8. **Callar y cerrar.** ⌃⌥. corre `jv decir --callar` en OTRO proceso (Hammerspoon), así que el ciclo de voz no se entera, y al morir `say`, `decir()` regresa como si hubiera terminado → abriría FOLLOW_UP. Arreglo: `callar()` además crea la bandera `~/.jarvis/cerrar_conversacion`; el ciclo la revisa dentro de `frase()` (igual que el disparador) y justo después de que `decir()` regresa. Si existe: no abre ventana, cierra y borra la bandera. También se borra al iniciar cada conversación nueva, para que una vieja no cierre la siguiente. Si se calla durante PROCESSING, no se habla la respuesta y se cierra. "Cállate"/"silencio" en FOLLOW_UP cierran. Activar "modo dormir" dentro de la conversación la cierra.

9. **Cierre manual sin hablar de más.** "Terminamos", "cierra la conversación", "eso es todo" (con o sin «Jarvis») cierran con un sonido corto del sistema (ej. /System/Library/Sounds/Bottle.aiff), sin frase hablada. Documéntalo.

10. **HUD.** Agrega el estado "seguimiento" a `estado.json` y a `ETIQUETAS` en `hammerspoon/init.lua`, con una indicación discreta (sin texto tipo "¿algo más?") y un timer de seguridad de timeout + 2 s para que se oculte aunque el ciclo muera. Al cerrar, el ciclo escribe "listo". Revisa cómo carga Hammerspoon ese archivo (no adivines) y recárgalo al final.

11. **Telemetría.** Un `conv_id` aleatorio por conversación + número de turno. Cada turno de FOLLOW_UP es su propio `tm.nueva("voz")` para que `jv latencia` siga igual. Máximo un evento por transición. Agrega a `jv latencia` un resumen corto: conversaciones, turnos promedio, cierres por motivo, % de seguimientos descartados. El `log()` de bitácora existente no se cambia en este upgrade.

12. **Groq.** No leas ni imprimas `secretos.env`. Si no hay llave de Groq, el seguimiento cae a faster-whisper small: repórtalo con los números de latencia, no lo arregles aquí.

13. **Cuota de llamadas reales:** máximo ~10 `claude -p` en todo el upgrade (las automáticas van con mocks).

14. **Prueba real.** Cuando las automáticas pasen y ya hiciste el commit: reinicia la voz (`open ~/Documents/Jarvis/Jarvis.command`), confirma que arrancó, y dale a JP las frases de la prueba y la de los planetas en UN bloque numerado y corto. Luego verifica tú cada paso con la salida de la voz / telemetría; no dependas de que JP te lo cuente. Reporta qué pasó en cada paso.

15. **Al terminar:** commit "Upgrade 04: conversación continua por voz". Actualiza `memoria/estado_proyecto.md` ("Ya funciona", "Paso actual", fecha; el roadmap 1 queda con barge-in pendiente y streaming pasa al siguiente upgrade) y `modulos/voz.md`. Reporte con el hash para rollback. Si la prueba física quedó pendiente, dilo claro en "Paso actual".
