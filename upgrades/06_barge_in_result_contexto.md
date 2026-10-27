# JARVIS — Upgrade 06: Barge-in + voz al recibir `result` + contexto personal
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-27)

Eres el ingeniero principal de JARVIS, ubicado en `~/Documents/Jarvis`.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

**OBJETIVO PRINCIPAL:** que JP pueda interrumpir a JARVIS por voz mientras habla, sin reiniciar el asistente, sin perder el contexto y sin ejecutar instrucciones duplicadas.

**OBJETIVOS SECUNDARIOS:**
1. Empezar a hablar en cuanto llegue el evento `result` válido de Claude, sin esperar a que el subproceso termine (potencialmente 0.4–0.7 s).
2. Que las respuestas del asistente personal no incluyan cosas del desarrollo de Jarvis cuando JP pregunta por asuntos personales, escolares o cotidianos.

Presupuesto adicional: $0 MXN. No reconstruyas Jarvis: cambios pequeños y verificables sobre los upgrades 01–05.

La regla principal: interrumpir la REPRODUCCIÓN, no cancelar automáticamente el razonamiento ni las acciones ya iniciadas (cancelar procesos o repetir herramientas sin saber qué ejecutaron puede duplicar acciones). En esta versión se exige «Jarvis» para interrumpir mientras habla. Eso no equivale a cancelación de eco: la prueba física es indispensable.

## 1. Inspección obligatoria

- Lee `CLAUDE.md`, `estado_proyecto.md`, `modulos/voz.md`, `modulos/seguridad.md` y módulos relacionados.
- `git status` y conserva los cambios anteriores.
- Inspecciona `voz/jarvis_voz.py`, `voz/oido.py`, `voz/conversacion.py`, `bin/decir.py`, `bin/pensar.py`, `bin/streaming.py`, `bin/telemetria.py`, `config.json` y Hammerspoon.
- Quién posee el micrófono, quién administra el TTS, cómo funciona `~/.jarvis/voz.lock`, cómo se detecta el fin real de `say`, dónde se pasa a FOLLOW_UP, dónde se construyen las instrucciones del modo asistente.
- Revisa las 209 pruebas y el comportamiento real de los eventos `result`.

Documenta brevemente la arquitectura actual antes de editar. No asumas que los archivos tienen exactamente la estructura de este prompt.

## 2. Barge-in: comportamiento requerido

- **A. «Jarvis, cállate»** (también «calla», «deja de hablar»): detener la voz de inmediato, sin nueva consulta a Claude, cerrar la conversación, volver a IDLE.
- **B. «Jarvis, espera»:** detener la voz, conservar el contexto de Claude, abrir FOLLOW_UP de 15 s, permitir la siguiente pregunta sin repetir «Jarvis».
- **C. «Jarvis, no, mejor dime qué tengo mañana»:** detener la voz anterior, capturar la nueva instrucción completa, procesarla normal (cerebro o comando rápido), conservar contexto, responderla.
- **D. Solo «Jarvis»:** interrumpir la voz una vez verificada la activación, esperar la orden con el timeout existente; si no llega, cerrar limpio o volver a FOLLOW_UP según la política. Nunca inventar una orden.
- **E. Audio ambiental** (tele, música, voces lejanas, ruido) sin activación válida: Jarvis sigue hablando. Nada de interrupciones genéricas por ruido.

## 3. Captura concurrente (ver Ajuste 2: se hace SIN threads)

Componente preferido `voz/interrupciones.py`, responsabilidad exclusiva: vigilar activaciones mientras Jarvis habla, confirmarlas, pedir que se detenga el TTS y pasar el audio de la nueva instrucción al flujo conversacional. No crea otro asistente ni consultas paralelas a Claude.

- Un solo propietario efectivo del micrófono. Reutiliza el callback/cola existente. No abras dos streams sobre el PD100X. Que nadie consuma destructivamente la misma cola y pierda frames.
- Sin procesos residentes nuevos, sin espera activa, limpieza correcta al reiniciar, nunca varios oyentes. Colas con límite.

