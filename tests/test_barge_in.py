"""Pruebas del upgrade 06 (barge-in, voz al `result`, contexto personal).
Vigía con frames sintéticos reales y una cola real; cancelación con procesos reales en su propio grupo
(incluido un "say" nieto); conversaciones con reloj, oído, Groq, Whisper y Claude simulados.

    uv run --python 3.11 --with numpy python -m unittest tests.test_barge_in -v
"""
import functools, json, os, pathlib, queue, signal, subprocess, sys, tempfile, time, types, unittest
from unittest import mock
import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.path.insert(0, str(RAIZ / "tests"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

import telemetria as tm           # noqa: E402
import streaming as st            # noqa: E402
import pensar as pensar_mod       # noqa: E402
import sesiones, comun, politica, guardia   # noqa: E402
import conversacion as cv         # noqa: E402
import interrupciones as it       # noqa: E402
import jarvis_voz as voz          # noqa: E402
import oido as oido_mod           # noqa: E402
from test_streaming import (FalsoClaude, FalsaVoz, respuesta_simple, init, msg_start, bloque, delta, stop,  # noqa: E402
                            result, SID)

SILENCIO = (np.random.RandomState(1).randn(1600) * 40).astype(np.int16)
VOZ = (np.sin(np.arange(1600) / 5.0) * 4000).astype(np.int16)


def cola_con(*partes):
    """partes: ("s", n) silencio, ("v", n) voz (frames de 100 ms)."""
    q = queue.Queue()
    for tipo, n in partes:
        for _ in range(n):
            q.put((VOZ if tipo == "v" else SILENCIO).copy())
    return q


class ColaDiferida(queue.Queue):
    """Como el micrófono: los frames "llegan" a partir de `retraso` s después de la primera lectura."""
    def __init__(self, frames, retraso=0.4):
        super().__init__()
        for f in frames:
            self.put(f)
        self.retraso, self.t0 = retraso, None

    def get_nowait(self):
        if self.t0 is None:
            self.t0 = time.perf_counter()
        if time.perf_counter() - self.t0 < self.retraso:
            raise queue.Empty
        return super().get_nowait()


class Reloj:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


def vigia(q, texto="Jarvis, cállate", reloj=None, registrar=None):
    llamadas = []
    def transcribir(modelo, audio, idioma="es", **kw):
        llamadas.append(len(audio))
        if isinstance(texto, Exception):
            raise texto
        return texto
    v = it.Vigia(q, "base", transcribir=transcribir, reloj=reloj or Reloj(), registrar=registrar)
    v.llamadas = llamadas
    return v


# ---------------------------------------------------------------- detección (T1–T11, T49, T52)
class T01_IdleIgual(unittest.TestCase):
    def test_idle_no_usa_vigia(self):
        src = (RAIZ / "voz/jarvis_voz.py").read_text()
        idle = src[src.index("def escuchar_una"):src.index("def main")]
        self.assertNotIn("Vigia", idle)
        self.assertIsNone(voz._vigia())                      # sin oído (fuera de main) no hay vigía


class T02_ActivacionEnSpeaking(unittest.TestCase):
    def test_confirmada(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)))
        det = v.revisar("Una órbita es el camino que sigue un objeto.", 0.0)
        self.assertEqual((det.tipo, det.resto), ("callar", ""))
        self.assertEqual(len(v.llamadas), 1)

    def test_tipos(self):
        for texto, tipo, resto in (("Jarvis, espera", "espera", ""), ("Jarvis", "solo_jarvis", ""),
                                   ("Jarvis, no, mejor dime tres estrellas", "orden", "dime tres estrellas"),
                                   ("Oye Jarvis, deja de hablar", "callar", ""),
                                   ("Jarvis, mejor abre Spotify", "orden", "abre Spotify")):
            det = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), texto).revisar("Hablo de otra cosa.", 0.0)
            self.assertEqual((det.tipo, det.resto), (tipo, resto), texto)


class T03_RuidoNoInterrumpe(unittest.TestCase):
    def test_ruido_bajo_ni_transcribe(self):
        v = vigia(cola_con(("s", 40)))
        self.assertIsNone(v.revisar("Algo.", 0.0))
        self.assertEqual(v.llamadas, [])

    def test_ruidito_corto(self):
        v = vigia(cola_con(("s", 5), ("v", 2), ("s", 8)))
        self.assertIsNone(v.revisar("Algo.", 0.0))
        self.assertEqual(v.llamadas, [])

    def test_voz_sin_jarvis(self):
        regs = []
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "pon la música más fuerte",
                  registrar=lambda *a, **k: regs.append(k["extra"]["motivo"]))
        self.assertIsNone(v.revisar("Algo distinto.", 0.0))
        self.assertEqual(regs, ["sin_jarvis"])


class T04_SuPropiaVoz(unittest.TestCase):
    def test_eco_por_texto(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "Jarvis está listo para ayudarle")
        self.assertIsNone(v.revisar("Señor, Jarvis está listo para ayudarle cuando quiera.", 0.0))

    def test_pedazo_con_jarvis_exige_orden(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "Jarvis")
        self.assertIsNone(v.revisar("Soy Jarvis, su asistente.", 0.0))
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "Jarvis, cállate")
        self.assertEqual(v.revisar("Soy Jarvis, su asistente.", 0.0).tipo, "callar")

    def test_ignora_inicio_del_pedazo(self):
        r = Reloj(100.0)
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), reloj=r)
        self.assertIsNone(v.revisar("Algo.", 99.9))                      # a 0.1 s de empezar el pedazo
        self.assertEqual(v.llamadas, [])


