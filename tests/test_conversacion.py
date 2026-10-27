"""Pruebas del upgrade 04 (conversación continua por voz). Todo con mocks: reloj, micrófono, Groq,
voz y Claude. No toca ~/.jarvis real.

    uv run --python 3.11 --with numpy python -m unittest tests.test_conversacion -v
"""
import json, os, pathlib, subprocess, sys, tempfile, time, types, unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

import telemetria as tm           # noqa: E402
import pensar as pensar_mod       # noqa: E402
import sesiones                   # noqa: E402
import conversacion as cv         # noqa: E402
import jarvis_voz as voz          # noqa: E402
import comun                      # noqa: E402

SID = "77777777-7777-4777-8777-777777777777"


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Audio:
    """Lo que el micrófono "oyó": la transcripción que daría Whisper/Groq, sin audio real."""
    def __init__(self, texto, otra_voz=False):
        self.texto, self.otra_voz = texto, otra_voz


class OidoFalso:
    """Guion de frases. ("di", texto, seg) habla tras `seg` segundos; ("calla", seg) nadie habla;
    "DISPARO" = ⌃⌥J; "CERRAR" = existe la bandera; ("otra", texto) = el vigía habló."""
    def __init__(self, guion, reloj, bitacora, casa):
        self.guion, self.reloj, self.bit, self.casa = list(guion), reloj, bitacora, casa
        self.ultima = (0, 0, 0)

    def vaciar(self):
        self.bit.append("vaciar")

    def frase(self, fin_silencio=0.7, max_dur=15.0, espera_inicio=None, disparador=None, cerrar=None, **kw):
        self.bit.append(("frase", espera_inicio))
        if cerrar is not None and pathlib.Path(cerrar).exists():
            return "CERRAR"
        if not self.guion:
            self.reloj.t += espera_inicio or 0
            return None
        paso = self.guion.pop(0)
        if paso in ("DISPARO", "CERRAR"):
            return paso
        if paso[0] == "calla":
            self.reloj.t += paso[1]
            return None if espera_inicio and paso[1] >= espera_inicio else self.frase(
                fin_silencio, max_dur, espera_inicio and espera_inicio - paso[1], disparador, cerrar)
        seg = paso[2] if len(paso) > 2 else 1
        if espera_inicio and seg >= espera_inicio:
            self.reloj.t += espera_inicio
            self.guion.insert(0, paso)
            return None
        self.reloj.t += seg
        if paso[0] == "otra":                          # el vigía habla: decir() toca voz.lock
            (self.casa / "voz.lock").write_text("")
        return Audio(paso[1], otra_voz=paso[0] == "otra")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.casa = pathlib.Path(self.tmp.name)
        self.reloj = Reloj()
        self.bit = []                       # orden de lo que pasó: decir, vaciar, frase…
        self.dicho, self.pensado, self.groq, self.base_llamadas, self.osa = [], [], [], [], []
        self.decir_ok = True
        self.parches = [
            mock.patch.object(tm, "ARCHIVO", self.casa / "metricas.jsonl"),
            mock.patch.object(tm, "CONV_ARCHIVO", self.casa / "conversaciones.jsonl"),
            mock.patch.object(voz, "CASA", self.casa),
            mock.patch.object(voz, "CERRAR", self.casa / "cerrar_conversacion"),
            mock.patch.object(voz, "DISPARADOR", self.casa / "escuchar"),
            mock.patch.object(voz, "estado", self._estado),
            mock.patch.object(voz, "log"),
            mock.patch.object(voz, "subprocess"),
            mock.patch.object(voz, "osa", lambda s: (self.osa.append(s), subprocess.CompletedProcess([], 0, "", ""))[1]),
            mock.patch.object(voz, "decir", self._decir),
            mock.patch.object(voz, "callar", lambda: (self.casa / "cerrar_conversacion").touch()),
            mock.patch.object(voz, "pensar", self._pensar),
            mock.patch.object(voz, "oir_bien", self._oir_bien),
            mock.patch.object(voz, "transcribir", self._base),
            mock.patch.object(voz, "modo", lambda m: f"Modo {m} activado, señor."),
            mock.patch.object(voz, "disponibles", lambda: ["gamer", "estudio", "trabajo", "dormir"]),
            mock.patch.object(voz, "abrir_url", return_value=True),
        ]
        for p in self.parches:
            p.start()
        voz.subprocess.run.return_value = subprocess.CompletedProcess([], 0, "", "")   # open -a … funciona
        self.estados = []
        tm.terminar()
        self.conv = cv.Conversacion(reloj=self.reloj, registrar=tm.conversacion)

    def tearDown(self):
        tm.terminar()
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    # ---- dobles ----
    def _estado(self, nombre, texto=""):
        self.estados.append(nombre)

    def _decir(self, texto, forzar=False):
        if isinstance(self.decir_ok, Exception):
            raise self.decir_ok
        self.bit.append("decir"); self.dicho.append(texto)
        self.reloj.t += 1
        return self.decir_ok

    def _pensar(self, texto, voz=False, origen="personal", **kw):     # upgrade 05: hablador, sin_herramientas
        self.bit.append("pensar"); self.pensado.append((texto, origen))
        self.reloj.t += 2
        return f"Respuesta a: {texto}", "claude"

    def _oir_bien(self, audio, preciso):
        self.bit.append("groq"); self.groq.append(audio.texto)
        return audio.texto

    def _base(self, modelo, audio, idioma="es", **kw):
        self.bit.append("base"); self.base_llamadas.append(audio.texto)
        return audio.texto

    # ---- correr ----
    def oido(self, *guion):
        return OidoFalso(guion, self.reloj, self.bit, self.casa)

    def desde_idle(self, primera, *guion):
        """El usuario dice `primera` en IDLE y luego sigue el guion de FOLLOW_UP."""
        o = self.oido(("di", primera, 0), *guion)
        voz.escuchar_una(o, "base", "small", self.conv)
        return o

    def eventos(self, tipo=None):
        f = self.casa / "conversaciones.jsonl"
        filas = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
        return [x for x in filas if tipo is None or x["evento"] == tipo]

    def cierre(self):
        (c,) = self.eventos("cierre")
        return c["motivo"]


