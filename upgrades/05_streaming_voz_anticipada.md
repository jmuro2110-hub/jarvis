# JARVIS — Upgrade 05: Streaming de Claude + voz anticipada + corrección de captura
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-27)

Eres el ingeniero principal de JARVIS, ubicado en `~/Documents/Jarvis`.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

**OBJETIVO:** Implementar `stream-json` en `claude -p` para medir el tiempo hasta el primer texto y permitir que JARVIS empiece a decir la primera frase de una respuesta segura antes de que Claude termine de generarla.

Adicionalmente, corregir el bug que provoca que se pierda el inicio de una orden cuando JP dice «Jarvis», hace una pausa y luego empieza a hablar.

**IMPORTANTE:** Este upgrade NO incluye barge-in. Jarvis seguirá sin aceptar interrupciones habladas mientras reproduce su propia voz.

Costo adicional: $0 MXN.

## 1. Inspección obligatoria

Antes de editar:

- Lee `CLAUDE.md`, `estado_proyecto.md`, `modulos/voz.md` y `modulos/seguridad.md`.
- Ejecuta `git status` y conserva cualquier cambio existente.
- Inspecciona `bin/pensar.py`, `bin/telemetria.py`, `bin/decir.py`, `bin/jv`, `voz/jarvis_voz.py`, `voz/oido.py`, `voz/conversacion.py`, `config.json` y los componentes de Hammerspoon correspondientes.
- Revisa cómo se utiliza actualmente `~/.jarvis/voz.lock`.
- Revisa el almacenamiento de las sesiones explícitas del Upgrade 03.
- Identifica todos los consumidores de la respuesta de `pensar.py`.
- Inspecciona las 149 pruebas existentes.

Primero documenta el recorrido real de una consulta. No supongas que todas las funciones o archivos tienen exactamente la estructura descrita aquí.

Revisa la versión instalada de Claude: `claude --version`

Y comprueba la compatibilidad de: `--output-format stream-json`, `--verbose`, `--include-partial-messages`

Documentación:
https://code.claude.com/docs/en/headless
https://code.claude.com/docs/en/agent-sdk/streaming-output

No actualices Claude Code automáticamente.

## 2. Migración a stream-json

Actualmente JARVIS ejecuta `claude -p` con salida JSON y espera la respuesta completa.

Implementa un consumidor incremental usando: `--output-format stream-json --verbose --include-partial-messages`

Conserva los argumentos actuales necesarios para:

- Modo restringido `--restricted`.
- Configuración de seguridad del asistente.
- Hooks del Upgrade 02.
- Sesiones `--session-id` y `--resume`.
- Prompt de sistema de JARVIS.
- Autenticación actual mediante Claude Pro.
- stdin cerrado correctamente.
- Aislamiento de las sesiones personal y automática.

No introduzcas `--continue`, `--bare`, nuevas APIs ni opciones que debiliten el aislamiento.

### Lectura incremental

Utiliza `subprocess.Popen` o un mecanismo equivalente para recibir stdout mientras el proceso continúa ejecutándose.

Los eventos llegan como objetos JSON separados por líneas.

Implementa un parser robusto, preferentemente en `bin/streaming.py`. Si la arquitectura existente recomienda otro lugar, justifica la elección.

Distingue como mínimo: `system`, `stream_event`, `assistant`, `result`.

Dentro de `stream_event`, procesa los eventos relevantes de `content_block_start`, `content_block_delta`, `content_block_stop` y los límites de mensajes.

Para recuperar texto incremental, considera exclusivamente eventos cuyo contenido corresponda a un bloque de texto de la conversación principal y cuya delta sea `text_delta`.

No trates como respuesta hablable:

- `thinking_delta`
- `input_json_delta`
- Argumentos de herramientas.
- Resultados de herramientas.
- Mensajes del sistema.
- Metadatos.
- Texto de subagentes.
- Mensajes `assistant` duplicados respecto a los deltas.

No mezcles fragmentos de distintos bloques o mensajes.

El formato puede variar entre versiones; comprueba las estructuras reales antes de implementar el parser.

### Resultado definitivo

El evento final `result` es la fuente autoritativa del resultado completo.

