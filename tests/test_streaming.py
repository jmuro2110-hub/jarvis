"""Pruebas del upgrade 05 (stream-json, voz anticipada, captura tras «Jarvis»).
El "Claude" de estas pruebas es un proceso real que emite stream-json sintético por un pipe (así se prueban
selectors, pipes y limpieza de verdad); la "voz" es un proceso real que duerme. Sin cuota de Claude.

    uv run --python 3.11 --with numpy python -m unittest tests.test_streaming -v
"""
import functools, json, os, pathlib, subprocess, sys, tempfile, time, types, unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

import telemetria as tm           # noqa: E402
import streaming as st            # noqa: E402
import pensar as pensar_mod       # noqa: E402
import sesiones                   # noqa: E402
import conversacion as cv         # noqa: E402
import jarvis_voz as voz          # noqa: E402
import politica, guardia, comun   # noqa: E402

SID = "88888888-8888-4888-8888-888888888888"

# ---------------------------------------------------------------- eventos sintéticos (formato real 2.1.311)
def init(tools=(), mcp=()):
    return {"type": "system", "subtype": "init", "session_id": SID, "tools": list(tools), "mcp_servers": list(mcp)}

def status():
    return {"type": "system", "subtype": "status", "status": "requesting", "session_id": SID}

def se(event, parent=None):
    return {"type": "stream_event", "event": event, "session_id": SID, "parent_tool_use_id": parent}

def msg_start(parent=None):
    return se({"type": "message_start", "message": {"role": "assistant", "content": []}}, parent)

def bloque(i, tipo="text", parent=None):
    cb = {"type": tipo, "text": ""} if tipo == "text" else {"type": tipo, "id": "t1", "name": "Bash", "input": {}}
    return se({"type": "content_block_start", "index": i, "content_block": cb}, parent)

def delta(i, texto, tipo="text_delta", parent=None):
    d = {"type": tipo, "text": texto} if tipo == "text_delta" else (
        {"type": tipo, "thinking": texto} if tipo == "thinking_delta" else {"type": tipo, "partial_json": texto})
    return se({"type": "content_block_delta", "index": i, "delta": d}, parent)

def stop(i, parent=None):
    return se({"type": "content_block_stop", "index": i}, parent)

def asistente(texto, tool=False):
    c = [{"type": "text", "text": texto}] + ([{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}] if tool else [])
    return {"type": "assistant", "message": {"role": "assistant", "content": c}, "session_id": SID}

def result(texto, sid=SID, is_error=False):
    return {"type": "result", "subtype": "success", "is_error": is_error, "result": texto, "session_id": sid,
            "duration_ms": 900, "duration_api_ms": 700}

def respuesta_simple(trozos, final=None, tools=(), espera_tras=0.0, sid=SID):
    texto = final if final is not None else "".join(trozos)
    ev = [init(tools), status(), msg_start(), bloque(0)]
    ev += [delta(0, t) for t in trozos]
    ev += [("dormir", espera_tras), asistente(texto), stop(0), result(texto, sid)]
    return ev


# ---------------------------------------------------------------- "claude" y "voz" falsos (procesos reales)
GUION = r'''
import json, os, sys, time
ev = json.loads(os.environ["GUION_EVENTOS"])
sys.stderr.write(os.environ.get("GUION_STDERR", ""))
sys.stderr.flush()
for e in ev:
    if isinstance(e, list) and e[0] == "dormir":
        time.sleep(e[1]); continue
    if isinstance(e, str):
        sys.stdout.write(e + "\n")
    else:
        sys.stdout.write(json.dumps(e) + "\n")
    sys.stdout.flush()
    time.sleep(float(os.environ.get("GUION_PAUSA", "0.01")))
sys.exit(int(os.environ.get("GUION_RC", "0")))
'''


class FalsoClaude:
    """popen sustituto: corre el guion con los eventos; recuerda los comandos que le pidieron."""
    def __init__(self, *guiones, stderr="", rc=0, pausa=0.01):
        self.guiones, self.stderr, self.rc, self.pausa = list(guiones), stderr, rc, pausa
        self.cmds, self.procs = [], []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        ev = self.guiones.pop(0) if len(self.guiones) > 1 else self.guiones[0]
        sid = next((cmd[i + 1] for i, c in enumerate(cmd[:-1]) if c in ("--session-id", "--resume")), SID)
        env = dict(kw.get("env") or os.environ, GUION_EVENTOS=json.dumps(ev).replace(SID, sid),   # como el real GUION_STDERR=self.stderr,
                   GUION_RC=str(self.rc), GUION_PAUSA=str(self.pausa))
        kw = {**kw, "env": env, "cwd": None}
        p = subprocess.Popen([sys.executable, "-c", GUION], **kw)
        self.procs.append(p)
        return p


