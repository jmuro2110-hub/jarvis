"""Bug de activación (2026-10-28): en IDLE, Whisper base con ruido de fondo tardaba hasta 24 s en frases de 15 s y el
`oido.vaciar()` del final tiraba lo que JP dijo mientras tanto («Jarvis» se perdía; en seguimiento, con Groq, no).

    uv run --python 3.11 --with numpy python -m unittest tests.test_activacion_idle -v
"""
import json, unittest
from unittest import mock

import numpy as np

from tests.test_streaming import Captura, OidoCola, Audio, voz, tm


class Recortable(Audio):
    """Audio con largo real: anota cuánto le llega a Whisper base."""
    def __init__(self, texto, seg):
        super().__init__(texto)
        self.muestras, self.vistas = int(seg * voz.RATE), []

    def __getitem__(self, s):
        self.vistas.append(min(s.stop, self.muestras))
        return self


class Idle(Captura):
    def filas(self, etapa):
        archivo = tm.ARCHIVO
        if not archivo.exists():
            return []
        return [f for f in map(json.loads, archivo.read_text().splitlines()) if f["etapa"] == etapa]


class SoloTresSegundosABase(Idle):
    def test_base_ve_3_s_y_groq_la_frase_completa(self):
        larga = Recortable("Jarvis, cuéntame la historia completa de la revolución", seg=14.0)
        o = OidoCola("x", voz_seg=4.0)
        o.frase = mock.Mock(side_effect=[larga] + [None] * 5)
        self.correr(o)
        self.assertEqual(larga.vistas, [int(3.0 * voz.RATE)])         # base: solo los primeros 3 s
        self.assertEqual(self.groq, ["Jarvis, cuéntame la historia completa de la revolución"])  # Groq: completa

    def test_numpy_real(self):
        vistos = []
        audio = np.zeros(15 * voz.RATE, np.float32)
        o = mock.MagicMock(); o.frase.return_value = audio
        with mock.patch.object(voz, "transcribir", lambda m, a, *x, **k: (vistos.append(len(a)), "")[1]):
            voz.escuchar_una(o, "base", "small", self.conv)
        self.assertEqual(vistos, [3 * voz.RATE])
        audio = np.zeros(2 * voz.RATE, np.float32); o.frase.return_value = audio
        with mock.patch.object(voz, "transcribir", lambda m, a, *x, **k: (vistos.append(len(a)), "")[1]):
            voz.escuchar_una(o, "base", "small", self.conv)
        self.assertEqual(vistos[-1], 2 * voz.RATE)                     # más corta: entera


class NoSeTiraLoQueDijo(Idle):
    def test_jarvis_dicho_mientras_base_transcribia(self):
        o = OidoCola("plática de fondo sin el llamado", en_cola=["Jarvis, qué hora es"])
        self.correr(o)                                                 # no era «Jarvis»: la cola se queda
        self.assertEqual(o.vaciados, 0)
        self.assertEqual(o.cola, ["Jarvis, qué hora es"])
        self.correr(o)                                                 # la siguiente frase ES lo que dijo
        self.assertTrue(any(b[0] == "decir" and b[1].startswith("Son las") for b in self.bit), self.bit)

    def test_despues_de_conversar_si_vacia(self):
        o = OidoCola("Jarvis, abre Spotify", voz_seg=1.2)
        self.correr(o)
        self.assertIn(("decir", "Abriendo spotify, señor."), self.bit)
        self.assertGreaterEqual(o.vaciados, 1)                         # la cola trae la voz de Jarvis

    def test_atajo_de_teclado_si_vacia(self):
        o = OidoCola("DISPARO")
        self.correr(o)
        self.assertGreaterEqual(o.vaciados, 1)


class TelemetriaDeBase(Idle):
    def test_sin_jarvis_se_registra_sin_texto(self):
        self.correr(OidoCola("una canción con mucha letra"))
        f = self.filas("deteccion_base")
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0]["motivo"], f[0]["estado"], f[0]["origen"]), ("sin_jarvis", "fallback", "voz"))
        self.assertEqual(set(f[0]), {"fecha", "id", "origen", "etapa", "ms", "ruta", "estado", "motivo"})
        self.assertNotIn("canción", tm.ARCHIVO.read_text())
        self.assertEqual(self.filas("deteccion_jarvis"), [])

    def test_lenta_con_jarvis(self):
        with mock.patch.object(voz, "BASE_LENTA_MS", -1):
            self.correr(OidoCola("Jarvis, abre Spotify", voz_seg=1.2))
        f = self.filas("deteccion_base")
        self.assertEqual([(x["motivo"], x["estado"]) for x in f], [("lenta", "exito")])
        self.assertEqual(len(self.filas("deteccion_jarvis")), 1)
        self.assertNotEqual(f[0]["id"], self.filas("deteccion_jarvis")[0]["id"])

    def test_rapida_con_jarvis_no_se_registra(self):
        self.correr(OidoCola("Jarvis, abre Spotify", voz_seg=1.2))
        self.assertEqual(self.filas("deteccion_base"), [])
        self.assertEqual(len(self.filas("deteccion_jarvis")), 1)


class QueHoras(unittest.TestCase):
    def test_variantes(self):
        for t in ("que horas", "Qué horas son?", "Jarvis, que horas", "¿Qué horas son?", "que hora es",
                  "Qué hora es", "la hora", "dime la hora"):
            r, cat = voz.clasificar_rapido(t)
            self.assertTrue(r and r.startswith("Son las"), t)

    def test_no_se_confunde(self):
        for t in ("qué horas tengo de clase el lunes", "a qué hora es el examen"):
            r, _ = voz.clasificar_rapido(t)
            self.assertFalse(r and r.startswith("Son las"), t)


if __name__ == "__main__":
    unittest.main()
