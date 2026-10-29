"""Streaming de Claude y voz anticipada (upgrade 05).

Piezas, de la más pura a la que toca procesos:
- `ruta_sin_herramientas(texto, ...)`: clasificador determinista (solo voz) de preguntas de conocimiento general.
- `Parser`: lee el stream-json de `claude -p --verbose --include-partial-messages` línea por línea.
  Solo el PRIMER bloque de texto del mensaje principal (parent_tool_use_id = null, text_delta) alimenta la
  voz; thinking, input_json, herramientas, subagentes y los `assistant` duplicados se ignoran. `result` manda.
- `Frases`: de ese texto saca lo hablable SIN pasar del primer salto de línea: primero la frase 1 (con un
  límite confiable), luego el resto de la primera línea cuando la línea cierra.
- `Hablador`: reproduce los pedazos con `bin/decir.py` como proceso hijo, uno a la vez (voz.lock, Juan,
  callar por pkill). Sin threads: quien lo usa llama `tick()`.
- `correr(...)`: coordinador con `selectors` sobre stdout de Claude (timeout 0.15 s) + `tick()` de la voz.

Nada de esto guarda texto en la telemetría.
"""
import json, os, re, selectors, signal, subprocess, sys, tempfile, time, pathlib

BIN = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
from comun import limpiar_para_voz                    # noqa: E402
import telemetria as tm                                # noqa: E402

MAX_LINEA = 4 * 1024 * 1024        # una línea de stream más grande que esto = stream inservible
MAX_FRASE = 600                    # sin límite de frase en 600 caracteres: se espera al resultado
MOTIVOS = ("con_tools", "sin_frase", "init_con_tools", "tool_use_inesperado", "desactivado", "error",
           "no_voz", "markdown")
LIMITE_RE = re.compile(r"(usage limit|limit reached|rate.?limit|out of (extra )?usage|"
                       r"credit balance|quota|overloaded|hit your limit)", re.I)


def primera_linea(resp):
    for l in (resp or "").splitlines():
        if l.strip():
            return l.strip()
    return resp or ""


def result_valido(d):
    """UN solo criterio (upgrade 06) para hablar al `result` y para aceptar la respuesta: éxito, sin error,
    texto no vacío y que no sea un aviso de límite. Si no, no se habla nada."""
    if not isinstance(d, dict) or d.get("type", "result") != "result":
        return False
    res = d.get("result")
    if d.get("is_error") or d.get("subtype", "success") != "success" or not isinstance(res, str) or not res.strip():
        return False
    return not (LIMITE_RE.search(res) and len(res.strip()) < 400)


# ---------------------------------------------------------------- clasificador (solo voz)
CONOCIMIENTO_RE = re.compile(
    r"\b(qu[eé] es|qu[eé] son|qu[eé] significa|qui[eé]n fue|qui[eé]n es|qui[eé]nes|expl[ií]ca(me)?|"
    r"cu[eé]ntame|por qu[eé]|c[oó]mo funciona|c[oó]mo se|cu[aá]nto es|cu[aá]ntos|cu[aá]ntas|"
    r"dime (un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)|traduce|define|"
    r"what is|who (is|was)|explain|tell me about|how does|why)\b", re.I)
SEGUIMIENTO_RE = re.compile(r"\b(cu[aá]l|cu[aá]les|y (el|la|los|las)|de esos|de esas|y por qu[eé])\b", re.I)
ACCION_RE = re.compile(
    r"\b(abre|abrir|[aá]breme|pon|ponme|ponle|manda|m[aá]ndale|env[ií]a|borra|elimina|apunta|anota|"
    r"recu[eé]rdame|busca|b[uú]scame|investiga|guarda|crea|cambia|mueve|lee|l[eé]eme|escribe|ejecuta|"
    r"instala|compra|paga|publica|sube|baja|activa|desactiva|archivo|archivos|carpeta|carpetas|"
    r"mi|mis|me|tengo|tenemos|pendiente|pendientes|tarea|tareas|entrega|entregas|escuela|classroom|correo|"
    r"correos|gmail|calendario|agenda|dinero|meta|coche|modo|spotify|m[uú]sica|canci[oó]n|rutina|hoy|"
    r"ma[ñn]ana|ahorita|ahora|actual|actualmente|[uú]ltimo|[uú]ltima|reciente|noticias|precio|precios|"
    r"clima|tiempo hace|hora|fecha|semana|mensaje|whatsapp|instagram|tiktok|snapchat|p[aá]gina|web|link|"
    r"url|volumen|panel|jarvis hq|my|open|send|delete|today|tomorrow|now|latest|news|price|weather)\b",
    re.I)


