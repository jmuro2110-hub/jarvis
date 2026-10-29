"""Barge-in (upgrade 06): oír «Jarvis, …» mientras Jarvis habla.

Sin threads ni otro stream del micrófono: `Hablador.tick()` llama `Vigia.revisar()` mientras hay un hijo de
voz vivo, y el vigía consume `oido.cola` (que el callback de sounddevice sigue llenando). Una inferencia de
Whisper base a la vez (~0.7 s en el Intel; mientras, el callback no pierde frames).

Filtros, en este orden; con duda NO interrumpe:
  a) «Jarvis» en las dos primeras palabras del candidato (no a media frase).
  b) anti-eco por texto: si la mayoría de las palabras (sin «Jarvis») están en el pedazo que Jarvis está
     diciendo, es su propia voz.
  c) si ese pedazo trae algo que case con «Jarvis», se exige además una orden de la lista.
  d) se ignoran ~300 ms al empezar cada pedazo.
  e) es_fantasma de siempre.
No hay cancelación de eco (AEC): con bocinas puede no alcanzar. Nunca se toca `oido.ruido` (IDLE/FOLLOW_UP).
"""
import collections, queue, re, time
import numpy as np

from oido import WAKE_RE, es_fantasma, transcribir

BLOQUE_SEG = 0.1                 # cada frame de la cola son 100 ms
SILENCIO_FIN = 0.5               # candidato = segmento cerrado por 0.5 s de silencio…
VENTANA = 2.5                    # …o 2.5 s de voz continua (con bocinas casi nunca hay silencio)
MIN_VOZ = 3                      # 0.3 s de voz mínimo
IGNORAR_INICIO = 0.3             # tras empezar cada pedazo
MAX_FRAMES = 30                  # buffer máximo ~3 s

CALLAR_RE = re.compile(r"^(c[aá]llate|calla|deja de hablar|silencio|ya c[aá]llate|basta)$")
ESPERA_RE = re.compile(r"^(esp[eé]rame|espera|un momento|un segundo)$")
CORRECCION_RE = re.compile(r"^(no\W+mejor|mejor|no)\b\W*")


def palabras(t):
    return re.findall(r"[a-záéíóúñü]+", (t or "").lower())