# ---------------------------------------------------------------- T1–T25
class T01_SinActivacion(Base):
    def test_sin_jarvis_queda_en_idle(self):
        self.desde_idle("abre spotify")
        self.assertEqual(self.conv.estado, cv.IDLE)
        self.assertEqual((self.groq, self.dicho, self.pensado), ([], [], []))   # nada va a Groq
        self.assertEqual(self.eventos(), [])


class T02_Activacion(Base):
    def test_jarvis_abre_conversacion(self):
        self.desde_idle("Jarvis", ("di", "qué hora es"))                       # solo «Jarvis» + tin
        self.assertEqual(len(self.eventos("activada")), 1)
        self.assertTrue(self.dicho[0].startswith("Son las"))

    def test_atajo_abre_conversacion(self):
        o = self.oido("DISPARO", ("di", "qué hora es"))
        voz.escuchar_una(o, "base", "small", self.conv)
        self.assertEqual(len(self.eventos("activada")), 1)
        self.assertEqual(self.base_llamadas, [])


class T03_PrimeraOrden(Base):
    def test_se_procesa(self):
        self.desde_idle("Jarvis, qué hora es")
        self.assertTrue(self.dicho[0].startswith("Son las"))
        self.assertEqual(self.groq, ["Jarvis, qué hora es"])                    # una sola vez


class T04_AbreSeguimiento(Base):
    def test_despues_de_hablar_vacia_y_escucha_15s(self):
        self.desde_idle("Jarvis, qué hora es")
        i = self.bit.index("decir")
        self.assertEqual(self.bit[i + 1], "vaciar")                             # lo que se oyó al hablar, fuera
        self.assertEqual(self.bit[i + 2], ("frase", 15.0))
        self.assertIn("seguimiento", self.estados)
        self.assertEqual(len(self.eventos("seguimiento_abre")), 1)