class T05_Ambiguo(unittest.TestCase):
    def test_jarvis_a_media_frase(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "y luego el señor jarvis dijo que sí")
        self.assertIsNone(v.revisar("Algo.", 0.0))

    def test_fantasma(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), "Gracias por ver el video")
        self.assertIsNone(v.revisar("Algo.", 0.0))


class T06_UnaInferenciaALaVez(unittest.TestCase):
    def test_ocupado(self):
        q = cola_con(("s", 5), ("v", 8), ("s", 6))
        v = vigia(q)
        v.ocupado = True
        self.assertIsNone(v.revisar("Algo.", 0.0))
        self.assertEqual(q.qsize(), 19)                                    # ni siquiera consumió la cola

    def test_un_candidato_por_segmento(self):
        v = vigia(cola_con(("s", 5), ("v", 40), ("s", 6)), "pon música")   # voz continua: ventanas de 2.5 s
        v.revisar("Algo.", 0.0)
        self.assertLessEqual(len(v.llamadas), 2)
        self.assertTrue(all(n <= 30 * 1600 for n in v.llamadas))          # buffer máximo ~3 s


class T49_AntiEco(unittest.TestCase):
    def test_mayoria_de_palabras(self):
        self.assertEqual(it.Vigia(None, None)._filtrar("Jarvis, la gravedad atrae", "La gravedad atrae masas.",
                                                       None, False, 0)[0], "eco")
        self.assertEqual(it.Vigia(None, None)._filtrar("Jarvis, dime la hora", "La gravedad atrae masas.",
                                                       None, False, 0)[0], "confirmado")


class T52_PisoDeRuidoIntacto(unittest.TestCase):
    def test_oido_ruido_no_cambia(self):
        o = oido_mod.Oido.__new__(oido_mod.Oido)
        o.ruido = 123.0
        o.cola = cola_con(("v", 30), ("s", 6))
        v = vigia(o.cola, "pon música")
        v.revisar("Algo.", 0.0)
        self.assertEqual(o.ruido, 123.0)
        self.assertIsNotNone(v.ruido)


class T10_FalloWhisper(unittest.TestCase):
    def test_no_rompe_la_voz(self):
        v = vigia(cola_con(("s", 5), ("v", 8), ("s", 6)), RuntimeError("whisper"))
        self.assertIsNone(v.revisar("Algo.", 0.0))
        self.assertFalse(v.ocupado)


# ---------------------------------------------------------------- cancelación con procesos reales
NIETO = r'''
import os, subprocess, sys, time
p = subprocess.Popen(["/bin/sleep", "30"])          # el "say"
open(sys.argv[1], "w").write(str(p.pid))
if len(sys.argv) > 2:                               # toma voz.lock como decir.py
    import fcntl
    f = open(sys.argv[2], "w"); fcntl.flock(f, fcntl.LOCK_EX)
p.wait()
'''


def vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:                                            # zombi = muerto
        return "Z" not in subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
    except Exception:
        return True


class Cancelacion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lanzar(self, lock=None):
        pidf = self.d / f"nieto{time.perf_counter_ns()}"
        args = [sys.executable, "-c", NIETO, str(pidf)] + ([str(lock)] if lock else [])
        p = subprocess.Popen(args, start_new_session=True)
        for _ in range(100):
            if pidf.exists() and pidf.read_text():
                break
            time.sleep(0.02)
        p.nieto = int(pidf.read_text())
        return p


class T47_SinSayHuerfano(Cancelacion):
    def test_mata_al_nieto(self):
        p = self.lanzar()
        h = st.Hablador(lanzar=lambda t: p)
        h.decir("hola")
        h.cancelar()
        time.sleep(0.1)
        self.assertFalse(vivo(p.nieto))                                    # el "say" no quedó hablando
        self.assertIsNotNone(p.returncode)

    def test_terminate_simple_si_dejaria_huerfano(self):
        """Control: así cancelaba el 05 (terminate al padre) y el nieto seguía vivo."""
        p = self.lanzar()
        p.terminate(); p.wait()
        time.sleep(0.1)
        self.assertTrue(vivo(p.nieto))
        os.kill(p.nieto, signal.SIGKILL)


class T15_16_SoloSuVoz(Cancelacion):
    def test_no_toca_otros_procesos(self):
        spotify = subprocess.Popen(["/bin/sleep", "30"])                  # otro audio (Spotify, el tin…)
        otra_voz = self.lanzar()                                          # la voz de otra petición
        p = self.lanzar()
        h = st.Hablador(lanzar=lambda t: p)
        h.decir("hola"); h.cancelar()
        self.assertIsNone(spotify.poll())
        self.assertIsNone(otra_voz.poll())
        self.assertTrue(vivo(otra_voz.nieto))
        for q in (spotify, otra_voz):
            os.killpg(os.getpgid(q.pid), signal.SIGKILL) if q is otra_voz else q.kill()
            q.wait()

    def test_nunca_mata_el_grupo_de_jarvis(self):
        p = subprocess.Popen(["/bin/sleep", "30"])                        # MISMO grupo que este proceso
        st.matar_grupo(p)
        self.assertIsNotNone(p.returncode)                                 # murió él, y seguimos vivos


