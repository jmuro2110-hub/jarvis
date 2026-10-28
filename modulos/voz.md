# Módulo Voz

- `voz/jarvis_voz.py` (arranca con `Jarvis.command`).
- Activación: decir "Jarvis, …" (detección con Whisper `base`, entiende español; voz/oido.py) o ⌃⌥J. Se puede dar la orden de un jalón: "Jarvis, abre Spotify".
- Transcripción de la orden: Groq whisper-large-v3-turbo (gratis, GROQ_API_KEY en ~/.jarvis/secretos.env, se guarda con `jv llave groq`); si falla, faster-whisper local (`small`). La detección de "Jarvis" siempre es local (`base`).
- Filtro de frases fantasma ("Suscríbete", "Gracias por ver"…) en voz/oido.py.
- IDLE (arreglo 2026-10-28): Whisper base busca «Jarvis» solo en los primeros 3 s de la frase (`DETECCION_SEG`); la orden completa sigue yendo a Groq. Lo que JP dice mientras base transcribe se queda en la cola: solo se vacía después de una conversación (ahí la cola trae la voz de Jarvis). Telemetría `deteccion_base` (sin texto ni audio) cuando base tarda más de 2 s (motivo `lenta`) o no encuentra «Jarvis» (`sin_jarvis`). Causa: con ruido de fondo, base alucinaba hasta 15 s de texto, tardaba hasta 24 s y el `vaciar()` tiraba el «Jarvis» dicho mientras tanto.
- Hora: «qué hora es», «qué horas (son)», «la hora», «dime la hora».
- Eco del prompt de Groq: si la transcripción son 3+ palabras y todas salen de `VOCAB` (sin contar «jarvis»/«señor»), p. ej. «Pendientes, tarea, rutina, panel.», no va a Claude: Jarvis dice «No le entendí, señor.» (`solo_vocabulario()`, telemetría `transcripcion_descartada`). «Jarvis, abre Spotify» o «modo gamer» siguen funcionando.
- Sensibilidad: JARVIS_SENSIBILIDAD (3.0; súbela si el ruido lo activa). Prueba: voz/prueba_mic.py.
- Cerebro: `bin/pensar.py` → Claude con sesión personal explícita (upgrade 03: `--resume` del ID si fue hace <30 min) y, si topa límite o falla, ChatGPT con Codex aislado.
- Voz: `bin/decir.py` → ElevenLabs si hay ELEVENLABS_API_KEY en ~/.jarvis/secretos.env y crédito del mes; si no, `say` de macOS (Juan).
- Latencia: `bin/telemetria.py` mide cada etapa (sin guardar texto ni audio) en ~/.jarvis/metricas_latencia.jsonl; `jv latencia` muestra el resumen. Pruebas: `uv run --python 3.11 --with numpy python -m unittest tests/test_latencia.py`.

## Conversación continua (upgrade 04)
- Tras «Jarvis» (de un jalón o solo «Jarvis» + tin) o ⌃⌥J, después de cada respuesta se abre una ventana de **15 s** para seguir sin repetir «Jarvis». Máximo **5 turnos** o **3 min** desde la activación; luego vuelve a esperar «Jarvis». Ajustable en `config.json` (`conversacion_continua`, `timeout_seguimiento_seg`, `max_turnos`, `duracion_maxima_seg`), sin reiniciar.
- Máquina de estados en `voz/conversacion.py` (lógica pura): IDLE → ACTIVATED → PROCESSING → SPEAKING → FOLLOW_UP → … → CLOSED → IDLE. Corre en el mismo hilo del ciclo de voz; "terminó de hablar" = `decir()` regresó. Siempre se vacía la cola del micrófono antes de escuchar.
- En la ventana: voz por energía → Groq (o faster-whisper `small` si no hay llave), una sola transcripción por intervención; sin Whisper base. Fantasmas y ruido no cuentan turno ni reinician los 15 s; dos transcripciones vacías seguidas cierran.
- Si otra voz de Jarvis (vigía, resumen, modo) suena durante la ventana (`voz.lock` tomado o tocado, o `estado.json` = hablando), ese audio se descarta.
- En plática, "siguiente"/"anterior" solo cambian canción si dice "canción" o justo después de otro comando de Spotify; "ya" y "para" solos van al cerebro.
- **Cierre:** "terminamos", "cierra la conversación" o "eso es todo" (con o sin «Jarvis»; también "cierro/cerremos/ya cierra la conversación", "ciérrala", "cerremos", "ya cierra" — nunca "cierra" a secas) → sonido Bottle, sin frase. También cierran: ⌃⌥. o "cállate" (bandera `~/.jarvis/cerrar_conversacion`), "resumen", modo dormir, un error de voz. Cerrar la ventana NO borra la sesión de Claude (sigue 30 min).
- HUD: anillo verde pequeño y sin texto = esperando seguimiento (se oculta solo a los timeout + 2 s).
- ⌃⌥Espacio (texto) no abre ni toca la conversación de voz.
- Telemetría: `~/.jarvis/conversaciones.jsonl` (un evento por transición, sin texto ni audio); resumen en `jv latencia`. Pruebas: `tests/test_conversacion.py`.

