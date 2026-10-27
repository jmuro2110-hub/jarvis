"""Guardia del modo asistente (upgrade 02): hook PreToolUse de Claude Code.

Solo se registra en seguridad/claude_asistente.json, que pensar.py pasa a `claude -p --restricted`.
El Claude Code interactivo de desarrollo NO lo carga. Convierte cada llamada a herramienta en una
operación estructurada, la evalúa con bin/politica.py y bloquea (exit 2) todo lo que no sea
permitido, incluido lo que no sabe interpretar. Ante cualquier error, bloquea.

Corre con el python3 del sistema (3.9), sin uv:  /usr/bin/python3 -I bin/guardia.py < evento.json
"""
import json, os, pathlib, re, shlex, sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import politica                                                   # noqa: E402

JARVIS = AQUI.parent
HOME = pathlib.Path.home()
JV = JARVIS / "bin" / "jv"

# Lo único que el asistente puede escribir con Edit/Write: sus notas de datos.
ANOTABLES = {JARVIS / "memoria" / n for n in ("pendientes.md", "dinero.json", "bitacora.md")}
# Tocar esto desde el asistente es intentar darse permisos.
CONTROLES = [JARVIS / ".claude", JARVIS / "seguridad", JARVIS / "bin", JARVIS / "voz",
             JARVIS / "hammerspoon", JARVIS / "scripts", JARVIS / "CLAUDE.md", JARVIS / "AGENTS.md",
             JARVIS / "config.json", JARVIS / ".git", HOME / ".jarvis", HOME / ".claude",
             HOME / ".codex", HOME / ".hammerspoon"]
SECRETOS = [HOME / ".jarvis" / "secretos.env", HOME / ".jarvis" / "autorizaciones.json",
            HOME / ".codex" / "auth.json", HOME / ".claude" / ".credentials.json", HOME / ".ssh",
            HOME / ".gnupg", HOME / "Library" / "Keychains", HOME / ".aws", HOME / ".config" / "gh",
            # upgrade 07: los recuerdos entran a Claude solo por la búsqueda selectiva, nunca leyendo el archivo
            HOME / ".jarvis" / "recuerdos.jsonl"]
# Dónde se permite organizar (mkdir/mv/cp sin sobrescribir). Jarvis y sus datos quedan fuera.
ORGANIZABLES = [HOME / d for d in ("Documents", "Desktop", "Downloads", "Pictures", "Movies", "Music")]
PAPELERA = HOME / ".Trash"

JV_LOCALES = {"decir", "avisar", "hq", "resumen", "latencia", "vigia"}
INTERPRETES = {"python", "python3", "perl", "ruby", "node", "osascript", "sh", "bash", "zsh", "env",
               "xargs", "sudo", "su", "eval", "exec", "command", "nohup", "swift", "php", "lua",
               "shortcuts", "automator", "jxa", "uv", "npx", "claude", "codex", "launchctl",
               "defaults", "crontab", "curl", "wget", "scp", "ssh", "rsync", "dd", "tee", "git"}
BORRADO = {"rm", "rmdir", "unlink", "srm", "trash", "shred", "truncate"}

APP_RE = r'[\w][\w .&+-]{0,40}'
OSA_PERMITIDOS = [
    (rf'tell application "Spotify" to (play|pause|playpause|next track|previous track)', "multimedia"),
    (rf'if application "Spotify" is running then tell application "Spotify" to (play|pause)', "multimedia"),
    (r'set volume output volume \d{1,3}', "multimedia"),
    (r'set volume output volume \(\(output volume of \(get volume settings\)\) \+ -?\d{1,3}\)', "multimedia"),
    (r'set volume (with|without) output muted', "multimedia"),
    (r'output volume of \(get volume settings\)', "consultar"),
    (r'tell application "Spotify" to \(?(name|artist) of current track\)?'
     r'( & " de " & \(?(name|artist) of current track\)?)?', "consultar"),
    (rf'tell application "{APP_RE}" to quit', "cerrar_app"),
]


class Bloqueo(Exception):
    pass


def ruta(p, cwd):
    p = os.path.expanduser(p)
    return pathlib.Path(os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p)))


def dentro(p, base):
    return p == base or base in p.parents


def es_secreta(p):
    """Secreto, o carpeta que contiene un secreto (un Grep sobre ~ también lo leería)."""
    return any(dentro(p, s) or dentro(s, p) for s in SECRETOS)


# ---------- Bash ----------
def tokens(cmd):
    if re.search(r"[`$\n\r\\]", cmd):
        raise Bloqueo("sustituciones, variables o varias líneas no se permiten en modo asistente")
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()")
    lx.whitespace_split = True
    lx.commenters = ""                   # un "#" nunca esconde texto: se evalúa todo
    try:
        t = list(lx)
    except ValueError:
        raise Bloqueo("comando mal formado")
    if not t:
        raise Bloqueo("comando vacío")
    if any(re.fullmatch(r"[;&|<>()]+", x) for x in t):
        raise Bloqueo("comandos encadenados, tuberías o redirecciones no se permiten")
    return t


