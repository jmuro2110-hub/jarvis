# JARVIS — Upgrade 09: Naturalidad de la voz
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-29)

**Lee también la sección final "Ajustes de Claude (revisor) — obligatorios". Si algo de ahí choca con el resto, mandan los ajustes.**

Diseña y, únicamente después de mi aprobación, implementa el UPGRADE 09: NATURALIDAD DE LA VOZ de Jarvis.

Trabaja en ~/Documents/Jarvis. Primero revisa esta propuesta contra el código real. Tu primera respuesta debe contener diagnóstico, ajustes justificados al plan y riesgos concretos. NO implementes todavía. Termina con ALTO y espera mi aprobación.

Después trabajaremos una parte por vez, con prueba física y ALTO entre partes. Aprobar una parte NO autoriza la siguiente.

**Contexto y restricciones**

Los upgrades 01–08 están terminados y aprobados físicamente. El 08 quedó documentado en el commit 2882c05, con 394 pruebas reportadas.

Jarvis corre desde ~/Applications/Jarvis.app: lanzador nativo con firma ad-hoc mx.jpmuro.jarvis, inicio de sesión automático, supervisor con candado, control desde Hammerspoon y rollback a Jarvis.command probado.

Equipo: Mac mini Intel 2018, 16 GB. Sin hardware nuevo. Presupuesto máximo TOTAL adicional: $200 MXN al mes. Tengo Claude Pro y ChatGPT Pro; conserva las integraciones actuales.

NO recompiles, refirmes ni reemplaces Jarvis.app. NO modifiques el arranque del 08: supervisor, lanzadores, inicio de sesión, permisos, firma ni controles de Hammerspoon. Los reinicios necesarios se hacen con los controles existentes.

Conserva seguridad del 02, sesiones del 03, conversación del 04, streaming del 05, barge-in del 06 y memoria del 07. La memoria sugerida con confirmación queda expresamente fuera del 09.

Lee CLAUDE.md, memoria/estado_proyecto.md y los módulos pertinentes. Revisa especialmente voz/oido.py, voz/interrupciones.py, voz/conversacion.py, voz/jarvis_voz.py, bin/pensar.py, bin/streaming.py, bin/decir.py y telemetría.

Inspecciona el estado de Git antes de trabajar. En la revisión previa había cambios ajenos en hq/index.html: no los sobrescribas ni los incluyas en commits del 09. No leas ni muestres llaves o tokens.

**Diagnóstico inicial, por prioridad**

1. Fiabilidad de escucha e interrupción.

No poder detenerlo o tener que repetir una orden destruye la sensación de conversación. El fallo físico de «espera» coincide con jarvis_en_medio: rechaza más de una palabra anterior a «Jarvis», aunque pueda tratarse del final de la propia voz.

Además, espera actualmente cancela la reproducción y abre seguimiento. No conserva una respuesta pausada ni existe un comando local sigue. Corregir el filtro por sí solo no resolverá ambas órdenes.

2. Latencia irregular.

Mediciones existentes: Whisper base en reposo, mediana 0.57 s y máximo 4.4 s; mientras habla sin música, 0.53–0.58 s; con música, 2.3–4.9 s. Groq: mediana 0.82 s y máximo 1.7 s.

Base no fija temperature y puede heredar reintentos con varias temperaturas. Es una hipótesis respaldada por la implementación de faster-whisper, todavía no una causa demostrada de cada pico. Probar temperature=0 exclusivamente en detección base, midiendo precisión y tiempos.

También hay segmentación por energía, sin cancelación acústica de eco. Acelerar Whisper no arregla por sí solo un candidato mal capturado.

3. Espera de turno y comprensión.

Orden y seguimiento esperan 1.3 s de silencio. Esa espera se suma a transcripción, razonamiento y voz. Debemos reducirla sin cortar pausas naturales, negaciones ni correcciones.

«Corazón» por «qué horas son» puede involucrar captura o transcripción. No se arregla sustituyendo palabras arbitrariamente. «Jardis» ya aparece entre las variantes aceptadas en partes del sistema: revisa dónde falla realmente.

4. Herramientas innecesarias.

Claude empezó a hablar en una mediana reportada de 4.98 s y máximo de 28.4 s. En 8 de 11 preguntas sencillas usó herramientas. No concluyas que todas eran innecesarias sin conocer las preguntas.