## Stream y voz anticipada (upgrade 05)
- En el ciclo de voz, `claude -p` corre con `--output-format stream-json --verbose --include-partial-messages` (`bin/streaming.py`). El evento `result` es la respuesta autoritativa (historial, pantalla).
- **Voz anticipada** solo si: (1) la frase es de conocimiento general según un clasificador determinista (`ruta_sin_herramientas`: qué es, explícame, dime tres…, y nada de acciones, datos personales ni tiempo actual; en seguimiento, solo si el turno anterior también lo fue), (2) esa ruta corre con `--tools ""` (mismos candados del 02), (3) el `init` del stream reporta cero herramientas y cero MCP, y (4) no aparece ningún `tool_use`. Si no, se espera el resultado y se habla como antes.
- Se habla solo la PRIMERA LÍNEA: la frase 1 en cuanto cierra con un límite confiable (no corta en Sr., p. ej., 3.14, URLs, Markdown), luego el resto de la línea. Voz en proceso hijo (`bin/decir.py`: voz.lock, Juan, ⌃⌥. la calla), una a la vez; Claude sigue generando mientras. La ventana de seguimiento se abre solo cuando Claude terminó Y la voz terminó.
- Si ya sonó algo y Claude falla: "Señor, la respuesta quedó incompleta." — sin Codex y sin reintentar. Si no sonó nada: Codex aislado como siempre.
- **Tras «Jarvis» solo:** ese audio ya no va a Groq y la cola no se vacía, así que la orden que JP empezó durante el tin se conserva. Espera de la orden: `timeout_orden_seg` (6 s). ⌃⌥J sigue vaciando.
- Config (sin reiniciar): `claude_streaming` (false = ruta JSON del 04), `voz_anticipada` (false = stream solo para medir), `timeout_orden_seg`. Ninguna cambia permisos.
- Telemetría: claude_primer_texto, claude_primera_frase, tts_inicio, claude_resultado (desde que se lanzó claude), respuesta_completa (desde que JP terminó), voz_solapada; `jv latencia` da el % de turnos con voz anticipada. Pruebas: `tests/test_streaming.py`.

## Barge-in, voz al result y pendientes (upgrade 06)
- **Interrumpir mientras habla:** siempre con «Jarvis». «Jarvis, cállate / calla / deja de hablar / silencio» → se calla y cierra. «Jarvis, espera» → se calla y abre la ventana de 15 s. «Jarvis, no, mejor X» o «Jarvis, X» → se calla y X es el siguiente turno. Solo «Jarvis» → se calla y espera la orden (`timeout_orden_seg`); si no llega, queda en seguimiento. Ruido, música o voces sin «Jarvis» no lo interrumpen.
- Cómo: `voz/interrupciones.py` (`Vigia`). Sin threads ni otro stream: mientras suena la voz (proceso hijo `decir.py`), `Hablador.tick()` le pasa los frames de `oido.cola`; segmenta por energía con su propio piso de ruido, y solo los candidatos (0.5 s de silencio o 2.5 s de voz) van a Whisper base, uno a la vez. Anti-eco por texto: «Jarvis» en las 2 primeras palabras; si la mayoría de las palabras están en lo que Jarvis está diciendo, se ignora; si Jarvis dice «Jarvis», se exige una orden de la lista; se ignoran 300 ms al empezar cada pedazo. **No hay cancelación de eco**: con bocinas puede fallar.
- Cancelar la voz mata SOLO el grupo de ese hijo (`decir.py` + su `say`), nunca Spotify ni otras voces; Claude no se mata: su respuesta se guarda en historial y sesión, solo no se habla. ⌃⌥. (callar global) sigue igual.
- **Voz al `result`:** en la ruta normal la primera línea suena en cuanto llega un `result` válido (éxito, sin error, no aviso de límite), sin esperar a que `claude` salga (~0.5–1.0 s antes). Si `claude` sale con error después de un `result` válido, la respuesta cuenta como buena.
- **Pendientes sin Claude:** «¿qué tengo pendiente?», «mis pendientes», «qué tengo de tarea», «qué tengo (para) hoy/mañana», «…de la escuela / de <materia>» leen `memoria/pendientes.md` (solo `[ ]`, por fecha; voz: 3 y "N más en pantalla"). «…de Jarvis / del proyecto / del desarrollo» va al cerebro.
- Config: `barge_in` (false = como el 05), `hablar_al_result` (false = espera la salida). Pruebas: `tests/test_barge_in.py`.

## Upgrade 07 (memoria)
- «Recuerda que… / corrige ese recuerdo… / olvida… / ¿qué recuerdas de…?» es comando rápido (`clasificar_rapido`, justo después de callar y antes de Spotify/volumen, a pedido de JP: «recuerda que… pausa…» se guarda, no pausa la música): local, sin Claude, con confirmación corta. También entra por la orden nueva del barge-in. «Recuérdame…» sigue yendo a pendientes. `conv.ultimo_recuerdo` (solo en memoria) resuelve «ese recuerdo». Ver `modulos/memoria.md`.
