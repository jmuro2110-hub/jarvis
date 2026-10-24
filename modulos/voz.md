# Módulo Voz

- `voz/jarvis_voz.py` (arranca con `Jarvis.command`).
- Activación: decir "Jarvis, …" (detección con Whisper `base`, entiende español; voz/oido.py) o ⌃⌥J. Se puede dar la orden de un jalón: "Jarvis, abre Spotify".
- Transcripción de la orden: Groq whisper-large-v3-turbo (gratis, GROQ_API_KEY en ~/.jarvis/secretos.env, se guarda con `jv llave groq`); si falla, faster-whisper local (`small`). La detección de "Jarvis" siempre es local (`base`).
- Filtro de frases fantasma ("Suscríbete", "Gracias por ver"…) en voz/oido.py.
- Sensibilidad: JARVIS_SENSIBILIDAD (3.0; súbela si el ruido lo activa). Prueba: voz/prueba_mic.py.
- Cerebro: `bin/pensar.py` → Claude (continúa la conversación si fue hace menos de 30 min) y, si topa límite o falla, ChatGPT con Codex.
- Voz: `bin/decir.py` → ElevenLabs si hay ELEVENLABS_API_KEY en ~/.jarvis/secretos.env y crédito del mes; si no, `say` de macOS (Juan).
