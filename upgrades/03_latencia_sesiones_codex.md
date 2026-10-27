# JARVIS — Upgrade 03: Latencia + sesiones aisladas + privacidad de Codex
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-24)

Eres el ingeniero principal del proyecto JARVIS, ubicado en ~/Documents/Jarvis.

OBJETIVO: Reducir la latencia del cerebro sin perder inteligencia, memoria ni seguridad, separar completamente las sesiones del asistente de las de desarrollo y evitar que el fallback Codex pueda leer ~/.jarvis/.

Trabaja sobre la arquitectura existente. No reconstruyas Jarvis.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

## 1. Inspección inicial
Antes de cambiar código:
- Lee CLAUDE.md, memoria/estado_proyecto.md y modulos/seguridad.md.
- Ejecuta git status.
- Inspecciona bin/pensar.py, bin/telemetria.py, bin/politica.py, bin/guardia.py, seguridad/claude_asistente.json, bin/jv y los puntos de entrada de voz, HUD y agenda (voz/jarvis_voz.py, hammerspoon/init.lua, bin/resumen.py).
- Revisa las 43 pruebas existentes.
- Comprueba las versiones y opciones disponibles mediante `claude --help`, `codex --version`, `codex exec --help` y la documentación correspondiente.
- Identifica la configuración efectiva de seguridad de Claude y Codex.
- No des por hecho que una opción documentada existe en las versiones instaladas.
- Conserva los commits 82d8143 y d58a2ad. No sobrescribas trabajo previo.

## 2. Diagnóstico y corrección de stdin
Se detectó una llamada real a `claude -p` que tardó 13.45 s en responder «Recibido, señor», y el mensaje `no stdin data received in 3s`.

Hipótesis: Claude espera innecesariamente datos de stdin cuando se invoca desde un subproceso no interactivo. (Revisión: en bin/pensar.py, `claude()` llama a `subprocess.run` SIN `stdin=`, así que hereda el stdin del padre; `codex()` ya usa `stdin=subprocess.DEVNULL`.)

Compara de forma controlada:
- A. Comportamiento actual.
- B. stdin cerrado explícitamente con `subprocess.DEVNULL`.
- C. Otra alternativa documentada, solo si B no funciona.

Requisitos: que Claude no espere datos que nunca llegarán; no introducir otra espera por pipes abiertos; no romper la captura de stdout/stderr; no afectar timeouts; no perder herramientas; no cambiar respuestas del modelo; no tocar autenticación; no introducir facturación por API. El prompt se sigue pasando como argumento (mecanismo actual).

Compara con pruebas reproducibles y registra cuál usaste. Si no puedes demostrar que los 3 s se eliminaron, repórtalo; no supongas que funcionó solo porque cerraste stdin.

## 3. Separación de sesiones de Claude
Hoy el asistente usa `--continue` si la última plática fue hace menos de 30 min. Problema: puede retomar la conversación más reciente del proyecto, incluida una sesión interactiva de desarrollo.

Implementa sesiones identificadas explícitamente (`--session-id`, `--resume`, `--output-format json`, según lo que soporte la versión instalada).

- **Sesión personal:** voz, ventana de texto de Hammerspoon y consultas personales. Voz y texto comparten sesión mientras esté vigente.
- **Sesión automática:** resumen matutino y consultas automáticas que necesiten el cerebro. No contamina la personal ni recupera sesiones de desarrollo.
- **Sesión de desarrollo:** totalmente independiente. Ninguna consulta de voz o HUD la recupera.

Persistencia: metadatos mínimos en `~/.jarvis/sesiones.json` (solo IDs, origen y marcas de tiempo), permisos 600. Sin tokens ni credenciales.

Comportamiento:
1. Sesión nueva → UUID válido con la opción compatible de Claude.
2. Sesión vigente → `--resume` con el ID exacto.
3. Límite de 30 min de inactividad (se conserva).
4. Pasados 30 min → nueva sesión personal.
5. Sesión inexistente o corrupta → crear otra sesión del asistente, NUNCA recuperar la última sesión global.
6. Dos consultas simultáneas no deben reutilizar ni actualizar mal el mismo ID (serializar o equivalente seguro).
7. Una consulta de desarrollo nunca aparece como contexto de una personal.
8. La política restringida del Upgrade 02 se aplica en cada ejecución, también al reanudar.

No borres historial existente. Mantén ~/.jarvis/historial.jsonl y el contexto necesario para el fallback a Codex, sin que Codex lo lea directamente.

## 4. Aislamiento de lectura para Codex (CRÍTICO)
Hoy Codex está en sandbox de solo lectura, pero puede LEER cualquier archivo. Hay que impedir que el fallback automático lea `~/.jarvis/` (secretos.env, historial.jsonl, seguridad.jsonl, metricas_latencia.jsonl, sesiones y cualquier archivo futuro ahí).