class FalsaVoz:
    """lanzar sustituto: cada pedazo es un proceso que "habla" `seg` segundos; rc configurable."""
    def __init__(self, seg=0.3, rc=0):
        self.seg, self.rc = seg, rc
        self.dichos, self.procs, self.vivos_max = [], [], 0

    def __call__(self, texto):
        vivos = sum(p.poll() is None for p in self.procs)
        self.vivos_max = max(self.vivos_max, vivos + 1)
        self.dichos.append(texto)
        p = subprocess.Popen([sys.executable, "-c", f"import time,sys; time.sleep({self.seg}); sys.exit({self.rc})"])
        self.procs.append(p)
        return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.casa = pathlib.Path(self.tmp.name)
        self.cerrar = self.casa / "cerrar_conversacion"
        self.parches = [mock.patch.object(tm, "ARCHIVO", self.casa / "metricas.jsonl"),
                        mock.patch.object(tm, "CONV_ARCHIVO", self.casa / "conversaciones.jsonl"),
                        mock.patch.object(sesiones, "DIR", self.casa),
                        mock.patch.object(pensar_mod, "estado"), mock.patch.object(pensar_mod, "log"),
                        mock.patch.object(pensar_mod, "HIST", self.casa / "historial.jsonl"),
                        mock.patch.object(pensar_mod, "shutil", mock.MagicMock(which=lambda x: "/x/claude")),
                        mock.patch.object(politica, "AUDITORIA", self.casa / "seguridad.jsonl")]
        for p in self.parches:
            p.start()
        tm.terminar()
        tm.nueva("voz", tm.ahora())

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def hablador(self, voz_f=None):
        return st.Hablador(lanzar=voz_f or FalsaVoz(), cerrar_pedido=self.cerrar.exists)

    def pensar(self, falso, texto="qué es una órbita", hablador=None, sin_herr=True, config=None, codex=None):
        cfg = {"claude_streaming": True, "voz_anticipada": True, **(config or {})}
        with mock.patch.object(pensar_mod.streaming, "correr", functools.partial(st.correr, popen=falso)), \
             mock.patch.object(pensar_mod, "config", return_value=cfg), \
             mock.patch.object(pensar_mod, "codex", codex or mock.MagicMock(return_value=(None, "sin codex"))):
            return pensar_mod.pensar(texto, voz=True, hablador=hablador, sin_herramientas=sin_herr)

    def filas(self):
        f = self.casa / "metricas.jsonl"
        return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


# ---------------------------------------------------------------- parser y frases
class T01_Parser(unittest.TestCase):
    def test_eventos_validos(self):
        textos = []
        p = st.Parser(al_texto=textos.append)
        for e in respuesta_simple(["Una órbita ", "es un camino."]):
            if isinstance(e, dict):
                p.linea(json.dumps(e))
        self.assertEqual("".join(textos), "Una órbita es un camino.")
        self.assertEqual((p.init_tools, p.init_mcp), ([], []))
        self.assertEqual(p.result["result"], "Una órbita es un camino.")
        self.assertFalse(p.tool_use)


class T02_Sistema(unittest.TestCase):
    def test_ignora_sistema(self):
        textos = []
        p = st.Parser(al_texto=textos.append)
        for e in (status(), {"type": "rate_limit_event", "rate_limit_info": {}}, {"type": "system", "subtype": "x"}):
            p.linea(json.dumps(e))
        self.assertEqual(textos, [])


class T03_ThinkingYHerramientas(unittest.TestCase):
    def test_ignora(self):
        textos = []
        p = st.Parser(al_texto=textos.append)
        for e in (init(), msg_start(), se({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}}),
                  delta(0, "pienso en borrar", "thinking_delta"), stop(0), bloque(1, "tool_use"),
                  delta(1, '{"command": "rm -rf"}', "input_json_delta"), stop(1), bloque(2), delta(2, "Hecho.")):
            p.linea(json.dumps(e))
        self.assertTrue(p.tool_use)
        self.assertNotIn("borrar", "".join(textos))
        self.assertNotIn("rm", "".join(textos))


class T04_Subagentes(unittest.TestCase):
    def test_ignora(self):
        textos = []
        p = st.Parser(al_texto=textos.append)
        for e in (init(), msg_start(parent="toolu_1"), bloque(0, parent="toolu_1"),
                  delta(0, "texto del subagente", parent="toolu_1"), msg_start(), bloque(0), delta(0, "Principal.")):
            p.linea(json.dumps(e))
        self.assertEqual("".join(textos), "Principal.")


class T05_FraseDeFragmentos(unittest.TestCase):
    def test_reconstruye(self):
        f = st.Frases()
        for t in ("Señor, el planeta más", " grande del sistema solar", " es Júpiter.", " Su diámetro..."):
            f.agregar(t)
        self.assertEqual(f.siguiente(), "Señor, el planeta más grande del sistema solar es Júpiter.")


class T06_Incompleta(unittest.TestCase):
    def test_no_habla_incompleta(self):
        f = st.Frases()
        f.agregar("Señor, el planeta más grande es Júpiter")
        self.assertIsNone(f.siguiente())
        f2 = st.Frases(); f2.agregar("Señor. ")
        self.assertIsNone(f2.siguiente())                                  # «Señor.» no es frase
        f3 = st.Frases(); f3.agregar("Señor, ")
        self.assertIsNone(f3.siguiente())

    def test_buffer_limitado(self):
        f = st.Frases(); f.agregar("palabra " * 200)
        self.assertIsNone(f.siguiente())
        self.assertEqual(f.motivo, "sin_frase")

    def test_markdown_y_codigo(self):
        for inicio in ("# Título\n", "- punto uno. ", "```python\n", "1. Primero. "):
            f = st.Frases(); f.agregar(inicio + "Algo largo que no se debe decir. ")
            self.assertIsNone(f.siguiente(), inicio)


