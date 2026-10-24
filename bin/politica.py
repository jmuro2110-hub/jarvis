"""Política de seguridad de Jarvis (upgrade 02). Determinista: evalúa OPERACIONES estructuradas,
no frases. La usan el guardia del modo asistente (bin/guardia.py) y los ejecutores locales (jv abrir).

    evaluar({"tipo": "abrir_app", "app": "Spotify"})          → Decision("permitido", ...)
    evaluar({"tipo": "enviar_correo", ...})                     → Decision("confirmar", ...)
    evaluar({"tipo": "publicar", "red": "instagram"}, aut=...)  → Decision("prohibido", ...)

Niveles: permitido · confirmar (requiere autorización de un solo uso) · prohibido (nunca) ·
bloqueado (desconocido, identidad sin resolver o sin ruta protegida).
Una autorización solo nace de una interfaz local confiable (aún no existe: Parte B). Ni el modelo,
ni una página, ni un "sí" en el historial pueden crearla: vive en ~/.jarvis, fuera de su alcance.
Compatible con el python3 del sistema (3.9): el hook corre sin uv para no sumar latencia.
"""
import datetime, fcntl, hashlib, json, os, pathlib, re, secrets, time
from collections import namedtuple

CASA = pathlib.Path.home() / ".jarvis"
AUDITORIA = CASA / "seguridad.jsonl"
AUTORIZACIONES = CASA / "autorizaciones.json"
VIGENCIA_S = 120                      # una autorización caduca a los 2 minutos

Decision = namedtuple("Decision", "nivel motivo")

PERMITIDAS = {"abrir_app", "abrir_web", "multimedia", "consultar", "modo", "funcion_local",
              "organizar_archivos", "anotar", "cerrar_app", "sistema"}
CON_CONFIRMACION = {"enviar_correo", "enviar_whatsapp", "enviar_classroom", "borrar",
                    "vaciar_papelera", "gasto", "irreversible"}
PROHIBIDAS = {"conectar_snapchat", "evadir_controles", "cruzar_mundos"}
REDES_VETADAS = {"instagram", "tiktok", "snapchat"}
MUNDOS = {"escuela", "personal"}

ESCUELA_RE = re.compile(r"classroom\.google|meet\.google|/a/[^/]*\.edu|escuela", re.I)   # = comun.mundo_de


def mundo_de(url):
    return "escuela" if ESCUELA_RE.search(url or "") else "personal"


def evaluar(op, autorizacion=None):
    """Decide sobre una operación. `autorizacion` es el id que entregó la interfaz confiable."""
    if not isinstance(op, dict) or not isinstance(op.get("tipo"), str):
        return Decision("bloqueado", "operación sin estructura")
    tipo = op["tipo"]
    red = str(op.get("red") or op.get("destino") or "").lower()

    # 1. Prohibiciones: no hay confirmación que las abra.
    if tipo in PROHIBIDAS:
        return Decision("prohibido", _MOTIVOS.get(tipo, "prohibido"))
    if tipo == "conectar" and "snapchat" in red:
        return Decision("prohibido", _MOTIVOS["conectar_snapchat"])
    if red in REDES_VETADAS and tipo not in ("abrir_web", "abrir_app", "consultar"):
        return Decision("prohibido", f"cero publicaciones ni acciones en {red}")
    if op.get("mundo_origen") and op.get("mundo_destino") and op["mundo_origen"] != op["mundo_destino"]:
        return Decision("prohibido", _MOTIVOS["cruzar_mundos"])

    # 2. Identidad: escuela y personal no se mezclan; si no se sabe la cuenta, no se actúa.
    if tipo == "abrir_web":
        url = str(op.get("url") or "")
        if not re.match(r"^https?://", url, re.I):
            return Decision("bloqueado", "solo páginas http(s)")
        mundo = op.get("mundo") or mundo_de(url)
        if mundo not in MUNDOS:
            return Decision("bloqueado", "perfil de Chrome desconocido")
        if mundo_de(url) == "escuela" and mundo != "escuela":
            return Decision("bloqueado", "página escolar con la cuenta personal: resuelva la identidad")
    if tipo in ("enviar_correo", "enviar_classroom") or op.get("requiere_cuenta"):
        cuenta = op.get("cuenta")
        if cuenta not in MUNDOS:
            return Decision("bloqueado", "no sé de qué mundo es la cuenta: hay que preguntar")
        if tipo == "enviar_classroom" and cuenta != "escuela":
            return Decision("bloqueado", "Classroom solo con la cuenta de la escuela")

    # 3. Clasificación.
    if tipo in PERMITIDAS:
        return Decision("permitido", "operación inocua autorizada")
    if tipo in CON_CONFIRMACION:
        if autorizacion and consumir(op, autorizacion):
            return Decision("permitido", "autorización de un solo uso válida")
        return Decision("confirmar", "requiere aprobación manual de JP desde una interfaz local")
    return Decision("bloqueado", f"operación sin clasificar ({tipo[:40]})")


