"""Oído de Jarvis: corta tu voz en frases y detecta la palabra "Jarvis" con Whisper (entiende español)."""
import re, time, queue, collections, pathlib
import numpy as np
import sounddevice as sd

RATE = 16000
CHUNK = 1600            # 100 ms
WAKE_RE = re.compile(r"\b(j[aá]rvis|jarvi|yarvis|yarvi|harvis|jarbis|yarbis|charvis|garvis|jervis|yervis|travis|jardis|yardis)\b", re.I)


class Oido:
    def __init__(self, mic=None, sensibilidad=3.0):
        self.cola = queue.Queue()
        self.sens = sensibilidad
        self.ruido = None
        self.ultima = None      # telemetría: (inicio de voz, último pedazo con voz, fin) en perf_counter_ns
        self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                                     blocksize=CHUNK, device=mic, callback=self._cb)

    def _cb(self, indata, frames, t, status):
        self.cola.put(indata[:, 0].copy())

    def __enter__(self):
        self.stream.start(); return self

    def __exit__(self, *a):
        self.stream.stop(); self.stream.close()

    def vaciar(self):
        while True:
            try: self.cola.get_nowait()
            except queue.Empty: return

    def frase(self, fin_silencio=0.7, max_dur=15.0, espera_inicio=None, disparador=None, nivel_cb=None,
              cerrar=None):
        """Regresa el audio de la siguiente frase (float32), None si nadie habló a tiempo,
        "DISPARO" si se presionó el atajo de teclado o "CERRAR" si existe la bandera `cerrar`."""
        previo = collections.deque(maxlen=4)
        voz, hablando, silencio, inicio, con_voz = [], False, 0, time.monotonic(), 0
        while True:
            if disparador is not None and pathlib.Path(disparador).exists():
                pathlib.Path(disparador).unlink(missing_ok=True)
                return "DISPARO"
            if cerrar is not None and pathlib.Path(cerrar).exists():
                return "CERRAR"             # quien llama la borra
            try:
                b = self.cola.get(timeout=0.3)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(b.astype(np.float32) ** 2)))
            if self.ruido is None:
                self.ruido = max(rms, 60.0)
            umbral = max(self.ruido * self.sens, 300.0)
            if nivel_cb:
                nivel_cb(rms, umbral, hablando)
            if not hablando:
                if rms > umbral:
                    hablando, silencio, voz, con_voz = True, 0, list(previo) + [b], 1
                    t_voz = t_ultima = time.perf_counter_ns()
                else:
                    self.ruido = 0.97 * self.ruido + 0.03 * rms
                    previo.append(b)
                    if espera_inicio and time.monotonic() - inicio > espera_inicio:
                        return None
            else:
                voz.append(b)
                if rms < umbral * 0.8:
                    silencio += 1
                else:
                    silencio, con_voz = 0, con_voz + 1
                    t_ultima = time.perf_counter_ns()
                duracion = len(voz) * 0.1
                if silencio * 0.1 >= fin_silencio or duracion >= max_dur:
                    if con_voz < 3:      # menos de 0.3 s de voz: ruidito
                        hablando, voz, con_voz = False, [], 0
                        continue
                    self.ultima = (t_voz, t_ultima, time.perf_counter_ns())
                    return np.concatenate(voz).astype(np.float32) / 32768.0


def transcribir(modelo, audio, idioma="es", prompt="Jarvis, señor.", preciso=False):
    segs, info = modelo.transcribe(audio, language=idioma, beam_size=5 if preciso else 1,
                                   vad_filter=preciso, condition_on_previous_text=False,
                                   initial_prompt=prompt, no_speech_threshold=0.5)
    texto = " ".join(s.text for s in segs if s.no_speech_prob < 0.7).strip()
    return "" if es_fantasma(texto) else texto


def separar(texto):
    """'Jarvis, abre Spotify' → (True, 'abre Spotify')"""
    m = WAKE_RE.search(texto)
    if not m:
        return False, ""
    resto = texto[m.end():].strip(" ,.;:!¡?¿-")
    if len(re.sub(r"[^\wáéíóúñ]", "", resto)) < 2:
        antes = texto[:m.start()].strip(" ,.;:!¡?¿-")
        resto = antes if len(antes.split()) >= 2 else ""
    return True, resto


# ---------- frases fantasma que Whisper inventa con ruido o silencio ----------
FANTASMAS = re.compile(r"^\W*(suscr[ií]bete.*|gracias por ver.*|subt[ií]tulos.*|amara\.org.*|"
                       r"gracias\.?|thanks for watching.*|thank you\.?|m[uú]sica|\.+|"
                       r"no olvides suscribirte.*|dale like.*)\W*$", re.I)

def es_fantasma(texto):
    return not texto.strip() or bool(FANTASMAS.match(texto.strip()))


# ---------- oído en la nube (Groq, gratis) ----------
VOCAB = ("Jarvis, señor. Abre YouTube, Spotify, Classroom, Minecraft, Twitch, Gmail, TikTok, Instagram, "
         "WhatsApp, ChatGPT. Modo gamer, modo estudio. Pendientes, tarea, rutina, panel.")

# Groq a veces "transcribe" el silencio repitiendo su propio prompt («Pendientes, tarea, rutina, panel.»).
def _palabras(texto):
    import unicodedata
    plano = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plano)

PALABRAS_VOCAB = frozenset(_palabras(VOCAB))

def solo_vocabulario(texto):
    """True si son 3+ palabras (sin contar «jarvis» ni «señor») y TODAS salen de VOCAB: eco del prompt.
    «Jarvis, modo gamer» o «abre Spotify» (2 palabras) siguen siendo órdenes."""
    p = [w for w in _palabras(texto) if w not in ("jarvis", "senor")]
    return len(p) >= 3 and all(w in PALABRAS_VOCAB for w in p)

def _wav(audio):
    import io, wave
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return b.getvalue()

def transcribir_nube(audio, llave, idioma="es"):
    """Whisper large-v3-turbo en Groq. Regresa texto o None si falla."""
    import json, urllib.request, uuid
    if not llave:
        return None
    limite = "----jarvis" + uuid.uuid4().hex
    campos = {"model": "whisper-large-v3-turbo", "language": idioma, "prompt": VOCAB,
              "response_format": "json", "temperature": "0"}
    cuerpo = b""
    for k, v in campos.items():
        cuerpo += f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    cuerpo += (f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="voz.wav"\r\n'
               f'Content-Type: audio/wav\r\n\r\n').encode() + _wav(audio) + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=cuerpo,
                                 headers={"Authorization": f"Bearer {llave}",
                                          "Content-Type": f"multipart/form-data; boundary={limite}",
                                          "User-Agent": "jarvis-jp"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r).get("text", "").strip()
    except Exception:
        return None
