"""Upgrade 08: supervisor de arranque (bin/arranque.py), sección 9 del upgrade. Procesos REALES con comandos
falsos y una casa temporal con espacios en la ruta: candado, hijos, reinicios, parada y huérfanos.
Los mocks no demuestran permisos de macOS: eso es la prueba física (A–H).

    <python del entorno de voz> -m unittest tests.test_arranque -v
"""
import json, os, pathlib, signal, subprocess, sys, tempfile, time, unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bin"))
import arranque                                                    # noqa: E402
import streaming                                                   # noqa: E402

PY = "/usr/bin/python3"           # el mismo intérprete que usa arranque.sh

# Hijo falso: usa la vigilancia REAL (comun.vigilar_supervisor) y, si es la voz, la limpieza REAL de streaming.
FALSO = r'''
import os, pathlib, signal, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
nombre, modo = sys.argv[2], sys.argv[3]
casa = pathlib.Path(os.environ["JARVIS_CASA"])
with open(casa / f"pids_{nombre}", "a") as f:
    f.write(f"{os.getpid()}\n")
print("SECRETO conversación privada de JP", flush=True)
print("SECRETO por stderr", file=sys.stderr, flush=True)
if modo == "fatal":
    sys.exit(3)
if modo == "cae":
    time.sleep(0.2); sys.exit(1)
if modo != "terco":
    from comun import vigilar_supervisor
    vigilar_supervisor()
if modo == "terco":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if nombre == "voz" and modo == "tts":
    import streaming
    p = subprocess.Popen(["/bin/sh", "-c", "sleep 60 & sleep 60; wait"], start_new_session=True)
    streaming.VOCES.add(p)
    (casa / "tts_pgid").write_text(str(p.pid))
    def fin(*_):
        streaming.limpiar_voces(); sys.exit(0)
    signal.signal(signal.SIGTERM, fin)
if nombre == "voz":
    time.sleep(0.3)
    (casa / "voz_lista").write_text(str(os.getpid()))
while True:
    time.sleep(0.05)
'''