## 4. Detección de activación durante la voz

Reutiliza faster-whisper base (Mac Intel, ~0.7 s por detección). No instales otro motor de wake word. Groq ya transcribe las órdenes.

1. Audio entrante en buffer limitado. 2. VAD para localizar candidatos. 3. Reconocimiento local solo sobre candidatos razonables. 4. Confirmar «Jarvis». 5. Detener el TTS con activación confiable. 6. Conservar el audio posterior para la orden completa. 7. Groq + su fallback para la orden.

No Whisper sobre cada bloque de 100 ms, no mandar a Groq todo lo captado durante la voz, no varias inferencias simultáneas, un mismo segmento no provoca varias interrupciones.

**Eco (riesgo principal):** el PD100X puede captar la voz de Jarvis por las bocinas. No presupongas cancelación de eco. Usa información de la reproducción activa para descartar candidatos de su propia voz, con reglas ligeras y de confianza; prueba con audífonos y con bocinas. No seas tan restrictivo que sea imposible hablarle encima. Si el audio no permite distinguir con confianza, documenta la limitación; no afirmes AEC sin implementarlo y probarlo. Nunca conviertas una detección incierta en una acción sensible.

## 5. Cancelación segura de TTS

Operación explícita tipo `cancelar_reproduccion_actual()`:
- Detiene SOLO la reproducción de JARVIS. No mata otros audios ni Spotify ni todos los `say` por nombre.
- No cancela a Claude. Libera `voz.lock`. Invalida reproducciones pendientes de la interacción anterior. Un callback tardío no reabre SPEAKING.
- Referencias al proceso exacto, nada de terminación global por nombre. ElevenLabs compatible pero sin activarlo.
- Idempotente. Probar: interrupción al empezar la voz, a la mitad, justo al terminar, dos casi simultáneas, tras un error de TTS, y cuando la voz anticipada termina antes que Claude.

## 6. Coordinación con Claude y conversación continua

Interrumpir la voz no interrumpe el cerebro. Si Claude ya terminó, se limpia la voz y se procesa lo siguiente. Si sigue generando: se para el TTS, se conserva el resultado, NO se inicia otra consulta en la misma sesión, no se mata Claude, no se repiten herramientas ni acciones con efectos. La nueva instrucción puede esperar en una cola limitada. Máximo una consulta activa por sesión personal.

Estados: puedes usar INTERRUPTION_DETECTED / STOPPING_SPEECH / CAPTURING_INTERRUPTION o eventos internos, sin duplicar la máquina existente. Conserva FOLLOW_UP 15 s, 5 turnos, duración máxima, cierre local, sesiones por ID, separación de sesiones automáticas y contexto. Solo las solicitudes procesadas cuentan como turno (no falsas activaciones ni «cállate»). Un límite alcanzado no se reinicia en silencio.

## 7. Ajuste A: hablar al recibir `result`

Tras `result`, el proceso de Claude tarda 0.4–0.7 s en salir y la ruta normal espera esa salida. Objetivo: empezar la voz en cuanto llegue un `result` completo, válido y exitoso.

Detectar `result` → validar estructura y estado → extraer la respuesta sin duplicados → desbloquear el TTS → seguir drenando stdout/stderr → recolectar el proceso → registrar errores tardíos. Recibir `result` no es tener el código de salida.

Seguridad: no hablar con evento incompleto o con error; no ejecutar herramientas por esta optimización; no duplicar voz si ya hubo voz anticipada; no relanzar Claude por un error posterior al `result`; no abrir FOLLOW_UP con procesos/callbacks pendientes. Nada de `kill` para ganar esos 0.4–0.7 s; limpieza supervisada con timeout. El modo JSON sigue como rollback.

Medir por separado: recepción de `result`, inicio de TTS, salida de Claude, diferencia voz–salida, tiempo de limpieza. Demostrar el ahorro con mediciones reales.

## 8. Ajuste B: contexto personal sin contaminación del desarrollo

Problema: «Jarvis, ¿qué tengo pendiente?» puede mencionar tareas del repositorio, `hq/index.html`, commits, etc.