Debe seguir proporcionando a los consumidores:

- Texto completo de la respuesta.
- Estado de ejecución.
- Información necesaria sobre la sesión.
- Errores.
- Información de uso que el sistema ya aproveche.

No construyas la respuesta definitiva mediante la concatenación indiscriminada de todos los fragmentos recibidos, porque pueden existir varios mensajes y llamadas a herramientas.

Conserva la compatibilidad de las funciones que actualmente esperan una respuesta completa.

No dupliques texto en el HUD o en `historial.jsonl`.

## 3. Primer texto y primera frase

Implementa detección de estos eventos:

1. Inicio del subproceso.
2. Primer evento recibido.
3. Primer fragmento de texto válido del asistente principal.
4. Primera frase completa candidata a voz.
5. Inicio real de reproducción de voz.
6. Finalización de reproducción de voz.
7. Recepción del resultado definitivo.
8. Finalización del subproceso.

### Detección de frases

Acumula fragmentos hasta identificar una primera oración completa, con criterios apropiados para español e inglés.

Ejemplo. Fragmentos: «Señor, el planeta más» / « grande del sistema solar» / « es Júpiter.» / « Su diámetro...»

La primera frase hablable será: «Señor, el planeta más grande del sistema solar es Júpiter.»

No la reproduzcas antes de recibir un límite de frase confiable.

Evita cortes incorrectos en: abreviaturas, números decimales, direcciones web, texto Markdown, bloques de código, encabezados, oraciones incompletas.

No consideres «Señor,» una frase completa.

Establece un límite razonable de longitud del buffer para evitar crecimiento descontrolado.

Si no aparece un límite de frase confiable, espera el resultado final y utiliza el comportamiento anterior.

## 4. Seguridad de la voz anticipada

**REQUISITO CRÍTICO: no hablar texto provisional que describa acciones todavía no realizadas.**

Claude puede emitir una explicación antes de llamar a una herramienta y posteriormente modificar su respuesta. Por ejemplo: «He eliminado el archivo, señor.» No debe pronunciarse antes de comprobar que la acción efectivamente terminó y fue autorizada.

Implementa una política conservadora:

### Respuestas de conversación sin herramientas

Permite voz anticipada cuando el sistema haya establecido que la consulta es puramente conversacional y la ejecución esté realmente limitada a no utilizar herramientas.

Puedes implementar una ruta de consulta sin herramientas si la versión instalada permite restringirlas explícitamente, por ejemplo mediante `--tools ""`, conservando los demás controles de seguridad.

Verifica que esa restricción funcione y que no queden herramientas MCP accesibles.

La clasificación debe ser conservadora y determinista; no uses únicamente la afirmación del propio modelo de que no necesitará herramientas.

No conviertas consultas que necesitan archivos, memoria, web o acciones en consultas sin herramientas solamente para acelerar la voz.

### Respuestas que pueden usar herramientas

Conserva streaming y telemetría, pero espera el resultado final antes de hablar si no puedes determinar de forma confiable que el texto es definitivo.

Esto incluye consultas con: lectura o modificación de archivos, acciones sobre aplicaciones, consultas externas mediante herramientas, modificación de pendientes o memoria, solicitudes sujetas a controles de seguridad, cualquier operación con efectos secundarios.

No hables razonamientos intermedios, argumentos de herramientas ni mensajes como si ya se hubiera completado una acción.

### Resultado inconsistente

Si se habló una frase anticipada y el resultado final difiere, registra el incidente técnico sin almacenar contenido privado.

No vuelvas a reproducir automáticamente la respuesta completa.

Si se produce un error posterior, informa de manera clara que la respuesta quedó incompleta, sin afirmar que se completaron acciones.

No intentes ejecutar una herramienta por segunda vez para corregir una diferencia de texto.

La protección del Upgrade 02 prevalece sobre cualquier optimización.

## 5. Reproducción anticipada sin bloquear el streaming

Actualmente el flujo es síncrono: `oido.frase() → procesar() → decir()`, y `decir()` no regresa hasta que `say` termina.

Necesitamos que Claude continúe generando mientras Jarvis pronuncia la primera frase.

