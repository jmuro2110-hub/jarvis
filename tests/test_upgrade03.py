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
                        mock.patch.object(pensar_mod, "_continuar", return_value=False)]
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


if __name__ == "__main__":
    unittest.main()
