# /// script
# requires-python = ">=3.11"
# ///
"""Cerebro de Jarvis: Claude primero; si topa límite o falla, ChatGPT (Codex)."""
import json, os, re, shutil, subprocess, sys, tempfile, time, pathlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import JARVIS, CASA, log, estado, config
import telemetria as tm
import sesiones
import streaming

INSTRUCCION_VOZ = (
    "Te están hablando por voz. Responde en el idioma en que te hablaron. "
    "La PRIMERA LÍNEA de tu respuesta se dice en voz alta: una o dos frases cortas, "
    "sin markdown, con tu estilo de Jarvis. Si hace falta más detalle, ponlo después "
    "de una línea en blanco; eso solo se muestra en pantalla."
)
# Modo asistente (upgrade 06): la vida de JP sale de memoria/ y modulos/, no del código del proyecto.
# (Diagnóstico: ante "¿qué tengo pendiente?" Claude corría git y Glob/Grep por el repo.) Solo personal.
INSTRUCCION_ASISTENTE = (
    "Estás en modo asistente personal, no de desarrollo. Para la vida de JP (pendientes, escuela, rutina, "
    "dinero, planes) tus fuentes son memoria/pendientes.md, memoria/jp.md, memoria/bitacora.md, "
    "memoria/dinero.json y modulos/. No uses upgrades/, tests/, hq/, bin/, voz/, memoria/estado_proyecto.md, "
    "git ni el código para eso, salvo que JP pregunte explícitamente por el desarrollo de Jarvis. Si "
    "memoria/pendientes.md no tiene lo que pide, dilo tal cual: no busques en otro lado ni inventes."
)
LIMITE_RE = streaming.LIMITE_RE           # un solo criterio de "aviso de límite" (upgrade 06)
HIST = CASA / "historial.jsonl"

# Modo asistente (upgrade 02): una consulta cotidiana NO hereda los permisos de desarrollo.
# --restricted ignora .claude/settings.json del proyecto; solo valen el guardia y las reglas de
# seguridad/claude_asistente.json. Sin MCP, sin preguntas (dontAsk: lo no permitido se niega).
ASISTENTE_CLAUDE = ["--restricted", "--strict-mcp-config",
                    "--tools", "Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch",
                    "--permission-mode", "dontAsk",
                    "--settings", str(JARVIS / "seguridad" / "claude_asistente.json")]
# Codex de respaldo (upgrade 03): solo conversa, con dos capas.
# 1) Sin herramientas: ni comandos, ni imágenes, ni plugins/apps/navegador/computer-use/subagentes, y sin
#    cargar la config ni las reglas de JP (--ignore-user-config: nada de MCP ni perfiles de desarrollo).
# 2) Perfil de permisos "jarvis_asistente" (Seatbelt): lee solo lo mínimo del sistema, el proyecto y el
#    binario de Codex; ~/.jarvis/ DENEGADO; nada escribible; red apagada. OJO: --sandbox anula los perfiles
#    (no se suman), por eso ya no se usa --sandbox read-only.
CODEX_VERIFICADO = "0.164.0"     # versión donde se probó el aislamiento real (T11–T16); otra = sin respaldo
PERFIL_CODEX = "jarvis_asistente"
_FS_CODEX = ('{":minimal"="read", ":workspace_roots"={"."="read"}, "~/.local/bin"="read", '
             '"~/.codex/packages"="read", "~/.jarvis"="deny"}')
PERMISOS_CODEX = ["-c", f'default_permissions="{PERFIL_CODEX}"',
                  "-c", f"permissions.{PERFIL_CODEX}.filesystem={_FS_CODEX}",
                  "-c", f"permissions.{PERFIL_CODEX}.network.enabled=false"]
