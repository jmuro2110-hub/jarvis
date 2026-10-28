# JARVIS — Upgrade 08: Segundo plano, inicio automático y rollback
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-28)

Eres el ingeniero principal de JARVIS, ubicado en `/Users/jpmuro/Documents/Jarvis`.

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes. Los ajustes dividen este upgrade en etapas con ALTO: respétalos.**

**OBJETIVO:** ejecutar Jarvis sin ventana de Terminal, arrancarlo al iniciar sesión y conservar micrófono, Documentos, Hammerspoon y todas las funciones aprobadas. Poder volver fácilmente al funcionamiento actual en Terminal.

Mac mini Intel 2018, macOS Sequoia. Presupuesto adicional: $0 MXN.

## 1. Base que debes conservar

Upgrades 01–07 terminados y con prueba física aprobada. Conserva especialmente:
- Stream-json, voz anticipada y voz al recibir result.
- Barge-in: «Jarvis, cállate» y «Jarvis, espera».
- Conversación continua y sesiones personal/automática/desarrollo separadas.
- «¿Qué tengo pendiente?» local, sin contexto de desarrollo.
- Memoria permanente local y determinista: guardar, corregir, olvidar y consultar; máximo tres recuerdos relevantes como datos; Codex sin recuerdos.
- be17d98: cierre del 07. bb5416e: descarte del eco del vocabulario de Groq. 4c0f1d7: activación en reposo sin descartar la cola de audio.

No reconstruyas esas funciones. Este upgrade cambia cómo se ejecuta Jarvis.

## 2. Inspección y respaldo

Antes de editar:
- Lee CLAUDE.md, memoria/estado_proyecto.md, modulos/voz.md, modulos/seguridad.md y modulos/memoria.md.
- Revisa Git y establece la cantidad real de pruebas actuales.
- Inspecciona Jarvis.command, voz/iniciar.sh, el cierre de jarvis_voz.py, agenda, reproducción TTS, Hammerspoon y los instaladores.
- Comprueba los elementos de inicio realmente registrados. El instalador contiene entradas para Jarvis.command y Hammerspoon, pero eso no demuestra la configuración actual.
- Identifica rutas reales de Python/uv, dependencias, modelos, cachés y comandos utilizados.
- Guarda un respaldo recuperable del arranque actual y registra sus elementos de inicio.

No sobrescribas cambios existentes. No incluyas secretos ni .claude/settings.local.json en Git. No modifiques innecesariamente hq/index.html. El documento de estado todavía menciona el problema antiguo de IDLE: contrástalo con el código y el commit más reciente.

## 3. Arquitectura mínima

Crear una aplicación local en `/Users/jpmuro/Applications/Jarvis.app`:
- Lanzador nativo pequeño, compatible con Intel, compilado con las herramientas existentes.
- Ejecutable principal nativo; no un script disfrazado de aplicación.
- El lanzador permanece vivo y mantiene los procesos de Jarvis como descendientes.
- Sin ventana habitual ni icono permanente en el Dock.
- Menú discreto con estado, detener y acceso al diagnóstico (ver ajuste 3: va en el menú existente de Hammerspoon).
- Python, modelos, configuración y datos permanecen en sus ubicaciones actuales.

La app será el único dueño del arranque de voz, agenda y prevención de suspensión. Hammerspoon continúa como aplicación independiente.

Usar Elementos de inicio de macOS para abrir Jarvis.app al iniciar sesión. No añadir LaunchDaemon, ejecución como root, otro vigilante externo ni un servidor de control. No arrancar Python directamente desde un LaunchAgent en esta primera versión.

## 4. Primera etapa obligatoria: demostrar los permisos

Antes de sustituir el inicio automático, preparar una prueba manual de la app:
1. Solicitar micrófono mediante el mecanismo normal de macOS y las declaraciones de uso correspondientes.
2. Comprobar audio desde el proceso Python que realmente utiliza Jarvis. Que el lanzador tenga permiso no demuestra que Python capture sonido.
3. Leer desde esa ejecución un archivo de prueba preexistente en Documentos, preparado fuera de la app. Comprobar también lectura del proyecto y escritura controlada en un archivo de prueba.
4. Probar la integración real con Hammerspoon y una acción reversible habitual que use Automatización.
5. Cerrar y volver a abrir la app; repetir las comprobaciones.

Registrar qué aplicación aparece autorizada para cada permiso. Conservar los permisos actuales de Terminal y Hammerspoon. Solicitar únicamente los permisos necesarios; no recurrir a Acceso total al disco.

Mantener ruta, identificador y ejecutable estables. Si se utiliza firma ad-hoc, conservar el binario aprobado y documentar que recompilarlo puede exigir otra autorización. El mismo nombre no garantiza continuidad de permisos.