Implementa la mínima concurrencia necesaria. Preferencia arquitectónica:

- Mantener un coordinador principal.
- Leer incrementalmente stdout de Claude.
- Cuando haya una frase anticipada autorizada, iniciar el TTS mediante un subproceso supervisado o un mecanismo equivalente.
- Continuar leyendo stdout sin bloquearse esperando a que termine TTS.
- Esperar correctamente a que tanto Claude como la reproducción terminen antes de finalizar la interacción.

No agregues un servicio residente nuevo. No conviertas todo el sistema de voz a múltiples threads. Si se requiere un worker auxiliar, limita su responsabilidad a reproducción o coordinación, justifica su existencia y garantiza su limpieza.

### Integración con decir.py

Reutiliza la implementación actual de síntesis. Conserva: voz Juan de macOS; soporte existente para ElevenLabs, sin activarlo ni contratarlo; `~/.jarvis/voz.lock`; control de interrupción existente por teclado; comportamiento de voz breve para respuestas largas.

No inicies dos reproducciones simultáneas. Una frase anticipada ya reproducida no debe volver a reproducirse cuando llegue el resultado final. Si la voz anticipada no llegó a comenzar, usa el resultado completo al finalizar. Si el TTS falla, conserva el texto final y presenta un error controlado. No provoques una segunda ejecución de Claude.

### stdout y stderr

Evita deadlocks por pipes llenos. Lee y drena correctamente stdout y stderr, con límites de memoria y timeouts. No almacenes indefinidamente eventos de streaming. No utilices ciclos de espera ocupada que consuman CPU de manera innecesaria en el Intel. Los procesos finalizados deben recolectarse correctamente, sin dejar procesos huérfanos.

## 6. Mantener intacto el Upgrade 04

El gestor de conversación continua debe conservar: activación mediante «Jarvis»; seguimiento sin repetir «Jarvis»; timeout de 15 segundos; máximo de cinco turnos; límite de duración de la conversación; contexto personal mediante `--resume`; cierre manual; comandos rápidos; protección contra escuchar su propia voz.

### Condición importante

La ventana FOLLOW_UP no puede comenzar mientras: Claude continúa generando; el TTS continúa reproduciendo; hay fragmentos pendientes de procesar; la interacción anterior no ha finalizado correctamente.

Considera la interacción terminada solo cuando el resultado final haya sido procesado y la reproducción de voz correspondiente haya terminado o sido cancelada de forma controlada.

Si Claude termina antes que la voz, espera a la voz. Si la voz termina antes que Claude, no abras FOLLOW_UP hasta que Claude termine.

Conserva los estados existentes de la máquina de conversación y adapta las transiciones de manera explícita. No implementes escucha activa de órdenes durante SPEAKING.

## 7. Corrección del bug «Jarvis» + pausa + orden

Problema real: JP dice «Jarvis», hace una pausa, suena el tin, JP dice «Dime tres planetas». Actualmente la orden puede llegar incompleta, por ejemplo «Planetas». La causa sospechada es la limpieza de la cola de audio y/o el bloqueo provocado por el tin durante la transición.

**Objetivo:** conservar el inicio de la instrucción aunque JP comience a hablar mientras suena el tin.

### Diagnóstico

Inspecciona en `voz/oido.py` y `voz/jarvis_voz.py`: en qué momento se detecta «Jarvis»; cuándo se vacía la cola de audio; cuándo se reproduce el tin; cuándo comienza la captura de la orden; qué sucede con los frames recibidos durante esa transición; si existen buffers o callbacks que siguen recibiendo audio mientras el hilo principal está ocupado.

No apliques una solución basada únicamente en agregar un `sleep()`.

### Solución propuesta

Introduce una transición segura de detección a captura. Considera utilizar: un pequeño buffer circular de audio previo (pre-roll), aproximadamente 300–500 ms, ajustable mediante pruebas; conservación de los frames recibidos durante la transición; captura activa sin esperar a que termine el tin; un timeout específico para órdenes posteriores a una activación aislada; limpieza selectiva de audio obsoleto, evitando descartar el inicio de voz válido.