class T07_Abreviaturas(unittest.TestCase):
    def frase(self, texto):
        f = st.Frases(); f.agregar(texto)
        return f.siguiente()

    def test_casos(self):
        self.assertEqual(self.frase("El Sr. López llegó a la reunión temprano. Luego"),
                         "El Sr. López llegó a la reunión temprano.")
        self.assertEqual(self.frase("Pi vale 3.14 aproximadamente, señor. Y"), "Pi vale 3.14 aproximadamente, señor.")
        self.assertEqual(self.frase("Vea www.ejemplo.com para más detalles hoy. Y"),
                         "Vea www.ejemplo.com para más detalles hoy.")
        self.assertEqual(self.frase("Hay frutas, p. ej. manzanas y peras ricas. Y"),
                         "Hay frutas, p. ej. manzanas y peras ricas.")
        self.assertEqual(self.frase("¿Sabía que Júpiter es enorme, señor? Mide"), "¿Sabía que Júpiter es enorme, señor?")
        self.assertEqual(self.frase("Jupiter is the largest planet, sir! It"), "Jupiter is the largest planet, sir!")

    def test_nunca_pasa_de_la_primera_linea(self):
        f = st.Frases(); f.agregar("Júpiter es el más grande, señor\n\nDetalle. Otra frase.")
        self.assertIsNone(f.siguiente())                                  # la línea cerró sin límite de frase
        f = st.Frases(); f.agregar("Júpiter es el más grande, señor. Once veces la Tierra.\n\nDetalle largo.")
        self.assertEqual(f.siguiente(), "Júpiter es el más grande, señor.")
        self.assertEqual(f.siguiente(), "Once veces la Tierra.")
        self.assertIsNone(f.siguiente())


class Clasificador(unittest.TestCase):
    def test_entran(self):
        for t in ("explícame qué es una órbita", "¿Qué es la fotosíntesis?", "dime tres planetas del sistema solar",
                  "¿quién fue Benito Juárez?", "¿por qué el cielo es azul?", "traduce hola al inglés",
                  "¿cómo funciona un motor?", "what is an orbit"):
            self.assertTrue(st.ruta_sin_herramientas(t), t)

    def test_no_entran(self):
        for t in ("¿qué tengo pendiente?", "explícame mi tarea de mañana", "¿qué es lo último en noticias?",
                  "abre Spotify", "busca qué es una órbita", "¿qué hora es?", "cuéntame mis pendientes",
                  "¿qué clima hace?", "manda un correo", "borra el archivo", "hola", "", "dime tres cosas de hoy",
                  "¿cuál es el precio del dólar?", "qué es el modo gamer"):
            self.assertFalse(st.ruta_sin_herramientas(t), t)

    def test_seguimiento(self):
        self.assertTrue(st.ruta_sin_herramientas("¿Cuál de esos es el más grande?", True, True))
        self.assertFalse(st.ruta_sin_herramientas("¿Cuál de esos es el más grande?", True, False))
        self.assertFalse(st.ruta_sin_herramientas("¿Cuál de esos es el más grande?", False, False))
        self.assertFalse(st.ruta_sin_herramientas("¿qué es una estrella?", True, False))


# ---------------------------------------------------------------- coordinador con procesos reales
class T08_UnaFraseAnticipada(Base):
    def test_habla_exactamente_la_primera_frase_antes_del_resultado(self):
        voz_f = FalsaVoz(seg=0.2)
        h = self.hablador(voz_f)
        falso = FalsoClaude(respuesta_simple(["Una órbita es la ", "trayectoria de un objeto.", " Se mantiene ",
                                              "por la gravedad, señor."], espera_tras=0.8))
        resp, cerebro = self.pensar(falso, hablador=h)
        self.assertEqual(voz_f.dichos[0], "Una órbita es la trayectoria de un objeto.")
        self.assertEqual(cerebro, "claude")
        self.assertTrue(h.finalizar(pensar_mod.primera_linea(resp)))
        h.esperar()
        self.assertEqual(voz_f.dichos, ["Una órbita es la trayectoria de un objeto.",
                                        "Se mantiene por la gravedad, señor."])
        claude_p = [f for f in self.filas() if f["etapa"] == "claude_p"][0]
        self.assertTrue(claude_p["anticipada"])
        e = {f["etapa"]: f["ms"] for f in self.filas()}
        self.assertLess(e["tts_inicio"], e["claude_resultado"])           # empezó a hablar antes del resultado