class T17_VozLockLibre(Cancelacion):
    def test_flock_se_suelta(self):
        import fcntl
        lock = self.d / "voz.lock"
        p = self.lanzar(lock)
        time.sleep(0.2)
        h = st.Hablador(lanzar=lambda t: p); h.decir("x"); h.cancelar()
        with open(lock, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)                 # no lanza: quedó libre


class T18_19_20_Idempotente(Cancelacion):
    def test_cancelar_dos_veces(self):
        p = self.lanzar()
        h = st.Hablador(lanzar=lambda t: p); h.decir("x")
        h.cancelar(); h.cancelar()
        self.assertFalse(vivo(p.nieto))

    def test_interrumpir_justo_al_terminar(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True); p.wait()
        h = st.Hablador(lanzar=lambda t: p); h.decir("x")
        h.interrumpir(it.Interrupcion("espera", "", None, False, 0))
        h.interrumpir(it.Interrupcion("callar", "", None, False, 0))       # una segunda casi simultánea
        self.assertTrue(h.interrumpido)
        self.assertIsNone(h.proc)
        h.decir("más"); h.tick()
        self.assertEqual(h.cola, [])                                       # nada más de esa respuesta

    def test_tras_error_de_voz(self):
        p = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(1)"], start_new_session=True); p.wait()
        h = st.Hablador(lanzar=lambda t: p); h.decir("x"); h.tick()
        self.assertTrue(h.error)
        h.cancelar(); h.cancelar()


class T09_DosActivaciones(unittest.TestCase):
    def test_una_sola_interrupcion(self):
        voz_f = FalsaVoz(seg=5)
        dets = [it.Interrupcion("orden", "uno", None, False, 0), it.Interrupcion("orden", "dos", None, False, 0)]
        class V:
            def revisar(self, pedazo, t):
                return dets.pop(0) if dets else None
        h = st.Hablador(lanzar=voz_f, vigia=V())
        h.decir("hola"); h.tick(); h.tick(); h.tick()
        self.assertEqual(h.interrupcion.resto, "uno")
        self.assertEqual(len(dets), 1)                                    # el vigía no se vuelve a consultar
        h.cancelar()


# ---------------------------------------------------------------- flujo conversacional
class Audio:
    def __init__(self, texto):
        self.texto = texto


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.casa = pathlib.Path(self.tmp.name)
        (self.casa / "memoria").mkdir()
        (self.casa / "memoria/pendientes.md").write_text("# Pendientes\n")
        self.reloj = Reloj(1000.0)
        self.dicho, self.pensado, self.groq, self.estados, self.osa = [], [], [], [], []
        self.en_vuelo, self.max_vuelo = 0, 0
        self.det = {}                      # texto pensado → Interrupcion que ocurre mientras se habla
        self.parches = [
            mock.patch.object(tm, "ARCHIVO", self.casa / "metricas.jsonl"),
            mock.patch.object(tm, "CONV_ARCHIVO", self.casa / "conversaciones.jsonl"),
            mock.patch.object(comun, "JARVIS", self.casa),
            mock.patch.object(voz, "CASA", self.casa),
            mock.patch.object(voz, "CERRAR", self.casa / "cerrar_conversacion"),
            mock.patch.object(voz, "DISPARADOR", self.casa / "escuchar"),
            mock.patch.object(voz, "estado", lambda n, t="": self.estados.append(n)),
            mock.patch.object(voz, "log"), mock.patch.object(voz, "subprocess"),
            mock.patch.object(voz, "osa", lambda s: (self.osa.append(s), subprocess.CompletedProcess([], 0, "", ""))[1]),
            mock.patch.object(voz, "decir", lambda t, forzar=False: (self.dicho.append(t), True)[1]),
            mock.patch.object(voz, "pensar", self._pensar),
            mock.patch.object(voz, "oir_bien", lambda a, p: (self.groq.append(a.texto), a.texto)[1]),
            mock.patch.object(voz, "transcribir", lambda m, a, *x, **k: a.texto),
            mock.patch.object(voz, "config", return_value=dict(comun.DEFAULTS)),
        ]
        for p in self.parches:
            p.start()
        voz.subprocess.run.return_value = subprocess.CompletedProcess([], 0, "", "")
        tm.terminar()
        self.conv = cv.Conversacion(reloj=self.reloj, registrar=tm.conversacion)

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def _pensar(self, texto, voz=False, origen="personal", hablador=None, sin_herramientas=False):
        self.en_vuelo += 1; self.max_vuelo = max(self.max_vuelo, self.en_vuelo)
        self.pensado.append(texto)
        self.reloj.t += 2
        resp = f"Respuesta a {texto}, señor."
        if hablador is not None:
            hablador.lanzar = FalsaVoz(seg=0.05)
            hablador.decir(resp)                       # "hablar al result"
            if texto in self.det:
                hablador.interrumpir(self.det.pop(texto))   # el vigía la oyó mientras sonaba
        self.en_vuelo -= 1
        return resp, "claude"

    def correr(self, primera, *guion):
        o = OidoGuion(("di", primera), *guion, reloj=self.reloj)
        voz.escuchar_una(o, "base", "small", self.conv)
        return o

    def eventos(self, tipo=None):
        f = self.casa / "conversaciones.jsonl"
        filas = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
        return [x for x in filas if tipo is None or x["evento"] == tipo]

    def cierre(self):
        return [e["motivo"] for e in self.eventos("cierre")]