No utilices el buffer de manera que termine mezclando audio de conversaciones anteriores. El tin no debe incorporarse a la transcripción como si fuera una palabra de JP. Si el tin no puede reproducirse sin interferir con la captura, prioriza la captura correcta y utiliza temporalmente la indicación visual existente, antes que perder parte de la instrucción.

### Comportamientos obligatorios

- **Caso A:** «Jarvis, abre Spotify». Debe seguir funcionando como antes, sin esperar otra frase.
- **Caso B:** «Jarvis». Pausa breve. «Dime tres planetas». Debe recibirse la frase completa.
- **Caso C:** «Jarvis». Comienza el tin. JP empieza inmediatamente «Abre Spotify». No se debe perder «Abre».
- **Caso D:** «Jarvis» y nada más. Tras un timeout configurable (sugerido 6 s, independiente de los 15 s de seguimiento), vuelve a IDLE sin ejecutar órdenes inventadas.
- **Caso E:** después de «Jarvis» solo ruido. No debe convertirse en una orden.
- **Caso F:** una vez procesada la primera instrucción, FOLLOW_UP funciona exactamente como en el Upgrade 04.
- **Caso G:** la activación y su instrucción no deben producir órdenes duplicadas por reutilización accidental del pre-roll.

No cambies los motores de reconocimiento existentes.

## 8. Telemetría

Amplía el Upgrade 01 sin romper el formato actual. Añade métricas para: `claude_first_event_ms`, `claude_first_text_ms`, `claude_first_sentence_ms`, `tts_start_ms`, `tts_end_ms`, `claude_result_ms`, `response_complete_ms`, `voice_overlap_ms`, `voice_early_start`, `stream_fallback_reason`. Los nombres pueden adaptarse a las convenciones existentes.

Define claramente el punto inicial de cada métrica. Quiero distinguir:

- A. Tiempo desde lanzar Claude hasta el primer texto.
- B. Tiempo desde lanzar Claude hasta comenzar a hablar.
- C. Tiempo desde que JP termina su orden hasta comenzar a escuchar a Jarvis.
- D. Tiempo de ejecución total de Claude.
- E. Tiempo total de interacción.
- F. Tiempo ganado por solapar reproducción y generación, si efectivamente hubo solapamiento.

No confundas primer evento, primer token, primera oración ni primer audio. Registra cuándo se utilizó voz anticipada y cuándo se esperó el resultado final por seguridad. No guardes prompts, respuestas, transcripciones ni audio en la telemetría. Conserva `bin/jv latencia` y sus umbrales actuales para p50 y p90.

## 9. Compatibilidad y fallback

Implementa una opción de configuración para desactivar el streaming y regresar temporalmente a la ruta JSON del Upgrade 04. El mecanismo debe ser un rollback de comportamiento, no un cambio de permisos.

Si `stream-json` falla: evita respuestas duplicadas; evita repetir acciones con efectos secundarios; conserva los timeouts existentes; preserva la sesión de Claude; mantén las restricciones de seguridad; utiliza la ruta anterior únicamente cuando sea seguro reintentar; si no puede determinarse si una acción ya se ejecutó, informa del fallo sin relanzarla.

Si Claude no responde, conserva el fallback de Codex con las restricciones verificadas durante el Upgrade 03. Codex no debe recuperar acceso a `~/.jarvis/`, herramientas, escrituras o red. No permitas que una excepción del parser lleve a ejecutar Codex con privilegios ampliados. Si la respuesta de Codex no admite el mismo streaming, utiliza su salida completa como antes. No implementes streaming de Codex en este upgrade.

## 10. Pruebas automatizadas

Agrega pruebas, preferentemente en `tests/test_streaming.py`, y amplía las pruebas de voz existentes.

