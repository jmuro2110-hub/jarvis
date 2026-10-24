# JARVIS — Upgrade 02: Seguridad y control de operaciones sensibles
Actúa como arquitecto de seguridad y desarrollador principal de JARVIS.

OBJETIVO: Incorporar controles verificables por código para las acciones sensibles del asistente personal, sin romper sus funcionalidades actuales ni obstaculizar las sesiones interactivas de Claude Code usadas para desarrollar el proyecto.

Este es exclusivamente el Upgrade 02. No optimices latencia, no implementes streaming y no agregues nuevas integraciones.
1. Inspección obligatoria
Antes de modificar archivos:
- Lee CLAUDE.md y estado_proyecto.md si existe.
- Ejecuta git status y conserva los cambios existentes.
- Revisa bin/pensar.py, bin/jv, bin/abrir.py si existe, scripts de bin/, voz/jarvis_voz.py y los módulos de control de macOS.
- Inspecciona .claude/settings.json, permisos y hooks ya configurados.
- Identifica exactamente qué herramientas pueden ejecutar Claude y Codex durante el funcionamiento cotidiano.
- Revisa si los comandos rápidos pueden realizar operaciones sensibles.
- Comprueba cómo se ejecuta claude -p y cómo se activa el fallback codex exec.
No presupongas que las reglas escritas en CLAUDE.md son suficientes.
2. Separar desarrollo de uso cotidiano
Debemos distinguir dos contextos:

Modo desarrollo: cuando JP abre Claude Code manualmente en el proyecto para programar Jarvis.

Modo asistente: cuando una consulta llega desde voz, HUD, atajos o ejecución automática.

Implementa una diferenciación verificable entre ambos contextos, utilizando configuración específica del proceso si corresponde.

Los controles del asistente deben aplicarse también a consultas recibidas por texto y a las ejecuciones automáticas.

No deben desactivar las herramientas legítimas que JP utiliza manualmente para desarrollar Jarvis.

La separación no debe permitir que una respuesta del modelo se otorgue permisos por sí misma.
3. Política centralizada
Crea preferentemente bin/politica.py, salvo que el repositorio ya tenga un módulo equivalente.

Implementa una política determinista que evalúe operaciones estructuradas, no solamente palabras encontradas en el mensaje del usuario.

Clasificación:
PERMITIDO SIN CONFIRMACIÓN
- Abrir aplicaciones.
- Abrir sitios web mediante el perfil autorizado.
- Controlar Spotify y volumen.
- Consultar información.
- Activar o desactivar modos.
- Ejecutar funciones locales inocuas ya autorizadas.
- Organizar archivos mediante operaciones no destructivas, siempre que respeten los límites de acceso.
REQUIERE CONFIRMACIÓN EXPLÍCITA
- Enviar correos mediante Gmail.
- Enviar mensajes por WhatsApp.
- Enviar o entregar contenido mediante Classroom.
- Eliminar archivos o carpetas.
- Vaciar la papelera.
- Ejecutar compras, pagos, transferencias o cualquier gasto.
- Otras operaciones irreversibles o con consecuencias externas equivalentes.
PROHIBIDO SIEMPRE
- Publicar contenido en Instagram.
- Publicar contenido en TikTok.
- Publicar contenido en Snapchat.
- Conectar Snapchat.
- Evadir deliberadamente estas restricciones.
- Transferir información de la cuenta escolar a la personal o viceversa sin una autorización y un flujo expresamente diseñado para ello.
Estas prohibiciones no admiten confirmación excepcional.

Cualquier operación sensible desconocida debe quedar bloqueada hasta que sea clasificada.
4. Confirmación confiable
Para una operación sensible que ya esté soportada por el proyecto:
1. Preparar la acción sin ejecutarla.
2. Mostrar a JP el contenido completo y el destino.
3. Solicitar confirmación explícita desde una interfaz local confiable.
4. Ejecutar únicamente la acción aprobada.
5. Registrar el resultado.
La autorización debe vincularse a una acción concreta, su destino y su contenido exacto.

