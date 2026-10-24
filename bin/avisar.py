# /// script
# requires-python = ">=3.11"
# ///
"""Avisos: notificación en la Mac, push al iPhone (ntfy) y voz opcional."""
import json, os, subprocess, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import secretos, en_silencio, log

def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')

def avisar(titulo, mensaje, hablar=False, iphone=True, prioridad="default"):
    subprocess.run(["osascript", "-e",
                    f'display notification "{_esc(mensaje[:240])}" with title "{_esc(titulo)}"'])
    tema = secretos().get("NTFY_TOPIC")
    if iphone and tema:
        try:
            prio = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}.get(prioridad, 3)
            cuerpo = json.dumps({"topic": tema, "title": titulo, "message": mensaje,
                                 "priority": prio, "tags": ["robot"]}).encode()
            req = urllib.request.Request("https://ntfy.sh/", data=cuerpo,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            log(f"ntfy falló: {e}")
    if hablar and not en_silencio():
        from decir import decir
        decir(mensaje)

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    avisar(a[0] if a else "Jarvis", " ".join(a[1:]) or "Prueba de aviso, señor.", hablar="--hablar" in sys.argv)