def ruta_sin_herramientas(texto, seguimiento=False, previo_sin_herramientas=False):
    """True solo para preguntas de conocimiento general sin acción, datos personales ni tiempo actual.
    En FOLLOW_UP entra solo si el turno anterior también fue sin herramientas. En duda: False."""
    t = (texto or "").strip()
    if not t or len(t) > 300 or ACCION_RE.search(t):
        return False
    if seguimiento and not previo_sin_herramientas:
        return False
    if CONOCIMIENTO_RE.search(t):
        return True
    return bool(seguimiento and SEGUIMIENTO_RE.search(t))


# ---------------------------------------------------------------- parser
class StreamRoto(Exception):
    pass


class Parser:
    """Consume líneas del stream. Atributos: init (tools, mcp), texto del primer bloque, tool_use, result."""
    def __init__(self, al_texto=None, al_cerrar_bloque=None, al_ver_texto=None):
        self.al_texto = al_texto or (lambda s: None)
        self.al_ver_texto = al_ver_texto or (lambda: None)   # cualquier texto principal (solo para medir)
        self.al_cerrar_bloque = al_cerrar_bloque or (lambda: None)
        self.init_tools = self.init_mcp = None
        self.tool_use = False
        self.result = None
        self.eventos = 0
        self._bloque = None          # índice del primer bloque de texto del mensaje principal
        self._bloque_hecho = False
        self._mensaje = 0            # mensajes del asistente principal vistos

    def linea(self, raw):
        raw = raw.strip()
        if not raw:
            return
        if len(raw) > MAX_LINEA:
            raise StreamRoto("línea demasiado grande")
        try:
            ev = json.loads(raw)
        except ValueError:
            raise StreamRoto("json malformado")
        if not isinstance(ev, dict):
            raise StreamRoto("evento sin estructura")
        self.eventos += 1
        tipo = ev.get("type")
        if tipo == "system":
            if ev.get("subtype") == "init":
                tools, mcp = ev.get("tools"), ev.get("mcp_servers")
                self.init_tools = list(tools) if isinstance(tools, list) else ["?"]
                self.init_mcp = list(mcp) if isinstance(mcp, list) else ["?"]
        elif tipo == "stream_event":
            self._stream(ev)
        elif tipo == "assistant":
            # duplica los deltas: solo se mira si trae herramientas
            msg = ev.get("message") or {}
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") in ("tool_use", "server_tool_use", "mcp_tool_use"):
                    self.tool_use = True
        elif tipo == "result":
            self.result = ev

    def _stream(self, ev):
        e = ev.get("event") or {}
        principal = ev.get("parent_tool_use_id") is None       # los subagentes traen el id de su herramienta
        t = e.get("type")
        if t == "content_block_start":
            cb = e.get("content_block") or {}
            if cb.get("type") in ("tool_use", "server_tool_use", "mcp_tool_use"):
                self.tool_use = True
            elif principal and cb.get("type") == "text" and self._bloque is None and self._mensaje <= 1:
                self._bloque = e.get("index")
        elif t == "message_start" and principal:
            self._mensaje += 1
            if self._bloque is not None and not self._bloque_hecho:     # otro mensaje: no se mezcla
                self._cerrar()
        elif t == "content_block_delta" and principal:
            d = e.get("delta") or {}
            if d.get("type") == "text_delta":
                self.al_ver_texto()
            if self._bloque_hecho:
                return
            if d.get("type") == "text_delta" and e.get("index") == self._bloque and self._bloque is not None:
                if isinstance(d.get("text"), str):
                    self.al_texto(d["text"])
        elif t == "content_block_stop" and principal and e.get("index") == self._bloque and not self._bloque_hecho:
            self._cerrar()

    def _cerrar(self):
        self._bloque_hecho = True
        self.al_cerrar_bloque()