Diagnostica el origen (CLAUDE.md, cwd del repo, sesión personal, memoria, archivos de desarrollo, instrucciones de sistema, herramientas innecesarias). No asumas que se arregla solo con el prompt.

- «¿Qué tengo pendiente?» → pendientes personales/escolares registrados, por fecha.
- «¿Qué tengo pendiente de la escuela?» → solo escolares.
- «¿Qué tengo pendiente del proyecto Jarvis?» / «¿Qué archivos modificamos en el último upgrade?» → ahí sí información técnica.

Fuente prioritaria: `memoria/pendientes.md` (y otras fuentes personales autorizadas que existan). No escanees el repo para armar pendientes personales. Resuelve lo sencillo con una herramienta local determinista sin llamar a Claude. No inventes pendientes. No ocultes pendientes legítimos del negocio solo por técnicos: respeta el alcance de la pregunta.

Instrucciones exclusivas del modo asistente; modo desarrollo intacto; no modificar CLAUDE.md globalmente; no crear otro cerebro ni otra memoria; no "arreglarlo" filtrando palabras como git/HTML del resultado. Las sesiones personales existentes pueden traer contexto técnico: las reglas nuevas deben prevalecer; no borres sesiones ni historial.

## 9. Configuración

`barge_in: true`, `hablar_al_result: true` (ver Ajuste 8). Con `barge_in: false` = comportamiento del 05. Con `hablar_al_result: false` = espera anterior. Ninguna opción desactiva seguridad.

## 10. Telemetría

En `bin/telemetria.py` y `jv latencia`: activaciones del detector en SPEAKING, latencia de detección, inicio de intervención → TTS detenido, interrupciones confirmadas, candidatos rechazados, falsas interrupciones en pruebas, tipo (cerrar/esperar/nueva orden), tiempo hasta la siguiente respuesta, `result` recibido, salida de Claude, ahorro por hablar al `result`, limpieza de procesos. Distingue observado vs estimado. Sin audio, prompts, respuestas ni transcripciones. Sin registros que carguen la Mac Intel.

## 11. Pruebas automatizadas (`tests/test_barge_in.py` + ampliar las existentes)

Detección: T1 IDLE igual que antes · T2 activación válida en SPEAKING · T3 ruido no interrumpe · T4 su propia voz no interrumpe · T5 audio ambiguo no ejecuta · T6 sin inferencias simultáneas · T7 no se pierden palabras tras «Jarvis» · T8 pre-roll no duplica audio · T9 dos activaciones seguidas no duplican órdenes · T10 fallo de Whisper no rompe la voz · T11 fallo de Groq conserva el fallback.
Cancelación: T12 «cállate» detiene y cierra · T13 «espera» detiene y abre FOLLOW_UP · T14 «no, mejor…» procesa la nueva · T15 no detiene Spotify · T16 solo el TTS correcto · T17 `voz.lock` no queda tomado · T18 sin procesos/workers huérfanos · T19 cancelar dos veces es seguro · T20 interrupción al mismo tiempo que el fin de la voz sin estados inválidos.
Sesiones y seguridad: T21 se conserva contexto · T22 nunca dos consultas en la misma sesión · T23 interrumpir no repite herramientas · T24 guardia PreToolUse · T25 sensibles siguen pidiendo autorización · T26 Codex aislado · T27 límites de FOLLOW_UP · T28 HUD correcto · T29 `barge_in: false` = 05.
Result: T30 voz antes de la salida del proceso · T31 error no dispara voz · T32 no duplica con voz anticipada · T33 stdout/stderr sin deadlocks · T34 proceso recolectado · T35 error tardío no repite la consulta · T36 modo JSON sigue.
Contexto: T37 «¿qué tengo pendiente?» sin desarrollo · T38 «…de la escuela» fuentes escolares · T39 «…de Jarvis» sí técnico · T40 sesión con historia técnica no contamina · T41 no inventa · T42 no mezcla escuela/personal · T43 sesiones manuales de desarrollo intactas.
Regresión: T44 las 209 previas · T45 telemetría sin contenido sensible · T46 sin instancias duplicadas al reiniciar.

