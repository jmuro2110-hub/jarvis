"""Pruebas del upgrade 09A (medición del recorrido real, sin cambios funcionales).
Cola real con frames sintéticos, telemetría en archivo temporal y un hijo real para el reloj entre procesos.

    uv run --python 3.11 --with numpy python -m unittest tests.test_medicion -v
"""
import json, os, pathlib, queue, subprocess, sys, tempfile, types, unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.path.insert(0, str(RAIZ / "tests"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

import telemetria as tm           # noqa: E402
import streaming as st            # noqa: E402
import oido as oido_mod           # noqa: E402
import jarvis_voz as voz          # noqa: E402
from test_barge_in import cola_con, vigia, Reloj   # noqa: E402

CAMPOS = {"fecha", "id", "origen", "etapa", "ms", "ruta", "estado", "sesion", "motivo", "modo"}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.archivo = pathlib.Path(self.dir.name) / "metricas.jsonl"
        self.p = mock.patch.object(tm, "ARCHIVO", self.archivo)
        self.p.start()
        tm.terminar()

    def tearDown(self):
        tm.terminar()
        self.p.stop()
        self.dir.cleanup()

    def filas(self, etapa=None):
        if not self.archivo.exists():
            return []
        f = [json.loads(x) for x in self.archivo.read_text().splitlines()]
        return [x for x in f if etapa is None or x["etapa"] == etapa]


def oido_falso(cola):
    o = oido_mod.Oido.__new__(oido_mod.Oido)        # sin micrófono
    o.cola, o.sens, o.ruido, o.ultima = cola, 3.0, None, None
    o.atraso, o.fin_habla = 0, None
    return o


class FinHablaEnOido(unittest.TestCase):
    def test_estima_con_cola_y_silencio(self):
        # 5 de silencio, 8 de voz, 7 de silencio (cierra a 0.7 s) y 4 frames más que siguen en la cola
        o = oido_falso(cola_con(("s", 5), ("v", 8), ("s", 7), ("s", 4)))
        audio = o.frase(fin_silencio=0.7)
        self.assertIsNotNone(audio)
        self.assertEqual(o.atraso, 4)
        t_cierre = o.ultima[2]
        self.assertEqual(o.fin_habla, t_cierre - (4 + 7) * oido_mod.BLOQUE_NS)
        self.assertEqual(o.cola.qsize(), 4)              # la captura no cambió: el resto sigue en la cola

    def test_sin_atraso(self):
        o = oido_falso(cola_con(("s", 5), ("v", 8), ("s", 7)))
        o.frase(fin_silencio=0.7)
        self.assertEqual(o.atraso, 0)
        self.assertEqual(o.ultima[2] - o.fin_habla, 7 * oido_mod.BLOQUE_NS)


class FinOrdenEnVigia(unittest.TestCase):
    def test_estima_fin_de_la_orden(self):
        # cierra con 5 frames de silencio; queda 1 frame sacado sin revisar y 0 en la cola
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), reloj=Reloj(100.0))
        det = v.revisar("Una órbita es el camino que sigue un objeto.", 0.0)
        self.assertEqual(det.tipo, "callar")
        self.assertAlmostEqual(det.t_fin_orden, 100.0 - (5 + 1) * 0.1)

    def test_detecciones_iguales_que_antes(self):
        for texto, tipo in (("Jarvis, espera", "espera"), ("Jarvis", "solo_jarvis"),
                            ("Jarvis, mejor abre Spotify", "orden")):
            det = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), texto).revisar("Otra cosa.", 0.0)
            self.assertEqual(det.tipo, tipo)


class MedirFrase(Base):
    def test_metricas_viejas_y_nuevas(self):
        o = oido_falso(cola_con(("s", 5), ("v", 8), ("s", 13), ("s", 3)))
        o.frase(fin_silencio=1.3)
        tm.nueva("voz")
        voz.medir_frase(o, "seguimiento")
        t_voz, t_ultima, t_fin = o.ultima
        captura = self.filas("captura_frase")[0]["ms"]
        self.assertAlmostEqual(captura, round((t_fin - t_voz) / 1e6, 1))     # significado anterior intacto
        self.assertEqual(self.filas("cola_atraso")[0]["ms"], 300)
        self.assertAlmostEqual(self.filas("fin_habla_a_cierre")[0]["ms"], (3 + 13) * 100, delta=0.2)
        self.assertEqual(tm._actual["t_habla"], o.fin_habla)
        self.assertEqual(tm._actual["modo"], "seguimiento")

    def test_oido_sin_estimacion_no_truena(self):
        o = types.SimpleNamespace(ultima=(1, 2, 3))
        tm.nueva("voz")
        voz.medir_frase(o, "reposo")
        self.assertEqual(self.filas("fin_habla_a_cierre"), [])
        self.assertEqual(len(self.filas("captura_frase")), 1)

    def test_modos_de_cada_llamada(self):
        src = (RAIZ / "voz/jarvis_voz.py").read_text()
        for m in ('medir_frase(oido, "reposo")', 'medir_frase(oido, "seguimiento")',
                  'medir_frase(oido, "atajo" if vaciar else "tras_tin")', 'tm.modo("barge")'):
            self.assertIn(m, src)
        self.assertNotIn("medir_frase(oido)\n", src)