class T05_SegundaSinJarvis(Base):
    def test_no_necesita_jarvis(self):
        self.desde_idle("Jarvis, qué tengo mañana", ("di", "cuál vence primero"))
        self.assertEqual([p[0] for p in self.pensado], ["qué tengo mañana", "cuál vence primero"])
        self.assertEqual(self.base_llamadas, ["Jarvis, qué tengo mañana"])      # base solo en IDLE


class T06_ContextoClaude(Base):
    def test_segundo_turno_reanuda_la_sesion_personal(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            sid = cmd[cmd.index("--resume") + 1] if "--resume" in cmd else cmd[cmd.index("--session-id") + 1]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(
                {"result": "Dos pendientes, señor.", "is_error": False, "session_id": sid, "duration_ms": 9}), "")
        m = mock.MagicMock(); m.run.side_effect = run; m.DEVNULL = subprocess.DEVNULL
        m.TimeoutExpired = subprocess.TimeoutExpired
        with mock.patch.object(voz, "pensar", pensar_mod.pensar), \
             mock.patch.object(pensar_mod, "config", return_value={"claude_streaming": False}), \
             mock.patch.object(pensar_mod, "subprocess", m), mock.patch.object(pensar_mod, "estado"), \
             mock.patch.object(pensar_mod, "log"), mock.patch.object(pensar_mod, "_guardar"), \
             mock.patch.object(sesiones, "DIR", self.casa):
            self.desde_idle("Jarvis, qué tengo mañana", ("di", "cuál vence primero"))
        a, b = llamadas
        self.assertEqual(b[b.index("--resume") + 1], a[a.index("--session-id") + 1])
        self.assertEqual(b[2], "cuál vence primero")                            # sin reenviar historial
        self.assertNotIn("--continue", b)


class T07_Tercera(Base):
    def test_tercer_turno(self):
        self.desde_idle("Jarvis, uno", ("di", "dos"), ("di", "tres"))
        self.assertEqual([p[0] for p in self.pensado], ["uno", "dos", "tres"])


class T08_Timeout(Base):
    def test_15s_de_silencio_vuelve_a_idle(self):
        self.desde_idle("Jarvis, qué hora es", ("calla", 15))
        self.assertEqual(self.conv.estado, cv.IDLE)
        self.assertEqual(self.cierre(), "timeout")
        self.assertEqual(self.estados[-1], "listo")


class T09_TrasCierre(Base):
    def test_sin_jarvis_no_ejecuta(self):
        self.desde_idle("Jarvis, qué hora es", ("calla", 15))
        n = len(self.dicho)
        self.desde_idle("abre spotify")
        self.assertEqual(len(self.dicho), n)
        self.assertNotIn("open", str(voz.subprocess.run.call_args_list))


class T10_CincoTurnos(Base):
    def test_cierra_tras_el_quinto(self):
        self.desde_idle("Jarvis, uno", ("di", "dos"), ("di", "tres"), ("di", "cuatro"), ("di", "cinco"),
                        ("di", "seis"))
        self.assertEqual(len(self.pensado), 5)
        self.assertEqual(self.cierre(), "turnos")
        self.assertEqual(self.bit.count(("frase", 15.0)), 4)                    # sin ventana tras el 5.º