Streaming y voz anticipada YA existen. El clasificador es conservador y puede excluir formulaciones naturales. También está acoplada la decisión de herramientas con la de anticipar voz. Mejorar esas decisiones puede reducir mucho la espera sin cambiar de cerebro.

5. Timbre y redacción hablada.

Una voz más natural ayuda, pero no compensa órdenes mal entendidas ni silencios largos. La respuesta debe ser breve, clara y pronunciable; conservar el carácter de Jarvis sin muletillas repetidas.

Comprueba la voz efectiva: la documentación dice Juan, pero el inventario revisado mostró Paulina es_MX y Mónica es_ES, sin Juan/Jorge/Diego. Revisa selección y caché antes de asumir qué voz suena.

**Reglas comunes de medición y aprobación**

Los números siguientes son metas propuestas, NO resultados obtenidos ni garantías. Si una meta no es viable, presenta evidencia y una alternativa antes de cambiarla. No la rebajes silenciosamente.

Mide cada condición por separado: silencio/música, reposo/seguimiento/hablando y sesión nueva/reanudada. Separa la primera inferencia en frío.

Usa la misma posición del micrófono, distancia, bocinas, pista y volumen antes/después. Incluye música instrumental y con letra. Define “música moderada” mediante esa configuración reproducible.

Reporta cantidad de ensayos, aciertos, fallos, p50, p90 y máximo observado. Los fallos y timeouts cuentan; no desaparecen del informe. Una muestra corta no demuestra una tasa de fiabilidad permanente.

“Orden entendida” significa intención Y parámetros correctos a la primera. Reporta por separado los casos recuperados tras pedir repetición.

“Primera respuesta” significa contenido útil audible. Un tin o “un momento” no cumple esa métrica.

No sumes medianas de componentes para presentar una latencia total. Mide el recorrido completo.

No guardes grabaciones, transcripciones ni fragmentos hablados en nueva telemetría. Usa tiempos, contadores y motivos cerrados. Las frases del ensayo pueden ser sintéticas y conocidas.

**09A — Medición que represente la experiencia real**

Objetivo: tener una línea base fiable sin cambiar el comportamiento.

Distingue:

- Último audio de JP → cierre de frase.
- Tiempo en cola y detección base.
- Transcripción de la orden.
- Inicio de Claude → primer texto, primera frase y result.
- Solicitud TTS → audio disponible → inicio del reproductor.
- Fin de habla de JP → primera respuesta útil.
- Fin de la orden de interrupción → parada efectiva del audio.

Hoy algunas métricas empiezan después del silencio final y otras marcan lanzar decir.py como inicio de voz. Conserva las métricas antiguas o versiona las nuevas: no cambies su significado silenciosamente.

Usa reloj monotónico. Considera que los frames acumulados se procesan después de capturarse: no confundas esos tiempos. Si no puedes medir sonido físico automáticamente, identifica la aproximación y valídala durante la prueba.

Prueba física, aproximadamente 5 minutos: diez órdenes/preguntas en silencio y diez con música. Registra también algunos intentos de espera, sigue y cállate. Reutiliza estas frases en las partes correspondientes.

Aceptación: recorrido correlacionado y métricas interpretables, sin cambios funcionales ni contenido privado añadido a registros.

ALTO. Presenta línea base y espera aprobación.

**09B — Detección de «Jarvis» estable con música**

Ensaya temperature=0 únicamente para Whisper base, tanto en reposo como en barge-in. Mantén inicialmente los demás parámetros para atribuir el resultado.

Conserva una inferencia base a la vez, el límite actual de audio para detectar y la orden completa para transcribirla después. No vuelvas a vaciar el audio que JP dijo mientras Whisper procesaba.

No cambies simultáneamente el modelo small de respaldo ni introduzcas modelos locales más pesados. Una configuración rápida no equivale a un timeout efectivo de una llamada bloqueante: no presentes lo uno como lo otro.

Metas con modelo caliente:

- Sin música: inferencia base p50 ≤0.8 s y p90 ≤1.5 s.
- Con música moderada: p90 ≤2 s.
- Ninguna inferencia superior a 3 s en la muestra.
- Activación correcta: al menos 19/20 sin música y 18/20 con música.

Prueba física: veinte llamados por condición, repartidos entre «Jarvis» solo y «Jarvis, orden». Incluye llamados mientras habla. Puede dividirse en dos rondas breves.

Si mejora velocidad pero empeora reconocimiento o falsas activaciones, no se aprueba.

