# Estado del proyecto Jarvis — el hilo conductor

> Este archivo es la memoria del PROYECTO (no de JP). Cualquier chat nuevo (Claude, ChatGPT o Jarvis) empieza leyendo esto.
> Se actualiza al cerrar cada paso: qué se hizo, qué se decidió, qué sigue.

**Última actualización:** 2026-10-24

## Visión
- Corto plazo: el Jarvis más cercano al de Iron Man posible en la Mac de JP, con lo que hay y máximo $200 MXN/mes extra.
- Mediano plazo: Jarvis como centro de control de un negocio con IA que genere $1,500,000 MXN en ~1 año (meta: coche). Modelo de negocio aún sin decidir.

## Equipo de trabajo (roles)
| Quién | Rol |
|---|---|
| Jarvis (Claude Code en ~/Documents/Jarvis) | Ejecuta. ÚNICO que edita código. |
| ChatGPT — proyecto "Jarvis HQ" (modo Chat, nube, GPT-6 Astra alto) | Arquitecto y estratega. Diseña y da prompts para Jarvis. |
| Claude (chat de la app) | Revisor y constructor: revisa propuestas de ChatGPT, arregla lo que se rompe. |
Flujo: ChatGPT propone → Claude revisa → JP pega el prompt en Jarvis → Jarvis lo hace → se prueba → se actualiza este archivo.

## Ya funciona (2026-10-23/24)
- Base: CLAUDE.md (personalidad estilo Jarvis/Tony, reglas), memoria, módulos, git local.
- Voz: "Jarvis, …" de un jalón o solo "Jarvis" + tin. Detección local Whisper base; orden con Groq whisper-large-v3-turbo (gratis); filtro de frases fantasma.
- Cerebro: `claude -p` (con --continue si <30 min) y respaldo automático con Codex (ChatGPT). Codex con sesión iniciada.
- Comandos rápidos sin IA: apps, Spotify, volumen, hora, modos (gamer/estudio/trabajo/dormir), rutina, panel.
- Dos mundos: páginas se abren en el perfil de Chrome correcto (Classroom/Meet → escuela; lo demás → personal jmuro2110). Probado OK.
- Iniciativa: resumen matutino 7:30, vigía (Minecraft 1/2/3 h, entregas), avisos Mac + iPhone (ntfy, canal en ~/.jarvis/secretos.env).
- Panel Jarvis HQ (Ctrl+Alt+H): meta del coche, pendientes, clima, juego, últimas pláticas.
- Hammerspoon: Ctrl+Alt+J hablar, Ctrl+Alt+Espacio escribir, Ctrl+Alt+H panel, Ctrl+Alt+. callar. (Teclado Windows: Alt = Opción.)
- Arranque automático (Jarvis.command, una sola instancia, se reinicia solo).

## Decisiones tomadas
- No IA pesada local (Mac Intel). Nube para lo pesado, local para lo simple.
- openWakeWord descartado (no reconoce el acento de JP). Detección con Whisper.
- Procesos dentro de Terminal (no launchd) por permisos de micrófono/Documentos.
- ElevenLabs se pospone: primero conversación y velocidad (acuerdo con ChatGPT).
- ChatGPT nunca edita archivos; sin carpeta local en su proyecto.

## Pendientes conocidos
- [ ] JP: sacar llave de Groq y guardarla (`chmod +x ~/Documents/Jarvis/bin/jv && ~/Documents/Jarvis/bin/jv llave groq`), reiniciar Jarvis.
- [ ] Hammerspoon: confirmar permiso de Accesibilidad.
- [ ] iPhone: app ntfy suscrita al canal.
- [ ] Datos de JP: link app análisis facial, app de modos teclado/mouse (Logitech G HUB), ciudad para clima.
- [ ] Subir Jarvis a GitHub privado (jmuro2110-hub/jarvis) para que ChatGPT lea el código real.

## Roadmap de upgrade (diagnóstico de ChatGPT, 2026-10-24, aprobado)
1. **Conversación continua**: seguir la plática sin repetir "Jarvis", entender "esa/la primera", barge-in (interrumpirlo). ← PRIORIDAD
2. **Velocidad**: medir latencia por etapa; el arranque en frío de `claude -p` es el sospechoso principal.
3. **Memoria que aprende**: permanente vs reciente vs recuerdos relevantes.
4. **Iniciativa con criterio**: prioridades, silencio, no repetir avisos, contexto (modo, pendientes).
5. **Autonomía real en macOS** con candados por código (no solo instrucciones).
6. Después: voz premium (ElevenLabs), recordatorios con hora, Classroom.

## Paso actual
- Se le respondió a ChatGPT cómo funciona el cerebro (proceso en frío por pregunta, --continue, sin modo conversación, sin barge-in). Esperando su roadmap detallado y el PRIMER prompt para Jarvis. Claude lo revisa antes de aplicarlo.

## Fase B — Negocio (después del upgrade)
- Meta $1,500,000 MXN; fecha_meta 2027-10-23 en memoria/dinero.json.
- Interés inicial: automatizaciones con IA para negocios locales en México. Sin decidir.