class T11_TresMinutos(Base):
    def test_cierra_al_cumplir_180s(self):
        # Turnos de ~17 s (JP habla a los 14 s, Jarvis piensa 2 y habla 1) y sin límite de turnos.
        c = dict(comun.config(), max_turnos=99)
        with mock.patch.object(voz, "config", return_value=c):
            self.desde_idle("Jarvis, uno", *[("di", f"turno {i}", 14) for i in range(2, 30)])
        self.assertEqual(self.cierre(), "tiempo")
        self.assertGreaterEqual(self.reloj.t - 1000, 180)
        self.assertLess(self.reloj.t - 1000, 180 + 17)            # el último turno terminó y se cerró
        self.assertEqual(len(self.pensado), 11)

    def test_turno_largo_termina_y_luego_cierra(self):
        original = self._pensar
        def lento(texto, **kw):
            self.reloj.t += 200                                  # se pasa de 180 s pensando
            return original(texto, **kw)
        with mock.patch.object(voz, "pensar", lento):
            self.desde_idle("Jarvis, explica algo largo", ("di", "otra cosa"))
        self.assertEqual(len(self.dicho), 1)                     # el turno terminó normal
        self.assertEqual(self.cierre(), "tiempo")
        self.assertEqual(self.pensado and len(self.pensado), 1)

    def test_ventana_no_pasa_de_180(self):
        self.conv.activar(); self.conv.iniciar_turno()
        self.reloj.t += 175
        self.conv.respuesta_terminada()
        self.assertAlmostEqual(self.conv.restante(), 5.0)


class T12_JarvisEnSeguimiento(Base):
    def test_no_duplica(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "Jarvis, ponle pausa"))
        self.assertEqual(len(self.eventos("activada")), 1)
        self.assertEqual(self.groq.count("Jarvis, ponle pausa"), 1)
        self.assertEqual(self.osa.count('tell application "Spotify" to pause'), 1)

    def test_solo_jarvis_no_cuenta_turno(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "Jarvis"), ("di", "dime un chiste"))
        self.assertEqual([p[0] for p in self.pensado], ["dime un chiste"])
        self.assertEqual(self.eventos("cierre")[0]["turno"], 2)
        self.assertIn("solo_jarvis", [e.get("motivo") for e in self.eventos("seguimiento_descartado")])

    def test_atajo_en_seguimiento_es_el_mismo(self):
        self.desde_idle("Jarvis, qué hora es", "DISPARO", ("di", "dime un chiste"))
        self.assertEqual(len(self.eventos("activada")), 1)
        self.assertEqual([p[0] for p in self.pensado], ["dime un chiste"])


class T13_RapidoSinModelo(Base):
    def test_spotify_en_seguimiento(self):
        self.desde_idle("Jarvis, abre Spotify", ("di", "ponle pausa"), ("di", "siguiente canción"))
        self.assertEqual(self.pensado, [])
        self.assertIn('tell application "Spotify" to pause', self.osa)
        self.assertIn('tell application "Spotify" to next track', self.osa)

    def test_accion_sin_voz_abre_ventana_sin_esperar_voz(self):
        self.desde_idle("Jarvis, sube el volumen", ("di", "qué hora es"))
        self.assertEqual(self.dicho[:1][0][:7], "Son las")      # el 2.º turno sí se oyó
        self.assertEqual(self.bit.count("decir"), 1)