class PrimeraVoz(Base):
    def test_una_vez_por_frase_con_modo(self):
        tm.nueva("voz")
        tm.modo("reposo")
        tm.fin_habla(tm.ahora() - 500_000_000)
        tm.voz_preparando(); tm.voz_empieza("say_sistema")
        tm.voz_preparando(); tm.voz_empieza("say_sistema")      # segunda voz del mismo turno: no cuenta
        f = self.filas("fin_habla_a_voz")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["modo"], "reposo")
        self.assertGreaterEqual(f[0]["ms"], 500)
        self.assertEqual(self.filas("voz_lanzamiento"), [])       # en el proceso de voz no hay hijo

    def test_nueva_frase_vuelve_a_medir(self):
        tm.nueva("voz"); tm.fin_habla(tm.ahora())
        tm.primera_voz()
        tm.fin_habla(tm.ahora())                                  # siguiente frase (p. ej. tras «Jarvis»)
        tm.primera_voz()
        self.assertEqual(len(self.filas("fin_habla_a_voz")), 2)

    def test_sin_frase_no_mide(self):
        tm.nueva("voz")
        tm.primera_voz()
        self.assertEqual(self.filas("fin_habla_a_voz"), [])

    def test_modo_y_motivo_cerrados(self):
        tm.nueva("voz")
        tm.modo("lo que dijo JP")
        tm.registrar("fin_habla_a_voz", 10, extra={"modo": "texto libre", "motivo": "otra cosa"})
        f = self.filas("fin_habla_a_voz")[0]
        self.assertNotIn("modo", f)
        self.assertNotIn("motivo", f)
        self.assertNotIn("modo", tm._actual)

    def test_reclamar_evita_doble_medida(self):
        tm.nueva("voz"); tm.fin_habla(tm.ahora())
        self.assertTrue(tm.reclamar_primera_voz())
        self.assertFalse(tm.reclamar_primera_voz())
        tm.primera_voz()                                          # el padre ya no la mide
        self.assertEqual(self.filas("fin_habla_a_voz"), [])


class HijoDeVoz(Base):
    def entorno(self, **kw):
        base = {"JARVIS_REQ_ID": "abc123", "JARVIS_ORIGEN": "voz"}
        base.update(kw)
        return mock.patch.dict(os.environ, base)

    def test_primera_en_hijo(self):
        t = tm.ahora()
        with self.entorno(JARVIS_VOZ_PRIMERA="1", JARVIS_T_HABLA=str(t - 2_000_000_000), JARVIS_MODO="tras_tin",
                          JARVIS_T_LANZADO=str(t - 300_000_000)):
            tm.desde_entorno(con_total=False)
            tm.voz_preparando(); tm.voz_empieza("say_voz")
        lz, fv = self.filas("voz_lanzamiento"), self.filas("fin_habla_a_voz")
        self.assertEqual((len(lz), lz[0]["motivo"]), (1, "say_voz"))
        self.assertGreaterEqual(lz[0]["ms"], 300)
        self.assertEqual((len(fv), fv[0]["modo"], fv[0]["id"]), (1, "tras_tin", "abc123"))
        self.assertGreaterEqual(fv[0]["ms"], 2000)

    def test_pedazo_siguiente_no_mide_primera(self):
        t = tm.ahora()
        with self.entorno(JARVIS_T_HABLA=str(t), JARVIS_T_LANZADO=str(t)):
            os.environ.pop("JARVIS_VOZ_PRIMERA", None)
            tm.desde_entorno(con_total=False)
            tm.voz_preparando(); tm.voz_empieza("say_sistema")
        self.assertEqual(self.filas("fin_habla_a_voz"), [])
        self.assertEqual(len(self.filas("voz_lanzamiento")), 1)

    def test_jv_decir_desde_claude_no_mide(self):
        with self.entorno(JARVIS_T_HABLA=str(tm.ahora())):
            for k in ("JARVIS_VOZ_PRIMERA", "JARVIS_T_LANZADO"):
                os.environ.pop(k, None)
            tm.desde_entorno(con_total=False)
            tm.voz_preparando(); tm.voz_empieza("say_sistema")
        self.assertEqual(self.filas("fin_habla_a_voz") + self.filas("voz_lanzamiento"), [])

    def test_reloj_compartido_entre_procesos(self):
        # perf_counter_ns del intérprete de la voz vale en el hijo decir.py (mismo sys.executable)
        a = tm.ahora()
        b = int(subprocess.run([sys.executable, "-I", "-c", "import time; print(time.perf_counter_ns())"],
                               capture_output=True, text=True, timeout=30).stdout)
        c = tm.ahora()
        self.assertTrue(a < b < c, (a, b, c))


