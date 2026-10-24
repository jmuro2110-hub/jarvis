# /// script
# requires-python = ">=3.11"
# ///
"""Resumen matutino: clima, pendientes, rutina y meta. Voz + iPhone."""
import datetime, json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA, JARVIS, config, pendientes, fecha_bonita, leer_json, escribir_json, log

def clima(ciudad):
    try:
        url = f"https://wttr.in/{urllib.parse.quote(ciudad)}?format=j1&lang=es"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl"}), timeout=15) as r:
            d = json.load(r)
        hoy = d["weather"][0]
        actual = d["current_condition"][0]
        desc = (actual.get("lang_es") or actual.get("weatherDesc"))[0]["value"]
        lluvia = max(int(h.get("chanceofrain", 0)) for h in hoy["hourly"])
        c = {"ahora": int(actual["temp_C"]), "min": int(hoy["mintempC"]), "max": int(hoy["maxtempC"]),
             "desc": desc.lower(), "lluvia": lluvia}
        escribir_json(CASA / "clima.json", {**c, "t": datetime.datetime.now().isoformat()})
        return c
    except Exception as e:
        log(f"clima falló: {e}")
        return None

def meta():
    d = leer_json(JARVIS / "memoria" / "dinero.json", {"meta": 1500000, "movimientos": []})
    neto = sum(m["monto"] if m.get("tipo") != "gasto" else -m["monto"] for m in d.get("movimientos", []))
    return neto, d.get("meta", 1500000)

def datos_del_dia():
    c = config()
    hoy = datetime.date.today()
    cl = clima(c["ciudad"])
    pend = pendientes()
    urgentes = [p for p in pend if p["fecha"] and (p["fecha"] - hoy).days <= 2]
    neto, objetivo = meta()
    return {
        "fecha": fecha_bonita(hoy), "clima": cl,
        "pendientes_urgentes": [f"{p['texto']} ({p['area']}) para el {fecha_bonita(p['fecha'])}" for p in urgentes],
        "pendientes_total": len(pend),
        "meta_coche": f"{neto:,.0f} de {objetivo:,.0f} pesos ({neto / objetivo * 100:.1f}%)",
    }

def plantilla(d):
    t = f"Buenos días, señor. Hoy es {d['fecha']}."
    if d["clima"]:
        k = d["clima"]
        t += f" Hacen {k['ahora']} grados, {k['desc']}, máxima de {k['max']}."
        if k["lluvia"] >= 50:
            t += f" {k['lluvia']} por ciento de probabilidad de lluvia."
    if d["pendientes_urgentes"]:
        t += " Pendientes cercanos: " + "; ".join(d["pendientes_urgentes"][:3]) + "."
    elif d["pendientes_total"]:
        t += f" Tiene {d['pendientes_total']} pendientes, ninguno urgente."
    t += " Su rutina del día está en la app. Meta del coche: " + d["meta_coche"] + "."
    return t

def resumen(hablar=True):
    d = datos_del_dia()
    texto = None
    try:
        from pensar import pensar
        prompt = ("Genera mi resumen matutino como Jarvis, para decirse en voz alta: máximo 5 frases, "
                  "sin markdown ni listas, con tu humor seco. Termina con una frase de impulso hacia la meta "
                  "del coche. Datos de hoy (JSON): " + json.dumps(d, ensure_ascii=False, default=str))
        resp, cerebro = pensar(prompt)
        if cerebro != "ninguno":
            texto = resp.strip()
    except Exception as e:
        log(f"resumen IA falló: {e}")
    texto = texto or plantilla(d)
    from avisar import avisar
    avisar("Buenos días, señor", texto, hablar=False)
    if hablar:
        from decir import decir
        decir(texto)
    return texto

if __name__ == "__main__":
    if "--datos" in sys.argv:
        print(json.dumps(datos_del_dia(), ensure_ascii=False, indent=2, default=str))
    elif "--plantilla" in sys.argv:
        print(plantilla(datos_del_dia()))
    else:
        print(resumen(hablar="--sin-voz" not in sys.argv))
