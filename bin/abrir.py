# /// script
# requires-python = ">=3.11"
# ///
"""Abre una página en el perfil de Chrome correcto.  jv abrir URL [--escuela|--personal]  ·  jv abrir --perfiles"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import abrir_url, mundo_de, perfiles_chrome

if "--perfiles" in sys.argv:
    print(perfiles_chrome()); sys.exit()
url = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
if not url:
    print(__doc__); sys.exit(1)
mundo = "escuela" if "--escuela" in sys.argv else "personal" if "--personal" in sys.argv else mundo_de(url)
abrir_url(url, mundo)
print(f"Abierto en perfil {mundo}: {url}")
