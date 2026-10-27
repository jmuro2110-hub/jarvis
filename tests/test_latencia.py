"""Pruebas del upgrade 01 (telemetría de latencia). Todo con mocks: no llama a Claude, Codex,
Groq ni a la voz real, y no toca historial.jsonl ni el estado del HUD.

    uv run --python 3.11 --with numpy python -m unittest tests/test_latencia.py -v
"""
import json, os, pathlib, subprocess, sys, tempfile, types, unittest, queue
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))   # sin micrófono en pruebas

import telemetria as tm           # noqa: E402
import pensar as pensar_mod       # noqa: E402
import decir as decir_mod         # noqa: E402
import jarvis_voz as voz          # noqa: E402
import oido as oido_mod           # noqa: E402
import latencia                   # noqa: E402

GUARDAR_ORIGINAL = pensar_mod._guardar
CAMPOS = {"fecha", "id", "origen", "etapa", "ms", "ruta", "estado"}


def claude_json(texto, is_error=False, session_id="11111111-1111-4111-8111-111111111111"):
    """Lo que imprime `claude -p --output-format json` (upgrade 03)."""
    return json.dumps({"type": "result", "result": texto, "is_error": is_error, "session_id": session_id,
                       "duration_ms": 1500, "duration_api_ms": 1200})


def falso_subprocess(run):
    m = mock.MagicMock()
    m.run.side_effect = run
    m.TimeoutExpired = subprocess.TimeoutExpired
    m.DEVNULL = subprocess.DEVNULL
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.archivo = pathlib.Path(self.dir.name) / "metricas.jsonl"
        self.parches = [
            mock.patch.object(tm, "ARCHIVO", self.archivo),
            mock.patch.object(pensar_mod, "estado"), mock.patch.object(pensar_mod, "log"),
            mock.patch.object(pensar_mod, "_guardar"),
            mock.patch.object(pensar_mod, "_continuar", return_value=False),
            mock.patch.object(voz, "estado"), mock.patch.object(voz, "log"),
            mock.patch.object(decir_mod, "estado"),
            mock.patch.object(decir_mod, "secretos", return_value={}),
            mock.patch.object(decir_mod, "config", return_value={"voz_mac": "Juan"}),
            mock.patch.object(decir_mod, "subprocess"),
            mock.patch.object(voz, "subprocess"),
        ]
        for p in self.parches:
            p.start()
        tm.terminar()

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.dir.cleanup()

    def filas(self):
        if not self.archivo.exists():
            return []
        return [json.loads(l) for l in self.archivo.read_text().splitlines()]

    def etapas(self):
        return {f["etapa"]: f for f in self.filas()}


class A_ComandoRapido(Base):
    def test_registra_sin_llamar_al_modelo(self):
        with mock.patch.object(voz, "pensar", side_effect=AssertionError("no debe pensar")):
            tm.nueva("voz", tm.ahora())
            voz.procesar("qué hora es")
        e = self.etapas()
        self.assertEqual(set(e), {"comando_rapido", "voz_preparacion", "total"})
        self.assertEqual(e["comando_rapido"]["ruta"], "rapido")
        self.assertEqual(e["total"]["ruta"], "rapido")
        self.assertEqual(e["total"]["origen"], "voz")
        self.assertEqual(len({f["id"] for f in self.filas()}), 1)

    def test_comando_sin_voz_registra_total(self):
        with mock.patch.object(voz, "osa"):
            tm.nueva("voz", tm.ahora())
            voz.procesar("sube el volumen")
        self.assertEqual(set(self.etapas()), {"comando_rapido", "total"})

    def test_etapas_de_voz(self):
        o = types.SimpleNamespace(ultima=(1_000_000_000, 1_500_000_000, 2_200_000_000))
        tm.nueva("voz")
        voz.medir_frase(o)
        with mock.patch("comun.secretos", return_value={"GROQ_API_KEY": "gsk_FALSA"}), \
             mock.patch.object(voz, "transcribir_nube", return_value=None), \
             mock.patch.object(voz, "transcribir", return_value="abre spotify"):
            self.assertEqual(voz.oir_bien(object(), None), "abre spotify")
        e = self.etapas()
        self.assertEqual(e["captura_frase"]["ms"], 1200.0)
        self.assertEqual(e["espera_silencio"]["ms"], 700.0)
        self.assertEqual(e["transcripcion_groq"]["estado"], "error")
        self.assertEqual(e["transcripcion_local"]["estado"], "fallback")

    def test_sin_llave_groq_no_registra_groq(self):
        tm.nueva("voz")
        with mock.patch("comun.secretos", return_value={}), \
             mock.patch.object(voz, "transcribir", return_value="hola"):
            voz.oir_bien(object(), None)
        self.assertEqual(set(self.etapas()), {"transcripcion_local"})


