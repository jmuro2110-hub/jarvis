"""Telemetría de latencia de Jarvis: cuánto tarda cada etapa de una petición.

Solo librería estándar. Guarda en ~/.jarvis/metricas_latencia.jsonl una línea por etapa:
fecha, id, origen, etapa, ms, ruta, estado (y "sesion" en las de Claude). NUNCA texto, audio,
prompts ni llaves.
Si algo falla aquí, se ignora: Jarvis sigue funcionando igual.

Uso:
    telemetria.nueva("voz", t_fin_frase=ns)      # empieza una petición
    with telemetria.etapa("claude_p", ruta="claude") as e:
        ...; e.estado = "error"
    telemetria.terminar()

El ID viaja a los subprocesos por la variable de entorno JARVIS_REQ_ID (y JARVIS_ORIGEN).
"""
import contextlib, datetime, json, os, pathlib, time, uuid

ARCHIVO = pathlib.Path(os.environ.get("JARVIS_METRICAS")
                       or pathlib.Path.home() / ".jarvis" / "metricas_latencia.jsonl")

ETAPAS = ("captura_frase", "espera_silencio", "deteccion_jarvis", "transcripcion_groq",
          "transcripcion_local", "comando_rapido", "claude_preparacion", "claude_p",
          "claude_duracion", "claude_api", "claude_arranque_est", "codex_exec",
          "voz_preparacion", "total",
          # upgrade 05 (stream-json). Desde que se lanzó claude: primer evento, primer texto, primera frase,
          # comienzo de la voz (B), resultado (D) y fin de la voz. Desde el fin de la frase de JP:
          # respuesta_completa (E). voz_solapada (F) = cuánto antes del resultado empezó a hablar.
          "claude_primer_evento", "claude_primer_texto", "claude_primera_frase", "claude_resultado",
          "tts_inicio", "tts_fin", "voz_solapada", "respuesta_completa", "incidente_voz",
          # upgrade 06. claude_salida: claude cerrado y recolectado (desde que se lanzó). ahorro_result =
          # claude_salida − tts_inicio (observado). barge_deteccion: inferencia de Whisper base sobre un
          # candidato (motivo = confirmado o por qué se rechazó). barge_parada: inicio de la voz de JP → voz
          # de Jarvis parada (estimado con el reloj del bloque de audio). barge_tipo: qué pidió (motivo).
          "claude_salida", "ahorro_result", "barge_deteccion", "barge_parada", "barge_tipo",
          # upgrade 07 (memoria). memoria_busqueda: búsqueda para el prompt de Claude (candidatos, seleccionados,
          # usada). memoria_accion: guardar/corregir/olvidar/consultar local (motivo = resultado).
          # memoria_lectura: renglones inválidos o error al leer. Nunca el contenido de un recuerdo.
          "memoria_busqueda", "memoria_accion", "memoria_lectura",
          # después del 07: transcripción tirada antes de Claude (motivo = solo_vocabulario).
          "transcripcion_descartada")
# Por qué no hubo voz anticipada (o qué incidente hubo). Nunca texto.
MOTIVOS_STREAM = ("con_tools", "sin_frase", "init_con_tools", "tool_use_inesperado", "desactivado", "error",
                  "no_voz", "markdown", "distinto", "salida_tardia",
                  # barge-in (upgrade 06)
                  "confirmado", "sin_jarvis", "jarvis_en_medio", "eco", "eco_jarvis", "fantasma", "temprano",
                  "callar", "espera", "solo_jarvis", "orden",
                  # memoria (upgrade 07)
                  "guardado", "duplicado", "sensible", "ambiguo", "largo", "corregido", "desactivado", "consulta",
                  "sin_antecedente", "error_escritura", "error_lectura", "invalido",
                  # transcripción descartada
                  "solo_vocabulario")
# claude_duracion / claude_api: duration_ms y duration_api_ms que reporta el propio Claude (JSON).
# claude_arranque_est = claude_p − claude_duracion: ESTIMACIÓN del arranque local, no medida exacta.
ESTADOS = ("exito", "error", "timeout", "fallback")
RUTAS = ("rapido", "claude", "codex", "ninguno")
ORIGENES = ("voz", "texto", "auto")
SESIONES = ("nueva", "reanudada")

