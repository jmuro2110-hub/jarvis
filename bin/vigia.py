# /// script
# requires-python = ">=3.11"
# ///
"""Vigía (cada 5 min): tiempo de juego, entregas cercanas. Avisa con estilo."""
import datetime, os, random, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA, config, pendientes, leer_json, escribir_json, fecha_bonita, log

ARCH = CASA / "vigia.json"
FRASES_JUEGO = {
    60: ["Señor, lleva una hora en Minecraft. Solo lo menciono para el registro.",
         "Una hora de bloques, señor. Los creepers agradecen su dedicación."],
    120: ["Dos horas jugando, señor. Me permito sugerir un descanso para los ojos.",
          "Señor, dos horas. Hasta Tony Stark tomaba descansos. A veces."],
    180: ["Tres horas, señor. Empiezo a sospechar que el coche de millón y medio no se construye en Minecraft.",
          "Señor, tres horas. Con todo respeto, el mundo real también tiene gráficos decentes."],
}

def jugando():
    r = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout.lower()
    return any(("minecraft" in l and "vigia" not in l) for l in r.splitlines())

def vigilar():
    c = config()
    s = leer_json(ARCH, {})
    hoy = datetime.date.today().isoformat()
    if s.get("dia") != hoy:
        s = {"dia": hoy, "juego_min": 0, "ultima_vez_jugando": 0, "avisados": []}
    ahora = time.time()
    mensajes = []

    # --- tiempo de juego ---
    if jugando():
        s["juego_min"] += 5
        s["ultima_vez_jugando"] = ahora
        urgentes = [p for p in pendientes() if p["fecha"] and (p["fecha"] - datetime.date.today()).days <= 1]
        for umbral in c["minutos_juego_aviso"]:
            clave = f"juego{umbral}"
            if s["juego_min"] >= umbral and clave not in s["avisados"]:
                frase = random.choice(FRASES_JUEGO.get(umbral, [f"Señor, lleva {umbral} minutos jugando."]))
                if urgentes:
                    frase += f" Por cierto, {urgentes[0]['texto']} vence {('hoy' if urgentes[0]['fecha'].isoformat() == hoy else 'mañana')}."
                mensajes.append(("Tiempo de juego", frase))
                s["avisados"].append(clave)
    elif ahora - s.get("ultima_vez_jugando", 0) > 45 * 60 and s["juego_min"]:
        # descanso largo: reinicia el conteo de la sesión
        s["juego_min"] = 0
        s["avisados"] = [a for a in s["avisados"] if not a.startswith("juego")]

    # --- entregas ---
    hora = datetime.datetime.now().hour
    for p in pendientes():
        if not p["fecha"]:
            continue
        dias = (p["fecha"] - datetime.date.today()).days
        clave = f"pend:{p['texto']}:{dias}"
        if clave in s["avisados"]:
            continue
        if dias == 1 and hora >= 17:
            mensajes.append(("Entrega mañana", f"Señor, recordatorio: {p['texto']} se entrega mañana."))
            s["avisados"].append(clave)
        elif dias == 0 and 8 <= hora <= 20:
            mensajes.append(("Entrega HOY", f"Señor, {p['texto']} se entrega hoy. Le sugiero no dejarlo para el final."))
            s["avisados"].append(clave)
        elif dias < 0 and hora >= 9:
            mensajes.append(("Pendiente vencido", f"Señor, {p['texto']} venció el {fecha_bonita(p['fecha'])}. ¿Lo marcamos o lo movemos?"))
            s["avisados"].append(clave)

    escribir_json(ARCH, s)
    if mensajes:
        from avisar import avisar
        for titulo, m in mensajes:
            log(f"vigía: {m}")
            avisar(titulo, m, hablar=True, prioridad="high")
    return mensajes

if __name__ == "__main__":
    for t, m in vigilar():
        print(f"[{t}] {m}")