Mocks para micrófono, audio, Groq, Whisper, Claude y reloj. Incluye condiciones de carrera.

## 12. Prueba física obligatoria con JP (no declarar aprobado antes)

- **A Callar:** «Jarvis, explícame qué es un agujero negro» → mientras habla «Jarvis, cállate». Se detiene, cierra, no sigue hablando.
- **B Esperar:** explicación larga → «Jarvis, espera» → «¿Me lo puedes explicar más fácil?». Funciona sin repetir «Jarvis», con contexto.
- **C Corregir:** «Jarvis, dime tres planetas» → «Jarvis, no, mejor dime tres estrellas». Para, entiende, sin duplicados.
- **D Sin falsas interrupciones:** respuesta con música de fondo moderada. No se interrumpe solo ni toma Spotify como orden. Con audífonos y con bocinas; registrar diferencias.
- **E Result inmediato:** telemetría de `result`, inicio TTS, salida de Claude; ¿empezó la voz antes de la salida?
- **F Pendientes:** «Jarvis, ¿qué tengo pendiente?» → solo personal; sin pendientes lo dice. Luego «¿Y qué tenemos pendiente del desarrollo de Jarvis?» → ahí sí del proyecto.
- **G Conversación continua:** activación, seguimiento sin «Jarvis», cierre manual, timeout 15 s, contexto.
- **H Rollback:** `barge_in` y `hablar_al_result` en false, confirmar comportamiento anterior, restablecer.

## 13. Benchmark

Referencias: 03 Claude trivial 2.0–3.9 s; 04 Groq 0.7–1.5 s/turno, gestor 0–4 ms; 05 voz anticipada ~0.6 s antes del resultado, salida tras `result` 0.4–0.7 s.
Medir: latencia de detección de barge-in, tiempo hasta parar la voz, hasta procesar la nueva orden, latencia audible con `hablar_al_result` on/off, CPU y memoria con voz + detección, activaciones falsas, regresiones. Al menos 5 muestras comparables si se puede sin gastar cuota de más. Si lo local es muy lento, repórtalo; no instales modelos más pesados ni servicios de pago.

## 14. Restricciones no negociables

Mac mini Intel 2018, 16 GB, Sequoia. $0. Sin hardware. Sin APIs de pago. Whisper base y Groq. Claude Pro y ChatGPT Pro. Guardia del 02, aislamiento del 03, conversación continua del 04, streaming y arreglo del tin del 05. No debilitar restricciones por velocidad. No duplicar oyentes. No IA local adicional. No grabación permanente. No guardar datos sensibles en el proyecto. No mandar mensajes. No borrar archivos personales. No gastar. No publicar. No Snapchat. Escuela/personal separados. Nada de negocio. Nada de memoria nueva. No cambiar los permisos manuales de desarrollo. Sin refactors fuera de alcance. La seguridad no depende del reconocimiento de voz.

## 15. Reporte de cierre

Archivos; arquitectura de barge-in; micrófono en SPEAKING; cómo evita oírse; cómo cancela el TTS sin afectar otros procesos; concurrencia con Claude; ruta de `result` inmediato; latencia antes/después; separación de contextos; pruebas nuevas; las 209 previas; prueba física; CPU/memoria; limitaciones; rollback exacto; hash del commit.

Actualiza `estado_proyecto.md`. Commit cuando las automáticas pasen sin regresiones; si falta la física, dilo y no cierres el upgrade. Si la detección simultánea es inestable, `barge_in: false` y conserva los dos ajustes secundarios si pasaron sus pruebas.

**DETENTE AL TERMINAR EL UPGRADE 06. No avances al 07.**

**Prioridad: interrupciones confiables, respuestas más rápidas, separación de contextos y cero regresiones de seguridad.**

---

## Ajustes de Claude (revisor) — obligatorios

