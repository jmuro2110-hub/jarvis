"""Las pruebas nunca leen ni escriben los recuerdos reales de JP (upgrade 07)."""
import os, tempfile

os.environ.setdefault("JARVIS_RECUERDOS", os.path.join(tempfile.mkdtemp(prefix="jarvis_pruebas_"), "recuerdos.jsonl"))