def vivo(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def grupo_vivo(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


class Base(unittest.TestCase):
    voz, agenda, entorno, hs = "normal", "normal", 0, True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis arranque ")
        self.casa = pathlib.Path(self.tmp.name) / "casa con espacios"
        self.casa.mkdir()
        self.falso = pathlib.Path(self.tmp.name) / "hijo falso.py"
        self.falso.write_text(FALSO)
        (self.casa / "hs").write_text("1") if self.hs else None
        self.procs = []
        self.cmds = self.comandos()

    def comandos(self, voz=None, agenda=None):
        h = lambda n, m: [PY, str(self.falso), str(RAIZ / "bin"), n, m]
        return {"entorno": [PY, "-c", f"import sys; sys.exit({self.entorno})"],
                "voz": h("voz", voz or self.voz), "agenda": h("agenda", agenda or self.agenda),
                "caffeinate": [PY, "-c", "import time\nwhile True: time.sleep(1)", "{supervisor}"],
                "hammerspoon": ["/bin/test", "-f", str(self.casa / "hs")]}

    def env(self, **extra):
        cfg = {"cmds": self.cmds, "esperas": [0.3, 0.3, 0.3], "estable_s": 999, "hs_cada": 0.2,
               "hs_intentos": 1000, "gracia": 3}
        e = {"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"], "JARVIS_CASA": str(self.casa),
             "JARVIS_ARRANQUE_PRUEBA": json.dumps(cfg)}
        e.update(extra)
        return e

    def supervisor(self, lanzador="app", mic="autorizado"):
        p = subprocess.Popen([PY, "-I", str(RAIZ / "bin" / "arranque.py"), "supervisar", "--lanzador", lanzador],
                             env=self.env(JARVIS_MIC_APP=mic), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
        self.procs.append(p)
        return p

    def ctl(self, *args):
        r = subprocess.run([PY, "-I", str(RAIZ / "bin" / "arranque.py"), *args], env=self.env(),
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout

    def estado(self):
        try:
            return json.loads((self.casa / "arranque_estado.json").read_text())
        except Exception:
            return {}

    def esperar(self, cond, t=10, msg=""):
        fin = time.monotonic() + t
        while time.monotonic() < fin:
            if cond():
                return
            time.sleep(0.05)
        self.fail(f"no pasó a tiempo: {msg} — estado {self.estado().get('estado')} — log:\n{self.log()}")

    def pids(self, nombre):
        f = self.casa / f"pids_{nombre}"
        return [int(x) for x in f.read_text().split()] if f.exists() else []

    def log(self):
        f = self.casa / "arranque.log"
        return f.read_text() if f.exists() else ""

    def listo(self, proc=None):
        """`proc`: exige que el estado sea de ESE supervisor (no el que dejó escrito uno muerto)."""
        es = lambda e: e.get("estado") == "escuchando" and (proc is None or e["supervisor"]["pid"] == proc.pid)
        self.esperar(lambda: es(self.estado()), msg="escuchando")

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait()
            if p.stdout:
                p.stdout.close()
        for n in ("voz", "agenda"):
            for pid in self.pids(n):
                try:
                    os.killpg(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        self.tmp.cleanup()


class T01_DosAperturasSimultaneas(Base):
    def test_una_instancia(self):
        a, b = self.supervisor(), self.supervisor()
        self.listo()
        salio = [p for p in (a, b) if p.poll() is not None] or []
        self.esperar(lambda: any(p.poll() is not None for p in (a, b)), msg="la segunda sale")
        segunda = a if a.poll() is not None else b
        primera = b if segunda is a else a
        self.assertEqual(segunda.returncode, 0)
        self.assertIn("ya está activo", segunda.stdout.read())
        self.assertIsNone(primera.poll())
        time.sleep(0.5)
        self.assertEqual(len(self.pids("voz")), 1)
        self.assertEqual(len(self.pids("agenda")), 1)
        self.assertEqual(self.log().count("supervisor iniciado"), 1)
        self.assertIn("segunda apertura", self.log())


class T02_AppYTerminal(Base):
    def orden(self, primero, segundo):
        a = self.supervisor(primero)
        self.listo()
        b = self.supervisor(segundo)
        b.wait(10)
        self.assertEqual(b.returncode, 0)
        self.assertIn("ya está activo", b.stdout.read())
        self.assertIsNone(a.poll())                                     # la válida sigue
        self.assertTrue(all(vivo(p) for p in self.pids("voz")))
        self.assertEqual(len(self.pids("voz")), 1)
        self.assertEqual(self.estado()["lanzador"], primero)

    def test_app_luego_terminal(self):
        self.orden("app", "terminal")

    def test_terminal_luego_app(self):
        self.orden("terminal", "app")


class T03_ParadaVoluntaria(Base):
    def test_detener_sin_resurreccion(self):
        a = self.supervisor()
        self.listo()
        voz, agenda = self.pids("voz")[0], self.pids("agenda")[0]
        codigo, salida = self.ctl("detener")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("detenido", salida)
        a.wait(10)
        self.assertFalse(vivo(voz)); self.assertFalse(vivo(agenda))
        time.sleep(1.0)                                                 # más que las esperas de reinicio
        self.assertEqual(len(self.pids("voz")), 1)
        self.assertEqual(self.estado()["estado"], "detenido")
        self.assertTrue(arranque_libre(self.casa))

    def test_detener_con_otro_idioma(self):
        """Física G (2026-10-29): supervisor con LANG=es_MX, «Detener» desde Hammerspoon sin LANG."""
        e = self.env(JARVIS_MIC_APP="autorizado", LANG="es_MX.UTF-8", LC_ALL="es_MX.UTF-8")
        a = subprocess.Popen([PY, "-I", str(RAIZ / "bin" / "arranque.py"), "supervisar", "--lanzador", "app"],
                             env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(a)
        self.listo(a)
        r = subprocess.run([PY, "-I", str(RAIZ / "bin" / "arranque.py"), "detener"], env=self.env(),
                           capture_output=True, text=True, timeout=60)        # sin LANG, como Hammerspoon
        self.assertEqual(r.returncode, 0, r.stdout)
        a.wait(10)
        self.assertFalse(vivo(self.pids("voz")[0]))
        self.assertIn("parada pedida", self.log())

    def test_identidad_no_depende_del_idioma(self):
        with mock.patch.dict(os.environ, {"LANG": "es_MX.UTF-8", "LC_ALL": "es_MX.UTF-8"}):
            es = arranque.identidad(os.getpid())
        with mock.patch.dict(os.environ, {"LANG": "", "LC_ALL": ""}):
            otro = arranque.identidad(os.getpid())
        self.assertEqual(es, otro)
        self.assertRegex(es, r"^[A-Z][a-z]{2} [A-Z][a-z]{2} ")             # «Thu Oct 29 …»

    def test_parar_con_reinicio_pendiente(self):
        self.cmds = self.comandos(voz="cae")
        cfg_lento = self.env()
        cfg = json.loads(cfg_lento["JARVIS_ARRANQUE_PRUEBA"]); cfg["esperas"] = [5, 5]
        p = subprocess.Popen([PY, "-I", str(RAIZ / "bin" / "arranque.py"), "supervisar", "--lanzador", "app"],
                             env=dict(cfg_lento, JARVIS_ARRANQUE_PRUEBA=json.dumps(cfg), JARVIS_MIC_APP="autorizado"),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        self.esperar(lambda: "reinicio 1/2" in self.log(), msg="reinicio pendiente")
        p.send_signal(signal.SIGTERM)
        p.wait(10)
        time.sleep(0.3)
        self.assertEqual(len(self.pids("voz")), 1)                      # el reinicio pendiente no ocurrió


class T04_CaidaRecuperacionLimitada(Base):
    def test_voz_se_cae_siempre(self):
        self.cmds = self.comandos(voz="cae")
        a = self.supervisor()
        self.esperar(lambda: self.estado().get("estado") == "error", msg="error tras agotar intentos")
        self.assertEqual(len(self.pids("voz")), 4)                      # 1 + 3 reinicios, ni uno más
        time.sleep(1.0)
        self.assertEqual(len(self.pids("voz")), 4)
        self.assertIn("se cayó 4 veces", self.estado()["hijos"]["voz"]["error"])
        self.assertIsNone(a.poll())                                     # sigue vivo: agenda, menú y estado

    def test_agenda_se_cae_una_vez(self):
        self.supervisor()
        self.listo()
        os.killpg(self.pids("agenda")[0], signal.SIGKILL)
        self.esperar(lambda: len(self.pids("agenda")) == 2, msg="agenda reiniciada")
        self.assertIn("reinicio 1/3", self.log())

    def test_codigo_fatal_no_se_reintenta(self):
        self.cmds = self.comandos(voz="fatal")
        self.supervisor()
        self.esperar(lambda: self.estado().get("estado") == "error", msg="error")
        time.sleep(1.0)
        self.assertEqual(len(self.pids("voz")), 1)


class T05_CaidaDelSupervisor(Base):
    def test_hijos_se_apagan_solos(self):
        a = self.supervisor()
        self.listo()
        voz, agenda = self.pids("voz")[0], self.pids("agenda")[0]
        a.kill(); a.wait()
        self.esperar(lambda: not vivo(voz) and not vivo(agenda), msg="voz y agenda sin dueño se apagan")
        self.esperar(lambda: arranque_libre(self.casa), msg="candado libre")
        b = self.supervisor()
        self.listo(b)
        self.assertEqual(len([p for p in self.pids("voz") if vivo(p)]), 1)
        self.assertIsNone(b.poll())

    def test_hijo_terco_retiene_el_candado(self):
        self.cmds = self.comandos(voz="terco")
        a = self.supervisor()
        self.listo()
        a.kill(); a.wait()
        time.sleep(0.5)
        terco = self.pids("voz")[0]
        self.assertTrue(vivo(terco))
        b = self.supervisor()
        b.wait(10)
        self.assertIn("ya está activo", b.stdout.read())                 # no se duplica
        codigo, salida = self.ctl("estado")
        self.assertEqual(codigo, 2, salida)
        codigo, salida = self.ctl("detener")                            # ruta de emergencia, por identidad
        self.assertEqual(codigo, 0, salida)
        self.assertFalse(vivo(terco))
        linea = [l for l in self.log().splitlines() if "hijos sin supervisor terminados" in l]
        self.assertEqual(len(linea), 1); self.assertIn("voz", linea[0])


class T06_ParadaDuranteTTS(Base):
    voz = "tts"

    def test_sin_voces_huerfanas(self):
        a = self.supervisor()
        self.listo()
        pgid = int((self.casa / "tts_pgid").read_text())
        self.assertTrue(grupo_vivo(pgid))
        a.send_signal(signal.SIGTERM)
        a.wait(15)
        self.esperar(lambda: not grupo_vivo(pgid), t=3, msg="reproductor propio terminado")

    def test_registro_de_voces(self):
        falso = mock.Mock(); falso.poll.return_value = None
        with mock.patch.object(streaming.subprocess, "Popen", return_value=falso):
            p = streaming.lanzar_decir("hola")
        self.assertIn(p, streaming.VOCES)
        with mock.patch.object(streaming, "matar_grupo") as m:
            streaming.limpiar_voces()
        m.assert_called_once_with(falso, gracia=0.3)
        self.assertNotIn(p, streaming.VOCES)


class T07_DependenciaYPermiso(Base):
    def test_dependencia_ausente(self):
        self.entorno = 1
        self.cmds = self.comandos()
        a = self.supervisor()
        self.esperar(lambda: self.estado().get("estado") == "error", msg="error")
        time.sleep(0.6)
        self.assertEqual(self.pids("voz"), [])                          # ni lo intentó
        self.assertIsNone(self.estado().get("listo_s"))                 # sin falso «listo»
        self.assertIn("entorno de voz incompleto", self.log())
        self.assertIn("(aviso)", self.log())

    def test_microfono_denegado(self):
        self.supervisor(mic="denegado")
        self.esperar(lambda: self.estado().get("estado") == "error", msg="error")
        time.sleep(0.6)
        self.assertEqual(self.pids("voz"), [])
        self.assertIn("micrófono denegado", self.estado()["hijos"]["voz"]["error"])
        self.assertEqual(len(self.pids("agenda")), 1)                   # lo demás sigue

    def test_falta_uv_en_arranque_sh(self):
        home = pathlib.Path(self.tmp.name) / "home sin uv"
        home.mkdir()
        r = subprocess.run(["/bin/bash", str(RAIZ / "bin" / "arranque.sh"), "app"],
                           env={"HOME": str(home), "PATH": "/usr/bin:/bin", "JARVIS_CASA": str(self.casa)},
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 4)
        self.assertIn("falta uv", self.log())


class T08_EntornoMinimoYEspacios(Base):
    def test_arranca(self):
        self.assertIn(" ", str(self.casa)); self.assertIn(" ", str(self.falso))
        self.supervisor()                                               # PATH, HOME y JARVIS_CASA nada más
        self.listo()
        self.assertGreaterEqual(self.estado()["listo_s"], 0.2)

    def test_arranque_sh_entorno_explicito(self):
        texto = (RAIZ / "bin" / "arranque.sh").read_text()
        for x in ("UV_OFFLINE=1", "HF_HUB_OFFLINE=1", "unset PYTHONPATH", "/usr/bin/python3 -I"):
            self.assertIn(x, texto)
        self.assertNotIn("iniciar.sh", texto.split("case")[1])          # nunca el camino que instala uv
        voz = arranque.comandos()["voz"]
        self.assertEqual(voz[:3], [str(arranque.UV), "run", "--offline"])


class T09_Hammerspoon(Base):
    hs = False

    def test_antes_despues_y_recarga(self):
        self.supervisor()
        self.esperar(lambda: self.estado().get("estado") == "integracion_pendiente", msg="sin Hammerspoon")
        (self.casa / "hs").write_text("1")                               # abre después
        self.listo()
        (self.casa / "hs").unlink()                                      # recarga / cierre
        self.esperar(lambda: self.estado().get("estado") == "integracion_pendiente", msg="se fue")
        (self.casa / "hs").write_text("1")
        self.listo()
        self.assertEqual(len(self.pids("voz")), 1)                       # nada de eso reinicia la voz


class T10_ElementosDeInicio(unittest.TestCase):
    class Sistema:
        def __init__(self):
            self.items = [("Jarvis.command", "/Users/jp/Documents/Jarvis/Jarvis.command"),
                          ("Hammerspoon", "/Users/jp/Applications/Hammerspoon.app")]

        def __call__(self, script):
            if "delete" in script:
                n = script.split('name is "')[1].split('"')[0]
                self.items = [x for x in self.items if x[0] != n]
            elif "make login item" in script:
                ruta = script.split('path:"')[1].split('"')[0]
                nombre = pathlib.Path(ruta).name
                self.items.append((nombre[:-4] if nombre.endswith(".app") else nombre, ruta))
            elif "every login item" in script:
                return 0, "".join(f"{n}\t{r}\n" for n, r in self.items)
            return 0, ""

    def test_cambio_y_rollback_repetibles(self):
        s = self.Sistema()
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        app, comando = pathlib.Path(tmp.name) / "Jarvis.app", pathlib.Path(tmp.name) / "Jarvis.command"
        app.mkdir(); comando.write_text("")
        with mock.patch.object(arranque, "APP", app), mock.patch.object(arranque, "COMANDO", comando), \
                mock.patch.object(arranque, "anotar"), mock.patch("builtins.print"):
            for modo in ("app", "app", "terminal", "app", "terminal", "terminal", "app"):
                self.assertEqual(arranque.cmd_inicio(modo, osa=s), 0)
                jarvis = [x for x in s.items if x[0] in arranque.NOMBRES_JARVIS]
                self.assertEqual(len(jarvis), 1, s.items)
                self.assertIn(("Hammerspoon", "/Users/jp/Applications/Hammerspoon.app"), s.items)

    def test_instalador_registra_solo_la_app(self):
        t = (RAIZ / "scripts" / "instalar_todo.sh").read_text()
        self.assertIn("arranque.py\" inicio app", t)
        self.assertNotIn('path:\\"$JARVIS/Jarvis.command', t)

    def test_jarvis_command_usa_el_supervisor(self):
        t = (RAIZ / "Jarvis.command").read_text()
        self.assertIn("arranque.sh\" terminal", t)
        for prohibido in ("pkill", "pgrep", "killall"):
            self.assertNotIn(prohibido, t)
        self.assertTrue((RAIZ / "Jarvis.command.pre08").exists())


class T09b_HammerspoonInterfaz(unittest.TestCase):
    """Lua no se prueba aquí: se revisa que las piezas estén (física D y reapertura las confirman)."""
    def setUp(self):
        self.lua = (RAIZ / "hammerspoon" / "init.lua").read_text()

    def test_menu_no_se_lo_lleva_el_recolector(self):
        self.assertIn("jarvisMenu = hs.menubar.new()", self.lua)
        self.assertNotIn("local menu = hs.menubar.new()", self.lua)
        for global_ in ("estadoWatcher = hs.pathwatcher", "jarvisWatcher = hs.application.watcher"):
            self.assertIn(global_, self.lua)

    def test_reapertura_avisa(self):
        self.assertIn('"mx.jpmuro.jarvis"', self.lua)
        self.assertIn("Jarvis ya está activo, señor.", self.lua)
        bloque = self.lua.split("jarvisWatcher")[1]
        self.assertNotIn("arranque", bloque.split("hs.alert.show")[0].replace("arranque_estado.json", ""))
        for menu in ('{ "arranque", "estado" }', '{ "arranque", "detener" }', '{ "arranque", "abrir" }'):
            self.assertIn(menu, self.lua)


class T11_RegistroSinDatosPrivados(Base):
    def test_log_y_estado(self):
        a = self.supervisor()
        self.listo()
        self.ctl("detener"); a.wait(10)
        for f in ("arranque.log", "arranque_estado.json"):
            texto = (self.casa / f).read_text()
            self.assertNotIn("SECRETO", texto, f)
            self.assertNotIn("JARVIS_ARRANQUE_PRUEBA", texto, f)
            self.assertNotIn("HOME", texto, f)
            self.assertEqual(oct((self.casa / f).stat().st_mode & 0o777), "0o600", f)
        self.assertEqual(oct((self.casa / "jarvis.lock").stat().st_mode & 0o777), "0o600")


class T12_ControlesFueraDelAsistente(unittest.TestCase):
    """Instalar, parar y rollback no son comandos del modo asistente (igual que `jv memoria`)."""
    def test_jv_arranque_bloqueado(self):
        import guardia
        bash = lambda c: guardia.decidir({"tool_name": "Bash", "tool_input": {"command": c}, "cwd": str(RAIZ)})[0]
        for cmd in ("bin/jv arranque detener", "bin/jv arranque inicio terminal", "jv arranque estado",
                    f"{RAIZ}/bin/jv arranque abrir", "/usr/bin/python3 bin/arranque.py detener",
                    "python3 bin/arranque.py inicio app", "bash bin/arranque.sh terminal",
                    "Jarvis.command", "./Jarvis.command"):
            self.assertFalse(bash(cmd), cmd)
        self.assertTrue(bash("bin/jv latencia"))                          # lo permitido sigue permitido
        self.assertNotIn("arranque", guardia.JV_LOCALES)


def arranque_libre(casa):
    import fcntl
    f = casa / "jarvis.lock"
    if not f.exists():
        return True
    fd = os.open(f, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


if __name__ == "__main__":
    unittest.main()
