"""Upgrade 08, etapa 1: prueba REAL de permisos desde el Python que usa la voz, lanzado por Jarvis.app.
Mide micrófono (nivel de audio, no solo abrir el stream), Documentos (lectura de un archivo preparado fuera de
la app, lectura del proyecto y escritura controlada), modelos sin red y Automatización con consultas de solo
lectura (solo si la app ya está abierta). No toca la cola, el estado ni los candados del Jarvis que esté corriendo.
Resultado: ~/.jarvis/prueba_permisos.txt (0600) y en voz alta. Nada de audio ni de contenido se guarda."""
import os, pathlib, subprocess, sys, time

HOME = pathlib.Path.home()
CASA = HOME / ".jarvis"
LECTURA = HOME / "Documents" / "prueba_jarvis_app.txt"            # lo prepara Claude desde Terminal, no la app
TOKEN = CASA / "prueba_permisos_token"
ESCRITURA = HOME / "Documents" / "prueba_jarvis_app_escritura.txt"
PROYECTO = HOME / "Documents" / "Jarvis" / "CLAUDE.md"
SALIDA = CASA / "prueba_permisos.txt"
CORRIDAS = CASA / "prueba_permisos.n"
MIC_SEG = 5
PICO_VOZ = 1000              # int16: hablar normal da 5,000–20,000; silencio de cuarto ~100–600; denegado = 0


def decir(texto):
    subprocess.run(["say", "-v", "Paulina", texto], capture_output=True)


def osa(script, timeout=120):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout.strip() or r.stderr.strip())


def cadena_de_padres():
    """De este Python hacia arriba: debe pasar por Jarvis.app (quien responde ante macOS por los permisos)."""
    pid, cadena = os.getpid(), []
    for _ in range(8):
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True)
        if not r.stdout.strip():
            break
        ppid, comm = r.stdout.strip().split(None, 1)
        cadena.append(os.path.basename(comm) if "Jarvis.app" not in comm else "Jarvis.app/" + os.path.basename(comm))
        pid = int(ppid)
        if pid <= 1:
            break
    return cadena


def microfono():
    import numpy as np
    import sounddevice as sd
    nombre = sd.query_devices(kind="input")["name"]
    decir("Señor, prueba de micrófono. Diga algo durante cinco segundos.")
    audio = sd.rec(int(MIC_SEG * 16000), samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    a = audio[:, 0].astype(np.float32)
    pico, rms = int(np.max(np.abs(a))), int(np.sqrt(np.mean(a ** 2)))
    if pico == 0:
        return "FALLA", f"{nombre}: silencio total (ceros): macOS no le da audio a este proceso"
    if pico < PICO_VOZ:
        return "DUDOSO", f"{nombre}: pico {pico}, rms {rms}: hay audio pero no se oyó voz"
    return "OK", f"{nombre}: pico {pico}, rms {rms}"


def modelos():
    t0 = time.perf_counter()
    from faster_whisper import WhisperModel
    WhisperModel("base", device="cpu", compute_type="int8")
    return "OK", f"Whisper base cargado sin red en {time.perf_counter() - t0:.1f} s (HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')})"


def documentos_lectura():
    esperado = TOKEN.read_text().strip()
    leido = LECTURA.read_text().strip()
    return ("OK", f"{LECTURA.name} coincide") if leido == esperado else ("FALLA", f"{LECTURA.name} no coincide")


def proyecto_lectura():
    ok = PROYECTO.read_text().startswith("# J.A.R.V.I.S.")
    return ("OK", "CLAUDE.md legible") if ok else ("FALLA", "CLAUDE.md con contenido inesperado")


def documentos_escritura():
    marca = f"prueba de escritura de Jarvis.app {time.strftime('%F %T')}"
    ESCRITURA.write_text(marca + "\n")
    return ("OK", f"{ESCRITURA.name} escrito y leído") if ESCRITURA.read_text().strip() == marca \
        else ("FALLA", "lo escrito no coincide")


def automatizacion(app, consulta):
    """Solo lectura y solo si ya está abierta: no se abre ninguna app para la prueba."""
    c, corre = osa(f'application "{app}" is running', timeout=10)
    if c != 0 or corre != "true":
        return "PENDIENTE", f"{app} cerrada: no se abrió para la prueba"
    c, r = osa(f'tell application "{app}" to {consulta}')
    if c == 0:
        return "OK", f"{app} respondió ({consulta})"
    if "-1743" in r:
        return "FALLA", f"{app}: Automatización denegada (-1743)"
    return "FALLA", f"{app}: error {r[:80]}"


def hammerspoon():
    corre = subprocess.run(["pgrep", "-x", "Hammerspoon"], capture_output=True).returncode == 0
    if not corre:
        return "PENDIENTE", "Hammerspoon no está abierto"
    return "OK", "Hammerspoon abierto (sus atajos con la voz se prueban en la etapa 2, física D)"


def main():
    CASA.mkdir(exist_ok=True)
    n = int(CORRIDAS.read_text()) + 1 if CORRIDAS.exists() else 1
    CORRIDAS.write_text(str(n))
    filas = [("Lanzador", "OK" if os.environ.get("JARVIS_LANZADOR") == "app" else "FALLA",
              "padres: " + " ← ".join(cadena_de_padres())),
             ("Micrófono según la app", "OK" if os.environ.get("JARVIS_MIC_APP") == "autorizado" else "FALLA",
              os.environ.get("JARVIS_MIC_APP", "?")),
             ("uv sin red", "OK" if os.environ.get("UV_OFFLINE") == "1" else "FALLA", sys.executable)]
    for nombre, prueba in (("Micrófono (audio real en Python)", microfono), ("Modelos sin red", modelos),
                           ("Documentos: archivo preparado", documentos_lectura),
                           ("Documentos: proyecto", proyecto_lectura),
                           ("Documentos: escritura controlada", documentos_escritura),
                           ("Automatización: Spotify", lambda: automatizacion("Spotify", "player state")),
                           ("Automatización: Minecraft", lambda: automatizacion("Minecraft", "name")),
                           ("Hammerspoon", hammerspoon)):
        try:
            filas.append((nombre, *prueba()))
        except Exception as e:
            filas.append((nombre, "FALLA", f"{type(e).__name__}: {str(e)[:120]}"))
    texto = f"Prueba de permisos de Jarvis.app — corrida {n} — {time.strftime('%F %T')}\n" + \
        "\n".join(f"{r:<9} {p:<34} {d}" for p, r, d in filas) + "\n"
    SALIDA.write_text(texto)
    os.chmod(SALIDA, 0o600)
    print(texto, flush=True)
    malas = [p for p, r, _ in filas if r == "FALLA"]
    decir(f"Prueba de permisos {n} terminada, señor. " +
          ("Todo en orden." if not malas else f"Fallaron {len(malas)}: " + ", ".join(malas) + "."))
    return 0 if not malas else 2
