"""Pruebas del upgrade 03 (stdin, salida JSON, telemetría, sesiones, aislamiento de Codex).
Todo con mocks salvo lo marcado como real (se salta si falta el CLI).

    uv run --python 3.11 --with numpy python -m unittest tests.test_upgrade03 -v
"""
import io, json, os, pathlib, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))

import telemetria as tm           # noqa: E402
import pensar as pensar_mod       # noqa: E402
import latencia                   # noqa: E402
import sesiones                   # noqa: E402

SID = "22222222-2222-4222-8222-222222222222"


def claude_json(texto, is_error=False, session_id=SID, duration_ms=1500, duration_api_ms=1200):
    return json.dumps({"type": "result", "result": texto, "is_error": is_error, "session_id": session_id,
                       "duration_ms": duration_ms, "duration_api_ms": duration_api_ms})


def falso_subprocess(run):
    m = mock.MagicMock()
    m.run.side_effect = run
    m.TimeoutExpired = subprocess.TimeoutExpired
    m.DEVNULL = subprocess.DEVNULL
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.dir.name)
        self.archivo = d / "metricas.jsonl"
        self.parches = [mock.patch.object(tm, "ARCHIVO", self.archivo),
                        mock.patch.object(pensar_mod, "estado"), mock.patch.object(pensar_mod, "log"),
                        mock.patch.object(pensar_mod, "_guardar"),
                        mock.patch.object(sesiones, "DIR", d)]
        for p in self.parches:
            p.start()
        tm.terminar()

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.dir.cleanup()

    def filas(self):
        return [json.loads(l) for l in self.archivo.read_text().splitlines()] if self.archivo.exists() else []

    def correr(self, salida, rc=0, stderr="", texto="hola", codex=None):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append((cmd, kw))
            if cmd[0] == "claude":
                return subprocess.CompletedProcess(cmd, rc, salida, stderr)
            raise AssertionError("no debe llegar a Codex")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value=codex):
            tm.nueva("texto", tm.ahora())
            res = pensar_mod.claude(texto, False)
        return res, llamadas


class T01_Stdin(Base):
    def test_mock_stdin_cerrado(self):
        _, ((cmd, kw),) = self.correr(claude_json("ok"))
        self.assertIs(kw["stdin"], subprocess.DEVNULL)
        self.assertTrue(kw["capture_output"])
        self.assertEqual(kw["timeout"], 300)
        self.assertEqual(cmd[1:3], ["-p", "hola"])                       # el prompt sigue como argumento

    def test_real_el_hijo_recibe_eof(self):
        """Mismo subprocess.run que pensar.claude(), con un hijo que lee stdin: EOF inmediato, sin espera."""
        hijo = [sys.executable, "-c", "import sys,time;t=time.time();d=sys.stdin.read();"
                                      "print(len(d), round(time.time()-t, 2))"]
        r = subprocess.run(hijo, capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
        n, seg = r.stdout.split()
        self.assertEqual(n, "0")
        self.assertLess(float(seg), 0.5)


class T02_Respuesta(Base):
    def test_texto_igual_que_antes(self):
        (res, err), _ = self.correr(claude_json("Señor, listo.\n\nDetalle.\n"))
        self.assertEqual((res, err), ("Señor, listo.\n\nDetalle.", None))

    def test_is_error(self):
        (res, err), _ = self.correr(claude_json("You've hit your limit · resets 3pm", is_error=True), rc=1)
        self.assertIsNone(res)
        self.assertIn("limit", err)

    def test_limite_en_result_sin_is_error(self):
        (res, err), _ = self.correr(claude_json("Claude usage limit reached"))
        self.assertIsNone(res)

    def test_respuesta_larga_que_menciona_limite_pasa(self):
        largo = "Señor, el rate limit de la API es de 50 por minuto. " + "x" * 400
        (res, _), _ = self.correr(claude_json(largo))
        self.assertEqual(res, largo.strip())

    def test_salida_no_json_es_error(self):
        (res, err), _ = self.correr("Error: algo tronó", rc=1)
        self.assertIsNone(res)
        self.assertIn("tronó", err)

    def test_result_vacio(self):
        (res, _), _ = self.correr(claude_json(""))
        self.assertIsNone(res)

    def test_pensar_pasa_a_codex_si_is_error(self):
        def run(cmd, **kw):
            if cmd[0] == "claude":
                return subprocess.CompletedProcess(cmd, 1, claude_json("hit your limit", is_error=True), "")
            pathlib.Path(cmd[cmd.index("-o") + 1]).write_text("Respaldo, señor.")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value="/falso/codex"):
            self.assertEqual(pensar_mod.pensar("hola"), ("Respaldo, señor.", "chatgpt"))


