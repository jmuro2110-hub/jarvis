# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "onnxruntime<=1.23.2",
#   "faster-whisper>=1.1",
#   "sounddevice>=0.5",
#   "numpy",
# ]
# ///
"""Prueba de oído: escucha 40 segundos y te dice qué entendió y si detectó "Jarvis"."""
import os, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sounddevice as sd
from oido import Oido, transcribir, separar

print("\n=== Micrófonos ===")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(f"  [{i}] {d['name']}{'  ← EL QUE USO' if i == sd.default.device[0] else ''}")

from faster_whisper import WhisperModel
print("\nCargando el oído (la primera vez descarga ~150 MB)...")
modelo = WhisperModel("base", device="cpu", compute_type="int8")

print("\n=== Prueba de 40 segundos ===")
print('Di frases como:  "Jarvis, abre Spotify"   "Jarvis, qué hora es"   y alguna sin Jarvis.\n')
aciertos, frases, fin = 0, 0, time.time() + 40
with Oido() as oido:
    while time.time() < fin:
        audio = oido.frase(espera_inicio=max(1, fin - time.time()))
        if audio is None or isinstance(audio, str):
            break
        t0 = time.time()
        texto = transcribir(modelo, audio)
        si, orden = separar(texto)
        frases += 1; aciertos += si
        print(f"  🗣  \"{texto}\"   ({time.time() - t0:.1f}s)")
        print(f"     {'✅ JARVIS → orden: ' + (orden or '(esperaría tu orden)') if si else '·  sin Jarvis, lo ignoro'}\n")

print("=== Resultado ===")
if frases == 0:
    print("  ❌ No detecté que hablaras. Revisa el permiso del micrófono para Terminal.")
elif aciertos == 0:
    print("  ⚠️  Te oí pero nunca entendí 'Jarvis'. Mándale captura a Claude.")
else:
    print(f"  ✅ Detecté 'Jarvis' en {aciertos} de {frases} frases. Listo para usarse.")