class OidoGuion:
    def __init__(self, *guion, reloj):
        self.guion, self.reloj = list(guion), reloj
        self.ultima = (0, int(2e9), int(2e9) + 1)
        self.cola = queue.Queue()
        self.vaciados = 0

    def vaciar(self):
        self.vaciados += 1

    def frase(self, espera_inicio=None, **kw):
        if not self.guion:
            self.reloj.t += espera_inicio or 0
            return None
        paso = self.guion.pop(0)
        if paso[0] == "calla":
            self.reloj.t += paso[1]
            return None
        self.reloj.t += 1
        return Audio(paso[1])


def det(tipo, resto="", cortado=False, texto=None):
    d = it.Interrupcion(tipo, resto, Audio(texto if texto is not None else f"Jarvis, {resto}"), cortado, 0.0)
    return d


class T12_Callate(Base):
    def test_detiene_y_cierra(self):
        self.det["explícame qué es un agujero negro"] = det("callar")
        self.correr("Jarvis, explícame qué es un agujero negro", ("di", "abre spotify"))
        self.assertEqual(self.cierre(), ["callar"])
        self.assertEqual(self.pensado, ["explícame qué es un agujero negro"])
        self.assertEqual(self.eventos("cierre")[0]["turno"], 1)              # «cállate» no cuenta turno


class T13_Espera(Base):
    def test_abre_follow_up(self):
        self.det["explícame la relatividad"] = det("espera")
        self.correr("Jarvis, explícame la relatividad", ("di", "me lo explicas más fácil"))
        self.assertEqual(self.pensado, ["explícame la relatividad", "me lo explicas más fácil"])
        self.assertEqual(len(self.eventos("activada")), 1)
        self.assertIn("seguimiento", self.estados)


class T14_NoMejor(Base):
    def test_procesa_la_nueva(self):
        self.det["dime tres planetas"] = det("orden", "dime tres estrellas", texto="Jarvis, no, mejor dime tres estrellas")
        self.correr("Jarvis, dime tres planetas")
        self.assertEqual(self.pensado, ["dime tres planetas", "dime tres estrellas"])
        self.assertEqual(self.groq.count("Jarvis, no, mejor dime tres estrellas"), 1)
        self.assertEqual(self.eventos("cierre")[0]["turno"], 2)              # la corrección sí cuenta

    def test_rapido_tras_interrupcion(self):
        self.det["cuéntame algo"] = det("orden", "ponle pausa", texto="Jarvis, ponle pausa")
        self.correr("Jarvis, cuéntame algo")
        self.assertIn('tell application "Spotify" to pause', self.osa)
        self.assertEqual(self.pensado, ["cuéntame algo"])

    def test_cierre_manual_dentro(self):
        self.det["cuéntame algo"] = det("orden", "eso es todo", texto="Jarvis, eso es todo")
        self.correr("Jarvis, cuéntame algo", ("di", "abre spotify"))
        self.assertEqual(self.cierre(), ["manual"])


class T07_SoloJarvis(Base):
    def test_espera_la_orden_sin_vaciar(self):
        self.det["cuéntame algo"] = det("solo_jarvis", texto="Jarvis")
        o = self.correr("Jarvis, cuéntame algo", ("di", "dime la capital de Francia"))
        self.assertEqual(self.pensado, ["cuéntame algo", "dime la capital de Francia"])

    def test_sin_orden_queda_en_follow_up(self):
        self.det["cuéntame algo"] = det("solo_jarvis", texto="Jarvis")
        self.correr("Jarvis, cuéntame algo", ("calla", 6), ("calla", 15))
        self.assertEqual(self.pensado, ["cuéntame algo"])
        self.assertEqual(self.cierre(), ["timeout"])                        # no inventó nada


class T08_SinDuplicar(Base):
    def test_una_sola_transcripcion_y_un_turno(self):
        self.det["dime tres planetas"] = det("orden", "dime tres estrellas", texto="Jarvis, no, mejor dime tres estrellas")
        self.correr("Jarvis, dime tres planetas")
        self.assertEqual(len(self.groq), 2)                                   # la orden inicial + la corrección
        self.assertEqual(self.pensado.count("dime tres estrellas"), 1)

    def test_ventana_cortada_junta_audio_una_vez(self):
        o = OidoGuion(reloj=self.reloj)
        o.guion = [("di", "")]
        d = it.Interrupcion("orden", "dime", np.zeros(1600, np.float32), True, 0.0)
        o.frase = lambda **kw: np.ones(800, np.float32)
        llamadas = []
        with mock.patch.object(voz, "oir_bien", lambda a, p: (llamadas.append(len(a)), "Jarvis, dime la hora")[1]):
            r = voz.atender_interrupcion(o, "small", d)
        self.assertEqual(llamadas, [2400])
        self.assertEqual(r, ("turno", "dime la hora"))