class HabladorMarcaPrimera(Base):
    def test_solo_el_primer_pedazo(self):
        vistos = []

        class P:
            def poll(self):
                return 0

        def lanzar(texto):
            vistos.append(os.environ.get("JARVIS_VOZ_PRIMERA"))
            return P()
        tm.nueva("voz"); tm.fin_habla(tm.ahora())
        h = st.Hablador(lanzar=lanzar)
        h.decir("Primera frase.")
        h.decir("Segunda frase.")
        h.esperar(timeout=5)
        self.assertEqual(vistos, ["1", None])
        self.assertNotIn("JARVIS_VOZ_PRIMERA", os.environ)

    def test_sin_frase_no_marca(self):
        vistos = []

        class P:
            def poll(self):
                return 0

        def lanzar(texto):
            vistos.append(os.environ.get("JARVIS_VOZ_PRIMERA"))
            return P()
        tm.nueva("voz")
        h = st.Hablador(lanzar=lanzar)
        h.decir("Hola.")
        h.esperar(timeout=5)
        self.assertEqual(vistos, [None])

    def test_lanzar_decir_pasa_hora_de_lanzamiento(self):
        with mock.patch.object(st.subprocess, "Popen") as popen:
            st.lanzar_decir("Hola.")
        env = popen.call_args.kwargs["env"]
        self.assertTrue(env["JARVIS_T_LANZADO"].isdigit())
        st.VOCES.clear()


class BargeFinAParada(Base):
    def test_registra(self):
        det = types.SimpleNamespace(t_voz=10.0, t_parada=12.5, t_fin_orden=11.0)
        h = types.SimpleNamespace(interrumpido=True, interrupcion=det)
        conv = types.SimpleNamespace(interrupcion=None)
        tm.nueva("voz")
        voz._anotar_interrupcion(h, conv)
        self.assertEqual(self.filas("barge_parada")[0]["ms"], 2500)        # significado anterior intacto
        self.assertEqual(self.filas("barge_fin_a_parada")[0]["ms"], 1500)

    def test_turno_de_barge_conserva_su_peticion(self):
        src = (RAIZ / "voz/jarvis_voz.py").read_text()
        bloque = src[src.index("accion, x = atender_interrupcion"):src.index('if accion == "cerrar"')]
        self.assertIn('if accion != "turno":', bloque)


class SinContenido(Base):
    def test_filas_solo_con_campos_fijos(self):
        t = tm.ahora()
        with mock.patch.dict(os.environ, {"JARVIS_REQ_ID": "x1", "JARVIS_VOZ_PRIMERA": "1",
                                          "JARVIS_T_HABLA": str(t), "JARVIS_MODO": "reposo",
                                          "JARVIS_T_LANZADO": str(t)}):
            tm.desde_entorno(con_total=False)
            tm.voz_preparando(); tm.voz_empieza("eleven")
        tm.terminar()
        tm.nueva("voz"); tm.modo("barge"); tm.fin_habla(t); tm.primera_voz()
        tm.registrar("cola_atraso", 300); tm.registrar("barge_fin_a_parada", 900)
        tm.registrar("tts_descarga", 700, estado="timeout")
        for f in self.filas():
            self.assertLessEqual(set(f), CAMPOS, f)
        texto = self.archivo.read_text()
        for prohibido in ("Hola", "Jarvis,", "señor"):
            self.assertNotIn(prohibido, texto)

    def test_etapas_nuevas_registradas(self):
        for e in ("cola_atraso", "fin_habla_a_cierre", "fin_habla_a_voz", "voz_lanzamiento", "tts_descarga",
                  "barge_fin_a_parada"):
            self.assertIn(e, tm.ETAPAS)

    def test_terminar_limpia_entorno(self):
        tm.nueva("voz"); tm.modo("reposo"); tm.fin_habla(tm.ahora())
        tm.terminar()
        for k in ("JARVIS_T_HABLA", "JARVIS_MODO", "JARVIS_REQ_ID"):
            self.assertNotIn(k, os.environ)


class ReporteLatencia(Base):
    def test_muestra_recorrido(self):
        tm.nueva("voz"); tm.modo("seguimiento"); tm.ruta("claude"); tm.fin_habla(tm.ahora()); tm.primera_voz()
        with mock.patch.dict(os.environ, {"JARVIS_METRICAS": str(self.archivo)}):
            r = subprocess.run([sys.executable, str(RAIZ / "bin/latencia.py")], capture_output=True, text=True,
                               timeout=30, env=dict(os.environ))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("primera voz útil", r.stdout)
        self.assertIn("seguimiento · claude", r.stdout)


if __name__ == "__main__":
    unittest.main()