_MOTIVOS = {
    "conectar_snapchat": "Snapchat no se conecta",
    "evadir_controles": "intento de modificar o evadir los controles de seguridad",
    "cruzar_mundos": "no se pasa información entre la cuenta de la escuela y la personal",
}


# ---------- autorizaciones de un solo uso ----------
def huella(op):
    """Liga la autorización a la acción, su destino y su contenido exactos."""
    return hashlib.sha256(json.dumps(op, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _abrir_privado(ruta, modo):
    CASA.mkdir(exist_ok=True)
    extra = os.O_APPEND if modo == "a" else 0
    fd = os.open(str(ruta), os.O_RDWR | os.O_CREAT | extra, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, modo)


def _con_autorizaciones(cambiar):
    with _abrir_privado(AUTORIZACIONES, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            datos = json.loads(f.read() or "{}")
        except ValueError:
            datos = {}
        ahora = time.time()
        datos = {k: v for k, v in datos.items() if v.get("expira", 0) > ahora}   # limpia caducas
        res = cambiar(datos, ahora)
        f.seek(0); f.truncate(); f.write(json.dumps(datos))
        return res


def autorizar(op, vigencia=VIGENCIA_S):
    """SOLO para la interfaz local confiable (Parte B). Devuelve el id de la autorización."""
    if evaluar(op).nivel != "confirmar":
        raise ValueError("solo se autorizan operaciones que requieren confirmación")
    ident = secrets.token_hex(16)
    def poner(datos, ahora):
        datos[ident] = {"huella": huella(op), "expira": ahora + vigencia}
    _con_autorizaciones(poner)
    return ident


def consumir(op, ident):
    """True una sola vez, si `ident` existe, no caducó y es para exactamente esta operación."""
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
        return False
    def usar(datos, ahora):
        a = datos.get(ident)
        if not a or a["expira"] <= ahora or not secrets.compare_digest(a["huella"], huella(op)):
            return False
        del datos[ident]                  # un solo uso
        return True
    try:
        return _con_autorizaciones(usar)
    except OSError:
        return False


# ---------- auditoría ----------
def auditar(tipo, decision, origen=None, herramienta=None, detalle=None, resultado=None):
    """Una línea por decisión en ~/.jarvis/seguridad.jsonl (0600). Sin mensajes, rutas privadas ni secretos."""
    try:
        fila = {"fecha": f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
                "id": (os.environ.get("JARVIS_REQ_ID") or "")[:32],
                "contexto": os.environ.get("JARVIS_MODO") or "desarrollo",
                "origen": origen or os.environ.get("JARVIS_ORIGEN") or "desconocido",
                "herramienta": herramienta, "tipo": tipo, "decision": decision.nivel,
                "motivo": decision.motivo[:120], "detalle": (detalle or "")[:60] or None,
                "resultado": resultado or ("continua" if decision.nivel == "permitido" else "bloqueado")}
        with _abrir_privado(AUDITORIA, "a") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:
        pass                              # la auditoría nunca tumba a Jarvis