class T11_FalloGroq(Base):
    def test_fallback_local(self):
        self.parches[12].stop()
        try:
            with mock.patch("comun.secretos", return_value={"GROQ_API_KEY": "x"}), \
                 mock.patch.object(voz, "transcribir_nube", return_value=None), \
                 mock.patch.object(voz, "transcribir", return_value="dime la hora"):
                r = voz.atender_interrupcion(OidoGuion(reloj=self.reloj), "small",
                                             it.Interrupcion("orden", "x", np.zeros(10), False, 0.0))
        finally:
            self.parches[12].start()
        self.assertEqual(r, ("turno", "dime la hora"))

    def test_sin_texto_no_inventa(self):
        with mock.patch.object(voz, "oir_bien", return_value=""):
            r = voz.atender_interrupcion(OidoGuion(reloj=self.reloj), "small",
                                         it.Interrupcion("orden", "abre spotify", np.zeros(10), False, 0.0))
        self.assertEqual(r, ("turno", "abre spotify"))                       # el borrador de base, verificado
        with mock.patch.object(voz, "oir_bien", return_value=""):
            r = voz.atender_interrupcion(OidoGuion(reloj=self.reloj), "small",
                                         it.Interrupcion("orden", "", np.zeros(10), False, 0.0))
        self.assertEqual(r, ("seguimiento", None))


class T21_22_23_Contexto(Base):
    def test_nunca_dos_consultas_ni_repite(self):
        self.det["dime tres planetas"] = det("orden", "dime tres estrellas")
        self.correr("Jarvis, dime tres planetas")
        self.assertEqual(self.max_vuelo, 1)                                   # nunca dos a la vez
        self.assertEqual(self.pensado, ["dime tres planetas", "dime tres estrellas"])   # la 1.ª no se repite

    def test_sesion_personal_se_conserva(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sesiones, "DIR", pathlib.Path(d)):
            sesiones.guardar("personal", SID, nueva=True)
            self.det["dime tres planetas"] = det("espera")
            self.correr("Jarvis, dime tres planetas", ("calla", 15))
            self.assertEqual(sesiones.vigente("personal"), SID)


class T27_Limites(Base):
    def test_espera_y_callar_no_cuentan(self):
        self.det["uno"] = det("espera")
        self.correr("Jarvis, uno", ("di", "dos"), ("calla", 15))
        self.assertEqual(self.eventos("cierre")[0]["turno"], 2)

    def test_correccion_en_el_tope_abre_otra(self):
        self.det["cinco"] = det("orden", "seis")
        self.correr("Jarvis, uno", ("di", "dos"), ("di", "tres"), ("di", "cuatro"), ("di", "cinco"), ("calla", 15))
        self.assertEqual(self.pensado[-1], "seis")
        self.assertEqual(len(self.eventos("activada")), 2)
        self.assertEqual(self.cierre()[0], "turnos")


class TelemetriaEspera(Base):
    def test_barge_tipo_espera_se_registra(self):
        """Prueba física B: «espera» no dejaba fila de barge_tipo (la petición ya estaba cerrada)."""
        self.det["uno"] = det("espera")
        self.correr("Jarvis, uno", ("calla", 15))
        filas = [json.loads(l) for l in (self.casa / "metricas.jsonl").read_text().splitlines()]
        self.assertIn("espera", [f.get("motivo") for f in filas if f["etapa"] == "barge_tipo"])


class T28_Hud(Base):
    def test_estados(self):
        self.det["uno"] = det("espera")
        self.correr("Jarvis, uno", ("calla", 15))
        self.assertIn("seguimiento", self.estados)
        self.assertEqual(self.estados[-1], "listo")


class T48_EstadoTrasCancelar(Base):
    def test_no_queda_hablando(self):
        self.parches[6].stop()
        try:
            with mock.patch.object(comun, "CASA", self.casa):
                (self.casa / "estado.json").write_text('{"estado": "hablando"}')   # decir.py murió sin limpiar
                self.det["uno"] = det("espera")
                o = OidoGuion(("di", "Jarvis, uno"), reloj=self.reloj)
                fuera = []
                real = voz.esperar_seguimiento
                def mira(oido, preciso, conv):
                    fuera.append(voz.otra_voz(time.time() + 60))
                    return real(oido, preciso, conv)
                with mock.patch.object(voz, "esperar_seguimiento", mira):
                    voz.escuchar_una(o, "base", "small", self.conv)
        finally:
            self.parches[6].start()
        self.assertEqual(fuera, [False])                                       # la siguiente pregunta no se tira


class T29_BargeApagado(Base):
    def test_sin_vigia(self):
        voz._BARGE.update(oido=OidoGuion(reloj=self.reloj), rapido="base")
        try:
            with mock.patch.object(voz, "config", return_value=dict(comun.DEFAULTS, barge_in=False)):
                self.assertIsNone(voz._vigia())
                h = voz._nuevo_hablador(self.conv)
                self.assertIsNone(h.vigia)
            self.assertIsNotNone(voz._vigia())
        finally:
            voz._BARGE.update(oido=None, rapido=None)