def sin_comodines(args):
    for a in args:
        if re.search(r"[*?\[\]{}]", a) or (a.startswith("~") and not a.startswith("~/") and a != "~"):
            raise Bloqueo("comodines o rutas que no se pueden verificar")


def op_archivos(prog, args, cwd):
    flags = [a for a in args if a.startswith("-")]
    paths = [a for a in args if not a.startswith("-")]
    sin_comodines(paths)
    validos = {"mkdir": {"-p", "-v"}, "mv": {"-n", "-v"}, "cp": {"-n", "-v", "-R", "-r", "-p"}}[prog]
    if set(flags) - validos or not paths or (prog != "mkdir" and len(paths) < 2):
        raise Bloqueo(f"{prog}: opciones o argumentos no permitidos")
    rs = [ruta(p, cwd) for p in paths]
    if prog in ("mv", "cp") and dentro(rs[-1], PAPELERA):
        return {"tipo": "borrar", "via": prog}               # mandar a la Papelera es borrar
    for r in rs:
        if any(dentro(r, c) for c in CONTROLES) or dentro(JARVIS, r):
            return {"tipo": "evadir_controles", "via": prog}
        if es_secreta(r) or not any(dentro(r, o) and r != o for o in ORGANIZABLES):
            raise Bloqueo(f"{prog}: fuera de las carpetas que puedo organizar")
    if prog in ("mv", "cp"):
        destino, origenes = rs[-1], rs[:-1]
        finales = [destino / o.name for o in origenes] if destino.is_dir() else [destino]
        if len(origenes) > 1 and not destino.is_dir():
            raise Bloqueo(f"{prog}: varios orígenes a un destino que no es carpeta")
        if any(f.exists() or f.is_symlink() for f in finales):
            raise Bloqueo(f"{prog}: sobrescribiría un archivo existente (eso es borrar)")
    return {"tipo": "organizar_archivos", "via": prog}


def op_jv(args):
    if not args:
        raise Bloqueo("jv sin herramienta")
    sub, resto = args[0], args[1:]
    if sub == "abrir":
        if resto == ["--perfiles"]:
            return {"tipo": "consultar", "via": "jv abrir --perfiles"}
        urls = [a for a in resto if not a.startswith("--")]
        flags = set(resto) - set(urls)
        if len(urls) != 1 or flags - {"--escuela", "--personal"} or len(flags) > 1:
            raise Bloqueo("jv abrir: una URL y como mucho --escuela o --personal")
        mundo = "escuela" if "--escuela" in flags else "personal" if "--personal" in flags else None
        return {"tipo": "abrir_web", "url": urls[0], "mundo": mundo or politica.mundo_de(urls[0])}
    if sub == "modo" and len(resto) >= 1 and set(resto[1:]) <= {"--hablar"}:
        return {"tipo": "modo", "nombre": resto[0]}
    if sub in JV_LOCALES:
        return {"tipo": "funcion_local", "nombre": sub}
    raise Bloqueo(f"jv {sub[:20]}: herramienta no autorizada en modo asistente")


def op_osascript(args):
    if len(args) != 2 or args[0] != "-e":
        raise Bloqueo("osascript: solo una orden -e conocida")
    s = args[1].strip()
    for patron, tipo in OSA_PERMITIDOS:
        if re.fullmatch(patron, s):
            return {"tipo": tipo, "via": "osascript"}
    b = s.lower()
    if "empty" in b and "trash" in b:
        return {"tipo": "vaciar_papelera", "via": "osascript"}
    if re.search(r"\b(delete|move .* to trash)\b", b):
        return {"tipo": "borrar", "via": "osascript"}
    raise Bloqueo("AppleScript no clasificado (automatización de interfaz, shell u otra app)")