# ---------------------------------------------------------------- frases hablables
ABREVIATURAS = {"sr", "sra", "srta", "dr", "dra", "lic", "ing", "prof", "etc", "ej", "p", "pág", "núm", "no",
                "vs", "aprox", "av", "col", "cía", "ee", "uu", "mr", "mrs", "ms", "st", "jr", "a", "m", "u",
                "e", "i", "approx", "fig", "min", "máx", "mín", "km", "kg", "cm", "mm"}
FIN_RE = re.compile(r"([.!?…]+)[\"'”»)\]]*(\s)")
MARKDOWN_INICIO = re.compile(r"^\s*(#|```|[-*+] |\d+[.)] |\||>)")


class Frases:
    """Recibe el texto del primer bloque y entrega pedazos hablables de la PRIMERA LÍNEA.
    pedazo 1 = frase 1 (con límite confiable); pedazo 2 = resto de la línea cuando la línea cierra."""
    def __init__(self):
        self.buf = ""
        self.entregado = 0           # caracteres de la primera línea ya entregados
        self.linea_cerrada = False
        self.motivo = None           # por qué ya no se anticipa (de MOTIVOS)
        self.frase1 = False

    def agregar(self, s):
        if self.linea_cerrada or self.motivo:
            return
        self.buf += s
        if "\n" in self.buf:
            self.buf = self.buf[:self.buf.index("\n")]
            self.linea_cerrada = True
        if MARKDOWN_INICIO.match(self.buf) or "```" in self.buf:
            self.motivo = "markdown"
        elif not self.frase1 and len(self.buf) > MAX_FRASE:
            self.motivo = "sin_frase"

    def cerrar(self):
        """Terminó el bloque de texto: la línea quedó cerrada."""
        self.linea_cerrada = True

    def siguiente(self):
        """El siguiente pedazo listo para hablar, o None."""
        if self.motivo:
            return None
        if not self.frase1:
            fin = self._fin_frase1()
            if fin is None:
                if self.linea_cerrada:
                    self.motivo = self.motivo or "sin_frase"
                return None
            self.frase1, self.entregado = True, fin
            return self.buf[:fin].strip()
        if self.linea_cerrada and self.entregado < len(self.buf):
            resto = self.buf[self.entregado:].strip()
            self.entregado = len(self.buf)
            return resto or None
        return None

    def _fin_frase1(self):
        for m in FIN_RE.finditer(self.buf):
            fin = m.end(1)
            antes = self.buf[:m.start(1)]
            palabra = re.split(r"[\s(¿¡\"'«]+", antes)[-1] if antes else ""
            if m.group(1) == "." and (palabra.lower().strip(".") in ABREVIATURAS or re.fullmatch(r"\d+", palabra)):
                continue             # Sr. / p. ej. / 3. (y 3.14 nunca llega aquí: no hay espacio tras el punto)
            if re.search(r"https?://\S*$|www\.\S*$", antes):
                continue
            frase = self.buf[:fin]
            letras = re.sub(r"[^\wáéíóúñü]", "", frase.lower())
            sin_senor = re.sub(r"^\W*(señor|sir)\W*", "", frase.strip(), flags=re.I)
            if len(letras) < 10 or len(sin_senor.split()) < 3:
                continue             # "Señor." o "Claro." no son la frase
            return fin
        return None


def coincide(hablado, final):
    """¿La primera línea final empieza con lo que ya se dijo? (normaliza espacios y formato de voz)."""
    a = re.sub(r"\s+", " ", limpiar_para_voz(hablado)).strip()
    b = re.sub(r"\s+", " ", limpiar_para_voz(final)).strip()
    return b.startswith(a)