class IntegracionRapida(Base):
    def test_callate_durante_un_comando_rapido(self):
        """De punta a punta sin threads: voz real (proceso que duerme 3 s) + vigía con frames reales."""
        o = OidoGuion(("di", "Jarvis, qué hora es"), reloj=self.reloj)
        o.cola = ColaDiferida(list(cola_con(("s", 5), ("v", 8), ("s", 6)).queue))
        voz._BARGE.update(oido=o, rapido="base")
        voz_lenta = FalsaVoz(seg=3)
        try:
            with mock.patch.object(voz, "Hablador", functools.partial(st.Hablador, lanzar=voz_lenta)), \
                 mock.patch.object(it, "transcribir", lambda m, a, *x, **k: "Jarvis, cállate"), \
                 mock.patch.object(voz, "Vigia", functools.partial(it.Vigia, transcribir=lambda m, a, *x, **k: "Jarvis, cállate")):
                t0 = time.perf_counter()
                voz.escuchar_una(o, "base", "small", self.conv)
                dur = time.perf_counter() - t0
        finally:
            voz._BARGE.update(oido=None, rapido=None)
        self.assertLess(dur, 2.0)                                               # no esperó los 3 s de voz
        self.assertTrue(all(p.poll() is not None for p in voz_lenta.procs))
        self.assertEqual(self.cierre(), ["callar"])
        filas = [json.loads(l) for l in (self.casa / "metricas.jsonl").read_text().splitlines()]
        self.assertIn("confirmado", [f.get("motivo") for f in filas if f["etapa"] == "barge_deteccion"])
        self.assertIn("barge_parada", [f["etapa"] for f in filas])


# ---------------------------------------------------------------- voz al result (T30–T36, T50)
class Result(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.casa = pathlib.Path(self.tmp.name)
        self.parches = [mock.patch.object(tm, "ARCHIVO", self.casa / "m.jsonl"),
                        mock.patch.object(sesiones, "DIR", self.casa),
                        mock.patch.object(pensar_mod, "estado"), mock.patch.object(pensar_mod, "log"),
                        mock.patch.object(pensar_mod, "HIST", self.casa / "h.jsonl"),
                        mock.patch.object(pensar_mod, "shutil", mock.MagicMock(which=lambda x: "/x/claude"))]
        for p in self.parches:
            p.start()
        tm.terminar(); tm.nueva("voz", tm.ahora())

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def pensar(self, falso, voz_f, al_result=True, sin_herr=False, codex=None, **cfg):
        h = st.Hablador(lanzar=voz_f)
        c = {"claude_streaming": True, "voz_anticipada": True, "hablar_al_result": al_result, **cfg}
        with mock.patch.object(pensar_mod.streaming, "correr", functools.partial(st.correr, popen=falso)), \
             mock.patch.object(pensar_mod, "config", return_value=c), \
             mock.patch.object(pensar_mod, "codex", codex or mock.MagicMock(return_value=(None, "x"))):
            r = pensar_mod.pensar("qué tengo", voz=True, hablador=h, sin_herramientas=sin_herr)
        h.esperar()
        return r, h

    def etapas(self):
        return {json.loads(l)["etapa"]: json.loads(l) for l in (self.casa / "m.jsonl").read_text().splitlines()}


class T30_VozAntesDeLaSalida(Result):
    def test_habla_al_result(self):
        ev = respuesta_simple(["Tiene tres pendientes, señor."], tools=["Read"]) + [("dormir", 0.8)]
        voz_f = FalsaVoz(seg=0.1)
        (resp, _), h = self.pensar(FalsoClaude(ev), voz_f)
        self.assertEqual(voz_f.dichos, ["Tiene tres pendientes, señor."])
        e = self.etapas()
        self.assertLess(e["tts_inicio"]["ms"], e["claude_salida"]["ms"] - 600)
        self.assertGreater(e["ahorro_result"]["ms"], 600)

    def test_apagado_espera_la_salida(self):
        ev = respuesta_simple(["Tiene tres pendientes, señor."], tools=["Read"]) + [("dormir", 0.5)]
        voz_f = FalsaVoz(seg=0.1)
        self.pensar(FalsoClaude(ev), voz_f, al_result=False)
        self.assertEqual(voz_f.dichos, [])                                   # procesar() hablará después


class T31_ErrorNoHabla(Result):
    def test_error_y_limite(self):
        for r in (result("algo", is_error=True), result("You've hit your limit · resets 3pm"),
                  {**result("x"), "subtype": "error_during_execution"}, result("")):
            voz_f = FalsaVoz(seg=0.05)
            self.pensar(FalsoClaude([init(), msg_start(), r]), voz_f)
            self.assertEqual(voz_f.dichos, [], r)


class T32_SinDuplicarConAnticipada(Result):
    def test_una_vez(self):
        voz_f = FalsaVoz(seg=0.2)
        ev = respuesta_simple(["Una órbita es un camino curvo, señor. ", "Por la gravedad."], espera_tras=0.3)
        (resp, _), h = self.pensar(FalsoClaude(ev), voz_f, sin_herr=True)
        h.finalizar(pensar_mod.primera_linea(resp)); h.esperar()
        self.assertEqual(voz_f.dichos, ["Una órbita es un camino curvo, señor.", "Por la gravedad."])
        n = [json.loads(l)["etapa"] for l in (self.casa / "m.jsonl").read_text().splitlines()].count("tts_inicio")
        self.assertEqual(n, 1)


class T33_34_SinDeadlock(Result):
    def test_stderr_grande_y_recolecta(self):
        falso = FalsoClaude(respuesta_simple(["Listo, señor."], tools=["Read"]) + [("dormir", 0.3)],
                            stderr="E" * 300_000)
        (resp, _), h = self.pensar(falso, FalsaVoz(seg=0.05))
        self.assertEqual(resp, "Listo, señor.")
        self.assertIsNotNone(falso.procs[0].returncode)


class T35_50_ErrorTardio(Result):
    def test_rc_no_cero_tras_result_valido(self):
        codex = mock.MagicMock()
        falso = FalsoClaude(respuesta_simple(["Listo, señor."], tools=["Read"]), rc=1)
        (resp, cerebro), h = self.pensar(falso, FalsaVoz(seg=0.05), codex=codex)
        self.assertEqual((resp, cerebro), ("Listo, señor.", "claude"))
        self.assertFalse(h.incompleta)
        codex.assert_not_called()
        self.assertEqual(len(falso.cmds), 1)
        filas = [json.loads(l) for l in (self.casa / "m.jsonl").read_text().splitlines()]
        self.assertIn("salida_tardia", [f.get("motivo") for f in filas if f["etapa"] == "incidente_voz"])


class T36_JsonSigue(Result):
    def test_rollback(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(result("Hola, señor.")), "")
        m = mock.MagicMock(); m.run.side_effect = run; m.DEVNULL = subprocess.DEVNULL
        with mock.patch.object(pensar_mod, "subprocess", m):
            (resp, _), h = self.pensar(FalsoClaude([]), FalsaVoz(), claude_streaming=False)
        self.assertEqual(resp, "Hola, señor.")
        self.assertIn("json", llamadas[0])


# ---------------------------------------------------------------- contexto personal (T37–T43, T51)
class Pendientes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)
        (self.d / "memoria").mkdir()
        self.p = mock.patch.object(comun, "JARVIS", self.d); self.p.start()
        self.out = mock.patch("builtins.print"); self.out.start()

    def tearDown(self):
        self.p.stop(); self.out.stop(); self.tmp.cleanup()

    def escribir(self, *lineas):
        (self.d / "memoria/pendientes.md").write_text("# Pendientes\n" + "\n".join(lineas) + "\n")

    def r(self, t, seguimiento=False):
        return voz.clasificar_rapido(t, seguimiento)