def op_bash(cmd, cwd):
    t = tokens(cmd)
    prog, args = t[0], t[1:]
    if "=" in prog:
        raise Bloqueo("variables de entorno antes del comando")
    if "/" in prog:
        if ruta(prog, cwd) == JV:
            return op_jv(args)
        raise Bloqueo("solo bin/jv se ejecuta por ruta")
    if prog in BORRADO:
        return {"tipo": "borrar", "via": prog}
    if prog == "find":
        if any(re.fullmatch(r"-(delete|exec\w*|ok\w*|fprint\w*|fls)", a) for a in args):
            return {"tipo": "borrar", "via": "find"}
        return {"tipo": "consultar", "via": "find"}
    if prog == "osascript":
        return op_osascript(args)
    if prog in INTERPRETES:
        raise Bloqueo(f"{prog}: ejecutar código o red arbitraria no se permite en modo asistente")
    if prog == "open":
        if len(args) == 2 and args[0] == "-a" and "/" not in args[1]:
            return {"tipo": "abrir_app", "app": args[1]}
        raise Bloqueo("open: solo 'open -a App'; las páginas se abren con bin/jv abrir")
    if prog in ("mkdir", "mv", "cp"):
        return op_archivos(prog, args, cwd)
    if prog in ("ls", "pwd", "date", "cal", "mdfind", "echo", "whoami", "uptime"):
        if prog == "ls":
            for a in args:
                if not a.startswith("-") and es_secreta(ruta(a, cwd)):
                    raise Bloqueo("ls: carpeta con secretos")
        return {"tipo": "consultar", "via": prog}
    if prog in ("say", "afplay"):
        if any(a in ("-o", "--output-file") or a.startswith("--output") for a in args):
            raise Bloqueo("say: no escribe archivos en modo asistente")
        return {"tipo": "funcion_local", "nombre": prog}
    if prog == "pkill" and args in (["-x", "say"], ["-x", "afplay"]):
        return {"tipo": "funcion_local", "nombre": "callar"}
    if prog == "pmset":
        if args in (["sleepnow"], ["displaysleepnow"]):
            return {"tipo": "sistema", "via": "pmset"}
        if args[:1] == ["-g"]:
            return {"tipo": "consultar", "via": "pmset"}
    raise Bloqueo(f"{prog[:30]}: comando no clasificado en modo asistente")


# ---------- herramientas de Claude Code ----------
def op_herramienta(nombre, entrada, cwd):
    entrada = entrada or {}
    if nombre == "Bash":
        return op_bash(str(entrada.get("command") or ""), cwd)
    if nombre in ("Read", "Glob", "Grep"):
        p = entrada.get("file_path") or entrada.get("path") or cwd
        if es_secreta(ruta(str(p), cwd)):
            raise Bloqueo("lectura de credenciales o secretos")
        return {"tipo": "consultar", "via": nombre}
    if nombre in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        p = ruta(str(entrada.get("file_path") or entrada.get("notebook_path") or ""), cwd)
        if nombre != "NotebookEdit" and p in ANOTABLES:
            return {"tipo": "anotar", "via": nombre}
        if any(dentro(p, c) for c in CONTROLES) or es_secreta(p):
            return {"tipo": "evadir_controles", "via": nombre}
        raise Bloqueo("el asistente solo escribe pendientes, dinero y bitácora")
    if nombre in ("WebSearch", "WebFetch"):
        url = str(entrada.get("url") or "")
        if nombre == "WebFetch" and not re.match(r"^https?://", url, re.I):
            raise Bloqueo("WebFetch: solo http(s)")
        return {"tipo": "consultar", "via": nombre}
    if nombre in ("TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"):
        return {"tipo": "funcion_local", "nombre": nombre}
    raise Bloqueo(f"herramienta {nombre[:40]} no autorizada en modo asistente")


def detalle(op):
    if op.get("tipo") == "abrir_web":
        m = re.match(r"^https?://([^/?#]+)", op.get("url", ""), re.I)
        return m.group(1).lower() if m else None          # solo el dominio
    return op.get("app") or op.get("nombre") or op.get("via")


def decidir(evento):
    """→ (permitido: bool, motivo). Pura: la usan el hook y las pruebas."""
    nombre = str(evento.get("tool_name") or "")
    cwd = str(evento.get("cwd") or JARVIS)
    try:
        op = op_herramienta(nombre, evento.get("tool_input"), cwd)
        d = politica.evaluar(op)
    except Bloqueo as e:
        op, d = {"tipo": "desconocida"}, politica.Decision("bloqueado", str(e))
    politica.auditar(op["tipo"], d, herramienta=nombre[:40], detalle=detalle(op))
    if d.nivel == "permitido":
        return True, d.motivo
    if d.nivel == "confirmar":
        return False, ("Requiere aprobación manual de JP y todavía no hay una interfaz confiable para "
                       "darla: no se ejecuta. Dígale al señor qué haría falta, sin intentar otra vía.")
    if d.nivel == "prohibido":
        return False, f"Prohibido siempre ({d.motivo}). No lo intente por otra vía."
    return False, (f"Bloqueado en modo asistente: {d.motivo}. Si es legítimo, JP debe hacerlo "
                   "o clasificarlo en modo desarrollo.")


def main():
    try:
        evento = json.loads(sys.stdin.read() or "{}")
        ok, motivo = decidir(evento)
    except Exception as e:                       # cualquier fallo del guardia = bloqueo
        ok, motivo = False, f"guardia falló ({type(e).__name__}); por seguridad no se ejecuta"
    if ok:
        sys.exit(0)                              # sigue el flujo normal de permisos (dontAsk + allow)
    print(motivo, file=sys.stderr)
    sys.exit(2)                                  # exit 2 = Claude Code bloquea la herramienta


if __name__ == "__main__":
    main()