Si esta etapa falla, conservar Terminal como modo activo y reportar el impedimento concreto. No activar el arranque automático nuevo con permisos sin demostrar.

## 5. Una sola instancia y apagado completo

El arranque actual usa búsquedas y terminaciones por nombre. Sustituir esa convivencia por un mecanismo verificable:
- Candado real compartido entre app y entrada de Terminal, adquirido antes de iniciar voz o agenda.
- Una segunda apertura informa que Jarvis ya está activo; no mata ni reemplaza silenciosamente la primera.
- Un archivo PID por sí solo no cuenta como candado.
- La liberación del candado no debe permitir arrancar otra instancia mientras siguen vivos hijos de la anterior.
- Detener voluntariamente impide cualquier reinicio automático pendiente.
- Terminar solo procesos propios identificados; no usar terminaciones generales de Python, uv, say o afplay.

Atender salida de la app, SIGTERM y cierre de sesión. Liberar micrófono, agenda, reproducción y el caffeinate propio. El TTS de streaming utiliza grupos de procesos separados: no basta con terminar el grupo del lanzador. Reutiliza su limpieza dirigida y verifica que no queden voces huérfanas.

Mantener recuperación ante caídas de voz o agenda mientras el supervisor esté activo, con esperas crecientes y límite de intentos; al agotarlo, mostrar error. Un permiso denegado no debe producir reinicios interminables.

## 6. Entorno y disponibilidad

- Rutas explícitas, directorio de trabajo correcto y entorno mínimo definido.
- Mismo usuario, dependencias, modelos, cachés y autenticaciones actuales.
- Sin instalar uv, descargar modelos ni actualizar paquetes al iniciar sesión.
- Si falta algo, mostrar qué falta y detener el componente afectado.
- Mantener la política actual de suspensión, vinculada a la vida de Jarvis.

Hammerspoon puede iniciar antes o después: conservar su configuración y permisos, no convertirlo en supervisor, reintentos limitados para integraciones no disponibles, atajos funcionando cuando termine de cargar.

"Listo" significa que la voz terminó de inicializarse y puede escuchar. Distinguir: iniciando, escuchando, integración pendiente, detenido y error.

Registro técnico acotado de arranque, parada y fallos, con permisos restrictivos. Sin conversaciones, recuerdos, credenciales ni el entorno completo.

## 7. Migración reversible

Con la etapa de permisos aprobada:
1. Detener ordenadamente la ejecución anterior.
2. Confirmar que no quedan sus procesos de voz, agenda o reproducción.
3. Abrir Jarvis.app y verificar una sola instancia.
4. Sustituir únicamente el elemento de inicio de Jarvis.command por Jarvis.app.
5. Conservar Hammerspoon y los demás elementos de inicio.

Revisar que los instaladores no vuelvan a registrar ambos modos. Conservar Jarvis.command como entrada de respaldo con los cambios mínimos para respetar la exclusión mutua, y su versión previa al 08 para emergencia. No cambiar automáticamente de modo al fallar: mostrar el error y dar instrucciones de recuperación.

## 8. Restricciones

- $0 extra: sin servicios, suscripciones ni certificados de pago.
- Sin cambios de modelos, personalidad, memoria, sesiones o política de herramientas.
- Sin ampliar permisos del modo asistente. Los controles de instalación, parada y rollback no se agregan a los comandos que Claude puede ejecutar.
- Codex conserva su aislamiento y sigue sin recuerdos.
- No modificar bases de permisos de macOS, desactivar SIP ni restablecer permisos globalmente.
- No mover ni migrar ~/.jarvis. No agregar aprendizaje implícito.

## 9. Pruebas automatizadas y de integración

Con procesos simulados y archivos temporales cuando corresponda:
1. Dos aperturas simultáneas: una instancia.
2. App y Terminal en ambos órdenes: sin duplicación ni terminación de la instancia válida.
3. Parada voluntaria: sin resurrección.
4. Caída de voz o agenda: recuperación limitada.
5. Caída del supervisor: sin escucha huérfana ni duplicación al volver a abrir.
6. Parada durante TTS: limpieza de reproductores propios.
7. Dependencia ausente y permiso denegado: error visible, sin falso "listo".
8. Entorno mínimo y rutas con espacios: arranque correcto.
9. Hammerspoon antes, después y tras recargar su configuración.
10. Cambio de modo y rollback repetibles, sin duplicar elementos de inicio.
11. Registro técnico sin datos privados.
12. Suite actual completa (IDLE, eco de Groq, memoria, streaming, barge-in, seguridad).

Los mocks no demuestran permisos de macOS: separar pruebas automáticas de comprobaciones reales.

