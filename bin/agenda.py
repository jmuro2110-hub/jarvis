# /// script
# requires-python = ">=3.11"
# ///
"""Reloj interno de Jarvis: resumen matutino a su hora, vigía cada 5 min, panel actualizado."""
import datetime, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA, config, log, vigilar_supervisor

def main():
    vigilar_supervisor()                 # upgrade 08: si el supervisor muere, la agenda también
    log("agenda iniciada")
    ultimo_vigia = 0
    while True:
        try:
            c = config()
            ahora = datetime.datetime.now()
            hoy = ahora.date().isoformat()
            marca = CASA / "resumen_hecho.txt"
            hecho = marca.read_text().strip() if marca.exists() else ""
            h, m = map(int, c["hora_resumen"].split(":"))
            if hecho != hoy and (ahora.hour, ahora.minute) >= (h, m) and ahora.hour < 12:
                marca.write_text(hoy)
                from resumen import resumen
                resumen()
            if time.time() - ultimo_vigia >= 300:
                ultimo_vigia = time.time()
                from vigia import vigilar
                vigilar()
                from hq import generar
                generar()
        except Exception:
            log("agenda error: " + traceback.format_exc()[-500:])
        time.sleep(30)

if __name__ == "__main__":
    main()
