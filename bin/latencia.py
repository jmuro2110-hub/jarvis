# /// script
# requires-python = ">=3.11"
# ///
"""Diagnóstico de latencia:  jv latencia [--dias N]
Lee ~/.jarvis/metricas_latencia.jsonl y muestra muestras, p50, p90, mínimo y máximo por etapa.
Percentiles por rango más cercano: siempre son valores medidos, nunca interpolados."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telemetria as tm

MIN_P50, MIN_P90 = 5, 10       # menos muestras que esto: no se da ese percentil

def percentil(orden, p):
    return orden[max(0, math.ceil(p / 100 * len(orden)) - 1)]

def _f(ms):
    return f"{ms / 1000:.2f} s" if ms >= 1000 else f"{ms:.0f} ms"

def fila(nombre, valores):
    v = sorted(valores)
    n = len(v)
    p50 = _f(percentil(v, 50)) if n >= MIN_P50 else "—"
    p90 = _f(percentil(v, 90)) if n >= MIN_P90 else "—"
    return f"  {nombre:<32}{n:>4}  {p50:>9}  {p90:>9}  {_f(v[0]):>9}  {_f(v[-1]):>9}"

def tabla(titulo, grupos):
    print(f"\n{titulo}")
    if not grupos:
        print("  (sin muestras)"); return
    print(f"  {'':<32}{'n':>4}  {'p50':>9}  {'p90':>9}  {'mín':>9}  {'máx':>9}")
    for nombre, valores in grupos:
        print(fila(nombre, valores))

def agrupar(filas, clave):
    g = {}
    for f in filas:
        g.setdefault(clave(f), []).append(float(f["ms"]))
    return g

def conversaciones(dias):
    """Resumen corto de la conversación continua (upgrade 04)."""
    ev = tm.leer_conversaciones(dias)
    print("\nConversación continua:")
    cierres = [f for f in ev if f["evento"] == "cierre"]
    if not ev:
        print("  (sin conversaciones)"); return
    n = len({f["conv"] for f in ev if f["evento"] == "activada"})
    turnos = [f["turno"] for f in cierres]
    print(f"  conversaciones: {n}   turnos promedio: {sum(turnos) / len(turnos):.1f}" if turnos
          else f"  conversaciones: {n}")
    motivos = {}
    for f in cierres:
        motivos[f.get("motivo", "?")] = motivos.get(f.get("motivo", "?"), 0) + 1
    if motivos:
        print("  cierres: " + ", ".join(f"{m} {c}" for m, c in sorted(motivos.items(), key=lambda x: -x[1])))
    det = sum(f["evento"] == "seguimiento_detectado" for f in ev)
    desc = sum(f["evento"] == "seguimiento_descartado" for f in ev)
    if det + desc:
        print(f"  seguimientos: {det} atendidos, {desc} descartados ({desc / (det + desc) * 100:.0f}%)")
    gestor = sorted(f["ms"] for f in ev if f["evento"] == "seguimiento_abre" and "ms" in f)
    if gestor:
        print(f"  latencia del gestor (fin de voz → escuchando): mín {_f(gestor[0])}, máx {_f(gestor[-1])}")
    esperas = sorted(f["ms"] for f in ev if f["evento"] == "seguimiento_detectado" and "ms" in f)
    if esperas:
        print(f"  fin de respuesta → nueva intervención: mín {_f(esperas[0])}, máx {_f(esperas[-1])}")


def main():
    dias = None
    if "--dias" in sys.argv:
        try: dias = float(sys.argv[sys.argv.index("--dias") + 1])
        except (IndexError, ValueError):
            print("Uso: jv latencia [--dias N]"); sys.exit(1)
    filas = [f for f in tm.leer(dias)             # claude_api reanudada = acumulado de sesión, no sirve
             if not (f["etapa"] == "claude_api" and f.get("sesion") == "reanudada")]
    periodo = f"últimos {dias:g} días" if dias else "todo el historial"
    if not filas:
        print(f"Sin mediciones todavía ({periodo}) en {tm.ARCHIVO}.\n"
              "Hable con Jarvis unas cuantas veces y vuelva a correr `jv latencia`, señor.")
        return
    peticiones = len({f["id"] for f in filas})
    print(f"Latencia de Jarvis — {periodo}: {len(filas)} mediciones de {peticiones} peticiones.")

    por_etapa = agrupar(filas, lambda f: f["etapa"])
    tabla("Por etapa (todas las rutas):", [(e, por_etapa[e]) for e in tm.ETAPAS if e in por_etapa])

    totales = [f for f in filas if f["etapa"] == "total"]
    por_origen = agrupar(totales, lambda f: f["origen"])
    tabla("Total (fin de la frase → empieza a responder), por origen:",
          [(o, por_origen[o]) for o in tm.ORIGENES if o in por_origen])
    por_ruta = agrupar(totales, lambda f: f"{f['origen']} · {f.get('ruta') or '?'}")
    tabla("Total por ruta:", sorted(por_ruta.items()))

    cerebro = [f for f in filas if f["etapa"] in ("claude_p", "codex_exec")]
    por_estado = agrupar(cerebro, lambda f: f"{f['etapa']} · {f['estado']}")
    tabla("Cerebro por resultado:", sorted(por_estado.items()))

    desglose = [f for f in filas if f["etapa"].startswith("claude_")]
    por_sesion = agrupar(desglose, lambda f: f"{f['etapa']} · {f.get('sesion') or '?'}")
    tabla("Claude por sesión (nueva / reanudada):", sorted(por_sesion.items()))

    conversaciones(dias)

    poco = sorted(n for n, v in {**por_etapa, **por_ruta}.items() if len(v) < MIN_P90)
    if poco:
        print(f"\nOjo: pocas muestras en {', '.join(poco)}. "
              f"p50 necesita {MIN_P50}+ y p90 {MIN_P90}+; con menos solo se muestran mín y máx.")
    print("\nNotas: 'claude_p' y 'codex_exec' son el subproceso completo (arranque + red + modelo + salida)."
          "\n'claude_duracion' y 'claude_api' los reporta Claude en su JSON; 'claude_arranque_est' ="
          "\nclaude_p − claude_duracion es una ESTIMACIÓN del arranque local, no una medida exacta."
          "\n'claude_api' solo en sesiones nuevas (al reanudar, Claude lo da acumulado)."
          "\nTiempo a primer texto: todavía no medible (requiere stream-json, upgrade 04)."
          "\n'total' termina cuando se lanza la voz (say/afplay), no cuando suena el primer sonido.")

if __name__ == "__main__":
    main()