class T14_SuPropiaVoz(Base):
    def test_lo_oido_al_hablar_se_descarta(self):
        self.desde_idle("Jarvis, qué hora es")
        i = self.bit.index("decir")
        self.assertEqual(self.bit[i + 1], "vaciar")
        self.assertNotIn("Son las", " ".join(self.groq))

    def test_otra_voz_de_jarvis_no_es_orden(self):
        """Ajuste 4: el vigía habla durante FOLLOW_UP → no va a Groq, no reinicia el contador."""
        self.desde_idle("Jarvis, qué hora es", ("otra", "Señor, lleva una hora jugando", 5), ("calla", 10))
        self.assertNotIn("Señor, lleva una hora jugando", self.groq)
        self.assertEqual(self.pensado, [])
        self.assertIn("otra_voz", [e.get("motivo") for e in self.eventos("seguimiento_descartado")])
        self.assertEqual(self.cierre(), "timeout")
        self.assertLessEqual(self.reloj.t - 1000, 1 + 15 + 0.5)                 # no se reinició el contador

    def test_otra_voz_sonando_con_candado(self):
        import fcntl
        with open(self.casa / "voz.lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self.assertTrue(voz.otra_voz(time.time() + 60))
        self.assertFalse(voz.otra_voz(time.time() + 60))

    def test_estado_hablando_de_otro_proceso(self):
        (self.casa / "estado.json").write_text('{"estado": "hablando"}')
        self.assertTrue(voz.otra_voz(time.time() + 60))


class T15_BuffersAlCerrar(Base):
    def test_vacia_al_cerrar(self):
        self.desde_idle("Jarvis, qué hora es", ("calla", 15))
        self.assertEqual(self.bit[-1], "vaciar")
        self.assertFalse((self.casa / "cerrar_conversacion").exists())


class T16_ErroresTranscripcion(Base):
    def test_vacio_no_ejecuta_y_dos_seguidos_cierran(self):
        self.desde_idle("Jarvis, qué hora es", ("di", ""), ("di", ""), ("di", "abre spotify"))
        self.assertEqual(self.pensado, [])
        self.assertEqual(self.cierre(), "transcripcion")
        self.assertNotIn("Abriendo spotify, señor.", self.dicho)

    def test_un_fallo_sigue_esperando(self):
        self.desde_idle("Jarvis, qué hora es", ("di", ""), ("di", "dime un chiste"))
        self.assertEqual([p[0] for p in self.pensado], ["dime un chiste"])

    def test_fantasma_no_cuenta_turno(self):
        self.desde_idle("Jarvis, qué hora es", ("di", ""), ("di", "dime un chiste"))
        self.assertEqual(self.eventos("cierre")[0]["turno"], 2)


class T17_ErrorVoz(Base):
    def test_excepcion_de_tts_cierra(self):
        self.decir_ok = RuntimeError("say tronó")
        self.desde_idle("Jarvis, qué hora es", ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "error")
        self.assertEqual(self.conv.estado, cv.IDLE)
        self.assertNotIn(("frase", 15.0), self.bit)

    def test_say_falla_sin_excepcion_cierra(self):
        self.decir_ok = False
        self.desde_idle("Jarvis, qué hora es", ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "error")
        self.assertNotIn(("frase", 15.0), self.bit)


class T18_SinConcurrencia(Base):
    def test_no_hay_dos_conversaciones(self):
        self.assertTrue(self.conv.activar())
        self.conv.iniciar_turno()
        self.assertFalse(self.conv.activar())                                    # mientras procesa
        o = self.oido(("di", "abre spotify"))
        voz.conversar(o, "small", self.conv, "qué hora es")                     # no abre otra
        self.assertEqual(self.dicho, [])
        self.assertEqual(len(self.eventos("activada")), 1)

    def test_transiciones_invalidas(self):
        with self.assertRaises(cv.TransicionInvalida):
            self.conv.iniciar_turno()                                            # desde IDLE
        self.conv.activar()
        with self.assertRaises(cv.TransicionInvalida):
            self.conv.hablar()                                                   # sin procesar


class T19_CierreManual(Base):
    def test_frases_de_cierre(self):
        for frase in ("Terminamos, Jarvis", "cierra la conversación", "Eso es todo, Jarvis.", "Jarvis, terminamos"):
            self.assertTrue(cv.es_cierre(frase), frase)
        for frase in ("no", "gracias", "no, gracias", "ya", "terminamos la tarea"):
            self.assertFalse(cv.es_cierre(frase), frase)

    def test_variantes_de_groq(self):
        for frase in ("Cierro la conversación.", "ciérrala", "Ciérrala, Jarvis", "cerremos", "Cerremos la conversación",
                      "ya cierra", "Ya cierra la conversación", "Jarvis, ya cierra"):
            self.assertTrue(cv.es_cierre(frase), frase)
        for frase in ("cierra", "cierro", "cierra Spotify", "ya cierra la ventana", "cerremos el trato",
                      "cierro la puerta"):
            self.assertFalse(cv.es_cierre(frase), frase)

    def test_cierro_en_conversacion_cierra_local(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "Cierro la conversación."), ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "manual")
        self.assertEqual(self.pensado, [])

    def test_cierra_sin_cerebro_y_sin_hablar(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "Eso es todo, Jarvis"), ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "manual")
        self.assertEqual(self.pensado, [])
        self.assertEqual(len(self.dicho), 1)                                     # sin frase de despedida
        self.assertIn("Bottle.aiff", str(voz.subprocess.Popen.call_args_list[-1]))