# Conversación continua (upgrade 04): eventos aparte, para no inflar metricas_latencia.jsonl.
CONV_ARCHIVO = pathlib.Path(os.environ.get("JARVIS_CONVERSACIONES")
                            or pathlib.Path.home() / ".jarvis" / "conversaciones.jsonl")
CONV_EVENTOS = ("activada", "seguimiento_abre", "seguimiento_detectado", "seguimiento_descartado", "cierre")
CONV_MOTIVOS = ("timeout", "manual", "turnos", "tiempo", "callar", "transcripcion", "resumen", "dormir",
                "error", "sin_orden", "desactivada", "otra_voz", "fantasma", "solo_jarvis")

_actual = {}        # petición en curso: id, origen, t_fin (ns), ruta, total_hecho, sesion
_voz_t0 = None      # cuándo empezó decir() (ns)

ahora = time.perf_counter_ns


def _ms(desde_ns, hasta_ns=None):
    return round(((hasta_ns or ahora()) - desde_ns) / 1e6, 1)


def nueva(origen, t_fin_frase=None, id_=None):
    """Empieza una petición. t_fin_frase: perf_counter_ns() del momento en que el usuario terminó."""
    try:
        _actual.clear()
        _actual.update(id=id_ or uuid.uuid4().hex[:12], origen=origen if origen in ORIGENES else "texto",
                       t_fin=t_fin_frase, ruta=None, total_hecho=False)
        os.environ["JARVIS_REQ_ID"] = _actual["id"]
        os.environ["JARVIS_ORIGEN"] = _actual["origen"]
    except Exception:
        pass


def desde_entorno(origen_defecto="texto", con_total=True):
    """Para procesos hijos (jv pensar, jv decir…): se une a la petición del padre o empieza una.
    con_total=False cuando este proceso no ve el fin de la frase (no se puede medir el total aquí)."""
    try:
        nueva(os.environ.get("JARVIS_ORIGEN") or origen_defecto, ahora() if con_total else None,
              os.environ.get("JARVIS_REQ_ID"))
    except Exception:
        pass


def activa():
    return bool(_actual.get("id")) or bool(os.environ.get("JARVIS_REQ_ID"))


def fin_frase(t_ns):
    """Mueve el punto de partida del total (p. ej. dijo solo "Jarvis" y luego la orden)."""
    try:
        if _actual:
            _actual["t_fin"], _actual["total_hecho"] = t_ns, False
    except Exception:
        pass


def ruta(r):
    try:
        if _actual and r in RUTAS:
            _actual["ruta"] = r
    except Exception:
        pass


def sesion(tipo):
    """'nueva' o 'reanudada': se anota en las filas de Claude de esta petición."""
    try:
        if _actual and tipo in SESIONES:
            _actual["sesion"] = tipo
    except Exception:
        pass


def terminar():
    try:
        _actual.clear()
        os.environ.pop("JARVIS_REQ_ID", None)
        os.environ.pop("JARVIS_ORIGEN", None)
    except Exception:
        pass


def registrar(nombre, ms, ruta=None, estado="exito", extra=None):
    """Escribe una línea. Solo campos fijos y valores de listas cerradas: nada de contenido."""
    try:
        id_ = _actual.get("id") or os.environ.get("JARVIS_REQ_ID")
        if not id_ or nombre not in ETAPAS:
            return
        origen = _actual.get("origen") or os.environ.get("JARVIS_ORIGEN") or "texto"
        r = ruta or _actual.get("ruta")
        fila = {"fecha": datetime.datetime.now().isoformat(timespec="milliseconds"),
                "id": str(id_)[:32], "origen": origen if origen in ORIGENES else "texto",
                "etapa": nombre, "ms": round(float(ms), 1),
                "ruta": r if r in RUTAS else None,
                "estado": estado if estado in ESTADOS else "error"}
        if nombre.startswith("claude_") and _actual.get("sesion") in SESIONES:
            fila["sesion"] = _actual["sesion"]
        for k, v in (extra or {}).items():                  # upgrade 05: solo estos, con valores cerrados
            if k == "anticipada" and isinstance(v, bool):
                fila[k] = v
            elif k == "motivo" and v in MOTIVOS_STREAM:
                fila[k] = v
            elif k == "usada" and isinstance(v, bool):      # upgrade 07: solo conteos, nunca contenido
                fila[k] = v
            elif k in ("candidatos", "seleccionados") and isinstance(v, int) and not isinstance(v, bool):
                fila[k] = max(0, min(v, 100000))
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCHIVO, "a") as f:
            f.write(json.dumps(fila) + "\n")
    except Exception:
        pass


