# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "onnxruntime<=1.23.2",
#   "faster-whisper>=1.1",
#   "sounddevice>=0.5",
#   "numpy",
# ]
# ///
"""
J.A.R.V.I.S. — oídos
"Jarvis, …" (o el atajo Ctrl+Opción+J) → transcribe en la Mac →
comando rápido sin IA, o cerebro (Claude, con ChatGPT de respaldo) → voz.
"""
import os, re, sys, time, datetime, pathlib, subprocess

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "bin"))
sys.path.insert(0, str(AQUI))
from comun import CASA, JARVIS, config, estado, log, abrir_url, mundo_de            # noqa: E402
from decir import decir, callar                               # noqa: E402
from pensar import pensar, primera_linea                      # noqa: E402
from modo import modo, disponibles                            # noqa: E402
import telemetria as tm                                       # noqa: E402

SENSIBILIDAD = float(os.environ.get("JARVIS_SENSIBILIDAD", "3.0"))  # más alto = necesita voz más fuerte
MIC = os.environ.get("JARVIS_MIC")
MIC = int(MIC) if MIC and MIC.isdigit() else None
MODELO_WHISPER = os.environ.get("JARVIS_WHISPER", "small")
DISPARADOR = CASA / "escuchar"          # el atajo de teclado crea este archivo
PID = CASA / "voz.pid"


# ---------- comandos rápidos (sin IA) ----------
def osa(s):
    return subprocess.run(["osascript", "-e", s], capture_output=True, text=True)

APPS = {"minecraft": "Minecraft", "spotify": "Spotify", "safari": "Safari", "chrome": "Google Chrome",
        "whatsapp": "WhatsApp", "terminal": "Terminal", "ajustes": "System Settings",
        "configuración": "System Settings", "finder": "Finder", "chatgpt": "ChatGPT",
        "claude": "Claude", "notas": "Notes", "calculadora": "Calculator", "música": "Spotify"}
WEBS = {"youtube": "https://youtube.com", "twitch": "https://twitch.tv",
        "classroom": "https://classroom.google.com", "gmail": "https://mail.google.com",
        "instagram": "https://instagram.com", "tiktok": "https://tiktok.com",
        "github": "https://github.com/jmuro2110-hub",
        "drive": "https://drive.google.com", "calendario": "https://calendar.google.com"}

def comando_rapido(t):
    t = t.lower().strip(" .,!¿?¡")
    t = re.sub(r"^(oye |hey )?jarvis[, ]*", "", t)
    c = config()
    if re.fullmatch(r"(cállate|silencio|ya|basta|para)", t):
        callar(); return ""
    if re.search(r"\b(pausa|pausar|para la música|detén la música|quita la música)\b", t):
        osa('tell application "Spotify" to pause'); return "Música en pausa, señor."
    if re.search(r"\b(siguiente canción|siguiente|salta(la)?( canción)?|cambia(la)?( canción)?)\b", t):
        osa('tell application "Spotify" to next track'); return ""
    if re.search(r"\b(canción anterior|anterior|regresa la canción)\b", t):
        osa('tell application "Spotify" to previous track'); return ""
    if re.search(r"\b(pon música|ponme música|play|reanuda|dale play)\b", t):
        subprocess.run(["open", "-a", "Spotify"]); time.sleep(1.5)
        osa('tell application "Spotify" to play'); return "Música, señor."
    if re.search(r"\bqué (canción|rola) es\b", t):
        r = osa('tell application "Spotify" to (name of current track) & " de " & (artist of current track)')
        return f"Suena {r.stdout.strip()}, señor." if r.stdout.strip() else "No hay nada sonando, señor."
    m = re.search(r"\b(sube|baja)(le)? (el |al )?volumen\b", t)
    if m:
        d = 15 if m.group(1) == "sube" else -15
        osa(f"set volume output volume ((output volume of (get volume settings)) + {d})"); return ""
    m = re.search(r"volumen (al |a )?(\d{1,3})", t)
    if m:
        osa(f"set volume output volume {min(100, int(m.group(2)))}"); return ""
    if re.fullmatch(r"(qué hora es|la hora|dime la hora)", t):
        n = datetime.datetime.now(); return f"Son las {n.hour}:{n.minute:02d}, señor."
    m = re.search(r"\bmodo (\w+)", t)
    if m and m.group(1) in disponibles():
        return modo(m.group(1))
    if re.search(r"\b(abre|muestra|enséñame) (el |mi )?(panel|hq|cuartel)\b", t):
        subprocess.run([str(JARVIS / "bin" / "jv"), "hq", "--abrir"]); return "Panel en pantalla, señor."
    if re.search(r"\b(abre|muestra) (mi |la )?rutina\b", t):
        abrir_url(c["rutina_url"]); return "Su rutina, señor. Sin excusas hoy."
    if re.search(r"\b(abre|muestra) (mi |la )?(app de )?(análisis )?facial\b", t) and c.get("facial_url"):
        abrir_url(c["facial_url"]); return "Análisis facial listo, señor."
    if re.fullmatch(r"(resumen|dame el resumen|buenos días|resumen del día)", t):
        subprocess.Popen([str(JARVIS / "bin" / "jv"), "resumen"]); return ""
    m = re.match(r"^(abre|abrir|ábreme|ábrelo|abreme)\s+(el |la |los |las )?(.+)$", t)
    if m:
        app = m.group(3).strip()
        escuela = bool(re.search(r"\b(de|en) (la )?escuela\b", app))
        app = re.sub(r"\s*\b(de|en) (la )?(escuela|personal|mi cuenta)\b", "", app).strip()
        if app in WEBS:
            url = WEBS[app]
            mundo = "escuela" if escuela else mundo_de(url)
            abrir_url(url, mundo)
            return f"Abriendo {app}" + (" con su cuenta de la escuela." if mundo == "escuela" else ".")
        nombre = APPS.get(app) or app.title()
        if subprocess.run(["open", "-a", nombre], capture_output=True).returncode == 0:
            return f"Abriendo {app}, señor."
        return None     # no la conozco: que lo resuelva el cerebro
    return None