class T20_Sensibles(Base):
    def test_politica_02_intacta(self):
        import politica
        for (tipo, red), nivel in {("enviar_whatsapp", ""): "confirmar", ("borrar", ""): "confirmar",
                                   ("gasto", ""): "confirmar", ("publicar", "instagram"): "prohibido"}.items():
            self.assertEqual(politica.evaluar({"tipo": tipo, "red": red})[0], nivel)

    def test_turno_de_seguimiento_va_con_candados(self):
        llamadas = []
        def run(cmd, **kw):
            llamadas.append(cmd)
            sid = cmd[cmd.index("--resume") + 1] if "--resume" in cmd else cmd[cmd.index("--session-id") + 1]
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "No puedo, señor.",
                                                                   "is_error": False, "session_id": sid}), "")
        m = mock.MagicMock(); m.run.side_effect = run; m.DEVNULL = subprocess.DEVNULL
        with mock.patch.object(voz, "pensar", pensar_mod.pensar), \
             mock.patch.object(pensar_mod, "config", return_value={"claude_streaming": False}), \
             mock.patch.object(pensar_mod, "subprocess", m), mock.patch.object(pensar_mod, "estado"), \
             mock.patch.object(pensar_mod, "log"), mock.patch.object(pensar_mod, "_guardar"), \
             mock.patch.object(sesiones, "DIR", self.casa):
            self.desde_idle("Jarvis, hola", ("di", "manda un WhatsApp a mi mamá"))
        n = len(pensar_mod.ASISTENTE_CLAUDE)
        self.assertEqual(llamadas[1][-n:], pensar_mod.ASISTENTE_CLAUDE)


class T21_Codex(Base):
    def test_aislamiento_03_intacto(self):
        cmd = " ".join(pensar_mod.ASISTENTE_CODEX)
        self.assertIn('"~/.jarvis"="deny"', cmd)
        self.assertNotIn("--sandbox", cmd)
        self.assertIn("--disable shell_tool", cmd)
        with mock.patch.object(pensar_mod, "buscar_codex", return_value="/falso"), \
             mock.patch.object(pensar_mod, "codex_aislado", return_value=False):
            self.assertEqual(pensar_mod.codex("hola", True), (None, pensar_mod.SIN_RESPALDO))


class T22_Separacion(Base):
    def test_voz_es_personal_y_resumen_cierra(self):
        self.desde_idle("Jarvis, hola", ("di", "dame el resumen"), ("di", "otra cosa"))
        self.assertEqual({o for _, o in self.pensado}, {"personal"})
        self.assertEqual(self.cierre(), "resumen")                               # ajuste 4
        self.assertEqual(len(self.pensado), 1)

    def test_texto_no_toca_la_conversacion(self):
        src = (RAIZ / "bin/pensar.py").read_text()
        self.assertNotIn("conversacion", src)                                     # ⌃⌥Espacio no la abre


class T23_TelemetriaSinContenido(Base):
    def test_sin_audio_ni_texto(self):
        self.desde_idle("Jarvis, SECRETO_7731 qué hay", ("di", "PALABRA_PRIVADA_88"), ("di", "terminamos"))
        todo = "".join(p.read_text() for p in self.casa.glob("*.jsonl"))
        for x in ("SECRETO_7731", "PALABRA_PRIVADA_88", "terminamos"):
            self.assertNotIn(x, todo)
        for e in self.eventos():
            self.assertTrue(set(e) <= {"fecha", "conv", "evento", "turno", "motivo", "ms"})
        self.assertEqual(list(self.casa.glob("*.wav")) + list(self.casa.glob("*.mp3")), [])

    def test_un_evento_por_transicion(self):
        self.desde_idle("Jarvis, uno", ("di", "dos"), ("calla", 15))
        self.assertEqual([e["evento"] for e in self.eventos()],
                         ["activada", "seguimiento_abre", "seguimiento_detectado", "seguimiento_abre", "cierre"])

    def test_cada_turno_es_su_peticion(self):
        self.desde_idle("Jarvis, uno", ("di", "dos"), ("calla", 15))
        filas = [json.loads(l) for l in (self.casa / "metricas.jsonl").read_text().splitlines()]
        self.assertEqual(len({f["id"] for f in filas}), 2)


