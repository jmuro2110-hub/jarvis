# /// script
# requires-python = ">=3.11"
# ///
"""Cerebro de Jarvis: Claude primero; si topa límite o falla, ChatGPT (Codex)."""
import json, os, re, shutil, subprocess, sys, tempfile, time, pathlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import JARVIS, CASA, log, estado
import telemetria as tm
import sesiones

INSTRUCCION_VOZ = (
    "Te están hablando por voz. Responde en el idioma en que te hablaron. "
    "La PRIMERA LÍNEA de tu respuesta se dice en voz alta: una o dos frases cortas, "
    "sin markdown, con tu estilo de Jarvis. Si hace falta más detalle, ponlo después "
    "de una línea en blanco; eso solo se muestra en pantalla."
)
LIMITE_RE = re.compile(r"(usage limit|limit reached|rate.?limit|out of (extra )?usage|"
                       r"credit balance|quota|overloaded|hit your limit)", re.I)
HIST = CASA / "historial.jsonl"

# Modo asistente (upgrade 02): una consulta cotidiana NO hereda los permisos de desarrollo.
# --restricted ignora .claude/settings.json del proyecto; solo valen el guardia y las reglas de
# seguridad/claude_asistente.json. Sin MCP, sin preguntas (dontAsk: lo no permitido se niega).
ASISTENTE_CLAUDE = ["--restricted", "--strict-mcp-config",
                    "--tools", "Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch",
                    "--permission-mode", "dontAsk",
                    "--settings", str(JARVIS / "seguridad" / "claude_asistente.json")]
# Codex de respaldo: solo conversa. Sandbox de solo lectura (sin escribir, sin red, sin AppleScript)
# y sin plugins/MCP de computer-use o navegador, que actuarían fuera del sandbox.
ASISTENTE_CODEX = ["--sandbox", "read-only", "-c", 'approval_policy="never"',
                   "--disable", "plugins", "--disable", "apps", "--disable", "computer_use",
                   "--disable", "browser_use", "--disable", "browser_use_external",
                   "-c", "mcp_servers.node_repl.enabled=false"]

def entorno_asistente():
    return {**os.environ, "JARVIS_MODO": "asistente"}
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

def _claude_una(texto, voz, reanudar):
    """Una llamada a claude -p. reanudar = ID exacto (--resume) o None (sesión nueva con --session-id).
    Devuelve (respuesta, error, session_id devuelto)."""
    t_prep = tm.ahora()
    cmd = ["claude", "-p", texto, "--output-format", "json"]
    cmd += ["--resume", reanudar] if reanudar else ["--session-id", sesiones.nuevo_id()]
    if voz:
        cmd += ["--append-system-prompt", INSTRUCCION_VOZ]
    cmd += ASISTENTE_CLAUDE                       # candados del upgrade 02 en CADA llamada, también al reanudar
    tm.sesion("reanudada" if reanudar else "nueva")
    tm.registrar("claude_preparacion", tm._ms(t_prep))
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

def claude(texto, voz, origen="personal"):
    if not shutil.which("claude"):
        return None, "no instalado"
    with sesiones.turno(origen):                  # serializa por origen: nadie pisa el mismo ID
        sid = sesiones.vigente(origen)
        res, err, devuelto = _claude_una(texto, voz, sid)
        if res is None and sid and NO_EXISTE_RE.search(err or ""):
            log("la sesión del asistente ya no existe; empiezo otra (sin --continue)")
            sid = None
            res, err, devuelto = _claude_una(texto, voz, None)
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

def codex(texto, voz, origen="personal"):
    exe = buscar_codex()
    if not exe:
        return None, "Codex no instalado"
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
                               timeout=300, stdin=subprocess.DEVNULL, env=entorno_asistente())
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

def pensar(texto, voz=False, origen="personal"):
    """origen: 'personal' (voz, ⌃⌥Espacio, terminal) o 'auto' (resumen matutino). Nunca se mezclan."""
    origen = origen if origen in sesiones.ORIGENES else "personal"
    estado("pensando", texto)
    resp, err = claude(texto, voz, origen)
    cerebro = "claude"
    tm.ruta("claude")
    if resp is None:
        log(f"Claude no respondió ({err}); paso a ChatGPT")
        sesiones.olvidar(origen)        # la sesión de Claude no verá este turno: la próxima empieza limpia
        resp, err2 = codex(texto, voz, origen)
        cerebro = "chatgpt"
        tm.ruta("codex")
        if resp is None:
            log(f"ChatGPT tampoco ({err2})")
            resp = ("Señor, mis dos cerebros están fuera de servicio por el momento. "
                    "Los comandos rápidos siguen funcionando.")
            cerebro = "ninguno"
            tm.ruta("ninguno")
    _guardar(texto, resp, cerebro, origen)
    estado("listo")
    return resp, cerebro

def primera_linea(resp):
    for l in resp.splitlines():
        if l.strip():
            return l.strip()
    return resp

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