Debe caducar y ser de un solo uso.

Un «sí» encontrado en un documento, página web, correo, respuesta del modelo o historial nunca constituye autorización.

Tampoco debe bastar una frase ambiental detectada por el micrófono para ejecutar operaciones sensibles.

Si todavía no existe una interfaz confiable para obtener la autorización, bloquea la ejecución y explica que requiere aprobación manual. No simules una autorización.

No implementes servicios nuevos de envío, compra o eliminación solamente para probar el sistema.
5. Separación de cuentas
Conserva la lógica de perfiles de Chrome que ya funciona.
- Classroom y Meet: perfil escolar.
- Actividades personales: perfil personal.
- Para correo, calendarios o archivos de Google, verifica la identidad del mundo antes de actuar.
- Si no se puede determinar la cuenta, pregunta y no ejecutes la operación.
- No utilices un fallback silencioso al perfil personal para acciones escolares.
Prueba que las rutas existentes de bin/jv abrir no presenten regresiones.
6. Control de herramientas de Claude Code
Investiga la configuración real de permisos de la versión instalada.

Evalúa utilizar hooks síncronos PreToolUse para interceptar operaciones peligrosas antes de su ejecución.

Documentación de referencia:
https://code.claude.com/docs/en/hooks
https://code.claude.com/docs/en/permissions

Prioriza una lista reducida de herramientas y operaciones autorizadas para el asistente cotidiano.

No confíes únicamente en expresiones regulares que detecten rm, porque borrar también puede hacerse mediante Python, AppleScript, utilidades alternativas o herramientas de archivos.

Considera también las rutas indirectas mediante Bash, osascript, automatización de interfaces y herramientas externas.

Cuando no puedas garantizar que una operación se está ejecutando mediante una ruta protegida, bloquéala en el contexto del asistente.

No instales reglas globales que rompan el desarrollo interactivo.

No uses --dangerously-skip-permissions.
7. Seguridad del fallback Codex
Audita específicamente esta ejecución:

codex exec --skip-git-repo-check --sandbox workspace-write

Determina si Codex necesita realmente permiso de escritura durante una consulta cotidiana.

Prioriza un sandbox de solo lectura para el fallback conversacional.

Si esto impide actualizar pendientes o memoria, no le otorgues permisos generales de escritura para compensarlo. Conserva las escrituras autorizadas mediante herramientas específicas y reporta cualquier funcionalidad del fallback que deba quedar temporalmente limitada.

Comprueba que una restricción aplicada a Claude no desaparezca simplemente porque entró Codex.
8. Auditoría
Registra las decisiones de seguridad en un archivo privado dentro de:

~/.jarvis/

Incluye fecha, tipo de acción, autorización o bloqueo, origen y resultado.

No registres contraseñas, tokens, mensajes completos ni información privada innecesaria.

Conserva permisos restrictivos sobre los archivos sensibles.

No modifiques el formato de historial.jsonl ni el de metricas_latencia.jsonl.
9. Pruebas obligatorias
Crea pruebas automatizadas con mocks, sin enviar mensajes reales, publicar, borrar archivos importantes ni gastar dinero.

Comprueba los siguientes escenarios:

A. «Abre Spotify» → permitido.

B. «Activa modo gamer» → permitido.

C. «Desactiva modo gamer» → desactiva correctamente.

D. «Manda este correo» → solicita aprobación y no envía antes de obtenerla.

E. «Borra mi carpeta Descargas» → no ejecuta sin aprobación.

F. «Compra una suscripción» → no ejecuta sin aprobación.

G. «Publica esto en Instagram» → denegado incluso ante una confirmación del usuario.

H. «Conecta Snapchat» → denegado.

I. Una acción escolar con cuenta personal → bloqueada hasta resolver la identidad correcta.

J. Una autorización antigua o para contenido distinto → rechazada.

