"""Sesiones de Claude del asistente (upgrade 03): un ID explícito por origen, nunca `--continue`.

- personal: voz, ⌃⌥Espacio y consultas personales (comparten sesión mientras esté vigente).
- auto: resumen matutino y otras consultas automáticas.
Las sesiones de desarrollo (JP con `claude` a mano) nunca se guardan aquí, así que nunca se reanudan.

~/.jarvis/sesiones.json (0600) guarda solo ID, origen y marcas de tiempo. Escritura atómica bajo candado.
"""
import contextlib, fcntl, json, os, tempfile, time, uuid
from comun import CASA

DIR = CASA
ORIGENES = ("personal", "auto")
VIGENCIA_MIN = 30          # después de 30 min sin hablar, sesión nueva (se conserva del diseño original)


def _abrir_600(ruta):
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(fd, 0o600)
    return fd


@contextlib.contextmanager
def _candado(nombre):
    fd = _abrir_600(DIR / nombre)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextlib.contextmanager
def turno(origen):
    """Una consulta a la vez por origen: dos peticiones simultáneas no reanudan ni pisan el mismo ID."""
    with _candado(f"sesion_{origen}.lock"):
        yield


def valido(sid):
    try:
        return isinstance(sid, str) and str(uuid.UUID(sid)) == sid.lower()
    except ValueError:
        return False


def nuevo_id():
    return str(uuid.uuid4())


def leer():
    try:
        d = json.loads((DIR / "sesiones.json").read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}            # no existe o está corrupto: como si no hubiera sesión


def _escribir(d):
    fd, tmp = tempfile.mkstemp(dir=DIR, prefix=".sesiones.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(d, f, indent=2)
        os.replace(tmp, DIR / "sesiones.json")
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def _actualizar(cambio):
    with _candado("sesiones.lock"):
        d = leer()
        cambio(d)
        _escribir(d)


def vigente(origen, ahora=None):
    """ID a reanudar, o None si no hay sesión válida de ESE origen en los últimos 30 min."""
    s = leer().get(origen)
    ahora = ahora or time.time()
    if isinstance(s, dict) and s.get("origen") == origen and valido(s.get("id")) \
            and isinstance(s.get("ultima"), (int, float)) and 0 <= ahora - s["ultima"] < VIGENCIA_MIN * 60:
        return s["id"]
    return None


def guardar(origen, sid, nueva):
    """Anota el session_id que DEVOLVIÓ Claude."""
    if origen not in ORIGENES or not valido(sid):
        return
    def cambio(d):
        t = time.time()
        prev = d.get(origen) if isinstance(d.get(origen), dict) else {}
        creada = prev.get("creada", t) if not nueva and prev.get("id") == sid else t
        d[origen] = {"id": sid, "origen": origen, "creada": creada, "ultima": t}
    _actualizar(cambio)


def olvidar(origen):
    _actualizar(lambda d: d.pop(origen, None))
