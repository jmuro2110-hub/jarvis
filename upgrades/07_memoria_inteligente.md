# JARVIS — Upgrade 07: Memoria que aprende (permanente + recuerdos relevantes)
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-27)

Eres el ingeniero principal de JARVIS, ubicado en `~/Documents/Jarvis`.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

**OBJETIVO:** memoria permanente y recuperación selectiva: conservar información útil que JP autorice, recuperarla en conversaciones futuras y no meter contexto irrelevante. Pequeño, medible y reversible.

Alcance: 1) guardar recuerdos cuando JP lo pida explícitamente; 2) recuperar recuerdos relevantes después; 3) separar memoria reciente, permanente y contexto de desarrollo; 4) consultar y corregir recuerdos sin alterar archivos existentes. NO aprendizaje silencioso ni resúmenes periódicos. Presupuesto adicional: $0 MXN.

Claude ya conserva el contexto reciente con `--resume`; no se reconstruye. Se agrega una capa de recuerdos duraderos que sobreviven al vencimiento de las sesiones. Mejor cinco cosas correctas que cincuenta conclusiones equivocadas.

## 1. Inspección obligatoria

Lee `CLAUDE.md`, `estado_proyecto.md`, `modulos/seguridad.md` y módulos relacionados. `git status`. Inspecciona `bin/pensar.py`, `bin/jv`, `voz/jarvis_voz.py`, `voz/conversacion.py`, `bin/politica.py`, `bin/guardia.py`, `bin/telemetria.py`, la entrada de texto de Hammerspoon, `memoria/jp.md`, `memoria/bitacora.md`, `memoria/pendientes.md` y la estructura de `historial.jsonl`. Revisa las sesiones del 03, dónde se arma el prompt del modo asistente y las 275 pruebas. No edites archivos innecesarios, no sobrescribas recuerdos, no reconstruyas las sesiones.

## 2. Modelo de memoria

**A. Reciente:** igual que hoy (sesión personal `--session-id`/`--resume`, vencimiento actual, `historial.jsonl`, Codex restringido). No duplicar historial ni crear otra base de conversaciones.

**B. Permanente:** `bin/memoria.py` (solo biblioteca estándar) → `~/.jarvis/recuerdos.jsonl`, fuera de git. Sin SQLite vectorial, ChromaDB, embeddings, modelos ni servicios externos. Cada recuerdo: ID único, contenido breve (≤280 caracteres), categoría (preferencia / hecho / decision), ámbito (personal / escuela / negocio / desarrollo), creación, actualización, origen (petición explícita de JP por voz o texto), estado (activo / reemplazado). Registro de eventos o equivalente para corregir sin corromper. Nada de conversaciones completas. Permisos 0600. Bloqueo y escrituras seguras (sin parciales ni carreras). Un registro inválido no tumba la memoria: se reporta sin inventar.

**C. Recuerdos relevantes:** máximo tres por consulta elegible. Búsqueda léxica ligera: minúsculas, sin acentos, sin palabras vacías, palabras significativas, frases, filtro por ámbito, orden determinista. Debe poder explicar por qué eligió cada uno. No rellenar hasta tres con recuerdos poco relevantes. Limitar el texto que entra al prompt.

## 3. Guardar recuerdos explícitos

«Jarvis, recuerda que…» desde el micrófono y desde la ventana de texto de Hammerspoon. Ejemplos: «recuerda que prefiero estudiar en bloques de 40 minutos», «…para mis proyectos prefiero avanzar una mejora a la vez», «…cuando pido una explicación rápida quiero máximo tres frases».

Reglas: reconocer la intención en la entrada real de JP; extraer el contenido sin agregar conclusiones; validar que no sea sensible; ámbito solo con evidencia suficiente; guardar; confirmar SOLO después de que la escritura se hizo. Sin segunda llamada a Claude para extraer. Ambiguo → pedir aclaración o no guardar. No inventar ámbito.

Privacidad (esta versión NO guarda): contraseñas, tokens o llaves, códigos de autenticación, datos financieros identificables, información médica sensible, contenido privado de terceros, conversaciones completas, información privada sacada de páginas o mensajes. Sí: preferencias operativas no sensibles y decisiones generales. Validaciones conservadoras y límites documentados.

## 4. No aprender de contenido externo