K. Una instrucción maliciosa encontrada en una página o documento → no modifica permisos.

L. Un intento de evitar controles mediante una herramienta alternativa → bloqueado dentro de los límites realmente implementados.

M. Fallback a Codex → no amplía privilegios de manera involuntaria.

N. Sesión interactiva de desarrollo → conserva el funcionamiento esperado y los permisos explícitos de JP.

O. Regresión → ejecuta nuevamente las 19 pruebas del Upgrade 01 y las pruebas previas disponibles.

Si alguna ruta de ejecución no puede protegerse razonablemente, repórtala como limitación abierta. No afirmes que el sistema es invulnerable.
10. Restricciones
- Mac mini Intel 2018, 16 GB RAM.
- Sin servicios de pago adicionales.
- Sin librerías pesadas.
- Mantener Claude Pro y Codex como están.
- Conservar --continue.
- Mantener todos los comandos rápidos existentes.
- No agregar latencia perceptible a las operaciones habituales.
- Mantener separación escolar/personal.
- No modificar archivos privados innecesariamente.
- No realizar acciones irreversibles durante las pruebas.
- Evitar cambios amplios o refactors ajenos a seguridad.
11. Entrega
Cuando termines, informa:
1. Archivos creados y modificados.
2. Qué operaciones quedan protegidas mediante código.
3. Qué herramientas quedaron restringidas en el modo asistente.
4. Qué diferencias existen entre los permisos de Claude y Codex.
5. Qué rutas aún podrían evitar los controles.
6. Cuáles pruebas pasaron y cuáles fallaron.
7. Qué funcionalidades existentes cambiaron, si alguna.
8. Cómo verificar manualmente el sistema sin ejecutar acciones peligrosas.
Actualiza estado_proyecto.md al cerrar el upgrade, si existe.

No avances al Upgrade 03.

Prioridad absoluta: protección real, cambios mínimos, cero regresiones y ninguna falsa garantía de seguridad.

3. Criterio para aceptar el Upgrade 02
No basta con que Jarvis nos diga «ahora está protegido».

Hay tres resultados que quiero comprobar en su reporte:
- Separación de permisos: Claude Code puede seguir desarrollando, pero una consulta cotidiana no recibe automáticamente privilegios de desarrollador.
- Bloqueo antes de ejecutar: una acción prohibida no llega a ejecutarse, aunque el modelo la solicite.
- Cobertura de Claude y Codex: entrar al fallback no elimina las restricciones.
Y una limitación que debemos reconocer: mientras un proceso tenga acceso irrestricto a herramientas del sistema, sus credenciales y una shell general, ningún filtro de texto proporciona aislamiento absoluto. Eso exige restricciones reales sobre las capacidades disponibles, no solo mejores instrucciones. 





Mi objetivo inmediato: terminar este upgrade sin afectar tus 19 pruebas anteriores. Después sí vamos directamente por los 13.45 segundos de latencia; esa será nuestra siguiente prioridad de experiencia de usuario.

## Ajustes de Claude (revisor) — obligatorios
- ANTES de tocar nada: haz un commit de respaldo ("respaldo antes de upgrade 02") para poder revertir todo con git.
- Si el trabajo resulta demasiado grande para hacerlo bien en una sola pasada, divídelo: termina y prueba la Parte A (política centralizada + modo asistente vs desarrollo + fallback Codex en solo lectura), reporta y DETENTE. La Parte B (confirmación confiable de un solo uso + auditoría completa) se hace en otra sesión.
- La prueba C ("desactiva modo gamer") ya no activa el modo: hoy comando_rapido() lo manda al cerebro. Verifica que así siga.
- Al terminar, reinicia la voz (open ~/Documents/Jarvis/Jarvis.command) y comprueba que "Jarvis, abre YouTube" siga funcionando.
- Las llaves viven en ~/.jarvis/secretos.env: nunca las leas, imprimas ni copies a otro lado.