### Streaming
- T1. Parser de eventos válidos.
- T2. Ignorar eventos del sistema.
- T3. Ignorar thinking y argumentos de herramientas.
- T4. Ignorar mensajes de subagentes.
- T5. Reconstruir candidatos a frase desde fragmentos divididos.
- T6. Evitar hablar una frase incompleta.
- T7. Manejar abreviaturas, números y signos de puntuación.
- T8. Hablar exactamente una primera frase en una ruta autorizada sin herramientas.
- T9. No hablar anticipadamente en una ruta que puede utilizar herramientas.
- T10. Conservar el resultado final completo del evento `result`.
- T11. No duplicar texto por combinar `assistant` y `stream_event`.
- T12. No reproducir dos veces la misma frase.
- T13. Claude continúa generando mientras se reproduce la voz.
- T14. El proceso no queda bloqueado por stdout/stderr.
- T15. Un JSON incompleto o malformado provoca un fallo controlado.
- T16. Stream terminado sin evento `result` se considera incompleto.
- T17. Un error después de voz anticipada no ejecuta de nuevo herramientas.
- T18. El proceso y sus recursos se cierran correctamente.
- T19. El modo JSON anterior sigue disponible como rollback.
- T20. Las sesiones `--session-id` y `--resume` siguen funcionando.

### Voz y conversación
- T21. La ventana FOLLOW_UP espera tanto a Claude como al TTS.
- T22. Jarvis no se escucha a sí mismo.
- T23. El bloqueo `voz.lock` sigue evitando voces simultáneas.
- T24. Cancelar la voz no deja procesos huérfanos.
- T25. «Jarvis, abre Spotify» funciona en una frase.
- T26. «Jarvis» + pausa + orden conserva el inicio.
- T27. Una orden pronunciada durante el tin no pierde palabras.
- T28. Una activación aislada caduca correctamente.
- T29. El pre-roll no repite audio ni ejecuta órdenes duplicadas.
- T30. La conversación continua conserva los cinco turnos, los 15 segundos y el contexto de Claude.

### Seguridad y regresión
- T31. El guardia PreToolUse sigue funcionando.
- T32. Las operaciones sensibles siguen bloqueadas sin aprobación.
- T33. Las publicaciones prohibidas continúan rechazándose.
- T34. Se mantienen separados los perfiles escolar y personal.
- T35. Codex mantiene su sandbox probado.
- T36. `historial.jsonl` no almacena eventos internos duplicados.
- T37. La telemetría no almacena contenido sensible.
- T38. Ejecutar nuevamente las 149 pruebas previas sin regresiones.

Utiliza mocks y eventos de streaming sintéticos para cubrir casos normales, errores y condiciones de carrera. No necesitas consumir cuota de Claude para cada prueba.

## 11. Prueba de integración real

Una vez aprobadas las pruebas automatizadas, realiza pruebas breves con Claude CLI real para validar el formato de los eventos. No supongas que los mocks garantizan compatibilidad con la versión instalada.

- **Prueba A — Streaming real:** «Jarvis, explícame en dos frases qué es una órbita». Claude genera texto incremental; se detecta la primera frase completa; en una ruta demostrablemente libre de herramientas, Jarvis empieza a pronunciarla sin esperar necesariamente la segunda; después llega el resultado completo; no se duplica la voz. Registra si efectivamente comenzó a hablar antes del evento final.
- **Prueba B — Herramientas:** JP solicita una consulta que necesita una herramienta autorizada. Verifica que el streaming no provoque afirmaciones anticipadas ni salte permisos.
- **Prueba C — Activación con pausa:** «Jarvis». ~1 s. «Dime tres planetas». La instrucción debe llegar completa.
- **Prueba D — Orden durante el tin:** «Jarvis». Al escuchar el tin, inmediatamente «Abre Spotify». Debe ejecutarse completa.
- **Prueba E — Seguimiento:** sin repetir «Jarvis»: «¿Cuál de esos es el más grande?». Debe conservar contexto.
- **Prueba F — Cierre:** «Cierra la conversación». Después «Abre Spotify», sin activación. No debe ejecutarse.
- **Prueba G — Streaming desactivado:** desactiva temporalmente el streaming, comprueba que regresa a la ruta JSON y funciona. Restablece la configuración si sale bien.

Solicita la participación de JP exclusivamente para las pruebas físicas que la automatización no pueda verificar. No reportes una prueba física como aprobada antes de que JP confirme su resultado.

## 12. Benchmark

Referencia del Upgrade 03: respuesta trivial anterior 5.1–11.9 s; con stdin cerrado 2.0–3.9 s; arranque local estimado 0.8–1.4 s. Son tiempos completos, no primer token ni primera frase.

