# /// script
# requires-python = ">=3.11"
# ///
"""Guarda una llave privada en ~/.jarvis/secretos.env sin que quede en el historial.
   jv llave groq   ·   jv llave elevenlabs"""
import getpass, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA

NOMBRES = {"groq": "GROQ_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
cual = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
if cual not in NOMBRES:
    print(__doc__); sys.exit(1)
valor = getpass.getpass(f"Pega tu llave de {cual} (no se va a ver) y dale Enter: ").strip()
if len(valor) < 10:
    print("Esa llave se ve incompleta. Intenta otra vez."); sys.exit(1)
f = CASA / "secretos.env"
lineas = [l for l in (f.read_text().splitlines() if f.exists() else []) if not l.startswith(NOMBRES[cual] + "=")]
lineas.append(f"{NOMBRES[cual]}={valor}")
f.write_text("\n".join(lineas) + "\n")
os.chmod(f, 0o600)

if cual == "groq":
    import json, urllib.request
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                     headers={"Authorization": f"Bearer {valor}", "User-Agent": "jarvis-jp"})
        urllib.request.urlopen(req, timeout=10).read()
        print("✅ Llave de Groq guardada y funcionando. Reinicia Jarvis para que la use.")
    except Exception as e:
        print(f"⚠️  La guardé, pero Groq la rechazó ({e}). Revisa que la copiaste completa.")
else:
    print(f"✅ Llave de {cual} guardada. Reinicia Jarvis para que la use.")
