"""Groq repite su prompt (VOCAB) cuando oye silencio: «Pendientes, tarea, rutina, panel.» llegó a Claude en la
prueba física del 07 (2026-10-28 09:53). Ahora se descarta y se contesta «No le entendí, señor».

    uv run --python 3.11 --with numpy python -m unittest tests.test_eco_vocab -v
"""
import json, os, pathlib, sys, tempfile, types, unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
sys.path.insert(0, str(RAIZ / "voz"))
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

import telemetria as tm           # noqa: E402
import oido                       # noqa: E402
import jarvis_voz as voz          # noqa: E402


class SoloVocabulario(unittest.TestCase):
    def test_ecos_del_prompt(self):
        for t in ("Pendientes, tarea, rutina, panel.", "pendientes tarea rutina panel",
                  "Modo gamer, modo estudio. Pendientes, tarea, rutina, panel.",
                  "Jarvis, señor. Abre YouTube, Spotify, Classroom",
                  "PENDIENTES, TAREA, RUTINA.", "WhatsApp, ChatGPT, Twitch.", oido.VOCAB):
            self.assertTrue(oido.solo_vocabulario(t), t)

    def test_ordenes_reales_no_se_tocan(self):
        for t in ("modo gamer", "abre Spotify", "Jarvis, abre Spotify", "Jarvis, modo gamer, señor",
                  "Jarvis, señor.", "pendientes", "tarea", "Pendientes, tarea.",
                  "qué pendientes tengo", "abre YouTube y Spotify", "tengo tarea de mate",
                  "¿cuánto deberían durar mis bloques de estudio?", "explícame la fotosíntesis",
                  "recuerda que prefiero el modo estudio", "", "   "):
            self.assertFalse(oido.solo_vocabulario(t), t)


class NuncaAClaude(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.metricas = pathlib.Path(d) / "m.jsonl"
        self.p = mock.patch.object(tm, "ARCHIVO", self.metricas)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_clasificar(self):
        with mock.patch.object(voz, "callar") as callar, mock.patch.object(voz, "osa") as osa:
            self.assertEqual(voz.clasificar_rapido("Pendientes, tarea, rutina, panel."),
                             ("No le entendí, señor.", "no_entendi"))
            self.assertEqual(voz.clasificar_rapido("Pendientes, tarea, rutina, panel.", seguimiento=True)[1],
                             "no_entendi")
            callar.assert_not_called(); osa.assert_not_called()
            self.assertEqual(voz.clasificar_rapido("cállate")[1], "callar")    # callar sigue primero

    def test_procesar_habla_y_no_piensa(self):
        habla = mock.MagicMock()
        with mock.patch.object(voz, "pensar") as pensar, mock.patch.object(voz, "_hablar", habla), \
             mock.patch.object(voz, "estado"), mock.patch.object(voz, "log"), \
             mock.patch.object(voz, "cerrar_pedido", return_value=False):
            tm.nueva("voz")
            self.assertEqual(voz.procesar("Pendientes, tarea, rutina, panel."), "no_entendi")
            tm.terminar()
        pensar.assert_not_called()
        habla.assert_called_once()
        self.assertEqual(habla.call_args[0][0], "No le entendí, señor.")
        filas = [json.loads(l) for l in self.metricas.read_text().splitlines()]
        desc = [f for f in filas if f["etapa"] == "transcripcion_descartada"]
        self.assertEqual(len(desc), 1)
        self.assertEqual(desc[0]["motivo"], "solo_vocabulario")
        self.assertEqual(desc[0]["ruta"], "rapido")


if __name__ == "__main__":
    unittest.main()