# ---------------------------------------------------------------- voz en proceso hijo
def lanzar_decir(texto):
    """bin/decir.py como hijo: voz.lock, Juan, limpiar_para_voz, callar por pkill. Hereda JARVIS_REQ_ID.
    En su PROPIO grupo de procesos (upgrade 06): cancelar mata a decir.py y a su `say`/`afplay`, y a nadie más."""
    env = dict(os.environ, JARVIS_T_LANZADO=str(time.perf_counter_ns()))    # 09A: voz_lanzamiento
    p = subprocess.Popen([sys.executable, str(BIN / "decir.py"), texto], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                         start_new_session=True)
    VOCES.difference_update([v for v in VOCES if v.poll() is not None])
    VOCES.add(p)
    return p


VOCES = set()      # upgrade 08: voces de streaming vivas (su propia sesión), para apagar sin dejar huérfanas


def limpiar_voces():
    """Al apagar la voz (SIGTERM del supervisor): calla cada reproductor propio por su grupo. Idempotente."""
    for p in list(VOCES):
        matar_grupo(p, gracia=0.3)
        VOCES.discard(p)


def matar_grupo(proc, gracia=0.5):
    """SIGTERM al grupo del hijo de voz; SIGKILL si sigue vivo tras `gracia`. Idempotente."""
    if proc is None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        pgid = None
    propio = pgid is not None and pgid != os.getpgrp()      # nunca el grupo de Jarvis
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if propio:
                os.killpg(pgid, sig)
            elif proc.poll() is None:
                proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=gracia)
            if propio:
                try:
                    os.killpg(pgid, 0)                      # ¿queda alguien del grupo (el `say`)?
                except (ProcessLookupError, OSError):
                    return
            else:
                return
        except subprocess.TimeoutExpired:
            continue
    try: proc.wait(timeout=2)
    except Exception: pass