class T37_41_51_Pendientes(Pendientes):
    def test_vacio_no_inventa(self):
        self.escribir()
        self.assertEqual(self.r("¿Qué tengo pendiente?"), ("No tiene pendientes registrados, señor.", "pendientes"))

    def test_por_fecha_y_maximo_tres(self):
        hoy = comun.datetime.date.today()
        f = lambda n: (hoy + comun.datetime.timedelta(days=n)).isoformat()
        self.escribir(f"- [ ] Tarea de historia | historia | {f(3)}", f"- [ ] Pagar internet | personal | {f(1)}",
                      f"- [x] Ya hecho | historia | {f(0)}", f"- [ ] Examen de mate | matemáticas | {f(2)}",
                      "- [ ] Leer libro | personal")
        txt, cat = self.r("Jarvis, ¿qué tengo pendiente?")
        self.assertEqual(cat, "pendientes")
        self.assertTrue(txt.startswith("Tiene 4 pendientes, señor: Pagar internet"))
        self.assertLess(txt.index("Pagar"), txt.index("Examen"))
        self.assertIn("y 1 más en pantalla", txt)
        self.assertNotIn("Ya hecho", txt)

    def test_escuela(self):
        self.escribir("- [ ] Tarea de historia | historia | 2030-01-02", "- [ ] Pagar internet | personal",
                      "- [ ] Prueba | escuela")
        txt, _ = self.r("¿qué tengo pendiente de la escuela?")
        self.assertIn("Tarea de historia", txt); self.assertIn("Prueba", txt)
        self.assertNotIn("Pagar", txt)                                        # T42: no mezcla mundos
        txt, _ = self.r("qué tengo de tarea")
        self.assertNotIn("Pagar", txt)

    def test_por_area(self):
        self.escribir("- [ ] Tarea de historia | historia", "- [ ] Examen | matemáticas")
        txt, _ = self.r("qué tengo pendiente de historia")
        self.assertIn("Tarea de historia", txt); self.assertNotIn("Examen", txt)

    def test_puntuacion_de_en_medio(self):
        self.escribir("- [ ] Prueba | escuela")
        for t in ("qué tengo? Pendiente", "Qué tengo, pendiente.", "¿Qué tengo?, ¿pendiente?",
                  "qué tengo pendiente... de la escuela", "Jarvis, ¿mis pendientes?"):
            self.assertEqual(self.r(t)[1], "pendientes", t)
        self.assertEqual(self.r("qué tengo? Pendiente del desarrollo de Jarvis"), (None, None))

    def test_jarvis_va_al_cerebro(self):
        self.escribir("- [ ] Algo | personal")
        for t in ("¿Y qué tenemos pendiente del desarrollo de Jarvis?", "qué tengo pendiente de jarvis",
                  "qué hay pendiente del proyecto"):
            self.assertEqual(self.r(t), (None, None), t)

    def test_follow_up_no_roba(self):
        self.escribir("- [ ] Algo | personal")
        for t in ("¿y cuál es primero?", "¿cuál vence antes?", "explícame la tarea de historia"):
            self.assertEqual(self.r(t, True), (None, None), t)
        self.assertEqual(self.r("¿y qué tengo pendiente?", True)[1], "pendientes")