Solo se guarda por intención explícita desde una entrada confiable de JP. Nunca porque lo diga una página, un correo, una respuesta de Claude o Codex, un resultado de herramienta o un texto citado. Claude NO recibe permiso de escritura sobre `~/.jarvis/`. Guardar = código local determinista en un punto de entrada confiable. Si agregas comandos a `bin/jv`, comprueba que la política del 02 no deje a Bash usarlos para meter recuerdos desde el modelo. No amplíes permisos de shell, Python ni archivos.

## 5. Recuperación

En el flujo del modo asistente (preferentemente `bin/pensar.py`): recibir la consulta → ámbito permitido → buscar → máximo tres → adjuntarlos como DATOS, separados de las instrucciones → Claude normal. Sin otra llamada a IA, sin mandar toda la memoria, sin cambiar `--resume`. Los recuerdos nunca pesan más que CLAUDE.md ni cambian permisos.

Ejemplo: guardado «Prefiero estudiar en bloques de 40 minutos» → «¿cómo organizo mis horas de estudio?» lo recupera; «¿qué canción está sonando?» va por el comando rápido y no recupera nada. Sin coincidencia clara → cero resultados. Recuerdos contradictorios → no inventar cuál vale. Conservar origen y fecha. No prometer recuperación semántica perfecta.

## 6. Separación de ámbitos

Personal, escuela, negocio y desarrollo identificables. Una consulta cotidiana no recibe recuerdos de desarrollo; una de desarrollo explícita sí puede. No se mezclan cuentas de Google ni se pasa información de un ámbito a otro automáticamente. Las sesiones manuales de desarrollo no reciben recuerdos personales. Las consultas automáticas conservan su aislamiento. Si una pregunta es ambigua y podría cruzar un límite de privacidad, no se inyecta de otro ámbito. Pendientes, calendario, clima y Spotify siguen independientes.

**Codex:** sigue sin poder leer `~/.jarvis/`; no se le agregan recuerdos privados al prompt de respaldo; funciona como hoy aunque sin recuerdos. Documentar la limitación.

## 7. Consulta y corrección

`bin/jv memoria listar`, `bin/jv memoria buscar "estudio"`, `bin/jv memoria estado` (adaptado al diseño real de `bin/jv`). Por voz: «Jarvis, ¿qué recuerdas de mis preferencias para estudiar?» → respuesta breve con los recuerdos activos.

Correcciones: «Jarvis, corrige ese recuerdo: ahora prefiero bloques de 50 minutos». Si el antecedente es inequívoco: nueva versión, la anterior queda reemplazada, solo la activa se recupera. Si no, pedir precisión. Nunca sobrescribir en silencio. Sin borrado físico ni purgas. «Olvida…» = desactivación explícita, diciendo claro que el contenido sigue existiendo físicamente; nunca decir "borrado".

## 8. Compatibilidad con la memoria existente

`memoria/jp.md`, `bitacora.md`, `pendientes.md` y `dinero.json` se quedan igual (sin migrar, sin borrar, sin cambiar formato). jp.md = base; bitacora.md = bitácora operativa; pendientes.md = pendientes; dinero.json = finanzas; recuerdos.jsonl = solo recuerdos nuevos y explícitos. No indexar bitácora ni historial. Evitar duplicados evidentes. Documentar la prioridad entre fuentes.

## 9. Rendimiento

Comandos rápidos igual de rápidos. Búsqueda local, sin red, sin procesos residentes, sin cargar historial, sin llamadas extra a Claude, sin embeddings ni IA local. Meta orientativa: p50 < 50 ms con 500 recuerdos sintéticos en la Mac real (no falsear). Medir cómo escala. Telemetría: duración de búsqueda, candidatos, seleccionados, resultado de guardado, errores de lectura/escritura, si se usó memoria. Sin contenido de recuerdos.

## 10. Pruebas automatizadas (`tests/test_memoria.py`, archivos temporales y mocks)