ALTO. Presenta comparación y espera aprobación.

**09C — Interrupción sin perder la protección contra eco**

Repara jarvis_en_medio mediante una excepción estrecha y comprobable. Considera controles explícitos después de «Jarvis» cuando el prefijo sea compatible con el fragmento que Jarvis estaba diciendo.

No elimines globalmente la regla ni aceptes cualquier orden incrustada en cualquier frase. Conserva defensas contra eco, citas, fantasmas y voz propia.

Revisa también la conservación de frames: Vigia retira varios frames de la cola y puede retornar al confirmar una interrupción. Comprueba con una prueba si descarta frames ya retirados que contienen el resto de la orden.

Esta parte corrige detección/parada. La reanudación completa se implementa en 09D; no declares sigue resuelto todavía.

Metas:

- Al menos 9/10 controles correctos por condición.
- Parada desde el final de la orden: p90 ≤2 s sin música y ≤3 s con música moderada.
- Cero falsas interrupciones o acciones en el ensayo negativo.

Prueba física: diez controles por condición, repartidos entre espera y cállate. Añade dos minutos de música sin órdenes y dos minutos de voz propia, incluyendo una frase que cite «Jarvis, espera».

No prometas reconocimiento perfecto con música alta y bocinas sin cancelación acústica de eco.

ALTO. Presenta resultados y espera aprobación.

**09D — «Espera / sigue» realmente funcional**

Implementa una respuesta pausada, limitada a la conversación y al turno actuales, en RAM.

Comportamiento esperado:

- «Jarvis, espera»: detiene la reproducción y conserva lo pendiente.
- «Sigue» o «continúa», durante la ventana vigente y con respuesta pausada: retoma localmente.
- La reanudación no llama a Claude, no repite herramientas ni ejecuta de nuevo acciones.
- No confunde sigue con reanudar Spotify.
- Cállate, cierre, caducidad, reinicio o una orden sustitutiva invalidan la pausa.
- No crea escucha indefinida ni cambia los límites de conversación.

Define la granularidad. Si no hay posición exacta del audio, acepta retomar desde el principio de la frase interrumpida; puede repetirse esa frase, no toda la respuesta.

Distingue texto generado, texto reproducido y texto pendiente. Lanzar un fragmento no significa haberlo escuchado completo.

Prueba especialmente espera durante voz anticipada y sigue ANTES de que Claude entregue result. El sistema debe conservar/procesar ese control sin perderlo ni abrir otra llamada a la misma sesión. Mantén el resultado autoritativo y el candado del 03.

Una respuesta fallida o cancelada no debe reaparecer después como voz pendiente válida.

Metas:

- Diez de diez reanudaciones válidas sin Claude ni herramientas adicionales.
- Reanudación audible p90 ≤2 s desde el final de sigue, cuando ya existe contenido disponible.
- Cero acciones repetidas y cero reapariciones de voz descartada.

Prueba física: cinco ciclos sin música y cinco con música; incluye interrupción temprana, nueva orden, cállate y vencimiento. Comprueba tanto la parada como la capacidad de escuchar inmediatamente después.

ALTO. Presenta resultados y espera aprobación.

**09E — Entender mejor y cerrar el turno antes**

Ensaya silencio final configurable de aproximadamente 0.7–0.9 s frente a los 1.3 s actuales. Cambia una variable por iteración. No optimices solo frases pronunciadas sin pausas.

Conserva preaudio y finales de palabra. Prueba pausas naturales de 300–500 ms, frases largas, negaciones y correcciones antes de actuar.

Revisa el prompt de vocabulario de Groq con variantes breves y pertinentes. Groq ya usa español y temperature=0; no presentes eso como una mejora nueva.

Si modificas VOCAB, revisa el filtro solo_vocabulario y sus pruebas: no reintroduzcas el eco del prompt ni rechaces órdenes legítimas.

No uses reemplazos globales como corazón → qué horas son. No amplíes coincidencias aproximadas para acciones sensibles. Ante ambigüedad, pide repetición; no inventes una confianza que la respuesta del proveedor no entrega.

Mantén Groq como primera opción y el respaldo existente. Un reintento, si se justifica, debe ser acotado y medirse como recuperación, no como comprensión a la primera. No añadas otra llamada a un modelo para corregir todas las transcripciones.

Metas:

- ≥19/20 intenciones y parámetros correctos a la primera sin música.
- ≥18/20 con música moderada.
- Cero acciones incorrectas.
- Silencio de cierre p50 ≤0.9 s, sin cortes en las frases de prueba.

Prueba física: veinte frases por condición con hora, apps, volumen, música y variantes naturales. Incluye «no abras…», una corrección, una frase larga y «recuerda que prefiero hacer una pausa…», que debe conservar la prioridad de memoria del 07.

Si propones bajar temporalmente Spotify, preséntalo como una opción independiente. Bajar música después de detectar ayuda a la orden siguiente, pero no resuelve la activación inicial. No cambies volumen global ni sobrescribas ajustes manuales de JP al restaurar.

ALTO. Presenta resultados y espera aprobación.

**09F — Respuestas útiles más rápidas**

Mantén tres rutas explícitas:

1. Comandos locales existentes y paráfrasis seguras: sin IA.
2. Conversación y conocimiento estable inequívocos: Claude sin herramientas.
3. Acciones, información actual o consultas que necesitan fuentes: herramientas con la seguridad existente.

No confundas “pregunta corta” con “pregunta sin herramientas”. No uses un modelo adicional para clasificar cada turno.

Mejora formulaciones naturales como «me explicas…» cuando sean inequívocamente conocimiento general. Prueba negaciones, órdenes mixtas y seguimientos. Conserva «esa», «la primera» y contexto mediante la MISMA sesión personal; no crees una sesión rápida aparte.

Separa la política de herramientas de la decisión de anticipar voz. Desactivar voz anticipada no debe conceder herramientas a una consulta clasificada sin ellas.

Para anticipación conserva --tools "", validación del init, ausencia de MCP y veto a tool_use. Mantén result como fuente autoritativa. No anuncies acciones como completadas antes del resultado ni repitas operaciones para obtener una respuesta más rápida.

Conserva la recuperación selectiva de recuerdos del 07 y sus límites. No envíes recuerdos a Codex ni al origen auto. No alteres el aislamiento del respaldo.

Redacción hablada: una respuesta directa de una o dos frases por defecto, sin relleno, listas recitadas ni “señor” repetido mecánicamente. El detalle adicional puede seguir en pantalla.

Metas desde el final real del habla de JP:

- Comandos locales: p50 ≤2.2 s y p90 ≤3 s.
- Conocimiento simple en seguimiento: p50 ≤3.5 s y p90 ≤6 s.
- El mismo tipo de pregunta desde reposo: p50 ≤4.5 s y p90 ≤7.5 s.
- Cero herramientas en el conjunto declarado elegible para la ruta sin herramientas.
- Cero llamadas IA en comandos locales.

Estas metas requieren validación; no garantizan tiempos de la nube. Si se incumplen, identifica el componente responsable.

Prueba física: diez preguntas elegibles con formulaciones naturales, algunas con seguimiento, y cinco controles que sí necesitan contexto, actualidad o acciones. Incluye sesión nueva y reanudada. Registra ruta y número de herramientas sin contenido privado.

ALTO. Presenta resultados y espera aprobación.

**09G — Voz más natural dentro del presupuesto**

Primero realiza una audición breve y elige UN proveedor para implementar. No construyas tres integraciones completas.

Opciones verificadas para esta propuesta el 29 de octubre de 2026:

| Opción | Costo previsto | Evaluación |
|---|---:|---|
| Voz de macOS instalada o descargable compatible con say | $0 MXN/mes | Respaldo permanente y primera comparación. Verificar voces reales y mejorar ritmo. |
| Azure Speech Neural, recurso F0 | $0 dentro de 500,000 caracteres/mes | Candidato económico para uso habitual; comparar JorgeNeural es-MX y DaliaNeural es-MX. Requiere configurar cuenta/recurso. |
| ElevenLabs API Flash/Turbo | Starter publicado: US$6/mes, aproximadamente $144 MXN con el supuesto presupuestario indicado abajo | Candidato a probar por naturalidad e integración ya existente. La página API publica aproximadamente 150,000 caracteres incluidos; confirmar condiciones de la cuenta. |