class Hablador:
    """Reproduce pedazos uno a la vez, sin bloquear a quien lee el stream. Nunca dos voces a la vez."""
    def __init__(self, lanzar=lanzar_decir, cerrar_pedido=lambda: False, al_empezar=None, reloj=time.perf_counter,
                 vigia=None):
        self.lanzar, self.cerrar_pedido = lanzar, cerrar_pedido
        self.vigia = vigia           # upgrade 06: oye «Jarvis» mientras suena la voz (voz/interrupciones.py)
        self.interrumpido = False
        self.interrupcion = None     # lo que confirmó el vigía (tipo, borrador, audio…)
        self.t_pedazo = None
        self._final = None           # resultado de finalizar(): se calcula una sola vez
        self.al_empezar = al_empezar or (lambda: None)
        self.reloj = reloj
        self.cola, self.hablado = [], []
        self.proc = None
        self.error = False
        self.t_inicio = self.t_fin = None
        self.incompleta = False      # pensar() avisa que la respuesta quedó a medias tras hablar
        self.t0_claude = None        # correr() anota cuándo se lanzó claude (para tts_fin)

    @property
    def hablo(self):
        return bool(self.hablado)

    def decir(self, texto):
        texto = (texto or "").strip()
        if texto and not self.error and not self.interrumpido and not self.cerrar_pedido():
            self.cola.append(texto)
        self.tick()

    def tick(self):
        if self.proc is not None:
            rc = self.proc.poll()
            if rc is None:
                if self.vigia is not None and not self.interrumpido:
                    det = self.vigia.revisar(self.hablado[-1] if self.hablado else "", self.t_pedazo)
                    if det is not None:
                        self.interrumpir(det)
                return
            self.proc = None
            self.t_fin = self.reloj()
            if rc != 0 and not self.cerrar_pedido() and not self.interrumpido:
                self.error = True
        if self.cerrar_pedido() or self.error or self.interrumpido:
            self.cola.clear()
            return
        if self.cola:
            texto = self.cola.pop(0)
            primera = self.t_inicio is None and tm.reclamar_primera_voz()   # 09A: el hijo mide fin_habla_a_voz
            if primera:
                os.environ["JARVIS_VOZ_PRIMERA"] = "1"
            try:
                self.proc = self.lanzar(texto)
            finally:
                os.environ.pop("JARVIS_VOZ_PRIMERA", None)
            self.t_pedazo = self.reloj()
            self.hablado.append(texto)
            if self.t_inicio is None:
                self.t_inicio = self.reloj()
                try:
                    self.al_empezar()
                except Exception:
                    pass

    def activo(self):
        return self.proc is not None or bool(self.cola)

    def esperar(self, timeout=120):
        """Hasta que no quede voz (sin espera ocupada: 0.1 s entre revisiones)."""
        limite = self.reloj() + timeout
        while self.activo():
            self.tick()
            if not self.activo():
                break
            if self.reloj() > limite:
                self.cancelar(); break
            time.sleep(0.1)

    def cancelar(self):
        """Para SOLO esta voz (su grupo: decir.py + say/afplay). No toca a Claude, Spotify ni otras voces.
        Idempotente. voz.lock es flock: el SO lo suelta al morir el proceso."""
        self.cola.clear()
        if self.proc is not None:
            matar_grupo(self.proc)
            self.proc = None
            self.t_fin = self.reloj()

    def interrumpir(self, det):
        """Barge-in confirmado: se calla ya y nada más de esta respuesta vuelve a sonar."""
        self.interrumpido, self.interrupcion = True, det
        self.cancelar()
        try:
            det.t_parada = self.reloj()
        except Exception:
            pass

    def finalizar(self, primera_linea_final):
        """Llegó el resultado: habla lo que falte de la primera línea, si coincide con lo ya dicho.
        Regresa False si hubo incidente (el final no empieza con lo hablado): no se habla nada más.
        Se calcula una sola vez (se llama al llegar `result` y otra vez en procesar())."""
        if self._final is not None:
            return self._final
        if self.interrumpido:
            self._final = True
            return True
        self._final = self._finalizar(primera_linea_final)
        return self._final

    def _finalizar(self, primera_linea_final):
        dicho = " ".join(self.hablado + self.cola)     # lo que ya sonó Y lo que ya está en fila para sonar
        if not coincide(dicho, primera_linea_final):
            return False
        a = re.sub(r"\s+", " ", limpiar_para_voz(dicho)).strip()
        b = re.sub(r"\s+", " ", limpiar_para_voz(primera_linea_final)).strip()
        resto = b[len(a):].strip()
        if resto:
            self.decir(resto)
        return True


# ---------------------------------------------------------------- coordinador
def _al_result(c, parser, hablador, hablar_al_result):
    """Llegó `result`: si es válido, la primera línea se habla YA (sin esperar a que claude salga).
    Si ya hubo voz anticipada, solo lo que falte. Con error o límite, no se habla nada."""
    if hablador is None or not hablar_al_result:
        return                      # (un result válido ya es final aunque antes hubo herramientas)
    if not result_valido(parser.result):
        return
    linea = primera_linea(parser.result["result"])
    if hablador.hablo:
        if not hablador.finalizar(linea):
            c.incidente = "distinto"
    elif not hablador.interrumpido:
        c.al_result = True
        hablador.decir(linea)



class Corrida:
    """Lo que pasó en una ejecución con stream (tiempos en ms desde que se lanzó claude)."""
    def __init__(self):
        self.rc = None
        self.result = None
        self.stderr = ""
        self.tool_use = False
        self.init_tools = self.init_mcp = None
        self.error = None            # "timeout" / motivo del stream roto
        self.t0 = None               # reloj del lanzamiento (perf_counter, mismo que la telemetría)
        self.t = {}                  # primer_evento, primer_texto, primera_frase, voz_inicio, resultado, fin
        self.anticipada = False
        self.motivo = None           # de MOTIVOS cuando no hubo voz anticipada
        self.incidente = None
        self.al_result = False       # upgrade 06: la voz arrancó al llegar `result`, sin esperar la salida