class T09_ConHerramientasNoAnticipa(Base):
    def test_ruta_normal(self):
        voz_f = FalsaVoz()
        h = self.hablador(voz_f)
        falso = FalsoClaude(respuesta_simple(["He eliminado el archivo, señor. ", "Listo."], tools=["Bash"]))
        resp, _ = self.pensar(falso, "borra el archivo", hablador=h, sin_herr=False)
        self.assertEqual(voz_f.dichos, [])
        self.assertIn("--tools", falso.cmds[0])
        self.assertEqual(falso.cmds[0][falso.cmds[0].index("--tools") + 1], pensar_mod.ASISTENTE_CLAUDE[3])
        f = [x for x in self.filas() if x["etapa"] == "claude_p"][0]
        self.assertEqual((f["anticipada"], f["motivo"]), (False, "con_tools"))

    def test_init_con_herramientas_bloquea(self):
        voz_f = FalsaVoz()
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo. ", "Sí."], tools=["Bash"]))
        self.pensar(falso, hablador=self.hablador(voz_f))
        self.assertEqual(voz_f.dichos, [])
        self.assertEqual([x for x in self.filas() if x["etapa"] == "claude_p"][0]["motivo"], "init_con_tools")

    def test_tool_use_inesperado_detiene(self):
        voz_f = FalsaVoz()
        ev = [init(), msg_start(), bloque(0), bloque(1, "tool_use"), delta(0, "He borrado el archivo, señor. "),
              stop(0), result("Listo")]
        self.pensar(FalsoClaude(ev), hablador=self.hablador(voz_f))
        self.assertEqual(voz_f.dichos, [])

    def test_mcp_en_init_bloquea(self):
        voz_f = FalsaVoz()
        ev = [init((), [{"name": "x"}])] + respuesta_simple(["Una órbita es un camino curvo. ", "Sí."])[1:]
        self.pensar(FalsoClaude(ev), hablador=self.hablador(voz_f))
        self.assertEqual(voz_f.dichos, [])


class PrimerTextoConHerramientas(Base):
    def test_se_mide_aunque_el_primer_mensaje_sea_tool_use(self):
        ev = [init(["Read"]), msg_start(), bloque(0, "tool_use"), stop(0), msg_start(), bloque(0),
              delta(0, "Tiene tres pendientes, señor."), stop(0), result("Tiene tres pendientes, señor.")]
        voz_f = FalsaVoz()
        self.pensar(FalsoClaude(ev), "qué tengo pendiente", hablador=self.hablador(voz_f), sin_herr=False)
        self.assertIn("claude_primer_texto", {f["etapa"] for f in self.filas()})
        self.assertEqual(voz_f.dichos, [])


class T10_ResultadoAutoritativo(Base):
    def test_result_manda(self):
        ev = [init(), msg_start(), bloque(0), delta(0, "Primer mensaje. "), stop(0), msg_start(), bloque(0),
              delta(0, "Segundo mensaje."), stop(0), result("Respuesta final del result.")]
        resp, _ = self.pensar(FalsoClaude(ev), hablador=self.hablador(), sin_herr=False)
        self.assertEqual(resp, "Respuesta final del result.")


class T11_SinDuplicar(Base):
    def test_assistant_no_duplica(self):
        textos = []
        p = st.Parser(al_texto=textos.append)
        for e in respuesta_simple(["Hola, ", "señor."]):
            if isinstance(e, dict):
                p.linea(json.dumps(e))
        self.assertEqual("".join(textos), "Hola, señor.")


class T12_SinRepetir(Base):
    def test_linea_completa_ya_dicha_no_suena_al_final(self):
        voz_f = FalsaVoz(seg=0.1)
        h = self.hablador(voz_f)
        resp, _ = self.pensar(FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor.", "\n\nDetalle."])),
                              hablador=h)
        h.finalizar(pensar_mod.primera_linea(resp)); h.esperar()
        self.assertEqual(voz_f.dichos, ["Una órbita es un camino curvo, señor."])

    def test_lo_que_ya_esta_en_fila_no_se_repite(self):
        """Regresión: el resto de la línea ya estaba en cola (sonaba la frase 1) cuando llegó result."""
        h = self.hablador(FalsaVoz(seg=0.1))
        h.hablado, h.cola = ["Una órbita es un camino curvo, señor."], ["Sí."]
        self.assertTrue(h.finalizar("Una órbita es un camino curvo, señor. Sí."))
        self.assertEqual(h.cola, ["Sí."])

    def test_final_distinto_no_habla_mas(self):
        h = self.hablador(FalsaVoz(seg=0.1))
        h.hablado = ["Una órbita es un camino."]
        self.assertFalse(h.finalizar("Algo totalmente distinto. Y más."))
        self.assertEqual(h.cola, [])


class T13_GeneraMientrasHabla(Base):
    def test_solapamiento(self):
        voz_f = FalsaVoz(seg=0.5)
        h = self.hablador(voz_f)
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo alrededor de algo. ", "Más texto."],
                                             espera_tras=1.0))
        t0 = time.perf_counter()
        self.pensar(falso, hablador=h)
        dur = time.perf_counter() - t0
        e = {f["etapa"]: f["ms"] for f in self.filas()}
        self.assertGreater(e["voz_solapada"], 500)                         # habló mientras Claude seguía
        self.assertLess(dur, 3.0)
        h.esperar()


class T14_SinBloqueoDePipes(Base):
    def test_mucho_stdout_y_stderr(self):
        muchos = [delta(0, "x") for _ in range(3000)]
        ev = [init(), msg_start(), bloque(0)] + muchos + [stop(0), result("Fin.")]
        falso = FalsoClaude(ev, stderr="E" * 200_000, pausa=0)
        t0 = time.perf_counter()
        resp, _ = self.pensar(falso, hablador=self.hablador(), sin_herr=False)
        self.assertEqual(resp, "Fin.")
        self.assertLess(time.perf_counter() - t0, 20)