class T24_SinHud(Base):
    def test_funciona_solo_con_el_archivo(self):
        self.parches[5].stop()                                 # estado() real, a un directorio temporal
        try:
            with mock.patch.object(comun, "CASA", self.casa):
                self.desde_idle("Jarvis, qué hora es", ("calla", 15))
            self.assertEqual(json.loads((self.casa / "estado.json").read_text())["estado"], "listo")
        finally:
            self.parches[5].start()
        self.assertEqual(self.cierre(), "timeout")


class T25_ExpiracionIndependiente(Base):
    def test_cerrar_la_ventana_no_borra_la_sesion(self):
        with mock.patch.object(sesiones, "DIR", self.casa):
            sesiones.guardar("personal", SID, nueva=True)
            self.desde_idle("Jarvis, qué hora es", ("calla", 15))
            self.assertEqual(self.conv.estado, cv.IDLE)
            self.assertEqual(sesiones.vigente("personal"), SID)                  # sigue 30 min
            self.assertIsNone(sesiones.vigente("personal", time.time() + 31 * 60))


# ---------------------------------------------------------------- ajustes del revisor
class Ajuste05_Ambiguos(Base):
    def rapido(self, t, previo=None):
        return voz.clasificar_rapido(t, True, previo)

    def test_y_la_siguiente_es_pregunta(self):
        self.assertEqual(self.rapido("¿y la siguiente?"), (None, None))
        self.assertEqual(self.rapido("¿y el anterior?"), (None, None))

    def test_con_cancion_si_cambia(self):
        self.assertEqual(self.rapido("siguiente canción")[1], "spotify")
        self.assertEqual(self.rapido("salta la canción")[1], "spotify")
        self.assertEqual(self.rapido("canción anterior")[1], "spotify")
        self.assertEqual(self.rapido("regresa la canción")[1], "spotify")

    def test_a_secas_solo_tras_spotify(self):
        self.assertEqual(self.rapido("siguiente"), (None, None))
        self.assertEqual(self.rapido("siguiente", "spotify")[1], "spotify")
        self.assertEqual(self.rapido("anterior"), (None, None))
        self.assertEqual(self.rapido("anterior", "spotify")[1], "spotify")

    def test_ya_y_para_van_al_cerebro(self):
        self.assertEqual(self.rapido("ya"), (None, None))
        self.assertEqual(self.rapido("para"), (None, None))

    def test_idle_igual_que_antes(self):
        self.assertEqual(voz.clasificar_rapido("siguiente")[1], "spotify")
        self.assertEqual(voz.clasificar_rapido("ya")[1], "callar")

    def test_siguiente_tras_spotify_en_conversacion(self):
        self.desde_idle("Jarvis, ponle pausa", ("di", "siguiente"), ("di", "y la siguiente"))
        self.assertEqual(self.osa.count('tell application "Spotify" to next track'), 1)
        self.assertEqual([p[0] for p in self.pensado], ["y la siguiente"])       # tras Spotify, «siguiente» sí