def correr(cmd, hablador=None, anticipar=False, cwd=None, env=None, timeout=300, reloj=time.perf_counter,
           popen=subprocess.Popen, hablar_al_result=False):
    """Lanza claude con stream-json y lo consume. Si `anticipar`, habla la primera línea por pedazos
    mientras Claude sigue; solo si init trae cero herramientas y cero MCP, y no aparece ningún tool_use."""
    c = Corrida()
    frases = Frases()
    t0 = c.t0 = reloj()
    if hablador is not None:
        hablador.t0_claude = t0
    ms = lambda: round((reloj() - t0) * 1000, 1)

    parser = Parser(al_texto=frases.agregar, al_cerrar_bloque=frases.cerrar,
                    al_ver_texto=lambda: c.t.setdefault("primer_texto", ms()))
    err_f = tempfile.TemporaryFile()
    proc = popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err_f)
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    pendiente = b""
    permitido = None                 # se decide al ver init
    try:
        while True:
            if reloj() - t0 > timeout:
                c.error = "timeout"
                proc.kill(); proc.wait()
                break
            for _key, _ in sel.select(timeout=0.15):
                trozo = os.read(proc.stdout.fileno(), 65536)
                if not trozo:
                    sel.unregister(proc.stdout)
                    break
                pendiente += trozo
                if len(pendiente) > MAX_LINEA and b"\n" not in pendiente:
                    raise StreamRoto("línea demasiado grande")
                *lineas, pendiente = pendiente.split(b"\n")
                for l in lineas:
                    parser.linea(l.decode("utf-8", "replace"))
                    c.t.setdefault("primer_evento", ms())
                    if parser.result is not None and "resultado" not in c.t:
                        c.t["resultado"] = ms()
                        _al_result(c, parser, hablador, hablar_al_result)
            # ¿se puede hablar por adelantado?
            if anticipar and hablador is not None:
                if permitido is None and parser.init_tools is not None:
                    permitido = parser.init_tools == [] and parser.init_mcp == []
                    if not permitido:
                        c.motivo = "init_con_tools"
                if parser.tool_use and not c.motivo:
                    c.motivo = "tool_use_inesperado"
                    if hablador.hablo:
                        c.incidente = "tool_use_inesperado"
                if permitido and not parser.tool_use:
                    pedazo = frases.siguiente()
                    while pedazo:                    # la cola del hablador garantiza una voz a la vez
                        c.t.setdefault("primera_frase", ms())
                        hablador.decir(pedazo)
                        pedazo = frases.siguiente()
            if hablador is not None:
                hablador.tick()                      # siempre: voz al result y vigía de barge-in
                if hablador.t_inicio is not None:
                    c.t.setdefault("voz_inicio", round((hablador.t_inicio - t0) * 1000, 1))
            if "primera_frase" not in c.t and not frases.motivo and frases._fin_frase1() is not None:
                c.t["primera_frase"] = ms()          # solo medición: aquí no se habla
            if not sel.get_map():
                break
        if c.error is None:
            if pendiente.strip():
                parser.linea(pendiente.decode("utf-8", "replace"))
                if parser.result is not None and "resultado" not in c.t:
                    c.t["resultado"] = ms()
                    _al_result(c, parser, hablador, hablar_al_result)
            proc.wait(timeout=30)
    except StreamRoto as e:
        c.error = "error"
        c.motivo = c.motivo or "error"
        try: proc.kill(); proc.wait(timeout=10)
        except Exception: pass
    finally:
        sel.close()
        if proc.poll() is None:
            try: proc.terminate(); proc.wait(timeout=10)
            except Exception:
                proc.kill(); proc.wait()
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            err_f.seek(0, 2); n = err_f.tell(); err_f.seek(max(0, n - 300))
            c.stderr = err_f.read().decode("utf-8", "replace")
        except Exception:
            pass
        err_f.close()
    c.rc = proc.returncode
    c.result = parser.result
    c.tool_use = parser.tool_use
    c.init_tools, c.init_mcp = parser.init_tools, parser.init_mcp
    c.t["fin"] = ms()
    c.anticipada = bool(hablador is not None and hablador.hablo and not c.al_result)
    if anticipar and not c.anticipada and not c.motivo:
        c.motivo = frases.motivo or "sin_frase"
    return c