class T15_JsonMalformado(Base):
    def test_fallo_controlado(self):
        ev = [init(), msg_start(), "{esto no es json", result("nunca")]
        resp, cerebro = self.pensar(FalsoClaude(ev), hablador=self.hablador(), sin_herr=False)
        self.assertEqual(cerebro, "ninguno")                               # sin hablar: Codex (aquí apagado)
        f = [x for x in self.filas() if x["etapa"] == "claude_p"][0]
        self.assertEqual(f["estado"], "error")


class T16_SinResult(Base):
    def test_incompleto(self):
        voz_f = FalsaVoz(seg=0.1)
        h = self.hablador(voz_f)
        ev = [init(), msg_start(), bloque(0), delta(0, "Una órbita es un camino curvo, señor. "), delta(0, "Y")]
        codex = mock.MagicMock(return_value=("Respaldo", None))
        resp, cerebro = self.pensar(FalsoClaude(ev), hablador=h, codex=codex)
        self.assertEqual((resp, cerebro), (pensar_mod.INCOMPLETA, "ninguno"))
        self.assertTrue(h.incompleta)
        codex.assert_not_called()                                          # ya sonó algo: ni Codex
        h.esperar()


class T17_ErrorTrasVozNoRepite(Base):
    def test_no_relanza(self):
        h = self.hablador(FalsaVoz(seg=0.1))
        ev = [init(), msg_start(), bloque(0), delta(0, "Una órbita es un camino curvo, señor. "),
              result("No conversation found", is_error=True)]
        falso = FalsoClaude(ev, stderr="No conversation found with session ID: x", rc=1)
        sesiones.guardar("personal", SID, nueva=True)
        codex = mock.MagicMock()
        self.pensar(falso, hablador=h, codex=codex)
        self.assertEqual(len(falso.cmds), 1)                                # no se reintentó Claude
        codex.assert_not_called()
        self.assertIsNone(sesiones.vigente("personal"))                    # sesión olvidada, como hoy
        h.esperar()

    def test_tool_use_y_falla_no_codex(self):
        ev = [init(["Bash"]), msg_start(), bloque(0, "tool_use"), stop(0)]
        codex = mock.MagicMock()
        resp, _ = self.pensar(FalsoClaude(ev, rc=1), hablador=self.hablador(), sin_herr=False, codex=codex)
        codex.assert_not_called()
        self.assertEqual(resp, pensar_mod.INCOMPLETA)


class T18_Limpieza(Base):
    def test_procesos_recolectados(self):
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Más."]))
        h = self.hablador(FalsaVoz(seg=5))
        self.pensar(falso, hablador=h)
        self.assertIsNotNone(falso.procs[0].returncode)                    # claude recolectado
        h.cancelar()
        self.assertTrue(all(p.poll() is not None for p in h.lanzar.procs))  # la voz no queda huérfana

    def test_timeout_mata(self):
        ev = [init(), ("dormir", 5), result("tarde")]
        relojes = iter([0, 0] + [400] * 50)
        c = st.correr(["x"], popen=FalsoClaude(ev), timeout=300, reloj=lambda: next(relojes))
        self.assertEqual(c.error, "timeout")
        self.assertIsNotNone(c.rc)


class T19_RollbackJson(Base):
    def test_config_desactiva_stream(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(result("Hola, señor.")), "")
        m = mock.MagicMock(); m.run.side_effect = run; m.DEVNULL = subprocess.DEVNULL
        with mock.patch.object(pensar_mod, "subprocess", m):
            resp, _ = self.pensar(FalsoClaude([]), hablador=self.hablador(), config={"claude_streaming": False})
        self.assertEqual(resp, "Hola, señor.")
        cmd = llamadas[0]
        self.assertEqual(cmd[3:5], ["--output-format", "json"])
        self.assertEqual(cmd[-len(pensar_mod.ASISTENTE_CLAUDE):], pensar_mod.ASISTENTE_CLAUDE)   # con herramientas

    def test_voz_anticipada_apagada(self):
        voz_f = FalsaVoz()
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Más."]))
        self.pensar(falso, hablador=self.hablador(voz_f), config={"voz_anticipada": False})
        self.assertEqual(voz_f.dichos, [])
        self.assertIn("stream-json", falso.cmds[0])
        self.assertEqual(falso.cmds[0][-len(pensar_mod.ASISTENTE_CLAUDE):], pensar_mod.ASISTENTE_CLAUDE)
        self.assertEqual([x for x in self.filas() if x["etapa"] == "claude_p"][0]["motivo"], "desactivado")


class T20_Sesiones(Base):
    def test_nueva_y_reanudada_aunque_cambie_tools(self):
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor."]),
                            respuesta_simple(["Júpiter es el más grande, señor."], tools=["Bash"]))
        self.pensar(falso, hablador=self.hablador(FalsaVoz(seg=0.05)))
        sid = falso.cmds[0][falso.cmds[0].index("--session-id") + 1]
        falso.guiones = [respuesta_simple(["Júpiter es el más grande, señor."], sid=sid)]
        self.pensar(falso, "cuál es mi pendiente", hablador=self.hablador(), sin_herr=False)
        b = falso.cmds[1]
        self.assertEqual(b[b.index("--resume") + 1], sid)
        self.assertNotIn("--continue", b)
        self.assertEqual(b[b.index("--tools") + 1], pensar_mod.ASISTENTE_CLAUDE[3])