ASISTENTE_CODEX = ["--ignore-user-config", "--ignore-rules", "--ephemeral",
                   "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
                   "-c", 'shell_environment_policy.inherit="core"', "-c", "agents.enabled=false",
                   *[x for f in ("shell_tool", "unified_exec", "view_image", "multi_agent", "plugins", "apps",
                                 "computer_use", "browser_use", "browser_use_external", "in_app_browser",
                                 "image_generation", "hooks", "skill_search", "tool_suggest", "sleep_tool",
                                 "code_mode_host")
                     for x in ("--disable", f)],
                   *PERMISOS_CODEX]
CANARIO = CASA / "canario_upgrade03.txt"     # contenido inventado: si Codex lo lee, el aislamiento falló
SIN_RESPALDO = "respaldo deshabilitado por seguridad"
_SECRETO_RE = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION|^ANTHROPIC|^OPENAI|"
                         r"^GROQ|^ELEVEN|^NTFY|^GH_|^GITHUB|^AWS|^GOOGLE", re.I)

def entorno_asistente():
    return {**os.environ, "JARVIS_MODO": "asistente"}

def entorno_codex():
    """Sin llaves ni tokens de nadie (Codex usa su sesión de ChatGPT en ~/.codex, no variables)."""
    return {k: v for k, v in entorno_asistente().items() if not _SECRETO_RE.search(k)}
NO_EXISTE_RE = re.compile(r"no conversation found", re.I)   # --resume de un ID que Claude ya no tiene

def _historial(n=6, origen=None):
    """Últimas n pláticas. origen='personal' filtra (líneas viejas sin el campo = personal)."""
    if not HIST.exists():
        return []
    filas = [json.loads(l) for l in HIST.read_text().splitlines()[-(n * 10 if origen else n):] if l.strip()]
    if origen:
        filas = [h for h in filas if h.get("origen", "personal") == origen]
    return filas[-n:]

def _guardar(pregunta, respuesta, cerebro, origen="personal"):
    with open(HIST, "a") as f:
        f.write(json.dumps({"t": time.time(), "fecha": f"{datetime.datetime.now():%Y-%m-%d %H:%M}",
                            "tu": pregunta, "jarvis": respuesta, "cerebro": cerebro, "origen": origen},
                           ensure_ascii=False) + "\n")

def _leer_json(salida):
    """--output-format json: un objeto con result, is_error, session_id, duration_ms, duration_api_ms."""
    try:
        d = json.loads(salida)
        return d if isinstance(d, dict) else None
    except ValueError:
        return None

def asistente_sin_herramientas():
    """Los mismos candados, pero --tools "" (se REEMPLAZA el valor, sin duplicar la bandera)."""
    a = list(ASISTENTE_CLAUDE)
    a[a.index("--tools") + 1] = ""
    return a

def instrucciones(voz, origen):
    """Un solo --append-system-prompt: modo asistente (personal) + voz, juntos."""
    partes = ([INSTRUCCION_ASISTENTE] if origen == "personal" else []) + ([INSTRUCCION_VOZ] if voz else [])
    return ["--append-system-prompt", "\n\n".join(partes)] if partes else []

class Flujo:
    """Stream-json solo para el ciclo de voz (upgrade 05). anticipar = puede hablar antes del resultado.
    al_result (upgrade 06) = la primera línea suena al llegar `result`, sin esperar la salida de claude."""
    def __init__(self, hablador, anticipar, motivo=None, al_result=False):
        self.hablador, self.anticipar, self.al_result = hablador, anticipar, al_result
        self.motivo = motivo         # por qué no se anticipa de entrada: con_tools / desactivado
        self.corrida = None