# ---------- oídos ----------
from oido import Oido, transcribir, separar, transcribir_nube, es_fantasma, VOCAB          # noqa: E402

IDIOMA = os.environ.get("JARVIS_IDIOMA", "es")


def oir_bien(audio, preciso):
    """Transcripción buena: Groq (gratis, Whisper grande) y si falla, el oído local."""
    from comun import secretos
    llave = secretos().get("GROQ_API_KEY")
    texto = None
    if llave:
        with tm.etapa("transcripcion_groq") as e:
            texto = transcribir_nube(audio, llave, IDIOMA)
            if texto is None:
                e.estado = "error"
    if texto is not None:
        return "" if es_fantasma(texto) else texto
    with tm.etapa("transcripcion_local") as e:
        e.estado = "fallback" if llave else "exito"
        return transcribir(preciso, audio, IDIOMA, prompt=VOCAB, preciso=True)


def medir_frase(oido):
    """Telemetría: duración de la frase (incluye el silencio final) y espera de silencio."""
    try:
        t_voz, t_ultima, t_fin = oido.ultima
        tm.registrar("captura_frase", (t_fin - t_voz) / 1e6)
        tm.registrar("espera_silencio", (t_fin - t_ultima) / 1e6)
        tm.fin_frase(t_fin)
    except Exception:
        pass


def procesar(texto):
    print(f"🗣  Tú: {texto}")
    with tm.etapa("comando_rapido", ruta="rapido") as e:
        rapida = comando_rapido(texto)
        if rapida is None:
            e.ruta, e.estado = None, "fallback"       # no era comando rápido: pasa al cerebro
    if rapida is not None:
        tm.ruta("rapido")
        print(f"🤖 Jarvis: {rapida or '(hecho)'}")
        log(f"rápido: {texto} → {rapida}")
        if rapida: decir(rapida)
        else: tm.total()                              # acción sin voz: la respuesta es hacerla
        estado("listo"); return
    subprocess.Popen(["afplay", "/System/Library/Sounds/Pop.aiff"])
    resp, cerebro = pensar(texto, voz=True)
    (CASA / "ultima_respuesta.txt").write_text(resp)
    print(f"🤖 Jarvis [{cerebro}]: {resp}\n")
    decir(primera_linea(resp))


def pedir_comando(oido, preciso):
    estado("escuchando")
    subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])
    print("👂 ¿Sí, señor?")
    oido.vaciar()
    audio = oido.frase(fin_silencio=1.3, max_dur=25, espera_inicio=10)
    if audio is None or isinstance(audio, str):
        print("   (no escuché nada)"); estado("listo"); return
    if not tm.activa():
        tm.nueva("voz")
    medir_frase(oido)
    estado("pensando", "transcribiendo…")
    texto = oir_bien(audio, preciso)
    if texto:
        procesar(texto)
    else:
        estado("listo")


def main():
    from faster_whisper import WhisperModel

    PID.write_text(str(os.getpid()))
    print("Cargando modelos (la primera vez descarga ~600 MB)...")
    rapido = WhisperModel("base", device="cpu", compute_type="int8")
    preciso = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    DISPARADOR.unlink(missing_ok=True)

    with Oido(mic=MIC, sensibilidad=SENSIBILIDAD) as oido:
        estado("listo")
        decir("Sistemas en línea, señor.")
        print('\n🎙  Di "Jarvis, …" o usa Ctrl+Opción+J   (Ctrl+C para salir)\n')
        while True:
            audio = oido.frase(disparador=DISPARADOR)
            try:
                if isinstance(audio, str):                # atajo de teclado
                    pedir_comando(oido, preciso)
                else:
                    t0 = tm.ahora()
                    borrador = transcribir(rapido, audio, IDIOMA)
                    activado, _ = separar(borrador)
                    if not activado:
                        continue
                    tm.nueva("voz")
                    tm.registrar("deteccion_jarvis", (tm.ahora() - t0) / 1e6)
                    medir_frase(oido)
                    estado("pensando", "transcribiendo…")
                    texto = oir_bien(audio, preciso) or borrador
                    activado2, orden = separar(texto)
                    if not activado2:
                        _, orden = separar(borrador)
                    if orden:
                        procesar(orden)                   # "Jarvis, abre Spotify" de un jalón
                    else:
                        pedir_comando(oido, preciso)      # solo dijo "Jarvis"
            except Exception as e:
                log(f"voz error: {e}"); print(f"⚠️  {e}"); estado("listo")
            tm.terminar()
            oido.vaciar()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        estado("apagado"); print("\nHasta luego, señor.")