class T38_39_40_43_Instrucciones(unittest.TestCase):
    def test_asistente_en_voz_y_texto_no_en_auto(self):
        voz_i = pensar_mod.instrucciones(True, "personal")
        texto_i = pensar_mod.instrucciones(False, "personal")
        self.assertEqual(voz_i.count("--append-system-prompt"), 1)
        self.assertIn(pensar_mod.INSTRUCCION_ASISTENTE, voz_i[1]); self.assertIn(pensar_mod.INSTRUCCION_VOZ, voz_i[1])
        self.assertEqual(texto_i, ["--append-system-prompt", pensar_mod.INSTRUCCION_ASISTENTE])
        self.assertEqual(pensar_mod.instrucciones(False, "auto"), [])
        for x in ("upgrades/", "estado_proyecto", "git", "memoria/pendientes.md", "explícitamente por el desarrollo"):
            self.assertIn(x, pensar_mod.INSTRUCCION_ASISTENTE)

    def test_cada_llamada_incluso_al_reanudar(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(result("Ok.")), "")
        m = mock.MagicMock(); m.run.side_effect = run; m.DEVNULL = subprocess.DEVNULL
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sesiones, "DIR", pathlib.Path(d)), \
             mock.patch.object(pensar_mod, "subprocess", m), mock.patch.object(pensar_mod, "_guardar"), \
             mock.patch.object(pensar_mod, "estado"), mock.patch.object(pensar_mod, "shutil",
                                                                       mock.MagicMock(which=lambda x: "/x")):
            sesiones.guardar("personal", SID, nueva=True)                   # sesión vieja con historia técnica
            pensar_mod.pensar("¿qué tengo pendiente?")
        self.assertIn("--resume", llamadas[0])
        self.assertIn(pensar_mod.INSTRUCCION_ASISTENTE, llamadas[0][llamadas[0].index("--append-system-prompt") + 1])

    def test_desarrollo_intacto(self):
        self.assertNotIn("modo asistente personal", (RAIZ / "CLAUDE.md").read_text())
        dev = json.loads((RAIZ / ".claude/settings.json").read_text())
        self.assertNotIn("hooks", dev)


# ---------------------------------------------------------------- seguridad y regresión
class T24_26_Seguridad(unittest.TestCase):
    def test_guardia_politica_codex(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(politica, "AUDITORIA", pathlib.Path(d) / "s.jsonl"):
            self.assertFalse(guardia.decidir({"tool_name": "Bash", "tool_input": {"command": "git status"},
                                              "cwd": str(RAIZ)})[0])
            self.assertFalse(guardia.decidir({"tool_name": "Bash", "tool_input": {"command": "rm -rf ~/x"},
                                              "cwd": str(RAIZ)})[0])
        for (tipo, red), nivel in {("enviar_whatsapp", ""): "confirmar", ("borrar", ""): "confirmar",
                                   ("publicar", "instagram"): "prohibido"}.items():
            self.assertEqual(politica.evaluar({"tipo": tipo, "red": red})[0], nivel)
        cmd = " ".join(pensar_mod.ASISTENTE_CODEX)
        self.assertIn('"~/.jarvis"="deny"', cmd); self.assertNotIn("--sandbox", cmd)


class T45_TelemetriaSinContenido(Base):
    def test_sin_texto(self):
        self.det["SECRETO_UNO"] = det("orden", "PRIVADO_DOS")
        self.correr("Jarvis, SECRETO_UNO")
        txt = "".join(p.read_text() for p in self.casa.glob("*.jsonl"))
        for x in ("SECRETO", "PRIVADO"):
            self.assertNotIn(x, txt)


class T46_SinInstanciasDuplicadas(unittest.TestCase):
    def test_arranque(self):
        src = (RAIZ / "Jarvis.command").read_text()
        self.assertIn('pgrep -f "Jarvis.command"', src)
        self.assertIn('pkill -f "jarvis_voz.py"', src)


class Config(unittest.TestCase):
    def test_claves(self):
        c = json.loads((RAIZ / "config.json").read_text())
        self.assertEqual((c["barge_in"], c["hablar_al_result"]), (True, True))
        self.assertNotIn("barge_in_timeout_orden_seg", c)
        self.assertNotIn("barge_in_requiere_jarvis", c)


if __name__ == "__main__":
    unittest.main()