def _claude_una(texto, voz, reanudar, flujo=None, origen="personal"):
    """Una llamada a claude -p. reanudar = ID exacto (--resume) o None (sesión nueva con --session-id).
    Devuelve (respuesta, error, session_id devuelto)."""
    t_prep = tm.ahora()
    cmd = ["claude", "-p", texto]
    cmd += (["--output-format", "stream-json", "--verbose", "--include-partial-messages"] if flujo
            else ["--output-format", "json"])
    cmd += ["--resume", reanudar] if reanudar else ["--session-id", sesiones.nuevo_id()]
    cmd += instrucciones(voz, origen)
    # candados del upgrade 02 en CADA llamada, también al reanudar; la ruta sin herramientas solo vacía --tools
    cmd += asistente_sin_herramientas() if flujo and flujo.anticipar else ASISTENTE_CLAUDE
    tm.sesion("reanudada" if reanudar else "nueva")
    tm.registrar("claude_preparacion", tm._ms(t_prep))
    if flujo:
        return _claude_stream(cmd, reanudar, flujo)
    with tm.etapa("claude_p", ruta="claude") as e:      # proceso completo: arranque + API + salida
        t0 = tm.ahora()
        try:
            # stdin cerrado (EOF inmediato): heredado, claude -p espera 3 s "no stdin data received".
            r = subprocess.run(cmd, cwd=JARVIS, capture_output=True, text=True, timeout=300,
                               stdin=subprocess.DEVNULL, env=entorno_asistente())
        except subprocess.TimeoutExpired:
            e.estado = "timeout"
            return None, "tardó demasiado", None
        sub_ms = tm._ms(t0)
        salida, err = (r.stdout or "").strip(), (r.stderr or "").strip()
        d = _leer_json(salida)
        if d is not None:
            tm.desglose_claude(sub_ms, d.get("duration_ms"), d.get("duration_api_ms"), bool(reanudar))
        res = (d.get("result") or "").strip() if d and isinstance(d.get("result"), str) else ""
        if r.returncode != 0 or d is None or d.get("is_error") or not res \
                or (LIMITE_RE.search(res) and len(res) < 400):
            e.estado = "error"
            return None, (res or salida or err)[:300], None
    return res, None, d.get("session_id")

def _claude_stream(cmd, reanudar, flujo):
    """stream-json: misma interfaz que la ruta JSON. `result` es la fuente de la respuesta completa."""
    with tm.etapa("claude_p", ruta="claude") as e:
        c = streaming.correr(cmd, flujo.hablador, flujo.anticipar, cwd=JARVIS, env=entorno_asistente(),
                             hablar_al_result=flujo.al_result)
        flujo.corrida = c
        e.extra = {"anticipada": c.anticipada}
        if not c.anticipada:
            e.extra["motivo"] = c.motivo or flujo.motivo or "sin_frase"
        for clave, etapa in (("primer_evento", "claude_primer_evento"), ("primer_texto", "claude_primer_texto"),
                             ("primera_frase", "claude_primera_frase"), ("resultado", "claude_resultado"),
                             ("voz_inicio", "tts_inicio")):
            if clave in c.t:
                tm.registrar(etapa, c.t[clave])
        if c.anticipada and "voz_inicio" in c.t and "resultado" in c.t and c.t["resultado"] > c.t["voz_inicio"]:
            tm.registrar("voz_solapada", c.t["resultado"] - c.t["voz_inicio"])
        if "fin" in c.t:
            tm.registrar("claude_salida", c.t["fin"])        # proceso cerrado y recolectado
            if "voz_inicio" in c.t and c.t["fin"] > c.t["voz_inicio"]:
                tm.registrar("ahorro_result", c.t["fin"] - c.t["voz_inicio"])   # cuánto antes de la salida habló
        if c.incidente:
            tm.registrar("incidente_voz", 0, estado="error", extra={"motivo": c.incidente})
        d = c.result if isinstance(c.result, dict) else None
        if d is not None:
            tm.desglose_claude(c.t.get("fin", 0), d.get("duration_ms"), d.get("duration_api_ms"), bool(reanudar))
        if c.error == "timeout":
            e.estado = "timeout"
            return None, "tardó demasiado", None
        res = (d.get("result") or "").strip() if d and isinstance(d.get("result"), str) else ""
        if streaming.result_valido(d) and c.error is None:
            if c.rc != 0:                                    # result bueno y luego salió mal: cuenta como buena
                tm.registrar("incidente_voz", 0, estado="error", extra={"motivo": "salida_tardia"})
            return res, None, d.get("session_id")
        e.estado = "error"
        return None, (res or c.stderr.strip() or "stream incompleto")[:300], None