Revisados contra el código real (`voz/jarvis_voz.py`, `voz/oido.py`, `voz/conversacion.py`, `bin/streaming.py`, `bin/pensar.py`, `bin/decir.py`, `bin/guardia.py`, `config.json`, `memoria/pendientes.md`).

1. **Respaldo primero.** Commit "Respaldo antes de upgrade 06" incluyendo `hq/index.html` (está modificado otra vez). NO agregues `.claude/settings.local.json` a git, ni en este commit ni en los siguientes.

2. **Barge-in SIN threads (reemplaza la idea de "worker" de la sección 3).** El 05 ya coordina todo en un hilo con `Hablador.tick()`. El callback de sounddevice llena `oido.cola` y el hilo principal es el único que la consume. Entonces:
   - `voz/interrupciones.py` = una clase (p. ej. `Vigia`) alimentada con `oido.cola.get_nowait()`, que `Hablador.tick()` llama mientras haya un hijo de voz vivo. Eso cubre las dos esperas: dentro de `streaming.correr()` (voz anticipada y voz al `result` mientras Claude sale) y en `Hablador.esperar()`. Cero threads, cero streams nuevos del micrófono.
   - Una inferencia de Whisper base (~0.7 s) bloquea ese tick y está bien: el callback sigue llenando la cola (no se pierden frames) y el pipe de Claude aguanta.
   - Con `barge_in: true`, TODA voz del ciclo conversacional pasa por `Hablador` (hijo `decir.py`): comandos rápidos (`_hablar`), ruta normal y voz anticipada. `decir()` en proceso se queda para vigía, resumen, ⌃⌥Espacio y "Sistemas en línea".
   - El `Vigia` tiene su PROPIO piso de ruido medido mientras Jarvis habla. NO toca `oido.ruido` (si lo sube, IDLE y FOLLOW_UP quedan sordos después).
   - Segmentación propia y no bloqueante, con los criterios de `frase()` (100 ms, umbral relativo, ~400 ms de previo, mínimo 0.3 s de voz). Candidato = segmento cerrado por ~0.5 s de silencio, o ventana de 2.5 s de voz continua (con bocinas casi nunca hay silencio). Una inferencia a la vez, un candidato por segmento. Buffer máximo ~3 s (`deque` con `maxlen`).

3. **Cancelación — bug real que el diseño no ve.**
   - `Hablador.cancelar()` hace `terminate()` al python de `decir.py`, pero `decir.py` corre `say` con `subprocess.run`: si matas al padre, **`say` queda huérfano y sigue hablando**. Arreglo: lanzar el hijo con `start_new_session=True` y cancelar con `os.killpg(pgid, SIGTERM)` (SIGKILL si sigue a los 0.5 s), o que `decir.py` atrape SIGTERM y mate a su `say`/`afplay`. Solo muere la voz de esa petición: ni Spotify, ni el tin, ni otras voces. Prueba real de que no queda ningún proceso de ese grupo.
   - `voz.lock` es flock: el SO lo suelta al morir el proceso. Pruébalo igual (T17).
   - Si matan a `decir.py`, `estado.json` se queda en "hablando" → `otra_voz()` lo lee y **descartaría la siguiente pregunta de JP como "otra voz"**. Tras cancelar, el coordinador pone el estado correcto. Prueba para esto.
   - Al interrumpir, el `Hablador` queda `interrumpido`: `decir()`/`finalizar()` ya no encolan nada más de esa respuesta.
   - `callar()` (⌃⌥., pkill global) se queda como está; no es parte de este upgrade. «Jarvis, cállate» hablado usa la cancelación nueva, no `callar()`.

4. **Eco: filtros deterministas y ligeros, en este orden.** Con duda → no interrumpe.
   - a) `WAKE_RE` en el texto del candidato y el «Jarvis» al inicio (primeras 2 palabras), no a media frase.
   - b) Anti-eco por texto: se sabe exactamente qué pedazo está diciendo Jarvis. Si la mayoría de las palabras del candidato (sin «Jarvis») están en ese pedazo → rechazado, es su propia voz.
   - c) Si el pedazo que suena contiene algo que case con `WAKE_RE`, en ese pedazo se exige además una orden de la lista (cállate/espera/no, mejor…).
   - d) Ignorar ~300 ms tras empezar cada pedazo.
   - e) `es_fantasma` de siempre.
   - Nada de AEC. Si con bocinas no sale, se documenta y vale para audífonos.