# ---------------------------------------------------------------- voz y conversación
class Voz(Base):
    def setUp(self):
        super().setUp()
        self.bit = []
        self.voz_f = FalsaVoz(seg=0.3)
        self.p2 = [mock.patch.object(voz, "CASA", self.casa), mock.patch.object(voz, "CERRAR", self.cerrar),
                   mock.patch.object(voz, "DISPARADOR", self.casa / "escuchar"),
                   mock.patch.object(voz, "estado"), mock.patch.object(voz, "log"),
                   mock.patch.object(voz, "subprocess"),
                   mock.patch.object(voz, "Hablador", functools.partial(st.Hablador, lanzar=self._lanzar)),
                   mock.patch.object(voz, "decir", self._decir),
                   mock.patch.object(voz, "config", return_value=dict(comun.config(), timeout_orden_seg=6))]
        for p in self.p2:
            p.start()
        voz.subprocess.run.return_value = subprocess.CompletedProcess([], 0, "", "")

    def tearDown(self):
        for p in self.p2:
            p.stop()
        super().tearDown()

    def _lanzar(self, texto):
        self.bit.append(("voz", texto))
        return self.voz_f(texto)

    def _decir(self, texto, forzar=False):
        self.bit.append(("decir", texto)); return True

    def turno(self, falso, texto="qué es una órbita", conv=None, sin_herr_cfg=None):
        cfg = {"claude_streaming": True, "voz_anticipada": True}
        with mock.patch.object(pensar_mod.streaming, "correr", functools.partial(st.correr, popen=falso)), \
             mock.patch.object(pensar_mod, "config", return_value=cfg), \
             mock.patch.object(voz, "pensar", pensar_mod.pensar):
            return voz.procesar(texto, conv)


class T21_FollowUpEsperaAmbos(Voz):
    def test_claude_termina_antes_que_la_voz(self):
        conv = cv.Conversacion(); conv.activar(); conv.iniciar_turno()
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Sí."]))
        t0 = time.perf_counter()
        self.turno(falso, conv=conv)
        self.assertEqual(len(self.voz_f.dichos), 2)                          # frase 1 anticipada + resto
        self.assertGreaterEqual(time.perf_counter() - t0, 0.6)              # esperó a las dos voces
        self.assertTrue(all(p.poll() is not None for p in self.voz_f.procs))
        self.assertEqual(conv.estado, cv.SPEAKING)
        self.assertTrue(conv.respuesta_terminada("cerebro"))

    def test_voz_termina_antes_que_claude(self):
        self.voz_f.seg = 0.05
        conv = cv.Conversacion(); conv.activar(); conv.iniciar_turno()
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Y más."], espera_tras=0.8))
        t0 = time.perf_counter()
        self.turno(falso, conv=conv)
        self.assertGreaterEqual(time.perf_counter() - t0, 0.8)              # esperó a Claude

    def test_voz_falla_no_abre_microfono(self):
        """Ajuste 6: el hijo de voz sale con error y nadie pidió callar → igual que el RuntimeError de _hablar()."""
        self.voz_f.rc = 1
        conv = cv.Conversacion(); conv.activar(); conv.iniciar_turno()
        with self.assertRaises(RuntimeError):
            self.turno(FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Más."])), conv=conv)


class T22_NoSeEscucha(Voz):
    def test_vacia_despues_de_toda_la_voz(self):
        conv = cv.Conversacion(); conv.activar(); conv.iniciar_turno()
        self.turno(FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Sí."])), conv=conv)
        conv.respuesta_terminada("cerebro")
        o = mock.MagicMock(); o.frase.return_value = None
        o.vaciar.side_effect = lambda: self.bit.append("vaciar")
        voz.esperar_seguimiento(o, "small", conv)
        self.assertEqual(self.bit[-1], "vaciar")
        self.assertTrue(all(p.poll() is not None for p in self.voz_f.procs))


class T23_VozLock(unittest.TestCase):
    def test_una_voz_a_la_vez(self):
        voz_f = FalsaVoz(seg=0.2)
        h = st.Hablador(lanzar=voz_f)
        h.decir("uno"); h.decir("dos"); h.decir("tres")
        h.esperar()
        self.assertEqual(voz_f.dichos, ["uno", "dos", "tres"])
        self.assertEqual(voz_f.vivos_max, 1)
        src = (RAIZ / "bin/decir.py").read_text()
        self.assertIn("fcntl.flock(candado, fcntl.LOCK_EX)", src)
        self.assertIn('"decir.py"', (RAIZ / "bin/streaming.py").read_text())   # el hijo usa decir.py (voz.lock)


class T24_CancelarSinHuerfanos(Voz):
    def test_callar_durante_voz_anticipada(self):
        """Ajuste 7: ⌃⌥. mata el say; no se habla el resto; Claude NO se mata; historial y cierre."""
        self.voz_f.seg = 0.4
        conv = cv.Conversacion(); conv.activar(); conv.iniciar_turno()
        falso = FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Y más cosas."],
                                             espera_tras=0.6))
        cerrar = self.cerrar
        real = self._lanzar
        def lanzar_y_callar(texto):
            p = real(texto); cerrar.touch(); return p            # JP calla en cuanto empieza a hablar
        with mock.patch.object(voz, "Hablador", functools.partial(st.Hablador, lanzar=lanzar_y_callar)):
            self.turno(falso, conv=conv)
        self.assertEqual(len(self.voz_f.dichos), 1)                       # no habló el resto
        self.assertEqual(falso.procs[0].returncode, 0)                   # Claude terminó normal
        hist = (self.casa / "historial.jsonl").read_text().splitlines()
        self.assertEqual(len(hist), 1)
        self.assertFalse(conv.respuesta_terminada("cerebro", cerrar=voz.cerrar_pedido()))
        self.assertTrue(all(p.poll() is not None for p in self.voz_f.procs))