Investiga el mecanismo oficial (perfiles de permisos de Codex: https://learn.chatgpt.com/docs/permissions). Perfil específico del asistente que:
- Permita leer solo lo necesario (mínimo privilegio, no "todo menos un directorio").
- Deniegue recursivamente ~/.jarvis/.
- Mantenga prohibidas las escrituras.
- Mantenga bloqueada la red de comandos locales.
- No habilite MCP, navegador, Computer Use ni herramientas extra.
- No permita aprobaciones automáticas para ampliar privilegios.

IMPORTANTE: no combines perfiles modernos con `--sandbox read-only` suponiendo que se suman. Determina cuál se aplica realmente.

No cambies permisos globales de las sesiones manuales de desarrollo. No copies, muevas ni expongas credenciales de Codex. Limpia del entorno del subproceso las variables que no necesite (sobre todo llaves y tokens de otros proveedores), sin registrar sus valores.

### Verificación real obligatoria
Hay un reporte público (https://github.com/openai/codex/issues/40555) donde, en Mac Intel, un perfil aparentemente correcto no bloqueaba lecturas reales. No basta con ver una regla deny en la config.

Prueba acceso efectivo por la ruta real de `codex exec`, con archivos canario de contenido inventado:
- A. Codex puede consultar información inocua autorizada.
- B. No puede leer el canario dentro de ~/.jarvis/.
- C. Tampoco por rutas relativas, enlaces simbólicos o equivalentes.
- D. No puede escribir archivos.
- E. Sus comandos locales no tienen red.
- F. La denegación viene del sandbox/sistema operativo, no de que el modelo obedeció una instrucción.

Compara el comando de diagnóstico del sandbox con `codex exec` real; el éxito del primero no prueba el segundo. No imprimas ni envíes contenido de archivos privados.

### Si no es seguro
Si la versión no soporta denegaciones verificables o falla la prueba real: desactiva temporalmente el fallback automático a Codex; cuando Claude no esté disponible, Jarvis dice que el respaldo está deshabilitado por seguridad. No lo ejecutes inseguro. No desinstales Codex CLI (JP lo usa manualmente). Documenta exactamente por qué.

## 5. Instrumentación adicional
Amplía bin/telemetria.py y `bin/jv latencia` solo donde tenga sentido. Si son observables: preparación del comando, creación del proceso → primer evento observable, primer texto (si el formato lo permite), fin de respuesta, duración del subproceso, ruta (sesión nueva o reanudada), comparación antes/después.

No confundas primer byte de stdout con primer token del modelo, ni inicio del proceso con fin de inicialización de Claude. Reloj monotónico, formato compatible, sin prompts, respuestas ni datos privados.

## 6. Optimización sin comprometer comportamiento
Después de stdin, solo optimizaciones de bajo riesgo (inicializaciones duplicadas, conversiones inútiles, si se demuestra). No cambies modelo, esfuerzo ni reglas de seguridad por un benchmark. Nada de cachés que mezclen sesiones. No migrar a Agent SDK ni API de pago. Nada de proceso persistente, streaming de audio ni barge-in todavía.

## 7. Pruebas obligatorias
Conserva las 43 y agrega:
- T1 stdin: el subproceso recibe EOF y no espera entrada inexistente.
- T2 Respuesta: Claude sigue devolviendo bien texto y errores.
- T3 Nueva sesión: ID único y válido.
- T4 Continuidad: dos consultas personales seguidas recuperan el mismo contexto.
- T5 Expiración: después de 30 min, sesión nueva.
- T6 Desarrollo aislado: una sesión de desarrollo no se recupera desde voz o HUD.
- T7 Automatización aislada: el resumen matutino no altera la sesión personal.
- T8 Concurrencia: dos peticiones simultáneas no corrompen metadatos.
- T9 Sesión inválida: recuperación segura sin `--continue`.
- T10 Guardia: siguen activos todos los bloqueos del Upgrade 02.
- T11 Codex permitido: lee un archivo de prueba autorizado.
- T12 Codex privado: no lee el canario de ~/.jarvis/.
- T13 Rutas alternativas: no obtiene el contenido protegido por rutas equivalentes.
- T14 Codex escritura: sigue bloqueada.
- T15 Codex red: sigue bloqueada.
- T16 Fallback inseguro: si falla el aislamiento, el fallback se desactiva con error claro.
- T17 Telemetría: las nuevas métricas no rompen `bin/jv latencia`.
- T18 Regresión: las 43 previas siguen pasando.

Prioriza mocks. Pocas consultas reales, inocuas, solo para demostrar aislamiento o latencia.

## 8. Benchmark antes y después
Registra por separado: invocaciones nuevas, reanudadas, duración total del subproceso, tiempo a primer texto (si se puede), variabilidad. Idealmente 5 muestras por variante si la cuota lo permite; si no, reporta sin conclusiones estadísticas fuertes. Referencia: una sola medición de 13.45 s. No prometas reducción; mide.

## 9. Restricciones
- Mac mini Intel 2018, macOS Sequoia.
- Este upgrade cuesta $0 (tope general $200 MXN/mes).
- Conservar sesión de Claude Pro y ChatGPT Pro.
- Mantener permisos y hooks del Upgrade 02; no debilitar bin/guardia.py.
- No cambiar comandos rápidos, modos, HUD, Spotify ni transcripción de voz.
- No alterar la separación escolar/personal.
- No publicar, no enviar mensajes, nada irreversible.
- No guardar contraseñas en el proyecto.
- No hacer cambios ajenos al objetivo.
- No actualizar CLIs ni instalar componentes externos sin autorización.

## 10. Entrega final
Reporte con:
1. Archivos modificados o creados.
2. Cómo se resolvió la espera por stdin.
3. Latencia antes y después, con número de muestras.
4. Funcionamiento exacto de las sesiones separadas.
5. Método de aislamiento de Codex y versión instalada.
6. Evidencia de que Codex no puede leer ~/.jarvis/, o por qué se desactivó el fallback.
7. Resultado de las 43 pruebas originales y las nuevas.
8. Problemas abiertos.
9. Instrucciones de rollback.

Actualiza memoria/estado_proyecto.md con el estado real. No avances al Upgrade 04. Detente al terminar.

Prioridad: seguridad comprobable, continuidad del contexto, reducción medible de latencia y cero regresiones.

---

## Ajustes de Claude (revisor) — obligatorios

1. **Respaldo primero.** Antes de tocar nada: commit "Respaldo antes de upgrade 03". Incluye `hq/index.html` (está modificado). NO agregues `.claude/settings.local.json` a git.

2. **Orden por partes, commit por parte.** (Esto reemplaza "commit solo al final".)
   - Parte A — stdin + telemetría + benchmark antes/después. Es el cambio chico y de mayor impacto.
   - Parte B — sesiones separadas.
   - Parte C — aislamiento de Codex.
   Al cerrar cada parte con las pruebas en verde, haz su commit ("Upgrade 03A: …", etc.). Si el trabajo no da para hacer las tres bien en una pasada, termina A y B, reporta y DETENTE; la C se hace en otra sesión (mientras tanto, el estado de Codex queda como hoy y se anota como límite abierto).

3. **Usa `--output-format json` en `claude -p`** (si la versión lo soporta). Da `result`, `is_error`, `session_id`, `duration_ms` y `duration_api_ms`:
   - Guarda en sesiones.json el `session_id` que DEVUELVE Claude, no el que supones que mandaste (al reanudar, verifica que coincida; si no, usa el devuelto).
   - Registra en telemetría `duration_ms`, `duration_api_ms` y la diferencia (subproceso total − duration_ms ≈ arranque local). Esa es la mejor división observable que tenemos; descríbela como estimación, no como medida exacta.
   - Adapta la detección de límite/errores a `is_error` y `result` (hoy `LIMITE_RE` revisa texto plano). La respuesta que ve JP debe ser idéntica a la de antes.
   - NO uses `stream-json` en este upgrade (eso es el 04). Reporta "tiempo a primer texto" como no medible todavía.

4. **El resumen matutino hoy contamina la plática.** `bin/resumen.py` llama a `pensar(prompt)` igual que la voz: se guarda en historial.jsonl y hace que la siguiente consulta personal (antes de 30 min) se continúe sobre el resumen. Agrega a `pensar()` un parámetro `origen` ("personal" por defecto, "auto" para resumen.py). Puedes añadir el campo `origen` a historial.jsonl de forma compatible (líneas viejas sin el campo = personal). El contexto que se le pasa a Codex solo toma líneas personales.

5. **Primero intenta que el fallback de Codex no tenga herramienta de comandos/archivos** (es solo plática). Si la versión instalada tiene una opción verificable para desactivarla, es el aislamiento más fuerte; el perfil con deny de ~/.jarvis/ queda como segunda capa. Si no existe, sigue con el perfil. En ambos casos, las pruebas T11–T16 son las que deciden, no la config.

6. **Canario.** Crea `~/.jarvis/canario_upgrade03.txt` (contenido inventado, chmod 600) sin tocar ni leer ningún otro archivo de ~/.jarvis/. Déjalo ahí de forma permanente para las pruebas de regresión: así no hay nada que borrar. Nunca leas secretos.env.

7. **Cuota de llamadas reales:** máximo ~20 `claude -p` y ~8 `codex exec` en todo el upgrade, con prompts triviales (ej. "Responde solo: ok"). Si te faltan muestras, reporta con las que hay.

8. **Concurrencia de sesiones.json:** candado con `fcntl.flock` en un archivo de lock dentro de ~/.jarvis/, escritura atómica (archivo temporal + `os.replace`), permisos 600.

9. **Límite que solo se documenta (no se arregla aquí):** las sesiones del asistente y las de desarrollo viven en la misma carpeta de proyecto de Claude, así que si JP usa `claude --continue` o `/resume` a mano dentro de Jarvis, podría caer en una sesión del asistente. Anótalo en modulos/seguridad.md.

10. **Al terminar:** reinicia la voz (`open ~/Documents/Jarvis/Jarvis.command`), confirma que un comando rápido sigue funcionando y haz una prueba real de continuidad en dos turnos con `bin/pensar.py` (ej. "Mi número de prueba es 47" → "¿Cuál es mi número de prueba?"), contándola dentro de la cuota del punto 7. Incluye en el reporte las instrucciones de rollback con los hashes de los commits.