class _Etapa:
    estado = "exito"
    ruta = None
    extra = None


@contextlib.contextmanager
def etapa(nombre, ruta=None):
    """Mide un bloque. Cambia e.estado / e.ruta adentro si hace falta. Si el bloque truena, queda 'error'."""
    e = _Etapa()
    e.ruta = ruta
    t0 = ahora()
    try:
        yield e
    except BaseException:
        e.estado = "error"
        raise
    finally:
        registrar(nombre, _ms(t0), e.ruta, e.estado, e.extra)


def desde_fin(nombre):
    """Etapa medida desde que JP terminó su frase (p. ej. respuesta_completa)."""
    try:
        if _actual.get("t_fin"):
            registrar(nombre, _ms(_actual["t_fin"]))
    except Exception:
        pass


def total(estado="exito"):
    """Total desde que terminó la frase del usuario hasta que Jarvis responde. Solo una vez por petición."""
    try:
        if _actual.get("t_fin") and not _actual.get("total_hecho"):
            _actual["total_hecho"] = True
            registrar("total", _ms(_actual["t_fin"]), estado=estado)
    except Exception:
        pass


def voz_preparando():
    """Al entrar a decir()."""
    global _voz_t0
    try:
        _voz_t0 = ahora()
    except Exception:
        pass


def voz_empieza():
    """Justo antes de lanzar say/afplay: cierra 'voz_preparacion' y el total."""
    global _voz_t0
    try:
        if _voz_t0 is not None:
            registrar("voz_preparacion", _ms(_voz_t0))
            _voz_t0 = None
            total()
    except Exception:
        pass


def desglose_claude(sub_ms, duration_ms, duration_api_ms, reanudada=False):
    """Lo que Claude reporta de sí mismo + la diferencia con el subproceso (arranque local estimado).
    Al reanudar, duration_api_ms viene ACUMULADO de toda la sesión (medido en 2.1.311): no se registra."""
    try:
        if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
            registrar("claude_duracion", duration_ms)
            registrar("claude_arranque_est", max(0.0, sub_ms - duration_ms))
        if not reanudada and isinstance(duration_api_ms, (int, float)) and duration_api_ms >= 0:
            registrar("claude_api", duration_api_ms)
    except Exception:
        pass


def conversacion(evento, conv_id, turno=0, ms=None, motivo=None):
    """Un evento por transición. Solo campos fijos y listas cerradas: nunca lo que dijo JP."""
    try:
        if evento not in CONV_EVENTOS or not conv_id:
            return
        fila = {"fecha": datetime.datetime.now().isoformat(timespec="milliseconds"),
                "conv": str(conv_id)[:16], "evento": evento, "turno": int(turno)}
        if motivo is not None:
            fila["motivo"] = motivo if motivo in CONV_MOTIVOS else "error"
        if isinstance(ms, (int, float)) and ms >= 0:
            fila["ms"] = round(float(ms), 1)
        CONV_ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        with open(CONV_ARCHIVO, "a") as f:
            f.write(json.dumps(fila) + "\n")
    except Exception:
        pass


def leer_conversaciones(dias=None):
    filas = []
    try:
        limite = datetime.datetime.now() - datetime.timedelta(days=dias) if dias else None
        for linea in CONV_ARCHIVO.read_text().splitlines():
            try:
                f = json.loads(linea)
                if limite and datetime.datetime.fromisoformat(f["fecha"]) < limite:
                    continue
                if f["evento"] in CONV_EVENTOS:
                    filas.append(f)
            except Exception:
                continue
    except OSError:
        pass
    return filas


# ---------- lectura para `jv latencia` ----------
def leer(dias=None):
    filas = []
    try:
        limite = datetime.datetime.now() - datetime.timedelta(days=dias) if dias else None
        for linea in ARCHIVO.read_text().splitlines():
            try:
                f = json.loads(linea)
                if limite and datetime.datetime.fromisoformat(f["fecha"]) < limite:
                    continue
                float(f["ms"]); f["etapa"]
                filas.append(f)
            except Exception:
                continue        # línea dañada: se salta
    except OSError:
        pass            # no existe o no se puede leer: sin mediciones
    return filas