class B_Claude(Base):
    def test_mide_sin_cambiar_respuesta_ni_contexto(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0, claude_json("Señor, todo en orden.\n\nDetalle.\n"), "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "_continuar", return_value=True):
            tm.nueva("voz", tm.ahora())
            resp, cerebro = pensar_mod.pensar("cómo vamos", voz=True)
        self.assertEqual((resp, cerebro), ("Señor, todo en orden.\n\nDetalle.", "claude"))
        cmd, kw = llamadas[0]
        self.assertEqual(cmd, ["claude", "-p", "cómo vamos", "--output-format", "json", "--continue",
                               "--append-system-prompt", pensar_mod.INSTRUCCION_VOZ,
                               *pensar_mod.ASISTENTE_CLAUDE])          # candados del upgrade 02
        self.assertEqual(kw["timeout"], 300)
        f = self.etapas()["claude_p"]
        self.assertEqual((f["ruta"], f["estado"]), ("claude", "exito"))

    def test_timeout(self):
        def run(cmd, **kw):
            if cmd[0] == "claude":
                raise subprocess.TimeoutExpired(cmd, 300)
            raise AssertionError
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value=None):
            tm.nueva("texto", tm.ahora())
            pensar_mod.pensar("hola")
        self.assertEqual(self.etapas()["claude_p"]["estado"], "timeout")


class C_Fallback(Base):
    def test_registra_codex_cuando_claude_falla(self):
        def run(cmd, **kw):
            if cmd[0] == "claude":
                return subprocess.CompletedProcess(cmd, 1, "You've hit your limit", "")
            pathlib.Path(cmd[cmd.index("-o") + 1]).write_text("Respuesta de respaldo, señor.")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.object(pensar_mod, "buscar_codex", return_value="/falso/codex"):
            tm.nueva("voz", tm.ahora())
            resp, cerebro = pensar_mod.pensar("hola", voz=True)
            decir_mod.decir(pensar_mod.primera_linea(resp))
        self.assertEqual((resp, cerebro), ("Respuesta de respaldo, señor.", "chatgpt"))
        e = self.etapas()
        self.assertEqual(e["claude_p"]["estado"], "error")
        self.assertEqual((e["codex_exec"]["ruta"], e["codex_exec"]["estado"]), ("codex", "exito"))
        self.assertEqual(e["total"]["ruta"], "codex")


SALIDA_OK = claude_json("Aquí sigo, señor.")      # fuera de la prueba: una de ellas rompe json.dumps


class D_Tolerancia(Base):
    def _pensar_ok(self):
        run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, SALIDA_OK, "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)):
            tm.nueva("voz", tm.ahora())
            return pensar_mod.pensar("hola", voz=True)

    def test_archivo_inservible(self):
        tm.ARCHIVO = pathlib.Path(self.dir.name)          # es carpeta: no se puede escribir
        self.assertEqual(self._pensar_ok(), ("Aquí sigo, señor.", "claude"))
        self.assertEqual(tm.leer(), [])

    def test_json_truena(self):
        with mock.patch.object(tm.json, "dumps", side_effect=RuntimeError("boom")):
            self.assertEqual(self._pensar_ok(), ("Aquí sigo, señor.", "claude"))
            decir_mod.decir("Aquí sigo, señor.")
            voz.procesar("qué hora es")

    def test_lineas_danadas(self):
        self.archivo.write_text('basura\n{"etapa": "total"}\n')
        tm.nueva("voz"); tm.registrar("total", 10)
        self.assertEqual(len(tm.leer()), 1)