Fuentes:
[Apple: selección y descarga de voces](https://support.apple.com/en-ph/guide/mac-help/mchlp2290/mac).
[Azure: precios y cuota F0](https://azure.microsoft.com/en-us/pricing/details/speech/).
[Azure: idiomas y voces](https://learn.microsoft.com/azure/cognitive-services/speech-service/language-support?tabs=tts).
[ElevenLabs: precios de API](https://elevenlabs.io/pricing/api).

El cálculo de $144 usa US$6 × $20 MXN/USD × 1.20 de margen para impuestos/comisiones. Es un supuesto de presupuesto, NO una cotización cambiaria ni el cobro final. Verifica precio recurrente, cuota y cargo total antes de contratar; no bases la decisión en promociones iniciales. Las cuotas de ElevenCreative y ElevenAPI pueden diferir.

Ejemplo de uso: veinte respuestas diarias de doscientos caracteres suman 120,000 caracteres al mes. Calcula también el consumo de avisos y otras voces de Jarvis. El límite actual de 55,000 caracteres no demuestra que exista crédito ni presupuesto suficiente.

Mi preferencia inicial: comparar Azure F0 y ElevenLabs con las mismas frases; elegir por audición, latencia y facilidad de mantenerlo. macOS permanece como respaldo.

Antes de activar ElevenLabs, corrige los problemas de la integración actual:

- Descarga completa antes de reproducción y espera de hasta 20 s.
- Cambio automático a say con textos mayores de 400 caracteres.
- Consumo registrado solo después de recibir el audio.
- Retorno del reproductor no comprobado.

No basta pegar una llave.

El proveedor elegido debe pasar por el mismo control de reproducción, candado y barge-in. La descarga o síntesis no puede bloquear la escucha de controles. Valora streaming de audio o fragmentos cortos completos según compatibilidad y medición, sin prometer latencia de proveedor como latencia final.

Establece una espera breve y acotada para caer a voz local. Si ya empezó a sonar, no repitas desde el principio por un fallo de red. Evita duplicados, procesos huérfanos y audio antiguo después de cancelar.

Presupuesta antes de cada solicitud de pago, incluyendo solicitudes canceladas o de resultado incierto que podrían cobrarse. Ajusta al ciclo/cuota reales y reconcilia con el proveedor cuando sea posible. No habilites recargas, sobreconsumo ni cambio automático a pago.

Usa archivos temporales privados y limpieza al terminar/cancelar. El proveedor recibe únicamente el texto necesario para hablar; no el archivo de recuerdos, historial completo ni micrófono permanente.

Metas:

- JP prefiere la voz candidata en al menos cuatro de cinco comparaciones.
- Cinco de cinco frases entendibles.
- Incremento de p90 de primera voz ≤0.5 s frente a la versión previa comparable.
- Se mantienen las metas de espera, sigue y cállate.
- Cuota agotada, error y falta de red producen respaldo local sin duplicación.
- Costo total adicional previsto ≤$200 MXN/mes.

Prueba física: cinco frases idénticas con ambas voces —hora/números, saludo, explicación, pregunta y palabras en inglés—; después espera/sigue y cállate con música. Simula cuota agotada y errores sin generar cargos adicionales.

No contrates ni actives cobros sin mi aprobación explícita.

ALTO. Presenta voz elegida, mediciones, consumo previsto y espera aprobación.

**09H — Cierre y regresión final**

Ejecuta la suite completa vigente y las nuevas pruebas pertinentes. Comprueba las 394 pruebas reportadas contra el estado real; informa cualquier diferencia sin ocultarla.

Prueba física final, aproximadamente diez minutos:

- Activación desde reposo y conversación continua.
- Órdenes de un jalón y después del tin.
- Música instrumental y con letra.
- Espera/sigue antes y después de result.
- Cállate, nueva orden y expiración.
- Memoria explícita, recuperación y corrección por el mecanismo del 07.
- Sesiones personal/auto separadas y contexto de seguimiento.
- Respaldo de voz y controles existentes del 08.

Las pruebas de seguridad y efectos sensibles se hacen con mocks o verificaciones de bloqueo, sin enviar mensajes, borrar archivos ni gastar dinero.

El upgrade solo queda aprobado cuando yo confirme la prueba física. Si queda un límite con música o nube, documéntalo claramente; no declares equivalencia con Alexa.

**Formato obligatorio al terminar cada parte**

Entrega:

- Qué cambió y por qué.
- Archivos afectados y pruebas automáticas ejecutadas.
- Resultados antes/después, con aciertos y fallos.
- Instrucciones breves para mi prueba física.
- Estado: implementado, pendiente de prueba física o aprobado por JP.
- Cómo revertir únicamente esa parte sin deshacer trabajos ajenos.
- ALTO: no avances hasta mi aprobación explícita.

Mantén cambios pequeños y reversibles. Usa pruebas que cubran fallos y contratos reales, especialmente eco, pérdida de frames, pausa, duplicados, memoria y sesiones.

Actualiza la documentación del 09 y memoria/estado_proyecto.md distinguiendo implementación de aprobación física. No marques como aprobado algo que solo pasó pruebas automáticas.

Empieza ahora con tu revisión del diagnóstico y el plan. Señala cualquier corrección necesaria y termina con ALTO, sin implementar.

---

## Ajustes de Claude (revisor) — obligatorios

Revisado contra el código real el 2026-10-29 ~15:00: HEAD 2882c05, `hq/index.html` modificado (ajeno) y `.claude/settings.local.json` sin rastrear. El diagnóstico de ChatGPT coincide con el código; estos puntos lo precisan. Confírmalos con número de línea en tu revisión inicial.

**1. Hallazgos en el código que cambian el plan**

a. **temperature compartida (09B).** `transcribir()` (voz/oido.py) no pasa `temperature`, así que usa el valor por defecto de faster-whisper con reintentos. La misma función la usan base en IDLE (`escuchar_una`), base en barge-in (`Vigia`) y el respaldo small (`oir_bien`, `preciso=True`). Agrega un parámetro opcional y pasa `temperature=0` SOLO desde los dos llamados de base; small y Groq quedan igual. Prueba automática que lo compruebe.

b. **Pérdida de frames confirmada por lectura (09C).** `Vigia.revisar()` saca hasta 60 frames con `_sacar()` y, al confirmar, regresa: los frames que quedaban en esa lista local se pierden. El comentario «lo demás queda en la cola» es falso. Afecta a «Jarvis, abre X» cortado por la ventana de 2.5 s. Arreglo preferido: sacar de la cola frame por frame y dejar de sacar al cerrar un candidato, para que el resto sí quede en `oido.cola`. Primero una prueba que falle con el código actual y pase con el arreglo.

c. **«Sigue» se pierde hoy por diseño (09D).** Tras interrumpir, el vigía deja de revisar (`not self.interrumpido`), `correr()` sigue esperando a Claude y después `esperar_seguimiento()` hace `oido.vaciar()`: todo lo que JP dijo mientras Claude terminaba se tira. Propuesta: con un «espera» confirmado, vaciar la cola en el momento de la parada (lo anterior trae eco) y NO volver a vaciar al abrir el seguimiento de esa pausa. Solo para espera/callar; nunca para una orden cortada, que necesita la cola intacta.

d. **Solo se habla la primera línea (09D y 09F).** `procesar()` y `_al_result()` hablan `primera_linea(resp)`. Lo que queda pendiente al pausar es poco: el resto de esa línea. En la ruta al `result` esa línea es UN solo pedazo del `Hablador`, así que «sigue» repetiría todo lo dicho. Granularidad propuesta: partir la línea en frases (reutiliza `FIN_RE`/abreviaturas de `Frases`) también en la ruta al result, y retomar desde la frase interrumpida. Cambio pequeño y medido; no cambia qué se dice, solo en cuántos pedazos.

e. **Choques con Spotify (09D).** `clasificar_rapido` ya manda «reanuda» a Spotify play y «pausa» a Spotify pause. «Sigue» / «continúa» solo cuentan como frase completa, solo con una pausa válida y se evalúan ANTES de `clasificar_rapido`. «Reanuda» sigue siendo Spotify. «Jarvis, pausa» NO se vuelve control de voz en el 09 (sigue pausando Spotify); si crees que conviene, propónlo aparte con ALTO.

f. **Silencio de cierre real (09E).** IDLE de un jalón usa `fin_silencio=0.7` (valor por defecto de `oido.frase`). Solo el turno después del tin y el seguimiento usan 1.3 s. El 09E aplica a esos dos, con una clave nueva en config.json (sin reiniciar para probar si se puede). No cambies el 0.7 de IDLE sin medirlo aparte.

g. **Acoplamiento confirmado (09F).** En `bin/pensar.py` el comando usa `asistente_sin_herramientas() if flujo and flujo.anticipar`, y `anticipar = voz_anticipada and sin_herramientas`: con `voz_anticipada=false` una consulta sin herramientas recibe todas. Además `ACCION_RE` (bin/streaming.py) incluye «me», «mi», «hora», «ahora», «tiempo hace»: «me explicas…» nunca entra a la ruta sin herramientas. Separa las dos decisiones; amplía solo formulaciones inequívocas, con pruebas negativas («me abres…», «explícame mis pendientes»).

h. **Voz efectiva (09A reporta, 09G arregla).** `decir.py` guarda la voz elegida en `~/.jarvis/voz_mac.txt`; si se guardó vacía (ninguna de PREFERIDAS instalada) nunca vuelve a revisar y suena la voz del sistema aunque JP descargue otra después. `config.json` tiene `voz_mac: ""`. En 09A solo reporta qué contiene el caché y qué voces `es_*` da `say -v ?`. En 09G haz que un caché vacío se vuelva a revisar.

i. **Hora de captura (09A).** El `t_fin` de `oido.frase()` es hora de procesamiento, no de captura: si Whisper estaba ocupado, hay frames atrasados en la cola. Aproximación barata y sin tocar la cola: captura ≈ ahora − `cola.qsize()` × 0.1 s al cerrar la frase. Regístrala como métrica nueva versionada; las viejas no cambian de significado. Valídala en la física.

j. **Conteo de pruebas.** Cuento 392 `def test_` en tests/; el 08 reportó 394. Corre la suite en tu revisión inicial y explica la diferencia (subTest, parametrización o conteo distinto). No es un problema si se explica.

**2. Metas que hay que precisar (no rebajar)**

- 09F «comandos locales p50 ≤2.2 s»: di si se mide desde IDLE de un jalón o en seguimiento, y reporta ambos. Desde IDLE el camino incluye silencio 0.7 s + base + Groq + arranque de la voz; si no da, presenta evidencia. No te saltes Groq usando el borrador de base para acciones. Para «qué hora es» exacta podría valer, pero solo como propuesta aparte con ALTO.
- 09G «incremento de p90 de primera voz»: compara la misma ruta (al result con al result, anticipada con anticipada).

**3. Dinero y cuentas (09G)**

- La audición se hace a $0: Azure F0 y el plan gratuito de ElevenLabs alcanzan para unas frases. Nada de Starter ni recurso de pago hasta que JP elija y apruebe por escrito.
- Crear cuentas, registrar tarjeta y sacar llaves lo hace JP; tú le das los pasos. Guárdalas con `jv llave` (agrega el nombre de Azure si no existe). Nunca en config.json ni en Git; no las muestres.
- En Azure solo recurso F0 (confirma que al llegar a la cuota se corta en vez de cobrar). Nunca S0.

**4. Orden y alcance**

- Mantén el orden 09A → 09H, con ALTO en cada parte.
- Un commit por parte. Nunca `hq/index.html` ni `.claude/settings.local.json`. Incluye este archivo en el commit del 09A.
- Máximo ~10 llamadas reales a `claude -p` por parte fuera de la física de JP.
- Cada física de JP en un bloque numerado y cerrado: frases exactas, en qué orden, qué canción y a qué volumen de Spotify (número), y dónde está el micrófono. Una ronda de máximo ~5 minutos; si la parte pide más, divídela en rondas.

**5. Estado.** En la revisión inicial solo pon en `memoria/estado_proyecto.md` → Paso actual: «Upgrade 09 en revisión (sin implementar)». Sin commit hasta que JP apruebe el 09A.

---

## Revisión inicial de Jarvis — aprobada por Claude (2026-10-29 15:25)

Se acepta la revisión inicial (hallazgos 1a–1j confirmados, 4 extras y ajustes 1–5). Dos precisiones:

1. **Variantes de «Jarvis» (09E).** Al unificar `WAKE_RE` y la lista de `memoria.py`, distingue dos usos. Para quitar el prefijo de una frase que YA activó (después del tin, en seguimiento, en memoria), una lista amplia es segura. Para activar desde IDLE y en barge-in, cada variante nueva (p. ej. «Jardvis») cuenta como posible falsa activación: agrégala solo si la mide un ensayo negativo con música y voz propia, y reporta cuáles quedaron en cada lista.
2. **«Para» como control (09C).** Hoy `CALLAR_RE` no lo incluye. Si lo agregas, solo como frase completa en barge-in («Jarvis, para»). No cambies la regla del seguimiento, donde «ya»/«para» van al cerebro.

Siguiente: 09A, con ALTO al terminar.