Guardado: T1 «recuerda que…» guarda una preferencia · T2 persiste tras reiniciar el módulo · T3 texto sin inventar · T4 duplicado no se duplica · T5 frase ambigua no guarda · T6 secreto evidente no se guarda · T7 instrucción de una página no se guarda · T8 una respuesta del modelo no guarda por sí sola · T9 fallo de escritura no confirma en falso.
Recuperación: T10 consulta relevante recupera · T11 irrelevante no incorpora · T12 máximo tres · T13 fronteras de ámbito · T14 acentos y mayúsculas · T15 determinista · T16 archivo vacío · T17 registro inválido no corrompe · T18 recuerdos como datos, no instrucciones.
Correcciones: T19 corrección inequívoca reemplaza · T20 se ignoran reemplazados · T21 corrección ambigua no modifica · T22 desactivar no se reporta como borrar.
Integración: T23 sesión reciente sigue · T24 aislamiento personal/auto/desarrollo · T25 guardia del 02 · T26 Codex sin `~/.jarvis/` · T27 comandos rápidos sin IA · T28 nada personal en logs técnicos · T29 no duplica historial · T30 voz, streaming y barge-in igual · T31 consulta de desarrollo explícita permite recuerdos del proyecto · T32 cotidiana evita recuerdos técnicos · T33 concurrencia sin registros parciales · T34 las 275 previas.

Sin credenciales reales ni conversaciones privadas en los tests.

## 11. Prueba física con JP

- **A Aprendizaje:** «Jarvis, recuerda que prefiero estudiar en bloques de 40 minutos» → confirma que se guardó.
- **B Recuperación:** «Jarvis, ¿cómo me recomiendas organizar mi estudio?» → usa los 40 minutos.
- **C Persistencia:** reiniciar Jarvis, conversación nueva sin depender de la sesión anterior → «Jarvis, ¿cuánto deberían durar mis bloques de estudio?» → 40 minutos desde memoria permanente.
- **D Corrección:** «Jarvis, corrige ese recuerdo: ahora prefiero 50 minutos» y volver a preguntar → 50, no 40.
- **E Irrelevancia:** «Jarvis, ¿qué hora es?» → comando rápido, sin recuerdos.
- **F Separación:** «Jarvis, ¿qué recuerdas sobre estudiar?» y luego «¿Qué recuerdas sobre el desarrollo de Jarvis?» → cada una con su ámbito.
- **G Regresión:** reiniciar y comprobar una sola instancia, streaming, barge-in, conversación continua, sesiones separadas y seguridad.

No declarar aprobadas las físicas sin los resultados reales de JP.

## 12. Rollback

`memoria_inteligente: true`. En false: no guarda ni recupera recuerdos nuevos, Claude como antes, archivos intactos, no borra `recuerdos.jsonl`, historial y sesiones igual, seguridad intacta. Documentar cómo apagarlo sin revertir los demás upgrades. Ninguna opción salta los controles de privacidad.

## 13. Restricciones obligatorias

Mac mini Intel 2018, Sequoia, 16 GB. $0. Sin APIs nuevas, embeddings, base vectorial, modelos locales pesados ni procesos permanentes. No tocar permisos de Claude Code manual. No debilitar el 02, no romper 03, 04, 05 ni 06. Escuela y personal separados. No publicar, no Snapchat, no mandar mensajes, no borrar archivos, no gastar, no credenciales en el repo. No modificar innecesariamente `hq/index.html`. No tocar en este upgrade el arranque en frío de Whisper ni la latencia del barge-in. Una mejora a la vez.

## 14. Reporte de cierre

Archivos; arquitectura; formato real; detección de la intención; validación del origen confiable; selección de recuerdos; separación de ámbitos; correcciones; cómo impide que Claude o Codex amplíen permisos; pruebas nuevas; las 275 previas; pruebas físicas; p50/p90 de recuperación; almacenamiento; limitaciones; rollback; hash del commit. Actualiza `estado_proyecto.md`. Commit tras las automáticas; dejar claro si falta la física.

**DETENTE AL TERMINAR EL UPGRADE 07.** Nada de aprendizaje implícito, embeddings ni memoria automática de conversaciones.

**Prioridad: recordar correctamente, recuperar selectivamente, preservar privacidad y cero regresiones.**

---

## Ajustes de Claude (revisor) — obligatorios

Revisados contra el código real (`bin/pensar.py`, `bin/guardia.py`, `bin/jv`, `bin/sesiones.py`, `voz/jarvis_voz.py`, `hammerspoon/init.lua`, `memoria/`).

1. **Respaldo primero.** Commit "Respaldo antes de upgrade 07" incluyendo `hq/index.html`. NO agregues `.claude/settings.local.json` a git, ni ahora ni después.