5. **Qué pasa con una interrupción confirmada.**
   - Primero se para la voz (no esperar a Groq). Telemetría: inicio de la intervención → voz parada.
   - La orden: si el borrador de Whisper base trae algo después de «Jarvis», ese segmento va a `oir_bien()` (Groq + fallback). Si solo dijo «Jarvis», captura lo que sigue sin vaciar la cola (como `pedir_comando(vaciar=False)` del 05) con `timeout_orden_seg`, que YA existe.
   - «cállate / calla / deja de hablar / silencio» → cierra con motivo "callar", sin Claude, no cuenta turno.
   - «espera» sola → `respuesta_terminada()` normal → FOLLOW_UP 15 s. No cuenta turno.
   - Solo «Jarvis» y nada en `timeout_orden_seg` → FOLLOW_UP con el tiempo que quede (no cierra, no inventa).
   - «Jarvis, no, mejor X» o «Jarvis, X» → quita «no, mejor / mejor / no» del inicio y X es el siguiente turno (sí cuenta). Pasa primero por `es_cierre()` y por `clasificar_rapido(…, seguimiento=True)` como cualquier turno. Si ya estaba en el máximo de turnos o de tiempo: se cierra esa conversación (motivo registrado) y X abre una nueva como «Jarvis, X» desde IDLE (hubo palabra de activación: no es reinicio silencioso).
   - Si Claude seguía generando: no se lanza nada nuevo hasta que `correr()` termine (ya es así: un hilo + `sesiones.turno`). Claude no se mata; su resultado se guarda en historial y sesión como siempre, solo no se habla. Luego se procesa X.

6. **Voz al `result` (ruta normal).**
   - En `correr()`, con hablador y sin anticipar: al llegar un `result` válido → `hablador.decir(primera_linea(result))` ahí mismo; el bucle sigue drenando stdout y llamando `tick()` hasta que el proceso cierre. Hoy `tick()` solo corre en la rama `anticipar`: que corra siempre que haya hablador.
   - "Válido" = UNA función compartida con `_claude_stream`: `subtype == "success"`, `is_error` falso, `result` str no vacío y que NO case `LIMITE_RE` (mismo criterio de <400 caracteres). Si no es válido no se habla nada y sigue el camino de error/Codex de hoy.
   - En `procesar()` ya existe `hablador.hablo → finalizar(primera_linea(resp))`: con la línea completa ya dicha no debe sonar nada más. Verifica que no duplique ni registre `tts_inicio` dos veces.
   - Si el `result` fue válido y después `rc != 0` → la respuesta CUENTA como buena: no "quedó incompleta", no Codex, no reintento; solo incidente `salida_tardia` en telemetría. Hoy `_claude_stream` trata `rc != 0` como error: ajústalo solo para este caso.
   - Telemetría: `claude_resultado`, `tts_inicio`, `claude_salida` y `ahorro_result = claude_salida − tts_inicio`.
   - Benchmark: 5 con `hablar_al_result: true` vs 5 con false, MISMA pregunta por la ruta normal (con herramientas), mismo todo lo demás.