## 10. Prueba física con JP

Bloque numerado corto. Tú preparas y observas; JP hace permisos, reinicios y frases.
- A. Sin Terminal: detener el modo antiguo, abrir la app, cerrar Terminal. «Jarvis, ¿qué hora es?».
- B. Reposo: dejarlo volver a IDLE y decir «Jarvis, qué tengo pendiente» de corrido; repetir con sonido de fondo. No pierde la instrucción.
- C. Voz: explicación, «Jarvis, cállate»; repetir con «Jarvis, espera» y continuar. Streaming y conversación continua.
- D. Hammerspoon: los cuatro atajos (hablar, escribir, panel, callar).
- E. Documentos y memoria: archivo de prueba; recuerdo sintético guardar/consultar/corregir/desactivar por rutas locales; persiste tras reabrir.
- F. Inicio automático: cerrar sesión y entrar; reiniciar la Mac y entrar. Sin abrir nada a mano: una instancia, micrófono y atajos. Agenda sin avisos duplicados.
- G. Recuperación: detener desde el menú, silencio y micrófono liberado; reabrir. Bloqueo/desbloqueo y reposo manual.
- H. Rollback real: volver a Terminal, voz y atajos OK, regresar a la app con el procedimiento documentado.

Comparar latencias con Terminal (primera activación, posteriores, barge-in): muestras, mediana y máximo. Objetivo: sin regresión apreciable. No cerrar el 08 como aprobado hasta completar las físicas, incluidos reinicio y rollback.

## 11. Rollback

Secuencia breve y exacta:
1. Detener Jarvis.app y comprobar que terminó sus procesos.
2. Retirar únicamente Jarvis.app de Elementos de inicio.
3. Restaurar el elemento anterior de Jarvis.command.
4. Abrir Jarvis.command.
5. Confirmar una voz, una agenda, micrófono y atajos.

Conserva recuerdos, historial, sesiones, configuración y permisos. No deshace 01–07 ni los arreglos posteriores. Incluir ruta de emergencia si la app no responde, dirigida solo a sus procesos, sin depender del menú de una app averiada.

## 12. Reporte de cierre

Corto: archivos y commit; arquitectura y forma de inicio; identidad/firma y límites al actualizar la app; permisos comprobados y app titular de cada uno; pruebas automáticas (cantidad y resultado); tabla de físicas (aprobada/fallida/pendiente); tiempo hasta "listo" y latencias vs Terminal; instancia única y apagado completo; rollback exacto; limitaciones. Actualizar memoria/estado_proyecto.md y documentar el nuevo arranque. Distinguir "implementado" de "aprobado físicamente".

**DETENTE AL TERMINAR EL UPGRADE 08.**

### Idea reservada para después del 08 (solo anotarla en el roadmap)
Memoria sugerida con confirmación: Jarvis detecta una posible preferencia y pregunta «¿Quiere que recuerde que…?». Queda pendiente un rato; solo un "sí" explícito de JP ligado a esa propuesta la guarda por el mecanismo local del 07. "No", silencio, vencimiento o ambigüedad no guardan nada. Misma validación de privacidad y ámbitos; nunca confirmaciones del modelo, páginas o herramientas. No implementarla en el 08.

---

## Ajustes de Claude (revisor) — obligatorios

Revisado contra el código real el 2026-10-28 ~12:50: HEAD 4c0f1d7 (367 pruebas según tu reporte), `hq/index.html` modificado (lo regenera la agenda) y `.claude/settings.local.json` sin rastrear.

**0. Tres etapas con ALTO.**
- **Etapa 0 (todo en Terminal, sin tocar el arranque):** cerrar el arreglo de IDLE y sacar línea base.
- **Etapa 1:** app mínima + prueba real de permisos (punto 4). **ALTO:** reporte corto y esperas.
- **Etapa 2 (solo cuando JP diga que sigas):** supervisor, candado, migración, pruebas 9 y física A–H.

**1. Etapa 0.** La prueba corta de 4c0f1d7 quedó pendiente. Revisa en la telemetría (`deteccion_jarvis`, `deteccion_base`) desde el arranque de las 11:52:31 qué se probó ya. Si falta algo, dale a JP un bloque de máximo 3 frases (app de Claude al frente, luego con música). Esas mismas muestras son la línea base de Terminal para comparar en la etapa 2: primera activación, posteriores y un «Jarvis, cállate». Actualiza `estado_proyecto.md`: el bug de IDLE pasa a arreglado (4c0f1d7) con su resultado físico, y agrega al roadmap la idea reservada. Commit propio. Si la prueba de IDLE falla, ALTO y reporta: no arranques el 08 sobre una voz rota.