2. **Dónde se intercepta (las dos entradas confiables, antes de Claude).** Una función pura `memoria.intencion(texto)` → `guardar` / `corregir` / `olvidar` / `consultar` / `None`, llamada en:
   - Voz: dentro de `clasificar_rapido()` (así cubre IDLE, FOLLOW_UP y la orden nueva del barge-in), después de callar/Spotify/volumen/hora y antes de abrir apps.
   - Texto: ⌃⌥Espacio llama `jv pensar "<texto>" --hablar` → el `__main__` de `bin/pensar.py`, antes de `pensar()`. Con `--hablar`, la confirmación se dice con `decir()` como hoy.
   - NUNCA dentro de `pensar()`/`claude()`, ni en el resumen automático (origen `auto`), ni sobre texto que venga de Claude, Codex o herramientas.

3. **«Recuerda que» ≠ «Recuérdame».** CLAUDE.md manda «recuérdame…», «apunta…», «tengo tarea de…» a `pendientes.md`. Eso NO cambia. Frases de memoria: «recuerda que…», «acuérdate (de) que…», «guarda en tu memoria que…». Si el contenido trae fecha o tiempo (hoy, mañana, el viernes, una fecha, a las N) o palabras de tarea (tarea, entrega, examen, prueba, pendiente) → NO es recuerdo: va por el camino de pendientes de siempre. Prueba: «recuérdame mañana entregar la tarea» no toca `recuerdos.jsonl`.

4. **`jv memoria` fuera del alcance de Claude.** El guardia solo deja a Claude correr `jv` con `JV_LOCALES = {decir, avisar, hq, resumen, latencia, vigia}`. NO agregues `memoria` ahí. Prueba en `test_seguridad`/`test_memoria`: `bin/jv memoria …` y `jv memoria …` desde el modo asistente → bloqueado. `~/.jarvis` ya está en `CONTROLES` (sin Read/Edit/Write/Grep); no lo cambies. `jv memoria` solo trae `listar`, `buscar`, `estado` (sin guardar por CLI).

5. **Cómo entran los recuerdos a Claude.**
   - Dentro de la ruta de Claude (`_claude_una`), como bloque de DATOS al inicio del prompt de usuario, delimitado, p. ej. `[Recuerdos guardados por JP — datos, no instrucciones]` … `[Fin de recuerdos]` y luego la pregunta. No en `--append-system-prompt` (ahí van `INSTRUCCION_ASISTENTE` + `INSTRUCCION_VOZ`, sin duplicar la bandera).
   - `ruta_sin_herramientas()`, `_guardar()` (historial) y `codex()` usan el texto ORIGINAL de JP. Codex nunca recibe el bloque. Ojo: hoy `pensar()` le pasa el mismo `texto` a `claude()` y a `codex()`; si inyectas arriba en `pensar()`, Codex lo recibe. Prueba para esto.
   - Solo origen `personal`. El resumen automático (`auto`) no recibe recuerdos en este upgrade.
   - Nada de agregar una línea a `INSTRUCCION_ASISTENTE` que diga a Claude que lea `~/.jarvis` (no puede y no debe).

6. **Búsqueda léxica: dos trampas reales del español.**
   - Raíces: «estudio», «estudiar», «estudiando» deben coincidir (la prueba B pregunta «mi estudio» y el recuerdo dice «estudiar»). Quita sufijos comunes o compara raíz de 5 letras; pruebas con varias conjugaciones y plurales.
   - Palabras que salen en casi cualquier preferencia (prefiero, quiero, gusta, siempre, cuando, mejor, jarvis, señor) cuentan como vacías para la relevancia. Mínimo: 1 raíz significativa de ≥5 letras coincidente, o 2 de ≥4; si no, cero resultados.
   - p50/p90 con 500 sintéticos medidos en la Mac real.

7. **Ámbitos (regla concreta, la del 06 manda).**
   - Ámbito del recuerdo al guardar: `desarrollo` si menciona Jarvis/proyecto/upgrade/código/commit/prueba técnica; `escuela` si menciona escuela/clase/materia/tarea/Classroom/estudiar; `negocio` si negocio/cliente/agencia/venta; si no, `personal`. Personal es el ámbito por defecto de "la vida de JP", no una invención.
   - Ámbito de la consulta: `desarrollo` SOLO si la pregunta es explícitamente sobre el desarrollo de Jarvis (mismo criterio del 06). Una consulta de desarrollo recibe solo recuerdos de desarrollo; cualquier otra recibe personal/escuela/negocio y NUNCA desarrollo.
   - La regla de "dos mundos" es de cuentas de Google, no de preferencias de JP: «prefiero estudiar en bloques de 40 minutos» sí puede llegarle a una pregunta escolar.