def normal(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip(" .,;:!¡?¿-")


def orden_explicita(resto):
    """¿Trae una orden de la lista (callar / espera / corrección)? Para el filtro c)."""
    r = normal(resto)
    return bool(CALLAR_RE.match(r) or ESPERA_RE.match(r) or CORRECCION_RE.match(r))


def tipo_de(resto):
    """callar / espera / solo_jarvis / orden (con el texto de la orden, sin «no, mejor»).
    Se compara en minúsculas, pero la orden conserva su texto original (Claude recibe «Francia», no «francia»)."""
    original = re.sub(r"\s+", " ", resto or "").strip(" .,;:!¡?¿-")
    r = original.lower()
    if len(re.sub(r"[^\wáéíóúñü]", "", r)) < 2:
        return "solo_jarvis", ""
    if CALLAR_RE.match(r):
        return "callar", ""
    if ESPERA_RE.match(r):
        return "espera", ""
    x = re.sub(CORRECCION_RE.pattern, "", original, count=1, flags=re.I).strip(" .,;:!¡?¿-")
    if not x:
        return "espera", ""          # «Jarvis, no» a secas: se calla y escucha, no inventa
    return "orden", x


class Interrupcion:
    def __init__(self, tipo, resto, audio, cortado, t_voz):
        self.tipo, self.resto, self.audio, self.cortado, self.t_voz = tipo, resto, audio, cortado, t_voz
        self.t_parada = None
        self.t_fin_orden = None      # 09A: fin estimado de la voz de JP en el micrófono (reloj del vigía)


class Vigia:
    def __init__(self, cola, modelo, sens=3.0, idioma="es", transcribir=transcribir, reloj=time.perf_counter,
                 registrar=None, max_frames_tick=60):
        self.cola, self.modelo, self.sens, self.idioma = cola, modelo, sens, idioma
        self.transcribir, self.reloj = transcribir, reloj
        self.registrar = registrar or (lambda *a, **k: None)
        self.max_frames_tick = max_frames_tick
        self.ruido = None                            # piso PROPIO, medido mientras Jarvis habla
        self.ocupado = False                         # una inferencia a la vez
        self.silencio_cierre = 0
        self._reset()

    def _reset(self):
        self.previo = collections.deque(maxlen=4)
        self.voz = collections.deque(maxlen=MAX_FRAMES)
        self.hablando, self.silencio, self.con_voz, self.t_voz = False, 0, 0, None

    def _sacar(self):
        frames = []
        for _ in range(self.max_frames_tick):
            try:
                frames.append(self.cola.get_nowait())
            except queue.Empty:
                break
        return frames

    def _segmentar(self, b):
        """Igual que oido.frase() pero sin bloquear. Regresa (audio, cortado, t_voz) al cerrar un candidato."""
        rms = float(np.sqrt(np.mean(b.astype(np.float32) ** 2)))
        if self.ruido is None:
            self.ruido = max(rms, 60.0)
        umbral = max(self.ruido * self.sens, 300.0)
        if not self.hablando:
            if rms > umbral:
                self.hablando, self.silencio, self.con_voz = True, 0, 1
                self.voz = collections.deque(list(self.previo) + [b], maxlen=MAX_FRAMES)
                self.t_voz = self.reloj()
            else:
                self.ruido = 0.97 * self.ruido + 0.03 * rms
                self.previo.append(b)
            return None
        self.voz.append(b)
        if rms < umbral * 0.8:
            self.silencio += 1
        else:
            self.silencio, self.con_voz = 0, self.con_voz + 1
        por_silencio = self.silencio * BLOQUE_SEG >= SILENCIO_FIN
        por_ventana = len(self.voz) * BLOQUE_SEG >= VENTANA
        if not (por_silencio or por_ventana):
            return None
        audio, con_voz, t_voz = list(self.voz), self.con_voz, self.t_voz
        self.silencio_cierre = self.silencio         # 09A: para estimar el fin de la orden
        self._reset()
        if con_voz < MIN_VOZ:
            return None                              # ruidito
        return np.concatenate(audio).astype(np.float32) / 32768.0, por_ventana and not por_silencio, t_voz

    def revisar(self, pedazo, t_pedazo):
        """Consume lo que haya en la cola. Regresa una Interrupcion confirmada o None."""
        if self.ocupado:
            return None
        frames = self._sacar()
        if t_pedazo is not None and self.reloj() - t_pedazo < IGNORAR_INICIO:
            self._reset()                            # d) el arranque de cada pedazo no cuenta
            return None
        for i, b in enumerate(frames):
            seg = self._segmentar(b)
            if seg is not None:
                # 09A: fin estimado de la voz = ahora − (silencio final + frames sacados sin revisar + cola)
                try:
                    atras = self.silencio_cierre + len(frames) - i - 1 + self.cola.qsize()
                except NotImplementedError:
                    atras = self.silencio_cierre + len(frames) - i - 1
                t_fin = self.reloj() - atras * BLOQUE_SEG
                det = self._evaluar(seg, pedazo)
                if det is not None:
                    det.t_fin_orden = t_fin
                    return det                       # un candidato por segmento; lo demás queda en la cola
        return None

    def _evaluar(self, seg, pedazo):
        audio, cortado, t_voz = seg
        self.ocupado = True
        t0 = self.reloj()
        try:
            texto = self.transcribir(self.modelo, audio, self.idioma)
        except Exception:
            texto = None                             # Whisper falló: la voz sigue, nada se interrumpe
        finally:
            self.ocupado = False
        ms = (self.reloj() - t0) * 1000
        motivo, det = self._filtrar(texto, pedazo, audio, cortado, t_voz)
        self.registrar("barge_deteccion", ms, extra={"motivo": motivo})
        return det

    def _filtrar(self, texto, pedazo, audio, cortado, t_voz):
        if texto is None or es_fantasma(texto):
            return "fantasma", None                                   # e)
        m = WAKE_RE.search(texto)
        if not m:
            return "sin_jarvis", None
        if len(palabras(texto[:m.start()])) > 1:
            return "jarvis_en_medio", None                            # a)
        resto = texto[m.end():]
        mias = palabras(resto)
        dicho = set(palabras(pedazo))
        if mias and sum(w in dicho for w in mias) * 2 > len(mias):
            return "eco", None                                        # b)
        if WAKE_RE.search(pedazo or "") and not orden_explicita(resto):
            return "eco_jarvis", None                                 # c)
        tipo, x = tipo_de(resto)
        return "confirmado", Interrupcion(tipo, x, audio, cortado, t_voz)