def claude(texto, voz, origen="personal", flujo=None):
    if not shutil.which("claude"):
        return None, "no instalado"
    with sesiones.turno(origen):                  # serializa por origen: nadie pisa el mismo ID
        sid = sesiones.vigente(origen)
        res, err, devuelto = _claude_una(texto, voz, sid, flujo, origen)
        nada_paso = not flujo or (not flujo.hablador.hablo and not (flujo.corrida and flujo.corrida.tool_use))
        if res is None and sid and NO_EXISTE_RE.search(err or "") and nada_paso:
            log("la sesión del asistente ya no existe; empiezo otra (sin --continue)")
            sid = None
            res, err, devuelto = _claude_una(texto, voz, None, flujo, origen)
        if res is not None:
            if sid and devuelto != sid:
                log("Claude devolvió otro session_id al reanudar; guardo el devuelto")
            if sesiones.valido(devuelto):
                sesiones.guardar(origen, devuelto, nueva=sid is None or devuelto != sid)
            else:
                sesiones.olvidar(origen)          # sin ID confiable: la próxima empieza limpia
        return res, err

def _codex_valido(c):
    try:
        return subprocess.run([c, "exec", "--help"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False

_CODEX = None
def buscar_codex():
    global _CODEX
    if _CODEX:
        return _CODEX
    for c in [str(pathlib.Path.home() / ".local/bin/codex"), shutil.which("codex"),
              "/Applications/ChatGPT.app/Contents/Resources/codex",
              "/Applications/Codex.app/Contents/Resources/codex"]:
        if c and os.path.isfile(c) and os.access(c, os.X_OK) and _codex_valido(c):
            _CODEX = c
            return c
    return None

_AISLADO = {}
def codex_aislado(exe):
    """Antes de usar Codex: versión verificada y prueba en Seatbelt de que el canario NO se lee y un
    archivo del proyecto SÍ. Se repite una vez por proceso. Si algo no cuadra, no hay respaldo."""
    if exe in _AISLADO:
        return _AISLADO[exe]
    ok = False
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL).stdout.split()
        if v and v[-1] == CODEX_VERIFICADO:
            if not CANARIO.exists():
                fd = os.open(CANARIO, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write("CANARIO-UPGRADE03 contenido inventado: zafiro-7319-murcielago-QX\n")
            base = [exe, "sandbox", *PERMISOS_CODEX, "-P", PERFIL_CODEX, "--"]
            no = subprocess.run(base + ["/bin/cat", str(CANARIO)], cwd=JARVIS, capture_output=True,
                                text=True, timeout=30, stdin=subprocess.DEVNULL, env=entorno_codex())
            si = subprocess.run(base + ["/bin/cat", str(JARVIS / "config.json")], cwd=JARVIS,
                                capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
                                env=entorno_codex())
            ok = (no.returncode != 0 and "zafiro" not in no.stdout + no.stderr
                  and "operation not permitted" in no.stderr.lower() and si.returncode == 0)
    except Exception:
        ok = False
    if not ok:
        log("Codex sin aislamiento verificable: respaldo deshabilitado por seguridad")
    _AISLADO[exe] = ok
    return ok

def codex(texto, voz, origen="personal"):
    exe = buscar_codex()
    if not exe:
        return None, "Codex no instalado"
    if not codex_aislado(exe):
        return None, SIN_RESPALDO
    # Contexto de respaldo: solo pláticas personales, y solo para consultas personales.
    previas = _historial(4, "personal") if origen == "personal" else []
    contexto = "\n".join(f"JP: {h['tu']}\nJarvis: {h['jarvis'][:400]}" for h in previas)
    prompt = (("Conversación reciente:\n" + contexto + "\n\n") if contexto else "") + \
             ("[Instrucción] " + INSTRUCCION_VOZ + "\n\n" if voz else "") + "JP dice: " + texto
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as t:
        salida_f = t.name
    with tm.etapa("codex_exec", ruta="codex") as e:
        try:
            r = subprocess.run([exe, "exec", "--skip-git-repo-check", *ASISTENTE_CODEX,
                                "-o", salida_f, prompt], cwd=JARVIS, capture_output=True, text=True,
                               timeout=300, stdin=subprocess.DEVNULL, env=entorno_codex())
            salida = pathlib.Path(salida_f).read_text().strip() or (r.stdout or "").strip()
        except subprocess.TimeoutExpired:
            e.estado = "timeout"
            return None, "Codex tardó demasiado"
        finally:
            try: os.unlink(salida_f)
            except OSError: pass
        if r.returncode != 0 or not salida:
            e.estado = "error"
            return None, (r.stderr or "")[-300:]
    return salida, None

INCOMPLETA = "Señor, la respuesta quedó incompleta."

def pensar(texto, voz=False, origen="personal", hablador=None, sin_herramientas=False):
    """origen: 'personal' (voz, ⌃⌥Espacio, terminal) o 'auto' (resumen matutino). Nunca se mezclan.
    hablador/sin_herramientas: solo el ciclo de voz (upgrade 05). Con hablador se usa stream-json y, si la
    pregunta va por la ruta sin herramientas, se puede hablar la primera línea antes del resultado."""
    origen = origen if origen in sesiones.ORIGENES else "personal"
    estado("pensando", texto)
    flujo = None
    if hablador is not None:
        c = config()
        if c.get("claude_streaming", True):
            activa = bool(c.get("voz_anticipada", True))
            flujo = Flujo(hablador, activa and sin_herramientas,
                          None if activa and sin_herramientas else ("desactivado" if not activa else "con_tools"),
                          al_result=bool(c.get("hablar_al_result", True)))
    resp, err = claude(texto, voz, origen, flujo) if flujo else claude(texto, voz, origen)
    cerebro = "claude"
    tm.ruta("claude")
    if resp is None and flujo and (hablador.hablo or (flujo.corrida and flujo.corrida.tool_use)):
        # Ya sonó algo o Claude usó herramientas: ni Codex ni reintento (no se repiten acciones).
        log(f"Claude falló tras hablar o usar herramientas ({(err or '')[:80]}); respuesta incompleta")
        sesiones.olvidar(origen)
        hablador.incompleta = True
        resp, cerebro = INCOMPLETA, "ninguno"
        tm.ruta("ninguno")
    elif resp is None:
        log(f"Claude no respondió ({err}); paso a ChatGPT")
        sesiones.olvidar(origen)        # la sesión de Claude no verá este turno: la próxima empieza limpia
        resp, err2 = codex(texto, voz, origen)
        cerebro = "chatgpt"
        tm.ruta("codex")
        if resp is None:
            log(f"ChatGPT tampoco ({err2})")
            if err2 == SIN_RESPALDO:
                resp = ("Señor, Claude no está disponible y el respaldo con ChatGPT está deshabilitado "
                        "por seguridad. Los comandos rápidos siguen funcionando.")
            else:
                resp = ("Señor, mis dos cerebros están fuera de servicio por el momento. "
                        "Los comandos rápidos siguen funcionando.")
            cerebro = "ninguno"
            tm.ruta("ninguno")
    _guardar(texto, resp, cerebro, origen)          # una sola vez, con el texto de `result`
    if not (hablador is not None and hablador.activo()):
        estado("listo")                             # si la voz anticipada sigue sonando, ella lo pone al final
    return resp, cerebro

primera_linea = streaming.primera_linea

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    hablar = "--hablar" in sys.argv
    texto = " ".join(args).strip()
    if not texto:
        print("Uso: pensar.py \"pregunta\" [--hablar]"); sys.exit(1)
    tm.desde_entorno("texto")               # ⌃⌥Espacio / terminal: el total empieza aquí
    resp, cerebro = pensar(texto, voz=hablar)
    print(resp)
    if hablar:
        from decir import decir
        decir(primera_linea(resp))
    else:
        tm.total()