class Ajuste08_Callar(Base):
    def test_callar_mientras_piensa_no_habla_y_cierra(self):
        original = self._pensar
        def y_lo_callan(texto, **kw):
            (self.casa / "cerrar_conversacion").touch()                         # ⌃⌥. desde Hammerspoon
            return original(texto, **kw)
        with mock.patch.object(voz, "pensar", y_lo_callan):
            self.desde_idle("Jarvis, cuéntame algo", ("di", "abre spotify"))
        self.assertEqual(self.dicho, [])
        self.assertEqual(self.cierre(), "callar")

    def test_callar_al_hablar_no_abre_ventana(self):
        def decir_callado(texto, forzar=False):
            self.dicho.append(texto); (self.casa / "cerrar_conversacion").touch()
            return False                                                         # say murió
        with mock.patch.object(voz, "decir", decir_callado):
            self.desde_idle("Jarvis, qué hora es", ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "callar")
        self.assertNotIn(("frase", 15.0), self.bit)
        self.assertFalse((self.casa / "cerrar_conversacion").exists())

    def test_callar_en_seguimiento(self):
        self.desde_idle("Jarvis, qué hora es", "CERRAR")
        self.assertEqual(self.cierre(), "callar")

    def test_bandera_vieja_no_cierra_la_nueva(self):
        (self.casa / "cerrar_conversacion").touch()
        self.desde_idle("Jarvis, qué hora es", ("di", "dime un chiste"))
        self.assertEqual(len(self.pensado), 1)

    def test_callate_en_seguimiento_cierra(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "cállate"), ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "callar")

    def test_modo_dormir_cierra(self):
        self.desde_idle("Jarvis, qué hora es", ("di", "activa el modo dormir"), ("di", "abre spotify"))
        self.assertEqual(self.cierre(), "dormir")


class ConfigYOido(unittest.TestCase):
    def test_config_ajustable(self):
        c = json.loads((RAIZ / "config.json").read_text())
        self.assertEqual((c["conversacion_continua"], c["timeout_seguimiento_seg"], c["max_turnos"],
                          c["duracion_maxima_seg"]), (True, 15, 5, 180))
        conv = cv.Conversacion.desde_config({"timeout_seguimiento_seg": 8, "max_turnos": 2})
        self.assertEqual((conv.timeout, conv.max_turnos, conv.duracion_max), (8.0, 2, 180.0))

    def test_desactivada_es_como_antes(self):
        r = Reloj()
        conv = cv.Conversacion(continua=False, reloj=r)
        conv.activar(); conv.iniciar_turno()
        self.assertFalse(conv.respuesta_terminada())
        self.assertEqual(conv.estado, cv.IDLE)

    def test_oido_usa_reloj_monotonico(self):
        src = (RAIZ / "voz/oido.py").read_text()
        self.assertIn("time.monotonic()", src)
        self.assertNotIn("time.time()", src)
        self.assertIn("con_voz < 3", src)                                        # «sí»/«no» siguen pasando

    def test_hud_conoce_seguimiento(self):
        lua = (RAIZ / "hammerspoon/init.lua").read_text()
        self.assertIn("seguimiento = \"\"", lua)
        self.assertIn("(tonumber(texto) or 15) + 2", lua)

    def test_callar_crea_la_bandera(self):
        import decir as decir_mod
        with tempfile.TemporaryDirectory() as d, mock.patch.object(decir_mod, "CASA", pathlib.Path(d)), \
             mock.patch.object(decir_mod, "subprocess"):
            decir_mod.callar()
            self.assertTrue((pathlib.Path(d) / "cerrar_conversacion").exists())

    def test_jv_latencia_resume_conversaciones(self):
        import io, latencia
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            arch = pathlib.Path(d) / "c.jsonl"
            with mock.patch.object(tm, "CONV_ARCHIVO", arch), mock.patch.object(tm, "ARCHIVO", pathlib.Path(d) / "m"):
                tm.conversacion("activada", "a1"); tm.conversacion("seguimiento_detectado", "a1", 1, ms=2500)
                tm.conversacion("seguimiento_descartado", "a1", 1, motivo="otra_voz")
                tm.conversacion("cierre", "a1", 2, motivo="timeout")
                tm.conversacion("evento_raro", "a1"); tm.conversacion("cierre", "a1", 2, motivo="inventado")
                with mock.patch.object(sys, "argv", ["latencia"]), redirect_stdout(io.StringIO()) as out:
                    latencia.conversaciones(None)
        txt = out.getvalue()
        self.assertIn("conversaciones: 1", txt)
        self.assertIn("timeout 1", txt)
        self.assertIn("error 1", txt)                                            # motivo fuera de lista
        self.assertIn("(50%)", txt)


if __name__ == "__main__":
    unittest.main()