Ahora medir: 1) tiempo hasta primer texto; 2) hasta primera frase; 3) hasta comenzar la voz; 4) hasta resultado final; 5) diferencia de experiencia entre JSON y streaming.

Si el límite de uso lo permite, al menos cinco muestras reales comparables por configuración. Si no, usa las disponibles e identifica la limitación. No hagas benchmark cambiando modelos, permisos o contexto entre variantes. No prometas una mejora antes de medirla.

## 13. Restricciones no negociables

Mac mini Intel 2018, macOS Sequoia, 16 GB RAM. Sin hardware nuevo. Sin servicios de pago adicionales. Claude Pro y ChatGPT Pro actuales. Groq existente. No instalar motores nuevos de IA. No usar `--bare`. No agregar procesos residentes innecesarios. No modificar el sistema de seguridad del Upgrade 02. No modificar el aislamiento de sesiones del Upgrade 03. No romper conversación continua del Upgrade 04. No implementar barge-in. No implementar memoria nueva. No conectar servicios adicionales. No activar ElevenLabs. No realizar acciones destructivas. No publicar en redes. No enviar mensajes reales. No gastar dinero. No cambiar los perfiles de Chrome. No guardar credenciales en la carpeta del proyecto. No modificar archivos ajenos al alcance.

Mantén la arquitectura ligera y evita cambios masivos.

## 14. Reporte de cierre

Entrega: 1) archivos creados o modificados; 2) versión de Claude Code utilizada; 3) estructura de eventos realmente observada; 4) cómo se obtiene el resultado final; 5) cómo detecta Jarvis la primera frase hablable; 6) cómo impide hablar contenido provisional o sensible; 7) cómo se solapan Claude y TTS; 8) cómo se conserva FOLLOW_UP; 9) causa identificada del bug del tin; 10) solución implementada para no perder audio; 11) resultados de pruebas nuevas; 12) resultado de las 149 pruebas anteriores; 13) métricas reales de latencia y voz anticipada; 14) limitaciones abiertas; 15) procedimiento de rollback a JSON y a la captura anterior.

Actualiza `estado_proyecto.md` con el estado real. Realiza un commit únicamente cuando la implementación esté probada, las regresiones estén resueltas y quede claro si falta alguna validación física. Si una prueba de seguridad falla, no habilites la funcionalidad involucrada.

**DETENTE AL TERMINAR ESTE UPGRADE.** No implementes barge-in ni avances al Upgrade 06.

**Prioridad: primera respuesta audible más rápida, captura completa de instrucciones, conservación de contexto y cero regresiones de seguridad.**

---

## Ajustes de Claude (revisor) — obligatorios

Revisados contra el código real (bin/pensar.py, bin/decir.py, voz/jarvis_voz.py, voz/oido.py, voz/conversacion.py, hammerspoon/init.lua, bin/resumen.py).

1. **Respaldo primero.** Antes de tocar nada: commit "Respaldo antes de upgrade 05" incluyendo `hq/index.html` (está modificado). NO agregues `.claude/settings.local.json` a git, ni en este commit ni en los siguientes.

2. **Lo que se habla es la PRIMERA LÍNEA, no "la primera frase" (el diseño no lo considera).** `INSTRUCCION_VOZ` pide que la primera línea (1–2 frases cortas) sea la hablada y el detalle vaya después de una línea en blanco, solo en pantalla; `procesar()` hace `decir(primera_linea(resp))`. Reglas:
   - La voz anticipada NUNCA pasa del primer salto de línea.
   - Frase 1 de la primera línea → se habla en cuanto cierre con un límite confiable.
   - El resto de esa primera línea (si lo hay) se habla en cuanto termine la frase 1 y la línea ya esté cerrada (salto de línea en el stream) o haya llegado `result`. Nunca dos voces a la vez: el segundo pedazo arranca solo cuando el primero terminó.
   - Al llegar `result`: `limpiar_para_voz(primera_linea(result))` debe empezar con lo ya hablado (normalizando espacios). Si no coincide → incidente en telemetría (sin texto) y no se habla nada más. Si la primera línea completa ya sonó, al final no suena nada.

