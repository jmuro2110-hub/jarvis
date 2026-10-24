# /// script
# requires-python = ">=3.11"
# ///
"""Jarvis HQ: panel local con estado, pendientes, meta y últimas conversaciones."""
import datetime, html, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import CASA, JARVIS, config, pendientes, leer_json, fecha_bonita

def generar():
    c = config()
    hoy = datetime.date.today()
    din = leer_json(JARVIS / "memoria" / "dinero.json", {"meta": 1500000, "movimientos": []})
    movs = din.get("movimientos", [])
    neto = sum(m["monto"] if m.get("tipo") != "gasto" else -m["monto"] for m in movs)
    objetivo = din.get("meta", 1500000)
    pct = max(0, min(100, neto / objetivo * 100)) if objetivo else 0
    try:
        limite = datetime.date.fromisoformat(din.get("fecha_meta", ""))
        dias_rest = (limite - hoy).days
    except ValueError:
        dias_rest = None
    por_mes = (objetivo - neto) / max(dias_rest / 30.4, 1) if dias_rest else None
    clima = leer_json(CASA / "clima.json", None)
    vig = leer_json(CASA / "vigia.json", {})
    hist = []
    if (CASA / "historial.jsonl").exists():
        for l in (CASA / "historial.jsonl").read_text().splitlines()[-6:]:
            try: hist.append(json.loads(l))
            except Exception: pass
    pend = pendientes()
    e = html.escape

    def fila_pend(p):
        if p["fecha"]:
            d = (p["fecha"] - hoy).days
            cls = "rojo" if d <= 0 else "ambar" if d <= 2 else ""
            cuando = "hoy" if d == 0 else "mañana" if d == 1 else ("vencido" if d < 0 else f"en {d} días")
        else:
            cls, cuando = "", "sin fecha"
        return f'<li class="{cls}"><span>{e(p["texto"])}</span><small>{e(" · ".join(x for x in (p["area"], cuando) if x))}</small></li>'

    filas = "".join(fila_pend(p) for p in pend[:12]) or '<li class="vacio">Sin pendientes. Sospechoso, señor.</li>'
    charla = "".join(
        f'<div class="msg"><b>Tú</b> {e(h["tu"][:160])}<br><b>Jarvis</b> {e(h["jarvis"].splitlines()[0][:220] if h["jarvis"] else "")}'
        f'<small>{e(h.get("fecha",""))} · {e(h.get("cerebro",""))}</small></div>' for h in reversed(hist)) \
        or '<div class="msg vacio">Aún no hemos hablado hoy.</div>'
    ultimos_mov = "".join(
        f'<li><span>{e(m.get("concepto",""))}</span><small class="{"rojo" if m.get("tipo")=="gasto" else "verde"}">'
        f'{"-" if m.get("tipo")=="gasto" else "+"}${m["monto"]:,.0f} · {e(m.get("fecha",""))}</small></li>'
        for m in movs[-5:][::-1]) or '<li class="vacio">Sin movimientos. Dígame "Jarvis, registra un ingreso de…"</li>'
    clima_txt = f'{clima["ahora"]}° · {e(clima["desc"])} · máx {clima["max"]}°' if clima else "—"

    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60">
<title>Jarvis HQ</title><style>
:root{{--bg:#05080d;--panel:#0b131d;--borde:#16324a;--cian:#4fd1ff;--txt:#d7e7f3;--suave:#7f98ad;--rojo:#ff6b6b;--ambar:#ffc857;--verde:#58e6a0}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 50% -20%,#0f2a40 0,var(--bg) 60%);color:var(--txt);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;min-height:100vh;padding:28px}}
header{{display:flex;align-items:center;gap:18px;margin-bottom:24px}}
.reactor{{width:54px;height:54px;border-radius:50%;border:3px solid var(--cian);box-shadow:0 0 22px var(--cian),inset 0 0 18px var(--cian);
display:grid;place-items:center}}.reactor:after{{content:"";width:16px;height:16px;border-radius:50%;background:var(--cian);box-shadow:0 0 16px var(--cian)}}
h1{{margin:0;font-size:22px;letter-spacing:.35em;font-weight:600}}header p{{margin:2px 0 0;color:var(--suave)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--borde);border-radius:14px;padding:18px}}
.card h2{{margin:0 0 12px;font-size:12px;letter-spacing:.2em;color:var(--cian);font-weight:600}}
.big{{font-size:30px;font-weight:600}}.barra{{height:10px;background:#0f2233;border-radius:6px;overflow:hidden;margin:10px 0}}
.barra i{{display:block;height:100%;width:{pct:.2f}%;background:linear-gradient(90deg,#1c8fd1,var(--cian));box-shadow:0 0 12px var(--cian)}}
ul{{list-style:none;margin:0;padding:0}}li{{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid #12263a}}
li:last-child{{border:0}}small{{color:var(--suave);white-space:nowrap}}li.rojo span{{color:var(--rojo)}}li.ambar span{{color:var(--ambar)}}
small.rojo{{color:var(--rojo)}}small.verde{{color:var(--verde)}}.vacio{{color:var(--suave);font-style:italic}}
.msg{{padding:8px 0;border-bottom:1px solid #12263a}}.msg b{{color:var(--cian);font-weight:600;margin-right:4px}}.msg small{{display:block}}
.kv{{display:flex;justify-content:space-between;padding:4px 0}}.kv span:first-child{{color:var(--suave)}}
a{{color:var(--cian)}}
</style></head><body>
<header><div class="reactor"></div><div><h1>J.A.R.V.I.S.</h1>
<p>{e(fecha_bonita(hoy).capitalize())} · actualizado {datetime.datetime.now():%H:%M}</p></div></header>
<div class="grid">
<section class="card"><h2>META · COCHE</h2><div class="big">${neto:,.0f}</div>
<div class="barra"><i></i></div><div class="kv"><span>Objetivo</span><span>${objetivo:,.0f} ({pct:.1f}%)</span></div>
{f'<div class="kv"><span>Días restantes</span><span>{dias_rest}</span></div><div class="kv"><span>Necesario por mes</span><span>${por_mes:,.0f}</span></div>' if dias_rest else ''}
<h2 style="margin-top:16px">MOVIMIENTOS</h2><ul>{ultimos_mov}</ul></section>
<section class="card"><h2>PENDIENTES · {len(pend)}</h2><ul>{filas}</ul></section>
<section class="card"><h2>HOY</h2>
<div class="kv"><span>Clima ({e(c["ciudad"])})</span><span>{clima_txt}</span></div>
<div class="kv"><span>Juego hoy</span><span>{vig.get("juego_min",0)} min</span></div>
<div class="kv"><span>Rutina</span><span><a href="{e(c["rutina_url"])}">abrir</a></span></div>
<h2 style="margin-top:16px">ÚLTIMAS CONVERSACIONES</h2>{charla}</section>
</div></body></html>"""
    destino = JARVIS / "hq" / "index.html"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(pagina)
    return destino

if __name__ == "__main__":
    d = generar()
    if "--abrir" in sys.argv:
        subprocess.run(["open", str(d)])
    print(d)
