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
Después sigue la plática sin repetir «Jarvis» (upgrade 04, voz/conversacion.py).
"""
import fcntl, json, os, re, sys, time, datetime, pathlib, subprocess

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "bin"))
sys.path.insert(0, str(AQUI))
from comun import CASA, JARVIS, config, estado, log, abrir_url, mundo_de            # noqa: E402
from decir import decir, callar                               # noqa: E402
from pensar import pensar, primera_linea                      # noqa: E402
from modo import modo, disponibles                            # noqa: E402
import telemetria as tm                                       # noqa: E402
from conversacion import Conversacion, PROCESSING, es_cierre  # noqa: E402

SENSIBILIDAD = float(os.environ.get("JARVIS_SENSIBILIDAD", "3.0"))  # más alto = necesita voz más fuerte
MIC = os.environ.get("JARVIS_MIC")
MIC = int(MIC) if MIC and MIC.isdigit() else None
MODELO_WHISPER = os.environ.get("JARVIS_WHISPER", "small")
DISPARADOR = CASA / "escuchar"          # el atajo de teclado crea este archivo
CERRAR = CASA / "cerrar_conversacion"   # callar() la crea (⌃⌥. corre en otro proceso)
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
    return clasificar_rapido(t)[0]

# En FOLLOW_UP "¿y la siguiente?" es una pregunta, no Spotify: ahí se pide la palabra "canción"
# (o "siguiente"/"anterior" a secas justo después de otro comando de Spotify). "ya"/"para" van al cerebro.
SIGUIENTE_CONV = re.compile(r"\b(siguiente canción|canción siguiente|(salta|cambia)(la)? (la )?canción)\b")
ANTERIOR_CONV = re.compile(r"\b(canción anterior|regresa la canción)\b")

def clasificar_rapido(t, seguimiento=False, previo=None):
    """(respuesta, categoría). respuesta None = no es comando rápido. En IDLE las reglas son las de siempre."""
    t = t.lower().strip(" .,!¿?¡")
    t = re.sub(r"^(oye |hey )?jarvis[, ]*", "", t)
    c = config()
    if re.fullmatch(r"(cállate|silencio|basta)" if seguimiento else r"(cállate|silencio|ya|basta|para)", t):
        callar(); return "", "callar"
    if re.search(r"\b(pausa|pausar|para la música|detén la música|quita la música)\b", t):
        osa('tell application "Spotify" to pause'); return "Música en pausa, señor.", "spotify"
    if (SIGUIENTE_CONV.search(t) or (t == "siguiente" and previo == "spotify")) if seguimiento else \
            re.search(r"\b(siguiente canción|siguiente|salta(la)?( canción)?|cambia(la)?( canción)?)\b", t):
        osa('tell application "Spotify" to next track'); return "", "spotify"
    if (ANTERIOR_CONV.search(t) or (t == "anterior" and previo == "spotify")) if seguimiento else \
            re.search(r"\b(canción anterior|anterior|regresa la canción)\b", t):
        osa('tell application "Spotify" to previous track'); return "", "spotify"
    if re.search(r"\b(pon música|ponme música|play|reanuda|dale play)\b", t):
        subprocess.run(["open", "-a", "Spotify"]); time.sleep(1.5)
        osa('tell application "Spotify" to play'); return "Música, señor.", "spotify"
    if re.search(r"\bqué (canción|rola) es\b", t):
        r = osa('tell application "Spotify" to (name of current track) & " de " & (artist of current track)')
        return (f"Suena {r.stdout.strip()}, señor." if r.stdout.strip() else "No hay nada sonando, señor."), "spotify"
    m = re.search(r"\b(sube|baja)(le)? (el |al )?volumen\b", t)
    if m:
        d = 15 if m.group(1) == "sube" else -15
        osa(f"set volume output volume ((output volume of (get volume settings)) + {d})"); return "", "volumen"
    m = re.search(r"volumen (al |a )?(\d{1,3})", t)
    if m:
        osa(f"set volume output volume {min(100, int(m.group(2)))}"); return "", "volumen"
    if re.fullmatch(r"(qué hora es|la hora|dime la hora)", t):
        n = datetime.datetime.now(); return f"Son las {n.hour}:{n.minute:02d}, señor.", "hora"
    m = re.search(r"\bmodo (\w+)", t)
    if m and re.search(r"\b(desactiva|quita|apaga|sal del|termina|cancela|ya no)\b", t):
        m = None        # "desactiva el modo gamer": no lo actives; que lo resuelva el cerebro
    if m and m.group(1) in disponibles():
        return modo(m.group(1)), ("modo_dormir" if m.group(1) == "dormir" else "modo")
    if re.search(r"\b(abre|muestra|enséñame) (el |mi )?(panel|hq|cuartel)\b", t):
        subprocess.run([str(JARVIS / "bin" / "jv"), "hq", "--abrir"]); return "Panel en pantalla, señor.", "panel"
    if re.search(r"\b(abre|muestra) (mi |la )?rutina\b", t):
        abrir_url(c["rutina_url"]); return "Su rutina, señor. Sin excusas hoy.", "abrir"
    if re.search(r"\b(abre|muestra) (mi |la )?(app de )?(análisis )?facial\b", t) and c.get("facial_url"):
        abrir_url(c["facial_url"]); return "Análisis facial listo, señor.", "abrir"
    if re.fullmatch(r"(resumen|dame el resumen|buenos días|resumen del día)", t):
        subprocess.Popen([str(JARVIS / "bin" / "jv"), "resumen"]); return "", "resumen"
    m = re.match(r"^(abre|abrir|ábreme|ábrelo|abreme)\s+(el |la |los |las )?(.+)$", t)
    if m:
        app = m.group(3).strip()
        escuela = bool(re.search(r"\b(de|en) (la )?escuela\b", app))
        app = re.sub(r"\s*\b(de|en) (la )?(escuela|personal|mi cuenta)\b", "", app).strip()
        if app in WEBS:
            url = WEBS[app]
            mundo = "escuela" if escuela else mundo_de(url)
            if not abrir_url(url, mundo):
                return "No encuentro su perfil de la escuela en Chrome, señor. No la abro en el personal.", "abrir"
            return f"Abriendo {app}" + (" con su cuenta de la escuela." if mundo == "escuela" else "."), "abrir"
        nombre = APPS.get(app) or app.title()
        if subprocess.run(["open", "-a", nombre], capture_output=True).returncode == 0:
            return f"Abriendo {app}, señor.", ("spotify" if nombre == "Spotify" else "abrir")
        return None, None     # no la conozco: que lo resuelva el cerebro
    return None, None


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


def cerrar_pedido():
    """⌃⌥. o "cállate" crearon la bandera (callar() en cualquier proceso)."""
    return CERRAR.exists()


def procesar(texto, conv=None, seguimiento=False):
    """Un turno: comando rápido o cerebro, y su voz. Regresa la categoría ("cerebro" si pensó).
    Si se pidió callar mientras pensaba, no se habla la respuesta."""
    print(f"🗣  Tú: {texto}")
    previo = conv.previo if conv else None
    with tm.etapa("comando_rapido", ruta="rapido") as e:
        rapida, categoria = clasificar_rapido(texto, seguimiento, previo)
        if rapida is None:
            e.ruta, e.estado = None, "fallback"       # no era comando rápido: pasa al cerebro
    if rapida is not None:
        tm.ruta("rapido")
        print(f"🤖 Jarvis: {rapida or '(hecho)'}")
        log(f"rápido: {texto} → {rapida}")
        if rapida and not cerrar_pedido():
            _hablar(rapida, conv)
        else:
            tm.total()                                # acción sin voz: la respuesta es hacerla
        estado("listo"); return categoria
    subprocess.Popen(["afplay", "/System/Library/Sounds/Pop.aiff"])
    resp, cerebro = pensar(texto, voz=True)          # sesión personal del upgrade 03 (--resume)
    (CASA / "ultima_respuesta.txt").write_text(resp)
    print(f"🤖 Jarvis [{cerebro}]: {resp}\n")
    if not cerrar_pedido():
        _hablar(primera_linea(resp), conv)
    return "cerebro"


def _hablar(texto, conv):
    if conv and conv.estado == PROCESSING:
        conv.hablar()
    ok = decir(texto)                                 # regresa cuando say/afplay de verdad terminó
    if conv and ok is False and not cerrar_pedido():
        raise RuntimeError("la voz falló")            # sin voz confiable no se abre el micrófono


def pedir_comando(oido, preciso):
    """Solo dijo «Jarvis» o ⌃⌥J: tin y escucha la orden. Regresa el texto, o "" si no hubo nada."""
    estado("escuchando")
    subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])
    print("👂 ¿Sí, señor?")
    oido.vaciar()
    audio = oido.frase(fin_silencio=1.3, max_dur=25, espera_inicio=10, cerrar=CERRAR)
    if audio is None or isinstance(audio, str):
        print("   (no escuché nada)"); estado("listo"); return ""
    if not tm.activa():
        tm.nueva("voz")
    medir_frase(oido)
    estado("pensando", "transcribiendo…")
    return oir_bien(audio, preciso)


# ---------- conversación continua (upgrade 04) ----------
def otra_voz(desde):
    """¿Otra voz de Jarvis (vigía, resumen, modo…) está sonando o sonó desde `desde` (time.time())?
    decir() abre voz.lock con "w" (cambia su fecha) y lo tiene tomado mientras habla."""
    candado = CASA / "voz.lock"
    try:
        if candado.exists() and candado.stat().st_mtime >= desde:
            return True
        with open(candado, "a") as f:                # "a": no lo trunca ni le cambia la fecha
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        return json.loads((CASA / "estado.json").read_text()).get("estado") == "hablando"
    except Exception:
        return False


def sonido(nombre):
    try:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{nombre}.aiff"])
    except Exception:
        pass


def esperar_seguimiento(oido, preciso, conv):
    """FOLLOW_UP: escucha sin «Jarvis» hasta que haya un turno válido. Regresa el texto o None (cerrada).
    Sin Whisper base: voz por energía → Groq (o small de respaldo), una vez por intervención."""
    t_fin_voz = tm.ahora()
    oido.vaciar()                                     # lo que se oyó mientras Jarvis hablaba, fuera
    estado("seguimiento", str(round(conv.restante())))
    conv.ventana_lista((tm.ahora() - t_fin_voz) / 1e6)
    t_abre = tm.ahora()
    while True:
        restante = conv.restante()
        if restante <= 0:
            conv.vencio(); return None
        desde = time.time()
        audio = oido.frase(fin_silencio=1.3, max_dur=25, espera_inicio=restante,
                           disparador=DISPARADOR, cerrar=CERRAR)
        if audio is None:
            conv.vencio(); return None
        if isinstance(audio, str) and audio == "CERRAR":
            conv.cerrar("callar"); return None
        if isinstance(audio, str):                    # ⌃⌥J dentro de la conversación: siguiente turno
            texto = pedir_comando(oido, preciso)
        else:
            if otra_voz(desde):                       # el vigía/resumen habló: no es una orden de JP
                conv.descartar("otra_voz"); oido.vaciar(); continue
            tm.nueva("voz")
            medir_frase(oido)
            try:
                conv.detectado((oido.ultima[0] - t_abre) / 1e6)
            except Exception:
                conv.detectado()
            estado("pensando", "transcribiendo…")
            texto = oir_bien(audio, preciso)
        if cerrar_pedido():
            conv.cerrar("callar"); return None
        if not texto or not texto.strip():
            tm.terminar()
            if not conv.fallo_transcripcion():
                return None
            estado("seguimiento", str(round(conv.restante()))); continue
        activado, resto = separar(texto)
        if activado:
            if not resto:                             # solo «Jarvis»: tin, la ventana sigue, no cuenta
                tm.terminar(); conv.descartar("solo_jarvis"); sonido("Tink")
                estado("seguimiento", str(round(conv.restante()))); continue
            texto = resto
        if es_cierre(texto):
            tm.terminar(); sonido("Bottle"); conv.cerrar("manual"); return None
        return texto


def conversar(oido, preciso, conv, orden=None):
    """De la activación al cierre, en este mismo hilo. orden=None → hay que pedirla."""
    if conv.abierta:
        return                                        # ya había una abierta: nunca dos
    CERRAR.unlink(missing_ok=True)                    # una bandera vieja no cierra esta conversación
    c = config()                                      # límites ajustables sin reiniciar ni editar Python
    conv.continua, conv.timeout = bool(c["conversacion_continua"]), float(c["timeout_seguimiento_seg"])
    conv.max_turnos, conv.duracion_max = int(c["max_turnos"]), float(c["duracion_maxima_seg"])
    conv.activar()
    try:
        texto = orden if orden is not None else pedir_comando(oido, preciso)
        if not texto or not texto.strip():
            conv.cerrar("sin_orden"); return
        if es_cierre(texto):
            sonido("Bottle"); conv.cerrar("manual"); return
        seguimiento = False
        while True:
            conv.iniciar_turno()
            categoria = procesar(texto, conv, seguimiento)
            tm.terminar()
            if not conv.respuesta_terminada(categoria, cerrar=cerrar_pedido()):
                return
            texto = esperar_seguimiento(oido, preciso, conv)
            if texto is None:
                return
            seguimiento = True
    except Exception as e:
        log(f"conversación error: {e}"); print(f"⚠️  {e}")
        conv.cerrar("error")
        raise
    finally:
        CERRAR.unlink(missing_ok=True)
        oido.vaciar()
        estado("listo")


def escuchar_una(oido, rapido, preciso, conv):
    """IDLE: una frase. Solo «Jarvis» (Whisper base, local) o ⌃⌥J abren conversación; nada va a Groq antes."""
    audio = oido.frase(disparador=DISPARADOR)
    try:
        if isinstance(audio, str):                    # atajo de teclado
            conversar(oido, preciso, conv)
        else:
            t0 = tm.ahora()
            borrador = transcribir(rapido, audio, IDIOMA)
            activado, _ = separar(borrador)
            if not activado:
                return
            tm.nueva("voz")
            tm.registrar("deteccion_jarvis", (tm.ahora() - t0) / 1e6)
            medir_frase(oido)
            estado("pensando", "transcribiendo…")
            texto = oir_bien(audio, preciso) or borrador
            activado2, orden = separar(texto)
            if not activado2:
                _, orden = separar(borrador)
            # "Jarvis, abre Spotify" de un jalón, o solo "Jarvis" (orden vacía → la pide)
            conversar(oido, preciso, conv, orden or None)
    except Exception as e:
        log(f"voz error: {e}"); print(f"⚠️  {e}"); estado("listo")
    finally:
        tm.terminar()
        oido.vaciar()


def main():
    from faster_whisper import WhisperModel

    PID.write_text(str(os.getpid()))
    print("Cargando modelos (la primera vez descarga ~600 MB)...")
    rapido = WhisperModel("base", device="cpu", compute_type="int8")
    preciso = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    DISPARADOR.unlink(missing_ok=True)
    conv = Conversacion.desde_config(config(), registrar=tm.conversacion)

    with Oido(mic=MIC, sensibilidad=SENSIBILIDAD) as oido:
        estado("listo")
        decir("Sistemas en línea, señor.")
        print('\n🎙  Di "Jarvis, …" o usa Ctrl+Opción+J   (Ctrl+C para salir)\n')
        while True:
            escuchar_una(oido, rapido, preciso, conv)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        estado("apagado"); print("\nHasta luego, señor.")
