# JARVIS — Upgrade 01: Instrumentación de latencia
(Diseñado por ChatGPT — proyecto Jarvis HQ, revisado por Claude. 2026-10-24)

Actúa como ingeniero principal del proyecto JARVIS.

Objetivo: Implementar un sistema ligero de medición de latencia para identificar los cuellos de botella reales del asistente, sin modificar su comportamiento.

## 1. Antes de editar
- Lee y respeta CLAUDE.md y memoria/estado_proyecto.md.
- Inspecciona el código real, las dependencias y los archivos existentes.
- Revisa especialmente bin/pensar.py, voz/jarvis_voz.py, voz/oido.py, bin/decir.py y bin/jv.
- Comprueba cómo se comunica cada módulo y qué pruebas existen.
- Revisa git status y conserva cualquier cambio previo (haz un commit de respaldo antes de empezar).
- No hagas refactors innecesarios ni reconstruyas componentes.

## 2. Implementación
Crea un módulo ligero de telemetría, bin/telemetria.py, usando únicamente librerías estándar de Python.
Registra la duración de estas etapas, cuando correspondan:
1. Captura de la frase y espera de silencio.
2. Detección local de "Jarvis" con faster-whisper base.
3. Transcripción remota con Groq.
4. Transcripción local de respaldo.
5. Clasificación y ejecución de comandos rápidos.
6. Ejecución completa del subproceso claude -p.
7. Ejecución completa de codex exec, cuando entre como fallback.
8. Preparación e inicio de la salida de voz.
9. Total desde que termina la frase del usuario hasta que Jarvis empieza a responder, si se puede medir de forma confiable.

Usa time.perf_counter_ns(). No afirmes medir solo el arranque en frío de Claude si solo se observa la duración completa del subproceso; explica las limitaciones.
Cada petición lleva un ID de correlación para unir sus etapas, incluso entre subprocesos.
Guarda en ~/.jarvis/metricas_latencia.jsonl: fecha y hora, ID, origen (voz/texto), etapa, duración en ms, ruta (rápido/claude/codex), estado (éxito/error/timeout/fallback).
NO guardes transcripciones, prompts, respuestas, audio, contraseñas, tokens ni llaves.
Si la telemetría falla, Jarvis debe seguir funcionando normal.

## 3. Comando de diagnóstico
Agrega: `bin/jv latencia`
Debe mostrar: muestras por etapa, p50, p90, mínimo y máximo, total por voz y por texto, y diferencia entre rutas (rápido, Claude, Codex). Si no hay suficientes muestras, dilo. No inventes estadísticas.

## 4. Restricciones
- Mantén --continue y el fallback a Codex.
- Conserva la personalidad de CLAUDE.md y no toques las reglas de permisos.
- No cambies la activación por voz, Spotify, modos, HUD ni notificaciones.
- No cambies el formato de historial.jsonl.
- Nada de servicios de pago, llamadas extra a modelos, dependencias pesadas ni LLM local.
- No modifiques memoria/ ni dinero.json (excepto actualizar memoria/estado_proyecto.md al final).
- Nada destructivo. Cambios pequeños y fáciles de revertir.

## 5. Pruebas obligatorias (con mocks cuando se pueda, sin decenas de llamadas reales)
- A. Comando rápido: registra etapas sin llamar al modelo.
- B. Claude: mide el subproceso sin cambiar su respuesta ni el contexto.
- C. Fallback: simula falla de Claude y verifica que registra Codex, sin gastar llamadas reales.
- D. Tolerancia: si falla el archivo de telemetría, Jarvis igual contesta.
- E. Privacidad: el JSONL no guarda contenido sensible.
- F. Regresión: los comandos existentes siguen funcionando.

## 6. Al terminar
- Haz commit de los cambios.
- Actualiza memoria/estado_proyecto.md (Ya funciona + Paso actual + fecha).
- Reinicia el módulo de voz para que tome los cambios (`open ~/Documents/Jarvis/Jarvis.command`).
- Dame un reporte breve: archivos tocados, qué etapas se miden exactas, cuáles no, pruebas y resultados, cómo usar bin/jv latencia y pendientes.

Implementa SOLO este upgrade, pruébalo y detente. No avances a streaming, cerebro persistente, memoria ni conversación continua.