3. **Voz anticipada solo en el ciclo de voz.** `pensar()` conserva su firma y sigue regresando `(resp, cerebro)`; agrégale un parámetro opcional (p. ej. un callback para el texto hablable) que solo usa `procesar()` de `voz/jarvis_voz.py`. `bin/resumen.py` (origen auto) y `pensar.py --hablar` (⌃⌥Espacio en `hammerspoon/init.lua`) pueden usar stream por dentro, pero hablan como hoy, con el resultado completo. `_guardar()` una sola vez, con el texto de `result`.

4. **Ruta sin herramientas: dos candados.**
   - a) **Clasificador determinista** (función pura en Python, con pruebas), solo para voz. Entra únicamente si la frase es de conocimiento general (qué es, quién fue, explícame, cuéntame, por qué, cómo funciona, cuánto es, dime + número…, traduce) Y no trae ninguna palabra de acción, datos personales o tiempo actual (abre, pon, manda, envía, borra, elimina, apunta, anota, recuérdame, busca, investiga, guarda, crea, cambia, mueve, archivo, carpeta, mi/mis/me/tengo, pendiente, tarea, entrega, escuela, classroom, correo, calendario, dinero, meta, modo, spotify, rutina, hoy, mañana, ahorita, ahora, actual, último, reciente, noticias, precio, clima…). En FOLLOW_UP solo entra si el turno anterior también fue sin herramientas. En duda → ruta normal.
   - b) **Verificación en tiempo real:** la ruta sin herramientas usa una copia de `ASISTENTE_CLAUDE` donde se REEMPLAZA el valor de `--tools` por `""` (sin duplicar la bandera) y se conservan `--restricted`, `--strict-mcp-config`, `--permission-mode dontAsk` y `--settings` del guardia. La voz anticipada solo se permite si el evento `system`/`init` del stream reporta lista de herramientas vacía y cero servidores MCP. Si trae cualquier herramienta, o aparece un `tool_use` en el stream → sin voz anticipada en ese turno + incidente en telemetría.
   - Comprueba con una llamada real que `--resume` de la sesión personal funciona aunque cambie `--tools` entre turnos.

5. **Concurrencia sin threads.** La voz anticipada = `Popen` de `bin/decir.py` como proceso hijo (mismo intérprete con el que hoy corre): reutiliza `voz.lock`, Juan, `limpiar_para_voz`, ElevenLabs apagado y el callar por `pkill`. Pásale `JARVIS_REQ_ID` en el entorno para que `tm.desde_entorno(con_total=False)` registre la voz en la misma petición (revisa cómo `telemetria.py` propaga el ID; no adivines). El coordinador usa `selectors`/`select` sobre stdout de Claude con timeout de 0.1–0.2 s y `poll()` del hijo de voz. stderr de Claude va a un archivo temporal (no PIPE) y al final se leen solo los últimos 300 caracteres, como hoy. Timeout total 300 s igual que hoy; si vence: `kill` + `wait`. En `finally`, cualquier hijo vivo → `terminate` + `wait`.

6. **Máquina de conversación.** `conv.hablar()` en cuanto arranca la voz anticipada (PROCESSING → SPEAKING mientras Claude sigue). `respuesta_terminada()` solo cuando `result` ya se procesó Y no hay hijo de voz vivo. Si el hijo de voz sale con error y no se pidió callar → mismo comportamiento que el `RuntimeError` actual de `_hablar()` (no se abre el micrófono). Prueba para esto.

7. **Callar (⌃⌥.) durante la voz anticipada.** `pkill` mata el `say` del hijo; el coordinador ve `~/.jarvis/cerrar_conversacion`, no habla el resto, NO mata a Claude (deja que termine para que sesión e historial queden consistentes), guarda historial y cierra la conversación.

8. **Fallo después de hablar.** Si ya sonó algo y luego Claude falla o el stream termina sin `result`: no Codex, no reintentar Claude; di una frase corta tipo "Señor, la respuesta quedó incompleta." (si no se pidió callar) y `sesiones.olvidar()` como hoy. Si no había sonado nada: comportamiento actual (Codex aislado de respaldo). Nunca se relanza Claude si en el stream apareció cualquier `tool_use`. El reintento existente por "no conversation found" se queda solo para ese error.