class E_Privacidad(Base):
    def test_no_guarda_contenido(self):
        secreto_p, secreto_r = "PREGUNTA_SECRETA_7731", "RESPUESTA_SECRETA_9912"
        run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, claude_json(secreto_r), "")
        with mock.patch.object(pensar_mod, "subprocess", falso_subprocess(run)), \
             mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_SECRETA"}):
            tm.nueva("voz", tm.ahora())
            resp, _ = pensar_mod.pensar(secreto_p, voz=True)
            decir_mod.decir(resp)
        texto = self.archivo.read_text()
        for s in (secreto_p, secreto_r, "gsk_SECRETA", "INSTRUCCION", "Te están hablando"):
            self.assertNotIn(s, texto)
        for f in self.filas():
            self.assertEqual(set(f), CAMPOS)

    def test_valores_fuera_de_lista_no_pasan(self):
        tm.nueva("voz")
        tm.registrar("mi contraseña es 123", 5)
        tm.registrar("total", 5, ruta="texto libre", estado="algo raro")
        f = self.filas()
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0]["ruta"], f[0]["estado"]), (None, "error"))

    def test_id_viaja_por_entorno(self):
        tm.nueva("voz")
        id_ = os.environ["JARVIS_REQ_ID"]
        hijo = subprocess.run([sys.executable, "-c",
                               "import os; print(os.environ['JARVIS_REQ_ID'], os.environ['JARVIS_ORIGEN'])"],
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(hijo, [id_, "voz"])
        tm.terminar()
        self.assertNotIn("JARVIS_REQ_ID", os.environ)

    def test_sin_peticion_no_registra(self):
        decir_mod.decir("Sistemas en línea, señor.")       # arranque, vigía, etc.
        self.assertEqual(self.filas(), [])


class F_Regresion(Base):
    def test_comandos_rapidos(self):
        with mock.patch.object(voz, "osa") as osa, mock.patch.object(voz, "abrir_url") as abrir:
            self.assertTrue(voz.comando_rapido("Jarvis, qué hora es").startswith("Son las"))
            self.assertEqual(voz.comando_rapido("sube el volumen"), "")
            self.assertEqual(voz.comando_rapido("pausa"), "Música en pausa, señor.")
            self.assertEqual(voz.comando_rapido("abre youtube"), "Abriendo youtube.")
            abrir.assert_called_with("https://youtube.com", "personal")
            self.assertEqual(voz.comando_rapido("abre classroom"),
                             "Abriendo classroom con su cuenta de la escuela.")
            self.assertIsNone(voz.comando_rapido("cuéntame un chiste"))
            self.assertTrue(osa.called)

    def test_oido_frase(self):
        o = oido_mod.Oido.__new__(oido_mod.Oido)
        o.cola, o.sens, o.ruido, o.ultima = queue.Queue(), 3.0, None, None
        np = oido_mod.np
        for _ in range(2): o.cola.put(np.full(1600, 10, dtype=np.int16))
        for _ in range(6): o.cola.put(np.full(1600, 5000, dtype=np.int16))
        for _ in range(8): o.cola.put(np.full(1600, 10, dtype=np.int16))
        audio = o.frase(fin_silencio=0.7)
        self.assertEqual(len(audio), 1600 * (2 + 6 + 7))
        t_voz, t_ult, t_fin = o.ultima
        self.assertTrue(t_voz <= t_ult <= t_fin)

    def test_historial_formato_intacto(self):
        hist = pathlib.Path(self.dir.name) / "h.jsonl"
        with mock.patch.object(pensar_mod, "HIST", hist):
            GUARDAR_ORIGINAL("hola", "Señor.", "claude")
        self.assertEqual(set(json.loads(hist.read_text())), {"t", "fecha", "tu", "jarvis", "cerebro"})

    def test_percentiles_y_pocas_muestras(self):
        v = list(range(1, 11))
        self.assertEqual(latencia.percentil(v, 50), 5)
        self.assertEqual(latencia.percentil(v, 90), 9)
        self.assertIn("—", latencia.fila("x", [1.0, 2.0]))

    def test_jv_latencia(self):
        env = dict(os.environ, JARVIS_METRICAS=str(self.archivo))
        r = subprocess.run([str(RAIZ / "bin/jv"), "latencia"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Sin mediciones", r.stdout)
        tm.nueva("voz")
        for ms in range(100, 1200, 100):
            tm.registrar("claude_p", ms, ruta="claude")
        tm.registrar("total", 2000)
        r = subprocess.run([str(RAIZ / "bin/jv"), "latencia"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude_p", r.stdout)
        self.assertIn("pocas muestras", r.stdout)


if __name__ == "__main__":
    unittest.main()