**2. App delgada, lógica en el proyecto.** El binario nativo solo arranca el supervisor, espera, le reenvía salida/SIGTERM/cierre de sesión y termina cuando termina el supervisor. Toda la lógica (candado, entorno, reinicios con espera creciente, limpieza, estado) va en un supervisor del proyecto (p. ej. `bin/arranque.py`, solo biblioteca estándar) que usan igual la app y Jarvis.command. Motivo: con firma ad-hoc cada recompilación cambia el cdhash y macOS puede volver a pedir micrófono y Automatización; así el binario se compila una vez y los arreglos futuros no tocan permisos.
- Herramienta: Swift (`swiftc`) o C (`clang`), la que ya exista. Verifica con `xcode-select -p`. Si no hay herramientas de línea de comandos, ALTO y pregunta antes de instalarlas.
- Info.plist: `CFBundleIdentifier` fijo (p. ej. `mx.jpmuro.jarvis`), `LSUIElement` = 1, `NSMicrophoneUsageDescription`, `NSAppleEventsUsageDescription`. Firma ad-hoc con ese identificador y sin hardened runtime (así no hace falta el entitlement de audio).

**3. Sin un segundo icono en la barra.** Hammerspoon ya tiene el menú J.A.R.V.I.S. (hablar, modos, carpeta, registro). Agrega ahí "Estado", "Detener Jarvis" y "Abrir Jarvis", que solo llaman a un comando del supervisor (p. ej. `bin/jv arranque estado|detener|abrir`). Hammerspoon no supervisa nada. Ese mismo comando desde cualquier Terminal es la ruta de emergencia y no depende de la app. Bloquea `jv arranque` en la política del modo asistente (igual que `jv memoria`) con su prueba.

**4. Candado.** `fcntl.flock` sobre `~/.jarvis/jarvis.lock` (0600), tomado por el supervisor antes de voz, agenda y caffeinate. Pasa el descriptor a voz y agenda (`pass_fds`) para que el candado no se libere mientras viva un hijo. El supervisor anota sus hijos con PID + hora de inicio + comando y solo termina esos (verificando identidad); para la voz de streaming usa la limpieza que ya existe en `bin/streaming.py`. Jarvis.command deja de usar `pgrep`/`pkill` por nombre y pasa a llamar al mismo supervisor; si el candado está tomado dice «Jarvis ya está activo» y sale sin matar a nadie. Versión previa guardada como `Jarvis.command.pre08`.

**5. Arranque sin red y sin instalar nada.** `voz/iniciar.sh` instala uv con curl si no lo ve: el supervisor NO usa ese camino. Llama a uv por ruta absoluta con `--offline` (o `UV_OFFLINE=1`) sobre el entorno ya cacheado; en la etapa 1 comprueba que la voz arranca así sin red. Si falta uv o el entorno: error visible, sin reintentos. PATH explícito como en Jarvis.command (`~/.local/bin`, `/usr/local/bin`); anota en el reporte las rutas reales de uv, claude y codex.

**6. Etapa 1 con permisos concretos.** Además del micrófono (desde el Python real de la voz, midiendo nivel de audio, no solo abrir el stream) y Documentos: saca del código la lista real de destinos de AppleScript (hoy aparecen Spotify, System Events, Finder, Mail y Minecraft) y prueba cada uno desde la app con una consulta inofensiva de solo lectura, para que JP apruebe cada aviso una vez. No abras apps cerradas solo para la prueba; si no se puede probar uno, anótalo como pendiente. Reporta en tabla: permiso → app titular en Ajustes → resultado, antes y después de reabrir la app. Si el micrófono no queda a nombre de Jarvis.app o Python no recibe audio: ALTO, Terminal sigue activo y propone en el reporte un plan B barato (p. ej. Terminal con la ventana oculta), sin implementarlo.

**7. Elementos de inicio.** Hoy se registran con System Events desde `scripts/instalar_todo.sh` (≈ líneas 98–103; Jarvis.command con `hidden:false`, por eso se ve la ventana). Migra con ese mismo mecanismo cambiando solo la entrada de Jarvis, y actualiza `instalar_todo.sh` para que registre Jarvis.app y no vuelva a meter Jarvis.command. El rollback restaura la entrada anterior con el mismo comando.

**8. Registro y alcance.** Registro técnico en `~/.jarvis/arranque.log` (0600, se recorta solo a ~200 KB) y que "Ver registro" del menú lo pueda abrir. Máximo ~10 `claude -p` reales en todo el upgrade. No commitees `hq/index.html` ni `.claude/settings.local.json`. Incluye este archivo en el commit del 08.

**9. Reporte en cada ALTO:** corto, con hash, tabla de lo probado y qué necesitas de JP (en un bloque numerado).