7. **Contexto personal — causa probable y arreglo.**
   - `memoria/pendientes.md` está VACÍO. El guardia ya bloquea `git` en modo asistente, así que lo de commits/`hq/index.html` no viene de git: casi seguro Claude, al no encontrar nada, hizo Grep/Glob/Read por el repo y sacó "Pendientes conocidos" de `estado_proyecto.md` y cosas de `upgrades/`. Confírmalo revisando las llamadas a herramientas del transcript de la sesión personal (en `~/.claude/projects/…`), sin copiar contenido al repo.
   - **Arreglo 1 (principal):** comando rápido determinista de pendientes en `clasificar_rapido()`: «qué tengo pendiente», «mis pendientes», «qué pendientes tengo», «qué tengo de tarea», «qué tengo (para) hoy/mañana», «qué tengo pendiente de la escuela / de <área>». Lee `memoria/pendientes.md`, solo `[ ]`, orden por fecha, filtra por área si la piden (revisa cómo se escriben las áreas; escuela = área "escuela" o una materia). Voz: máximo 3 + "y N más"; el resto en pantalla. Vacío → «No tiene pendientes registrados, señor.» Sin Claude. En FOLLOW_UP no roba frases como «¿y cuál es primero?» (solo las frases completas de arriba). «…de Jarvis / del proyecto / del desarrollo» NO entra: va al cerebro.
   - **Arreglo 2:** instrucción de modo asistente (constante nueva en `pensar.py`, en TODAS las llamadas del asistente, voz y texto; no en CLAUDE.md, no en el resumen automático si no aplica): para la vida de JP las fuentes son `memoria/` (pendientes.md, jp.md, bitacora.md, dinero.json) y `modulos/`; nada de `upgrades/`, `tests/`, `hq/`, `bin/`, `voz/`, `estado_proyecto.md` ni código, salvo que JP pregunte explícitamente por el desarrollo de Jarvis; si pendientes.md no tiene nada, decirlo, sin buscar en otro lado ni inventar. Ya existe `--append-system-prompt INSTRUCCION_VOZ`: no dupliques la bandera, júntalas en un solo texto.
   - No cambies el guardia para esto. No borres sesiones. CLAUDE.md sin cambios.

8. **Config:** solo `"barge_in": true` y `"hablar_al_result": true`, leídas por petición como las demás. NO agregues `barge_in_timeout_orden_seg` (ya existe `timeout_orden_seg`) ni `barge_in_requiere_jarvis` («Jarvis» siempre es obligatorio, no es opcional).

9. **Pruebas extra** (además de T1–T46): T47 cancelar no deja `say` huérfano (con un hijo real de prueba en su propio grupo) · T48 tras cancelar, el estado no queda "hablando" y la siguiente pregunta no se descarta como otra voz · T49 anti-eco por texto · T50 `rc != 0` tras `result` válido no dice "incompleta" ni llama a Codex · T51 comando de pendientes (vacío, con fechas, por área, «de Jarvis» no entra, FOLLOW_UP no roba) · T52 el piso de ruido de IDLE/FOLLOW_UP no cambia por lo que oyó el Vigia.

10. **Cuota real:** máximo ~15 `claude -p` reales en todo el upgrade.

11. **Prueba física (como en el 05).** Cuando las automáticas pasen y ya hiciste el commit: reinicia la voz (`open ~/Documents/Jarvis/Jarvis.command`), confirma que arrancó y pregúntale a JP si usa bocinas o audífonos (y si puede probar ambos). Luego dale en UN bloque numerado y corto las frases de A–H. Para F: primero «Jarvis, apunta pendiente de prueba de la escuela para mañana», después «Jarvis, ¿qué tengo pendiente?», después «¿Y qué tenemos pendiente del desarrollo de Jarvis?»; al final tú quitas la línea de prueba de `pendientes.md`. Tú cambias la config para H y la regresas. Verifica cada paso con la salida de la voz y la telemetría; no dependas de que JP te lo cuente.

12. **Si hay falsas interrupciones con lo que JP usa a diario** (bocinas o audífonos): `barge_in: false`, se documenta, y se quedan los otros dos ajustes si pasaron.

13. **Al terminar:** commit "Upgrade 06: barge-in, voz al result y contexto personal". Actualiza `memoria/estado_proyecto.md` ("Ya funciona", "Paso actual", fecha; roadmap 1 barge-in ✅ si pasó; quita de "Límites abiertos" lo resuelto: "sin barge-in" y "la ruta normal todavía espera esa salida") y `modulos/voz.md`. Reporte CORTO con el hash para rollback. Si la prueba física quedó pendiente, dilo claro en "Paso actual".
