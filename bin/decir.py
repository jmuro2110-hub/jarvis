# /// script
# requires-python = ">=3.11"
# ///
"""Boca de Jarvis: ElevenLabs si hay llave y crédito; si no, la voz de la Mac."""
import fcntl, json, re, subprocess, sys, urllib.request, datetime, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA, config, secretos, log, estado, leer_json, escribir_json, limpiar_para_voz
import telemetria as tm

PREFERIDAS = ["Juan (Enhanced)", "Juan (Premium)", "Jorge (Enhanced)", "Juan", "Jorge", "Diego"]

def voz_mac(c):
    if c.get("voz_mac"):
        return c["voz_mac"]
    cache = CASA / "voz_mac.txt"
    if cache.exists():
        return cache.read_text().strip() or None
    lista = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    for v in PREFERIDAS:
        if re.search(rf"^{re.escape(v)}\s{{2,}}", lista, re.M):
            cache.write_text(v)
            return v
    cache.write_text("")
    return None

def _uso_eleven():
    mes = datetime.date.today().strftime("%Y-%m")
    u = leer_json(CASA / "eleven_uso.json", {})
    return mes, u.get(mes, 0), u

def elevenlabs(texto, c, s):
    llave = s.get("ELEVENLABS_API_KEY")
    if not llave or len(texto) > 400:
        return False
    mes, usados, u = _uso_eleven()
    if usados + len(texto) > c["elevenlabs_limite_mes"]:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{c['elevenlabs_voice_id']}?output_format=mp3_44100_128"
    cuerpo = json.dumps({"text": texto, "model_id": c["elevenlabs_modelo"],
                         "voice_settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.15}}).encode()
    req = urllib.request.Request(url, data=cuerpo, headers={
        "xi-api-key": llave, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            audio = r.read()
    except Exception as e:
        log(f"ElevenLabs falló: {e}")
        return False
    mp3 = CASA / "voz.mp3"
    mp3.write_bytes(audio)
    u[mes] = usados + len(texto)
    escribir_json(CASA / "eleven_uso.json", u)
    tm.voz_empieza()
    subprocess.run(["afplay", str(mp3)])
    return True

def decir(texto, forzar=False):
    """Habla y regresa cuando terminó de sonar. True si sonó bien (False si say falló o lo callaron)."""
    tm.voz_preparando()
    texto = limpiar_para_voz(texto)
    if not texto:
        return True
    c, s = config(), secretos()
    with open(CASA / "voz.lock", "w") as candado:
        fcntl.flock(candado, fcntl.LOCK_EX)          # nunca dos voces encimadas
        estado("hablando", texto)
        ok = True
        if not elevenlabs(texto, c, s):
            cmd = ["say", "-r", "185"]
            v = voz_mac(c)
            if v:
                cmd += ["-v", v]
            tm.voz_empieza()
            ok = subprocess.run(cmd + [texto]).returncode == 0
        estado("listo")
        return ok

def callar():
    """Calla la voz y pide cerrar la conversación de voz abierta (⌃⌥. corre en otro proceso)."""
    try:
        (CASA / "cerrar_conversacion").touch()
    except OSError:
        pass
    subprocess.run(["pkill", "-x", "say"])
    subprocess.run(["pkill", "-x", "afplay"])

if __name__ == "__main__":
    if sys.argv[1:] == ["--callar"]:
        callar()
    else:
        if os.environ.get("JARVIS_REQ_ID"):
            tm.desde_entorno(con_total=False)   # lo llamó Claude/otro proceso dentro de una petición
        ok = decir(" ".join(sys.argv[1:]) or "Sistemas en línea, señor.")
        sys.exit(0 if ok is not False else 1)     # el hijo de voz anticipada (upgrade 05) sabe si falló
