"""Piezas compartidas de Jarvis: rutas, configuración, estado, registro."""
import json, os, pathlib, re, time, datetime

JARVIS = pathlib.Path(__file__).resolve().parent.parent
CASA = pathlib.Path.home() / ".jarvis"          # estado privado (fuera de Documentos y de git)
CASA.mkdir(exist_ok=True)

DEFAULTS = {
    "ciudad": "Ciudad de Mexico",
    "hora_resumen": "07:30",
    "silencio": ["23:00", "07:00"],
    "voz_mac": "",
    "elevenlabs_voice_id": "JBFqnCBsd6RMkjVDRZzb",
    "elevenlabs_modelo": "eleven_flash_v2_5",
    "elevenlabs_limite_mes": 55000,
    "minutos_juego_aviso": [60, 120, 180],
    "rutina_url": "https://jmuro2110-hub.github.io/rutina/",
    "facial_url": "",
    "modos": {},
    "conversacion_continua": True,      # upgrade 04: seguir la plática sin repetir «Jarvis»
    "timeout_seguimiento_seg": 15,
    "max_turnos": 5,
    "duracion_maxima_seg": 180,
    "claude_streaming": True,           # upgrade 05: false = ruta JSON exacta del 04 (no cambia permisos)
    "voz_anticipada": True,             # false = stream con telemetría, pero habla al final como antes
    "timeout_orden_seg": 6,             # tras «Jarvis» solo: cuánto esperar la orden
    "barge_in": True,                   # upgrade 06: «Jarvis, …» mientras habla lo interrumpe (false = 05)
    "hablar_al_result": True,           # upgrade 06: hablar al llegar `result`, sin esperar la salida de claude
}

def path_env():
    extra = [str(pathlib.Path.home() / ".local/bin"), "/usr/local/bin", "/opt/homebrew/bin"]
    actual = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    os.environ["PATH"] = ":".join(extra + [actual])

path_env()

def config():
    c = dict(DEFAULTS)
    try:
        c.update(json.loads((JARVIS / "config.json").read_text()))
    except Exception:
        pass
    return c

def secretos():
    s = {}
    f = CASA / "secretos.env"
    if f.exists():
        for linea in f.read_text().splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                s[k.strip()] = v.strip().strip('"')
    return s

def log(msg):
    with open(CASA / "jarvis.log", "a") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")

def estado(nombre, texto=""):
    """escuchando / pensando / hablando / listo — lo lee el HUD de Hammerspoon."""
    (CASA / "estado.json").write_text(json.dumps(
        {"estado": nombre, "texto": texto[:300], "t": time.time()}, ensure_ascii=False))

def leer_json(ruta, defecto):
    try:
        return json.loads(pathlib.Path(ruta).read_text())
    except Exception:
        return defecto

def escribir_json(ruta, datos):
    pathlib.Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2))

def _hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def en_silencio(c=None):
    c = c or config()
    ini, fin = (_hm(x) for x in c["silencio"])
    ahora = datetime.datetime.now()
    m = ahora.hour * 60 + ahora.minute
    return (m >= ini or m < fin) if ini > fin else (ini <= m < fin)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def fecha_bonita(d=None):
    d = d or datetime.date.today()
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"

# ---------- pendientes ----------
# Formato en memoria/pendientes.md:
#   - [ ] Descripción | materia o área | 2026-10-30
PEND_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+?)\s*(?:\|\s*(.*?)\s*)?(?:\|\s*(\d{4}-\d{2}-\d{2})\s*)?$")

def pendientes(solo_abiertos=True):
    f = JARVIS / "memoria" / "pendientes.md"
    res = []
    if not f.exists():
        return res
    for linea in f.read_text().splitlines():
        m = PEND_RE.match(linea)
        if not m:
            continue
        hecho = m.group(1).lower() == "x"
        if solo_abiertos and hecho:
            continue
        fecha = None
        if m.group(4):
            try:
                fecha = datetime.date.fromisoformat(m.group(4))
            except ValueError:
                pass
        res.append({"texto": m.group(2), "area": m.group(3) or "", "fecha": fecha, "hecho": hecho})
    res.sort(key=lambda p: p["fecha"] or datetime.date.max)
    return res

MATERIAS = {"matemáticas", "matematicas", "mate", "español", "historia", "geografía", "geografia", "física",
            "fisica", "química", "quimica", "biología", "biologia", "inglés", "ingles", "civismo", "formación cívica",
            "ética", "filosofía", "filosofia", "literatura", "ciencias", "computación", "computacion",
            "informática", "informatica", "educación física", "artes", "economía", "economia", "lógica", "logica",
            "taller de lectura y redacción", "tlr", "cálculo", "calculo", "álgebra", "algebra", "geometría",
            "estadística", "psicología", "sociología", "derecho", "metodología", "orientación"}

def es_escolar(area):
    """¿Es pendiente de la escuela? Área "escuela"/"tarea"/"examen" o una materia conocida."""
    a = (area or "").strip().lower()
    return bool(a) and (a in MATERIAS or bool(re.search(r"\b(escuela|tarea|examen|clase|classroom)\b", a)))

def limpiar_para_voz(t):
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"[*_`#>|]", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", t)
    return re.sub(r"\s+", " ", t).strip()

# ---------- dos mundos: perfiles de Chrome ----------
CORREO_PERSONAL = "jmuro2110@gmail.com"

def perfiles_chrome():
    """{'personal': 'Profile 1', 'escuela': 'Default'} leyendo los perfiles de Chrome."""
    c = config()
    res = {k: v for k, v in {"personal": c.get("chrome_perfil_personal"),
                              "escuela": c.get("chrome_perfil_escuela")}.items() if v}
    if len(res) == 2:
        return res
    estado_chrome = pathlib.Path.home() / "Library/Application Support/Google/Chrome/Local State"
    try:
        info = json.loads(estado_chrome.read_text())["profile"]["info_cache"]
    except Exception:
        return res
    for carpeta, datos in info.items():
        correo = (datos.get("user_name") or "").lower()
        if correo == CORREO_PERSONAL:
            res.setdefault("personal", carpeta)
        elif correo:
            res.setdefault("escuela", carpeta)
    return res

def abrir_url(url, mundo="personal"):
    """Abre la página en el perfil de Chrome correcto (personal o escuela). False si no se abrió."""
    import subprocess
    perfil = perfiles_chrome().get(mundo)
    if perfil:
        subprocess.run(["open", "-na", "Google Chrome", "--args", f"--profile-directory={perfil}", url])
    elif mundo == "escuela":
        log(f"no abrí {url[:60]}: no encuentro el perfil de la escuela")   # nunca cae al personal
        return False
    else:
        subprocess.run(["open", url])
    return True

ESCUELA_RE = re.compile(r"classroom\.google|meet\.google|/a/[^/]*\.edu|escuela", re.I)

def mundo_de(url):
    return "escuela" if ESCUELA_RE.search(url) else "personal"
