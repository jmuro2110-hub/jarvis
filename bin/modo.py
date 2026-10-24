# /// script
# requires-python = ">=3.11"
# ///
"""Modos de Jarvis (gamer, estudio, dormir...). Se configuran en config.json → "modos"."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import config, abrir_url, mundo_de

BASE = {
    "gamer": {
        "abrir": ["Minecraft"], "cerrar": [], "spotify": "play", "volumen": 60, "urls": [],
        "frase": "Modo gamer activado, señor. Intente no olvidar que existe el mundo exterior."},
    "estudio": {
        "abrir": [], "cerrar": ["Minecraft"], "spotify": "pause", "volumen": 35,
        "urls": ["https://classroom.google.com"],
        "frase": "Modo estudio, señor. He guardado los bloques para después."},
    "dormir": {
        "abrir": [], "cerrar": ["Minecraft"], "spotify": "pause", "volumen": 15, "urls": [],
        "frase": "Buenas noches, señor. Yo me quedo vigilando."},
    "trabajo": {
        "abrir": [], "cerrar": ["Minecraft"], "spotify": "play", "volumen": 35, "urls": [],
        "frase": "Modo trabajo, señor. Ese coche no se va a comprar solo."},
}

def osa(s):
    subprocess.run(["osascript", "-e", s], capture_output=True)

def modo(nombre):
    m = {**BASE, **config().get("modos", {})}.get(nombre)
    if not m:
        return None
    for app in m.get("cerrar", []):
        osa(f'tell application "{app}" to quit')
    for app in m.get("abrir", []):
        subprocess.run(["open", "-a", app], capture_output=True)
    for url in m.get("urls", []):
        abrir_url(url, mundo_de(url))
    if m.get("spotify") in ("play", "pause"):
        osa(f'if application "Spotify" is running then tell application "Spotify" to {m["spotify"]}')
    if "volumen" in m:
        osa(f"set volume output volume {int(m['volumen'])}")
    return m.get("frase", f"Modo {nombre} activado, señor.")

def disponibles():
    return sorted({**BASE, **config().get("modos", {})})

if __name__ == "__main__":
    n = sys.argv[1] if len(sys.argv) > 1 else ""
    frase = modo(n)
    if frase is None:
        print("Modos: " + ", ".join(disponibles())); sys.exit(1)
    print(frase)
    if "--hablar" in sys.argv:
        from decir import decir
        decir(frase)