class T17_Telemetria(Base):
    def test_desglose_y_jv_latencia(self):
        self.correr(claude_json("ok", duration_ms=2000, duration_api_ms=1700))
        f = {x["etapa"]: x for x in self.filas()}
        self.assertTrue({"claude_preparacion", "claude_p", "claude_duracion", "claude_api",
                         "claude_arranque_est"} <= set(f))
        self.assertEqual(f["claude_duracion"]["ms"], 2000)
        self.assertEqual(f["claude_api"]["ms"], 1700)
        self.assertEqual(f["claude_arranque_est"]["ms"], max(0.0, round(f["claude_p"]["ms"] - 2000, 1)))
        for x in f.values():
            self.assertTrue(set(x) <= {"fecha", "id", "origen", "etapa", "ms", "ruta", "estado", "sesion"})
            self.assertNotIn("hola", json.dumps(x))
        with mock.patch.object(sys, "argv", ["latencia"]), redirect_stdout(io.StringIO()) as out:
            latencia.main()
        self.assertIn("claude_arranque_est", out.getvalue())
        self.assertIn("ESTIMACIÓN", out.getvalue())

    def test_lineas_viejas_siguen_leyendose(self):
        self.archivo.write_text(json.dumps({"fecha": "2026-10-24T10:00:00.000", "id": "a", "origen": "voz",
                                            "etapa": "claude_p", "ms": 13450, "ruta": "claude",
                                            "estado": "exito"}) + "\n")
        with mock.patch.object(sys, "argv", ["latencia"]), redirect_stdout(io.StringIO()) as out:
            latencia.main()
        self.assertIn("claude_p", out.getvalue())

    def test_sin_json_no_registra_desglose(self):
        self.correr("texto suelto", rc=1)
        self.assertNotIn("claude_duracion", {x["etapa"] for x in self.filas()})


# ---------------------------------------------------------------- Parte B: sesiones
def claude_eco(llamadas, falla_resume=False, otro_id=None):
    """Mock de claude -p que devuelve el session_id que le mandaron (como el real)."""
    def run(cmd, **kw):
        llamadas.append(cmd)
        if cmd[0] != "claude":
            pathlib.Path(cmd[cmd.index("-o") + 1]).write_text("Respaldo, señor.")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "--resume" in cmd:
            sid = cmd[cmd.index("--resume") + 1]
            if falla_resume:
                return subprocess.CompletedProcess(cmd, 1, "", f"No conversation found with session ID: {sid}")
        else:
            sid = cmd[cmd.index("--session-id") + 1]
        return subprocess.CompletedProcess(cmd, 0, claude_json("Señor.", session_id=otro_id or sid), "")
    return run


class Sesiones(Base):
    def pensar(self, n=1, origen="personal", **kw):
        llamadas = []
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(claude_eco(llamadas, **kw))), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value="/falso/codex"):
            for _ in range(n):
                pensar_mod.pensar("hola", voz=True, origen=origen)
        return llamadas

    def assertSinContinue(self, llamadas):
        for cmd in llamadas:
            self.assertNotIn("--continue", cmd)
            self.assertNotIn("-c", cmd)
            if "--resume" in cmd:
                self.assertTrue(sesiones.valido(cmd[cmd.index("--resume") + 1]))   # nunca --resume a secas

    def guardada(self, origen="personal"):
        return sesiones.leer().get(origen)


class T17b_TelemetriaSesion(Sesiones):
    def test_api_acumulado_no_se_registra_al_reanudar(self):
        tm.nueva("texto", tm.ahora())
        self.pensar(2)
        filas = [f for f in self.filas() if f["etapa"].startswith("claude_")]
        self.assertEqual({f["sesion"] for f in filas}, {"nueva", "reanudada"})
        api = [f["sesion"] for f in filas if f["etapa"] == "claude_api"]
        self.assertEqual(api, ["nueva"])
        self.assertEqual(len([f for f in filas if f["etapa"] == "claude_duracion"]), 2)