# ---------------------------------------------------------------- captura tras «Jarvis» (bug del tin)
class Audio:
    def __init__(self, texto):
        self.texto = texto


class OidoCola:
    """Oído con COLA real: lo que JP dijo después de «Jarvis» está en la cola; vaciar() lo tira."""
    def __init__(self, primera, en_cola=(), voz_seg=0.5):
        self.primera, self.cola = primera, list(en_cola)
        self.ultima = (0, int(voz_seg * 1e9), int(voz_seg * 1e9) + 1)
        self.llamadas, self.vaciados, self.dada = [], 0, False

    def vaciar(self):
        self.vaciados += 1
        if self.dada:
            self.cola.clear()

    def frase(self, espera_inicio=None, **kw):
        self.llamadas.append(espera_inicio)
        if not self.dada:
            self.dada = True
            return "DISPARO" if self.primera == "DISPARO" else Audio(self.primera)
        if self.cola:
            self.ultima = (0, int(1e9), int(1e9) + 1)
            return Audio(self.cola.pop(0))
        return None


class Captura(Voz):
    def setUp(self):
        super().setUp()
        self.groq, self.pensado = [], []
        self.conv = cv.Conversacion()
        self.p3 = [mock.patch.object(voz, "transcribir", lambda m, a, *x, **k: a.texto),
                   mock.patch.object(voz, "oir_bien", lambda a, p: (self.groq.append(a.texto), a.texto)[1]),
                   mock.patch.object(voz, "pensar", lambda t, **k: (self.pensado.append(t), ("Listo, señor.", "claude"))[1]),
                   mock.patch.object(voz, "osa", lambda s: subprocess.CompletedProcess([], 0, "", ""))]
        for p in self.p3:
            p.start()

    def tearDown(self):
        for p in self.p3:
            p.stop()
        super().tearDown()

    def correr(self, oido):
        voz.escuchar_una(oido, "base", "small", self.conv)


class T25_UnaFrase(Captura):
    def test_jarvis_abre_spotify(self):
        o = OidoCola("Jarvis, abre Spotify", voz_seg=1.2)
        self.correr(o)
        self.assertEqual(self.groq, ["Jarvis, abre Spotify"])
        self.assertIn(("decir", "Abriendo spotify, señor."), self.bit)


class T26_PausaConservaInicio(Captura):
    def test_jarvis_pausa_orden(self):
        o = OidoCola("Jarvis", en_cola=["dime tres planetas"])
        self.correr(o)
        self.assertEqual(self.pensado, ["dime tres planetas"])
        self.assertEqual(self.groq, ["dime tres planetas"])                 # «Jarvis» solo no fue a Groq


class T27_OrdenDuranteElTin(Captura):
    def test_no_se_pierde_abre(self):
        o = OidoCola("Jarvis", en_cola=["Abre Spotify"])                      # ya hablaba cuando sonó el tin
        self.correr(o)
        self.assertIn(("decir", "Abriendo spotify, señor."), self.bit)
        self.assertEqual(o.llamadas[1], 6.0)                                 # timeout_orden_seg

    def test_antes_si_se_perdia(self):
        """Control: con el vaciado de antes (⌃⌥J) la orden que ya estaba en la cola se pierde."""
        o = OidoCola("Jarvis", en_cola=["Abre Spotify"])
        o.dada = True
        self.assertEqual(voz.pedir_comando(o, "small", vaciar=True), "")


class T28_ActivacionAisladaCaduca(Captura):
    def test_solo_jarvis(self):
        o = OidoCola("Jarvis")
        self.correr(o)
        self.assertEqual(self.pensado, [])
        self.assertEqual(o.llamadas[1], 6.0)
        self.assertEqual(self.conv.estado, cv.IDLE)

    def test_solo_ruido_no_es_orden(self):
        o = OidoCola("Jarvis", en_cola=[""])
        self.correr(o)
        self.assertEqual(self.pensado, [])


class T29_SinDuplicar(Captura):
    def test_preroll_no_repite(self):
        o = OidoCola("Jarvis", en_cola=["qué hora es"])
        self.correr(o)
        self.assertEqual(len([b for b in self.bit if b[0] == "decir"]), 1)
        self.assertEqual(self.groq, ["qué hora es"])

    def test_jarvis_largo_si_va_a_groq(self):
        o = OidoCola("Jarvis", voz_seg=2.5)                                  # dijo más que «Jarvis»: Groq
        self.correr(o)
        self.assertEqual(self.groq[:1], ["Jarvis"])

    def test_atajo_sigue_vaciando(self):
        """⌃⌥J (IDLE) vacía la cola como siempre: audio viejo no se vuelve orden."""
        o = OidoCola("DISPARO", en_cola=["abre Spotify"])
        self.correr(o)
        self.assertEqual(self.groq, [])
        self.assertNotIn(("decir", "Abriendo spotify, señor."), self.bit)


