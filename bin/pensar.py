# /// script
# requires-python = ">=3.11"
# ///
"""Cerebro de Jarvis: Claude primero; si topa límite o falla, ChatGPT (Codex)."""
import json, os, re, shutil, subprocess, sys, tempfile, time, pathlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import JARVIS, CASA, log, estado

INSTRUCCION_VOZ = (
    "Te están hablando por voz. Responde en el idioma en que te hablaron. "
    "La PRIMERA LÍNEA de tu respuesta se dice en voz alta: una o dos frases cortas, "
    "sin markdown, con tu estilo de Jarvis. Si hace falta más detalle, ponlo después "
    "de una línea en blanco; eso solo se muestra en pantalla."
)
LIMITE_RE = re.compile(r"(usage limit|limit reached|rate.?limit|out of (extra )?usage|"
                       r"credit balance|quota|overloaded|hit your limit)", re.I)
HIST = CASA / "historial.jsonl"
SESION_MIN = 30   # después de 30 min sin hablar, empieza conversación nueva (ahorra uso)

def _historial(n=6):
    if not HIST.exists():
        return []
    lineas = HIST.read_text().splitlines()[-n:]
    return [json.loads(l) for l in lineas if l.strip()]

def _guardar(pregunta, respuesta, cerebro):
    with open(HIST, "a") as f:
        f.write(json.dumps({"t": time.time(), "fecha": f"{datetime.datetime.now():%Y-%m-%d %H:%M}",
                            "tu": pregunta, "jarvis": respuesta, "cerebro": cerebro},
                           ensure_ascii=False) + "\n")

def _continuar():
    h = _historial(1)
    return bool(h) and time.time() - h[-1]["t"] < SESION_MIN * 60 and h[-1]["cerebro"] == "claude"

def claude(texto, voz):
    if not shutil.which("claude"):
        return None, "no instalado"
    cmd = ["claude", "-p", texto]
    if _continuar():
        cmd.append("--continue")
    if voz:
        cmd += ["--append-system-prompt", INSTRUCCION_VOZ]
    try:
        r = subprocess.run(cmd, cwd=JARVIS, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "tardó demasiado"
    salida, err = (r.stdout or "").strip(), (r.stderr or "").strip()
    if r.returncode != 0 or not salida or (LIMITE_RE.search(salida) and len(salida) < 400):
        return None, (salida or err)[:300]
    return salida, None

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

def codex(texto, voz):
    exe = buscar_codex()
    if not exe:
        return None, "Codex no instalado"
    contexto = "\n".join(f"JP: {h['tu']}\nJarvis: {h['jarvis'][:400]}" for h in _historial(4))
    prompt = (("Conversación reciente:\n" + contexto + "\n\n") if contexto else "") + \
             ("[Instrucción] " + INSTRUCCION_VOZ + "\n\n" if voz else "") + "JP dice: " + texto
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as t:
        salida_f = t.name
    try:
        r = subprocess.run([exe, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write",
                            "-o", salida_f, prompt], cwd=JARVIS, capture_output=True, text=True,
                           timeout=300, stdin=subprocess.DEVNULL)
        salida = pathlib.Path(salida_f).read_text().strip() or (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return None, "Codex tardó demasiado"
    finally:
        try: os.unlink(salida_f)
        except OSError: pass
    if r.returncode != 0 or not salida:
        return None, (r.stderr or "")[-300:]
    return salida, None

def pensar(texto, voz=False):
    estado("pensando", texto)
    resp, err = claude(texto, voz)
    cerebro = "claude"
    if resp is None:
        log(f"Claude no respondió ({err}); paso a ChatGPT")
        resp, err2 = codex(texto, voz)
        cerebro = "chatgpt"
        if resp is None:
            log(f"ChatGPT tampoco ({err2})")
            resp = ("Señor, mis dos cerebros están fuera de servicio por el momento. "
                    "Los comandos rápidos siguen funcionando.")
            cerebro = "ninguno"
    _guardar(texto, resp, cerebro)
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
    resp, cerebro = pensar(texto, voz=hablar)
    print(resp)
    if hablar:
        from decir import decir
        decir(primera_linea(resp))