class T03_NuevaSesion(Sesiones):
    def test_id_unico_y_valido(self):
        (cmd,) = self.pensar()
        sid = cmd[cmd.index("--session-id") + 1]
        self.assertTrue(sesiones.valido(sid))
        self.assertNotIn("--resume", cmd)
        self.assertEqual(self.guardada()["id"], sid)
        self.assertEqual(set(self.guardada()), {"id", "origen", "creada", "ultima"})   # nada más
        self.assertEqual(oct((sesiones.DIR / "sesiones.json").stat().st_mode & 0o777), "0o600")
        self.assertEqual(len({sesiones.nuevo_id() for _ in range(200)}), 200)

    def test_guarda_el_id_devuelto(self):
        otro = "55555555-5555-4555-8555-555555555555"
        self.pensar(otro_id=otro)
        self.assertEqual(self.guardada()["id"], otro)


class T04_Continuidad(Sesiones):
    def test_dos_personales_misma_sesion(self):
        a, b = self.pensar(2)
        sid = a[a.index("--session-id") + 1]
        self.assertEqual(b[b.index("--resume") + 1], sid)
        self.assertSinContinue([a, b])

    def test_voz_y_texto_comparten(self):
        llamadas = []
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(claude_eco(llamadas))):
            pensar_mod.pensar("por voz", voz=True)
            pensar_mod.pensar("por texto", voz=False)
        self.assertEqual(llamadas[1][llamadas[1].index("--resume") + 1],
                         llamadas[0][llamadas[0].index("--session-id") + 1])


class T05_Expiracion(Sesiones):
    def test_31_min_sesion_nueva(self):
        (a,) = self.pensar()
        d = sesiones.leer(); d["personal"]["ultima"] -= 31 * 60; sesiones._escribir(d)
        (b,) = self.pensar()
        self.assertIn("--session-id", b)
        self.assertNotEqual(b[b.index("--session-id") + 1], a[a.index("--session-id") + 1])

    def test_29_min_sigue(self):
        self.pensar()
        d = sesiones.leer(); d["personal"]["ultima"] -= 29 * 60; sesiones._escribir(d)
        (b,) = self.pensar()
        self.assertIn("--resume", b)


class T06_DesarrolloAislado(Sesiones):
    DEV = "66666666-6666-4666-8666-666666666666"

    def test_nunca_retoma_sesion_ajena(self):
        # Una sesión que no creó el asistente (o con origen alterado) no se reanuda.
        sesiones._escribir({"desarrollo": {"id": self.DEV, "origen": "desarrollo", "ultima": __import__("time").time()},
                            "personal": {"id": self.DEV, "origen": "desarrollo", "ultima": __import__("time").time()}})
        (cmd,) = self.pensar()
        self.assertNotIn(self.DEV, cmd)
        self.assertIn("--session-id", cmd)
        self.assertSinContinue([cmd])

    def test_voz_y_hud_usan_origen_personal(self):
        voz_src = (RAIZ / "voz/jarvis_voz.py").read_text()
        self.assertIn("pensar(texto, voz=True)", voz_src)               # sin origen = personal
        self.assertIn('"pensar", texto, "--hablar"', (RAIZ / "hammerspoon/init.lua").read_text())
        import inspect
        codigo = inspect.getsource(pensar_mod._claude_una) + inspect.getsource(pensar_mod.claude)
        self.assertNotIn('"--continue"', codigo)
        self.assertNotIn('"-c"', codigo)


class T07_AutoAislado(Sesiones):
    def test_resumen_no_toca_personal(self):
        self.pensar()
        antes = self.guardada()
        (cmd,) = self.pensar(origen="auto")
        self.assertIn("--session-id", cmd)                                # no reanuda la personal
        self.assertNotIn(antes["id"], cmd)
        self.assertEqual(self.guardada(), antes)
        self.assertEqual(self.guardada("auto")["origen"], "auto")

    def test_resumen_py_usa_origen_auto(self):
        import resumen
        with mock.patch("pensar.pensar", return_value=("Buenos días.", "claude")) as p, \
             mock.patch.object(resumen, "datos_del_dia", return_value={}), \
             mock.patch("avisar.avisar"):
            resumen.resumen(hablar=False)
        self.assertEqual(p.call_args.kwargs.get("origen"), "auto")

    def test_contexto_codex_solo_personal(self):
        hist = pathlib.Path(self.dir.name) / "h.jsonl"
        with mock.patch.object(pensar_mod, "HIST", hist):
            hist.write_text(json.dumps({"t": 1, "tu": "VIEJA_SIN_ORIGEN", "jarvis": "a", "cerebro": "claude"}) + "\n")
            for tu, o in (("RESUMEN_AUTO", "auto"), ("PLATICA_PERSONAL", "personal")):
                with open(hist, "a") as f:
                    f.write(json.dumps({"t": 2, "tu": tu, "jarvis": "b", "cerebro": "claude", "origen": o}) + "\n")
            textos = [h["tu"] for h in pensar_mod._historial(4, "personal")]
        self.assertEqual(textos, ["VIEJA_SIN_ORIGEN", "PLATICA_PERSONAL"])


