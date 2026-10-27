# Módulo Voz

- `voz/jarvis_voz.py` (arranca con `Jarvis.command`).
- Activación: decir "Jarvis, …" (detección con Whisper `base`, entiende español; voz/oido.py) o ⌃⌥J. Se puede dar la orden de un jalón: "Jarvis, abre Spotify".
- Transcripción de la orden: Groq whisper-large-v3-turbo (gratis, GROQ_API_KEY en ~/.jarvis/secretos.env, se guarda con `jv llave groq`); si falla, faster-whisper local (`small`). La detección de "Jarvis" siempre es local (`base`).
- Filtro de frases fantasma ("Suscríbete", "Gracias por ver"…) en voz/oido.py.
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
- **Cierre:** "terminamos", "cierra la conversación" o "eso es todo" (con o sin «Jarvis») → sonido Bottle, sin frase. También cierran: ⌃⌥. o "cállate" (bandera `~/.jarvis/cerrar_conversacion`), "resumen", modo dormir, un error de voz. Cerrar la ventana NO borra la sesión de Claude (sigue 30 min).
- HUD: anillo verde pequeño y sin texto = esperando seguimiento (se oculta solo a los timeout + 2 s).
- ⌃⌥Espacio (texto) no abre ni toca la conversación de voz.
- Telemetría: `~/.jarvis/conversaciones.jsonl` (un evento por transición, sin texto ni audio); resumen en `jv latencia`. Pruebas: `tests/test_conversacion.py`.