8. **Corrección: que el recuerdo corregido se siga encontrando.**
   - «ese recuerdo» = el último recuerdo guardado, corregido o usado en la conversación actual (guardado en memoria del proceso, en `conv`, nunca en disco). Si no hay conversación, coincidencia léxica con UN solo activo y margen claro sobre el segundo. Si no, no cambia nada y dice cuáles candidatos hay.
   - Trampa: la versión nueva «ahora prefiero 50 minutos» ya no contiene «estudiar» ni «bloques», y la prueba D no la encontraría. La nueva versión guarda su texto (sin el «ahora») Y las palabras de búsqueda de la anterior. Al prompt entra así: `prefiero 50 minutos (actualiza: «prefiero estudiar en bloques de 40 minutos»; vale solo la nueva)`.
   - Prueba: tras corregir, «¿cuánto deben durar mis bloques de estudio?» recupera SOLO la versión de 50.

9. **Respuestas locales (sin Claude, voz corta).**
   - Guardar: «Registrado, señor: <contenido>.» solo después de escribir con `fsync`. Si falla: «No pude guardarlo, señor.»
   - Rechazo por privacidad: «Eso no lo guardo, señor: parece <contraseña/dato sensible>.»
   - Consultar («¿qué recuerdas de/sobre X?»): hasta 3 recuerdos del ámbito correcto; si no hay, «No tengo nada guardado sobre eso, señor.» Sin Claude.
   - Olvidar: «Listo, señor, ya no lo uso. Sigue en el archivo, desactivado.»
   - `conv.previo_sin_herramientas = False` tras cualquiera de estos.

10. **`bitacora.md` no se toca.** Hoy Claude (modo asistente) puede escribir en `bitacora.md` (está en `ANOTABLES`). Se queda así. Con `memoria_inteligente: true`, «recuerda que…» ya no llega a Claude; con false, vuelve al comportamiento de hoy.

11. **Config:** solo `"memoria_inteligente": true`, leída por petición como las demás.

12. **Pruebas extra** (además de T1–T34): T35 «recuérdame…» con fecha no guarda recuerdo · T36 `jv memoria` bloqueado desde el modo asistente · T37 Codex nunca recibe el bloque de recuerdos · T38 historial guarda el texto original sin el bloque · T39 raíces (estudio/estudiar) · T40 corrección encontrable por las palabras de la anterior · T41 entrada de texto (`pensar.py --hablar`) guarda y confirma igual que la voz · T42 el resumen automático no recibe recuerdos · T43 la orden nueva del barge-in («Jarvis, no, mejor recuerda que…») guarda bien.

13. **Cuota real:** máximo ~10 `claude -p` reales en todo el upgrade.

14. **Prueba física (como en el 05 y 06).** Tras las automáticas y el commit: reinicia la voz (`open ~/Documents/Jarvis/Jarvis.command`), confirma una sola instancia y dale a JP en UN bloque numerado y corto las frases de A–G.
    - **C de verdad:** reiniciar Jarvis NO crea sesión nueva (`sesiones.json` dura 30 min). Antes de C, tú haces `sesiones.olvidar("personal")` (controlado, sin borrar historial) para que la respuesta salga de `recuerdos.jsonl` y no de `--resume`. Confírmalo en la telemetría (sesión nueva + memoria usada).
    - Al final, tú desactivas el recuerdo de prueba de 40/50 minutos si JP no quiere conservarlo (pregúntale).
    - Verifica cada paso con la salida y la telemetría; no dependas de que JP te lo cuente.

15. **Al terminar:** commit "Upgrade 07: memoria permanente y recuerdos relevantes". Actualiza `memoria/estado_proyecto.md` ("Ya funciona", "Paso actual", fecha, roadmap 3 ✅ si pasó, límites abiertos) y un módulo nuevo `modulos/memoria.md` (con la tabla de prioridad de fuentes) agregado a la tabla de módulos de CLAUDE.md (solo esa fila). Reporte CORTO con el hash para rollback. Si la física quedó pendiente, dilo claro en "Paso actual".