class T08_Concurrencia(Sesiones):
    def test_escrituras_simultaneas(self):
        import threading
        ids = [sesiones.nuevo_id() for _ in range(40)]
        hilos = [threading.Thread(target=sesiones.guardar, args=("personal" if i % 2 else "auto", sid, True))
                 for i, sid in enumerate(ids)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        d = json.loads((sesiones.DIR / "sesiones.json").read_text())       # JSON válido, sin mezclas
        self.assertEqual(set(d), {"personal", "auto"})
        self.assertIn(d["personal"]["id"], ids)
        self.assertEqual(list(sesiones.DIR.glob(".sesiones.*.tmp")), [])
        self.assertEqual(oct((sesiones.DIR / "sesiones.json").stat().st_mode & 0o777), "0o600")

    def test_dos_peticiones_no_se_traslapan(self):
        import threading, time
        dentro, maximo, llamadas = [0], [0], []
        eco = claude_eco(llamadas)
        def run(cmd, **kw):
            dentro[0] += 1; maximo[0] = max(maximo[0], dentro[0])
            time.sleep(0.1)
            dentro[0] -= 1
            return eco(cmd, **kw)
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)):
            hilos = [threading.Thread(target=pensar_mod.claude, args=("hola", False)) for _ in range(2)]
            for h in hilos: h.start()
            for h in hilos: h.join()
        self.assertEqual(maximo[0], 1)                                    # serializadas
        sid = llamadas[0][llamadas[0].index("--session-id") + 1]
        self.assertEqual(llamadas[1][llamadas[1].index("--resume") + 1], sid)   # la 2.ª ve el ID de la 1.ª


class T09_SesionInvalida(Sesiones):
    def test_archivo_corrupto(self):
        (sesiones.DIR / "sesiones.json").write_text("{basura")
        (cmd,) = self.pensar()
        self.assertIn("--session-id", cmd)
        self.assertTrue(sesiones.valido(self.guardada()["id"]))

    def test_id_no_uuid(self):
        sesiones._escribir({"personal": {"id": "../../x", "origen": "personal", "ultima": __import__("time").time()}})
        (cmd,) = self.pensar()
        self.assertIn("--session-id", cmd)
        self.assertNotIn("../../x", cmd)

    def test_sesion_que_ya_no_existe(self):
        self.pensar()
        viejo = self.guardada()["id"]
        a, b = self.pensar(falla_resume=True)
        self.assertEqual(a[a.index("--resume") + 1], viejo)
        self.assertIn("--session-id", b)                                  # sesión nueva del asistente
        self.assertSinContinue([a, b])
        self.assertNotEqual(self.guardada()["id"], viejo)

    def test_fallback_codex_reinicia_sesion(self):
        self.pensar()
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            if cmd[0] == "claude":
                return subprocess.CompletedProcess(cmd, 1, claude_json("hit your limit", is_error=True), "")
            pathlib.Path(cmd[cmd.index("-o") + 1]).write_text("Respaldo.")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value="/falso/codex"):
            pensar_mod.pensar("hola")
        self.assertEqual(len([c for c in llamadas if c[0] == "claude"]), 1)   # límite: no reintenta
        self.assertIsNone(self.guardada())


class T10_Guardia(Sesiones):
    def test_candados_en_nueva_y_reanudada(self):
        a, b = self.pensar(2)
        n = len(pensar_mod.ASISTENTE_CLAUDE)
        for cmd in (a, b):
            self.assertEqual(cmd[-n:], pensar_mod.ASISTENTE_CLAUDE)
            self.assertFalse(any("dangerously" in c or c == "bypassPermissions" for c in cmd))
        asis = json.loads((RAIZ / "seguridad/claude_asistente.json").read_text())
        self.assertIn("bin/guardia.py", asis["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

    def test_bloqueos_del_02(self):
        import politica
        casos = {("publicar", "instagram"): "prohibido", ("conectar", "snapchat"): "prohibido",
                 ("evadir_controles", ""): "prohibido", ("borrar", ""): "confirmar",
                 ("enviar_whatsapp", ""): "confirmar", ("gasto", ""): "confirmar", ("algo_raro", ""): "bloqueado"}
        for (tipo, red), esperado in casos.items():
            self.assertEqual(politica.evaluar({"tipo": tipo, "red": red})[0], esperado, tipo)


if __name__ == "__main__":
    unittest.main()