9. **Bug del tin — causa real (está en `voz/jarvis_voz.py`, no en `oido.py`).** En `escuchar_una()`, cuando JP dice solo «Jarvis», `frase()` cierra tras 0.7 s de silencio; luego se transcribe ese audio con Whisper base Y otra vez con Groq (~1–3 s en el Intel). Mientras, el micrófono sigue llenando la cola con lo que JP ya empezó a decir. Después `pedir_comando()` hace `oido.vaciar()` y lo tira, y el tin suena tarde. Arreglo:
   - a) Si el borrador de Whisper base trae «Jarvis» sin orden y el audio es corto (≤ ~1.5 s, ajustable), NO mandar ese audio a Groq: directo a pedir la orden.
   - b) `pedir_comando()` con una opción para NO vaciar la cola en ese camino. Lo que hay en la cola es audio posterior a «Jarvis», contiguo y sin ninguna voz de Jarvis en medio: no repite ni duplica. En ⌃⌥J (IDLE y FOLLOW_UP) se sigue vaciando como hoy.
   - c) El tin sigue con `Popen` sin esperar y la captura empieza de inmediato. No hace falta un buffer circular nuevo: la cola ya guarda todo y `frase()` ya tiene 400 ms de previo.
   - d) `espera_inicio` de la orden: hoy 10 s → `timeout_orden_seg: 6` en `config.json`.
   - e) Si en la prueba el tin entra a la transcripción o dispara la captura sin voz, quita el tin en ese camino y deja solo el HUD "escuchando".
   - f) Pruebas T25–T29 con un `Oido` simulado y frames sintéticos, incluyendo "la orden empezó durante la transcripción".

10. **Config (en `config.json`, leída en cada petición como `conversacion_continua`):** `"claude_streaming": true`, `"voz_anticipada": true`, `"timeout_orden_seg": 6`. `claude_streaming: false` = ruta JSON exacta del 04. `voz_anticipada: false` = stream con telemetría pero habla como antes. Ninguna cambia permisos.

11. **Telemetría.** Reutiliza `tm.desglose_claude` con `duration_ms`/`duration_api_ms` del evento `result`. Las métricas nuevas A, B, D cuentan desde el lanzamiento de `claude` (t0 en `_claude_una`); C desde `tm.fin_frase`. `voice_early_start` booleano; `stream_fallback_reason` solo de una lista fija (con_tools, sin_frase, init_con_tools, tool_use_inesperado, desactivado, error…), nunca texto. `jv latencia` agrega % de turnos con voz anticipada y los nuevos p50/p90.

12. **Cuota real.** Máximo ~20 `claude -p` reales en todo el upgrade. Benchmark: 5 JSON vs 5 stream con la MISMA pregunta trivial y la MISMA ruta sin herramientas (así solo cambia el streaming); aparte 2–3 muestras de la ruta normal con herramientas. Ojo: en respuestas de 1–2 frases la ganancia puede ser chica (la mayor parte es arranque y primer token); repórtalo tal cual.

13. **Prueba física.** Cuando las automáticas pasen y ya hiciste el commit: reinicia la voz (`open ~/Documents/Jarvis/Jarvis.command`), confirma que arrancó y dale a JP en UN bloque numerado y corto las frases de A, B («Jarvis, ¿qué tengo pendiente?»), C, D, E, F y G (tú cambias la config para G y la regresas). Verifica tú cada paso con la salida de la voz y la telemetría; no dependas de que JP te lo cuente.

14. **Al terminar:** commit "Upgrade 05: stream-json, voz anticipada y captura tras «Jarvis»". Actualiza `memoria/estado_proyecto.md` ("Ya funciona", "Paso actual", fecha; roadmap 2 ✅; quita de "Límites abiertos" el bug del tin si quedó resuelto; siguiente: barge-in) y `modulos/voz.md`. Reporte CORTO con el hash para rollback. Si la prueba física quedó pendiente, dilo claro en "Paso actual".