class T30_ConversacionIntacta(unittest.TestCase):
    def test_limites(self):
        c = json.loads((RAIZ / "config.json").read_text())
        self.assertEqual((c["timeout_seguimiento_seg"], c["max_turnos"], c["conversacion_continua"]), (15, 5, True))
        r = [0.0]
        conv = cv.Conversacion(reloj=lambda: r[0])
        conv.activar()
        for _ in range(4):
            conv.iniciar_turno(); conv.hablar()
            self.assertTrue(conv.respuesta_terminada("cerebro"))
            self.assertEqual(conv.restante(), 15.0)
        conv.iniciar_turno()
        self.assertFalse(conv.respuesta_terminada("cerebro"))


# ---------------------------------------------------------------- seguridad y regresión
class T31_Guardia(Base):
    def test_hook_y_candados_en_ambas_rutas(self):
        sin = pensar_mod.asistente_sin_herramientas()
        for f in ("--restricted", "--strict-mcp-config", "--settings"):
            self.assertIn(f, sin)
        self.assertEqual(sin.count("--tools"), 1)
        self.assertEqual(sin[sin.index("--tools") + 1], "")
        self.assertEqual(sin[sin.index("--permission-mode") + 1], "dontAsk")
        asis = json.loads((RAIZ / "seguridad/claude_asistente.json").read_text())
        self.assertIn("bin/guardia.py", asis["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertFalse(guardia.decidir({"tool_name": "Bash", "tool_input": {"command": "rm -rf ~/Documents"},
                                          "cwd": str(RAIZ)})[0])


class T32_33_Politica(Base):
    def test_sensibles_y_prohibidas(self):
        for (tipo, red), nivel in {("enviar_whatsapp", ""): "confirmar", ("borrar", ""): "confirmar",
                                   ("gasto", ""): "confirmar", ("publicar", "instagram"): "prohibido",
                                   ("publicar", "tiktok"): "prohibido", ("conectar", "snapchat"): "prohibido"}.items():
            self.assertEqual(politica.evaluar({"tipo": tipo, "red": red})[0], nivel)


class T34_Perfiles(unittest.TestCase):
    def test_mundos(self):
        self.assertEqual(comun.mundo_de("https://classroom.google.com"), "escuela")
        self.assertEqual(comun.mundo_de("https://youtube.com"), "personal")


class T35_Codex(Base):
    def test_sandbox_intacto_y_parser_no_lo_amplia(self):
        cmd = " ".join(pensar_mod.ASISTENTE_CODEX)
        self.assertIn('"~/.jarvis"="deny"', cmd)
        self.assertNotIn("--sandbox", cmd)
        codex = mock.MagicMock(return_value=(None, pensar_mod.SIN_RESPALDO))
        resp, _ = self.pensar(FalsoClaude([init(), "{roto"]), hablador=self.hablador(), sin_herr=False, codex=codex)
        codex.assert_called_once()                                           # el respaldo de siempre (aislado)
        self.assertIn("deshabilitado por seguridad", resp)
        with mock.patch.object(pensar_mod, "buscar_codex", return_value="/x"), \
             mock.patch.object(pensar_mod, "codex_aislado", return_value=False):
            self.assertEqual(pensar_mod.codex("hola", True), (None, pensar_mod.SIN_RESPALDO))


class T36_Historial(Base):
    def test_una_linea_con_el_result(self):
        h = self.hablador(FalsaVoz(seg=0.05))
        self.pensar(FalsoClaude(respuesta_simple(["Una órbita es un camino curvo, señor. ", "Más."],
                                                 final="Una órbita es un camino curvo, señor. Más.")), hablador=h)
        h.esperar()
        lineas = (self.casa / "historial.jsonl").read_text().splitlines()
        self.assertEqual(len(lineas), 1)
        self.assertEqual(json.loads(lineas[0])["jarvis"], "Una órbita es un camino curvo, señor. Más.")


class T37_TelemetriaSinContenido(Base):
    def test_sin_texto(self):
        h = self.hablador(FalsaVoz(seg=0.05))
        self.pensar(FalsoClaude(respuesta_simple(["SECRETO_ORBITA es un camino curvo, señor. ", "PRIVADO."])),
                    "qué es SECRETO_PREGUNTA", hablador=h)
        h.esperar()
        txt = (self.casa / "metricas.jsonl").read_text()
        for x in ("SECRETO", "PRIVADO", "órbita"):
            self.assertNotIn(x, txt)
        for f in self.filas():
            self.assertTrue(set(f) <= {"fecha", "id", "origen", "etapa", "ms", "ruta", "estado", "sesion",
                                       "anticipada", "motivo"})

    def test_jv_latencia_resume_voz_anticipada(self):
        import io, latencia
        from contextlib import redirect_stdout
        tm.registrar("claude_p", 2000, extra={"anticipada": True})
        tm.registrar("claude_p", 3000, extra={"anticipada": False, "motivo": "con_tools"})
        tm.registrar("claude_p", 3000, extra={"anticipada": "sí", "motivo": "inventado"})   # no pasan
        with mock.patch.object(sys, "argv", ["latencia"]), redirect_stdout(io.StringIO()) as out:
            latencia.main()
        self.assertIn("Voz anticipada (stream-json): 1 de 2 turnos (50%)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
