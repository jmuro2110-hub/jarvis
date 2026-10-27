"""Conversación continua por voz (upgrade 04): máquina de estados, lógica pura.

Sin micrófono, sin `say`, sin hilos: jarvis_voz.py la conecta en su ciclo síncrono. El reloj se inyecta
(monotónico por defecto) para probarla con mocks.

    IDLE ──activar()──▶ ACTIVATED ──iniciar_turno()──▶ PROCESSING ──hablar()──▶ SPEAKING
                                                          │                        │
                                                          └──respuesta_terminada()─┤
                                                                                   ▼
                     IDLE ◀── CLOSED ◀──(timeout · manual · turnos · tiempo · callar…)── FOLLOW_UP
                                                         FOLLOW_UP ──iniciar_turno()──▶ PROCESSING
"""
import re, time, uuid

IDLE, ACTIVATED, PROCESSING, SPEAKING, FOLLOW_UP, CLOSED = (
    "IDLE", "ACTIVATED", "PROCESSING", "SPEAKING", "FOLLOW_UP", "CLOSED")

# Cierre manual: frases inequívocas, con o sin «Jarvis». Nunca "no" ni "gracias".
CIERRE_RE = re.compile(r"^(?:(?:oye |hey )?jarvis\W*)?(terminamos|cierra la conversaci[oó]n|eso es todo)"
                       r"(?:\W*jarvis)?$")

# Categorías de comando rápido que terminan la conversación.
CIERRA_CATEGORIA = {"resumen": "resumen", "modo_dormir": "dormir", "callar": "callar"}


class TransicionInvalida(RuntimeError):
    pass


def normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").lower()).strip(" .,!¿?¡")


def es_cierre(texto):
    return bool(CIERRE_RE.match(normalizar(texto)))


class Conversacion:
    def __init__(self, continua=True, timeout=15.0, max_turnos=5, duracion_max=180.0,
                 reloj=time.monotonic, registrar=None):
        self.continua, self.timeout = bool(continua), float(timeout)
        self.max_turnos, self.duracion_max = int(max_turnos), float(duracion_max)
        self.reloj = reloj
        self._registrar = registrar or (lambda *a, **k: None)
        self.estado = IDLE
        self._limpiar()

    @classmethod
    def desde_config(cls, c, **kw):
        return cls(continua=c.get("conversacion_continua", True),
                   timeout=c.get("timeout_seguimiento_seg", 15), max_turnos=c.get("max_turnos", 5),
                   duracion_max=c.get("duracion_maxima_seg", 180), **kw)

    def _limpiar(self):
        self.id, self.turnos, self.fallos = None, 0, 0
        self.t0 = self.fin_ventana = None
        self.previo = None            # solo la categoría "spotify" del turno anterior, nunca el texto
        self.previo_sin_herramientas = False   # upgrade 05: el turno anterior fue por la ruta sin herramientas

    def _evento(self, evento, **kw):
        try:
            self._registrar(evento, self.id, self.turnos, **kw)
        except Exception:
            pass                      # la telemetría nunca tumba la conversación

    def _pasar(self, nuevo, desde):
        if self.estado not in desde:
            raise TransicionInvalida(f"{self.estado} → {nuevo}")
        self.estado = nuevo

    # ---------- transiciones ----------
    def activar(self):
        """«Jarvis» o ⌃⌥J desde IDLE. Si ya hay conversación, no abre otra (False)."""
        if self.estado != IDLE:
            return False
        self._limpiar()
        self.id, self.t0 = uuid.uuid4().hex[:12], self.reloj()
        self.estado = ACTIVATED
        self._evento("activada")
        return True

    def iniciar_turno(self):
        self._pasar(PROCESSING, (ACTIVATED, FOLLOW_UP))
        self.turnos += 1
        self.fallos = 0
        self.fin_ventana = None       # el contador no corre mientras se procesa

    def hablar(self):
        self._pasar(SPEAKING, (PROCESSING,))

    def respuesta_terminada(self, categoria=None, cerrar=False):
        """Ya terminó la voz (decir() regresó) o la acción sin voz. True = se abre FOLLOW_UP."""
        self._pasar(self.estado, (PROCESSING, SPEAKING))
        self.previo = "spotify" if categoria == "spotify" else None
        motivo = ("callar" if cerrar else CIERRA_CATEGORIA.get(categoria)
                  or (None if self.continua else "desactivada")
                  or ("turnos" if self.turnos >= self.max_turnos else None)
                  or ("tiempo" if self.transcurrido() >= self.duracion_max else None))
        if motivo:
            self.cerrar(motivo)
            return False
        self.estado = FOLLOW_UP
        self.fin_ventana = min(self.reloj() + self.timeout, self.t0 + self.duracion_max)
        return True

    def ventana_lista(self, ms=None):
        """Ya se vació la cola y se está escuchando. ms = latencia que agregó el gestor."""
        if self.estado == FOLLOW_UP:
            self._evento("seguimiento_abre", ms=ms)

    def restante(self):
        if self.estado != FOLLOW_UP or self.fin_ventana is None:
            return 0.0
        return max(0.0, self.fin_ventana - self.reloj())

    def vencio(self):
        """La ventana se acabó sin turno válido: por los 15 s o por el tope de 3 minutos."""
        self.cerrar("tiempo" if self.transcurrido() >= self.duracion_max else "timeout")

    def transcurrido(self):
        return 0.0 if self.t0 is None else self.reloj() - self.t0

    def descartar(self, motivo):
        """Ruido, otra voz, frase fantasma o «Jarvis» solo: no cuenta turno ni reinicia los 15 s."""
        if self.estado == FOLLOW_UP:
            self._evento("seguimiento_descartado", motivo=motivo)

    def fallo_transcripcion(self):
        """Transcripción vacía o fallida. Dos seguidas cierran. True = la ventana sigue."""
        if self.estado not in (FOLLOW_UP, ACTIVATED):
            return False
        self.fallos += 1
        if self.fallos >= 2:
            self.cerrar("transcripcion")
            return False
        self.descartar("fantasma")
        return True

    def detectado(self, ms=None):
        if self.estado == FOLLOW_UP:
            self._evento("seguimiento_detectado", ms=ms)

    def cerrar(self, motivo):
        """CLOSED y de vuelta a IDLE. No hace nada si no hay conversación."""
        if self.estado == IDLE:
            return
        self.estado = CLOSED
        self._evento("cierre", motivo=motivo)
        self._limpiar()
        self.estado = IDLE

    @property
    def abierta(self):
        return self.estado != IDLE
