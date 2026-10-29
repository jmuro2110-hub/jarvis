"""J.A.R.V.I.S. — supervisor de arranque (upgrade 08). Solo biblioteca estándar; corre con /usr/bin/python3 (3.9).

Lo usan igual Jarvis.app y Jarvis.command (vía bin/arranque.sh). Es el ÚNICO dueño de voz, agenda y caffeinate:
- Candado real: fcntl.flock sobre ~/.jarvis/jarvis.lock, tomado antes de arrancar nada y heredado por voz y
  agenda (pass_fds): el SO no lo suelta mientras viva cualquiera de ellos. Una segunda apertura dice
  «Jarvis ya está activo» y sale sin tocar a la primera.
- Tubo vigía: si el supervisor muere (incluso con SIGKILL) se cierra su extremo y voz y agenda se apagan solas
  (comun.vigilar_supervisor): nada se queda escuchando sin dueño.
- Hijos anotados con PID + identidad (hora de inicio y comando según ps). Solo se terminan esos, por grupo
  (cada uno en su propia sesión). La voz limpia sus reproductores de streaming al recibir SIGTERM.
- Caídas: esperas crecientes y tope de intentos; los códigos de salida FATALES y los permisos denegados no se
  reintentan. Parar a propósito cancela cualquier reinicio pendiente.
- Estados: iniciando, escuchando, integracion_pendiente, detenido, error ("listo" = la voz avisó que ya escucha).
- Registro técnico ~/.jarvis/arranque.log (0600): arranques, paradas, códigos. Nunca conversación ni entorno.

Comandos (bin/jv arranque …, o en emergencia /usr/bin/python3 ~/Documents/Jarvis/bin/arranque.py …):
  supervisar --lanzador app|terminal     lo llama arranque.sh; no se usa a mano
  estado | detener | abrir               lo que ofrece el menú de Hammerspoon
  inicio ver|app|terminal                elemento de inicio de sesión (migración y rollback)
"""
import fcntl, json, os, pathlib, signal, subprocess, sys, time

JARVIS = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path.home()
CASA = pathlib.Path(os.environ.get("JARVIS_CASA") or HOME / ".jarvis")
CANDADO = CASA / "jarvis.lock"
ESTADO = CASA / "arranque_estado.json"
LOG = CASA / "arranque.log"
LISTA = CASA / "voz_lista"                # la voz lo escribe cuando ya puede escuchar
APP = HOME / "Applications" / "Jarvis.app"
COMANDO = JARVIS / "Jarvis.command"
UV = HOME / ".local" / "bin" / "uv"

ESPERAS = (5, 15, 30, 60, 120)            # entre reinicios; agotadas = error
ESTABLE_S = 600                           # un hijo que aguantó esto vuelve a tener todos los intentos
FATALES = (3, 4, 5)                       # salida sin reintento (permiso, dependencia, configuración)
HS_CADA, HS_INTENTOS = 30, 40             # Hammerspoon: revisar cada 30 s, como mucho 20 min
GRACIA = 8                                # SIGTERM → SIGKILL (Jarvis.app espera 15 s)
LOG_MAX = 200 * 1024


def config_prueba():
    """Solo para tests/test_arranque.py: comandos falsos, esperas cortas y sin ventanas."""
    c = os.environ.get("JARVIS_ARRANQUE_PRUEBA")
    return json.loads(c) if c else None


def comandos():
    p = config_prueba()
    if p:
        return p["cmds"]
    voz = str(JARVIS / "voz" / "jarvis_voz.py")
    return {"entorno": [str(UV), "run", "--offline", "--quiet", "--script", voz, "--entorno"],
            "voz": [str(UV), "run", "--offline", "--script", voz],
            "agenda": [str(UV), "run", "--offline", "--quiet", "--script", str(JARVIS / "bin" / "agenda.py")],
            "caffeinate": ["/usr/bin/caffeinate", "-i", "-w", "{supervisor}"],
            "hammerspoon": ["/usr/bin/pgrep", "-x", "Hammerspoon"]}


# ---------------------------------------------------------------- utilidades
def anotar(msg, eco=False):
    CASA.mkdir(mode=0o700, exist_ok=True)
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_MAX:
            LOG.write_bytes(LOG.read_bytes()[-LOG_MAX // 2:])
    except OSError:
        pass
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f"{time.strftime('%F %T')} {msg}\n")
    if eco:
        print(msg, flush=True)


def identidad(pid):
    """PID + hora de inicio según ps: un PID reciclado no coincide. El comando no entra porque cambia con exec
    (/usr/bin/python3 se vuelve el Python de las herramientas; un hijo recién creado aún no ha hecho exec).
    Siempre con LC_ALL=C: el supervisor corre con LANG=es_MX («jue. 29 oct») y Hammerspoon sin LANG («Thu Oct 29»);
    sin esto, «Detener Jarvis» desde el menú no reconocía al supervisor y no paraba nada (física G, 2026-10-29)."""
    try:
        r = subprocess.run(["/bin/ps", "-o", "stat=", "-o", "lstart=", "-p", str(int(pid))],
                           capture_output=True, text=True, timeout=5, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"})
    except Exception:
        return None
    partes = r.stdout.split(None, 1)
    if len(partes) != 2 or partes[0].startswith("Z"):       # zombi: ya terminó, solo falta que lo recojan
        return None
    return partes[1].strip()


def escribir_estado(datos):
    tmp = ESTADO.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ESTADO)


def leer_estado():
    try:
        return json.loads(ESTADO.read_text())
    except Exception:
        return None


def candado_libre():
    """Prueba sin quedarse con él: True si nadie (supervisor ni hijos) lo tiene."""
    if not CANDADO.exists():
        return True
    fd = os.open(CANDADO, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def avisar(texto):
    """Error visible aunque no haya Terminal. `display alert` no necesita permisos de Automatización."""
    if config_prueba() is not None:
        anotar(f"(aviso) {texto}")
        return
    t = texto.replace("\\", "").replace('"', "'")
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display alert "J.A.R.V.I.S." message "{t}" as critical giving up after 120'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


# ---------------------------------------------------------------- supervisor
class Hijo:
    def __init__(self, nombre, cmd, cwd):
        self.nombre, self.cmd, self.cwd = nombre, cmd, cwd
        self.proc, self.ident, self.desde = None, None, 0.0
        self.intentos, self.siguiente, self.error = 0, None, ""

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None


class Supervisor:
    def __init__(self, lanzador, mic):
        self.lanzador, self.mic = lanzador, mic
        self.terminal = lanzador == "terminal"
        p = config_prueba() or {}
        self.esperas = p.get("esperas", ESPERAS)
        self.estable_s = p.get("estable_s", ESTABLE_S)
        self.hs_cada, self.hs_intentos = p.get("hs_cada", HS_CADA), p.get("hs_intentos", HS_INTENTOS)
        self.gracia = p.get("gracia", GRACIA)
        self.cmds = comandos()
        self.parar = False
        self.hijos = {}
        self.listo_s, self.t0 = None, time.monotonic()
        self.hs_ok, self.hs_n, self.hs_t = False, 0, -1e9
        self.ultimo = None

    # señales: salir de la app, SIGTERM, Ctrl+C, cerrar la ventana de Terminal, cierre de sesión
    def _pedir_parada(self, sig, _frame):
        if not self.parar:
            anotar(f"parada pedida (señal {signal.Signals(sig).name})")
        self.parar = True

    def tomar_candado(self):
        CASA.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(CANDADO, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        return fd

    def correr(self):
        self.candado = self.tomar_candado()
        if self.candado is None:
            anotar(f"segunda apertura ({self.lanzador}): Jarvis ya está activo; no se tocó a nadie")
            print("Jarvis ya está activo, señor. No toqué la instancia que está corriendo.", flush=True)
            if not self.terminal and config_prueba() is None:
                subprocess.run(["/usr/bin/osascript", "-e", 'display notification "Jarvis ya está activo, señor." '
                                'with title "J.A.R.V.I.S."'], capture_output=True, timeout=10)
            return 0
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s, self._pedir_parada)
        self.vigia_r, self.vigia_w = os.pipe()
        st = os.fstat(self.vigia_r)
        self.vigia_id = f"{st.st_dev}:{st.st_ino}"
        self.ident = identidad(os.getpid())
        anotar(f"supervisor iniciado (lanzador {self.lanzador}, micrófono según la app: {self.mic}, pid {os.getpid()})",
               eco=self.terminal)
        LISTA.unlink(missing_ok=True)
        self.hijos["caffeinate"] = Hijo("caffeinate", [a.replace("{supervisor}", str(os.getpid()))
                                                       for a in self.cmds["caffeinate"]], str(JARVIS))
        self.hijos["agenda"] = Hijo("agenda", self.cmds["agenda"], str(JARVIS))
        self.hijos["voz"] = Hijo("voz", self.cmds["voz"], str(JARVIS / "voz"))
        self.publicar()
        for n in ("caffeinate", "agenda"):
            self.lanzar(self.hijos[n])
        voz = self.hijos["voz"]
        if self.mic in ("denegado", "restringido"):
            self.fatal(voz, f"micrófono {self.mic} para Jarvis.app: Ajustes → Privacidad y seguridad → Micrófono")
        elif not self.parar:
            falta = self.verificar_entorno()
            if falta:
                self.fatal(voz, falta)
            elif not self.parar:
                self.lanzar(voz)
        try:
            while not self.parar:
                self.vuelta()
                time.sleep(0.2)
        finally:
            self.apagar()
        return 0

    def verificar_entorno(self):
        """Sin red y sin instalar: si falta uv, el entorno de la voz o los modelos, se dice qué y no se reintenta."""
        cmd = self.cmds["entorno"]
        if not os.path.exists(cmd[0]) and os.path.sep in cmd[0]:
            return f"falta {cmd[0]} (no se instala solo)"
        try:
            r = subprocess.run(cmd, cwd=str(JARVIS / "voz"), stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return "la revisión del entorno de voz tardó más de 3 min"
        except OSError as e:
            return f"no se pudo revisar el entorno de voz ({type(e).__name__})"
        if r.returncode != 0:
            ultima = (r.stderr.strip().splitlines() or ["?"])[-1][:160]
            return f"entorno de voz incompleto sin red (código {r.returncode}): {ultima}"
        return ""

    def fatal(self, h, motivo):
        h.error, h.siguiente = motivo, None
        anotar(f"error en {h.nombre}: {motivo} (sin reintentos)", eco=self.terminal)
        avisar(f"Jarvis no puede usar la {h.nombre}: {motivo}")
        self.publicar()

    def lanzar(self, h):
        env = dict(os.environ, JARVIS_SUPERVISADO="1", JARVIS_VIGIA_FD=str(self.vigia_r),
                   JARVIS_VIGIA_ID=self.vigia_id)
        if h.nombre == "voz":
            LISTA.unlink(missing_ok=True)
            self.listo_s = None
            salida = None if self.terminal else subprocess.DEVNULL     # en Terminal se ve como siempre
            err = None if self.terminal else self._archivo("voz.err")
        elif h.nombre == "agenda":
            salida = err = self._archivo("agenda.out")
        else:
            salida = err = subprocess.DEVNULL
        fds = (self.candado, self.vigia_r) if h.nombre != "caffeinate" else ()
        try:
            h.proc = subprocess.Popen(h.cmd, cwd=h.cwd, env=env, stdin=subprocess.DEVNULL, stdout=salida,
                                      stderr=err, start_new_session=True, pass_fds=fds)
        except OSError as e:
            self.fatal(h, f"no arrancó ({type(e).__name__})")
            return
        finally:
            for f in (salida, err):
                if hasattr(f, "close"):
                    f.close()
        h.ident, h.desde, h.siguiente, h.error = identidad(h.proc.pid), time.monotonic(), None, ""
        anotar(f"{h.nombre} arrancó (pid {h.proc.pid}, intento {h.intentos + 1})")
        self.publicar()

    def _archivo(self, nombre):
        ruta = CASA / nombre
        try:
            if ruta.exists() and ruta.stat().st_size > LOG_MAX:
                ruta.write_bytes(ruta.read_bytes()[-LOG_MAX // 2:])
        except OSError:
            pass
        return os.fdopen(os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "ab")

    def vuelta(self):
        ahora = time.monotonic()
        for h in self.hijos.values():
            if h.proc is not None and h.proc.poll() is not None:
                self.cayo(h, h.proc.returncode, ahora)
            if h.siguiente is not None and ahora >= h.siguiente and not self.parar:
                self.lanzar(h)
        voz = self.hijos["voz"]
        if self.listo_s is None and voz.vivo() and LISTA.exists():
            self.listo_s = round(ahora - voz.desde, 1)
            anotar(f"voz lista: escuchando ({self.listo_s} s desde que arrancó)", eco=self.terminal)
        if not self.hs_ok and self.hs_n < self.hs_intentos and ahora - self.hs_t >= self.hs_cada:
            self.hs_t, self.hs_n = ahora, self.hs_n + 1
            self.hs_ok = subprocess.run(self.cmds["hammerspoon"], capture_output=True).returncode == 0
            if self.hs_ok:
                anotar("Hammerspoon presente")
            elif self.hs_n == self.hs_intentos:
                anotar("Hammerspoon no apareció: atajos no disponibles (se deja de revisar)")
        elif self.hs_ok and ahora - self.hs_t >= self.hs_cada:      # sigue ahí (o lo cerraron / recargaron)
            self.hs_t = ahora
            self.hs_ok = subprocess.run(self.cmds["hammerspoon"], capture_output=True).returncode == 0
            if not self.hs_ok:
                self.hs_n = 0
                anotar("Hammerspoon ya no está: integración pendiente")
        self.publicar()

    def cayo(self, h, codigo, ahora):
        duro = ahora - h.desde
        h.proc = None
        if h.nombre == "voz":
            LISTA.unlink(missing_ok=True)
            self.listo_s = None
        if self.parar:
            return
        anotar(f"{h.nombre} terminó con código {codigo} tras {duro:.0f} s")
        if codigo in FATALES:
            self.fatal(h, f"salió con código {codigo} (permiso o dependencia: ver {h.nombre} y arranque.log)")
            return
        if duro >= self.estable_s:
            h.intentos = 0
        if h.intentos >= len(self.esperas):
            self.fatal(h, f"se cayó {h.intentos + 1} veces seguidas")
            return
        espera = self.esperas[h.intentos]
        h.intentos += 1
        h.siguiente = ahora + espera
        anotar(f"{h.nombre}: reinicio {h.intentos}/{len(self.esperas)} en {espera} s")

    def estado_general(self):
        voz = self.hijos.get("voz")
        if self.parar:
            return "detenido" if not any(h.vivo() for h in self.hijos.values()) else "deteniendo"
        if voz is None or voz.error:
            return "error"
        if self.listo_s is None:
            return "iniciando"
        return "escuchando" if self.hs_ok else "integracion_pendiente"

    def publicar(self):
        datos = {"estado": self.estado_general(), "lanzador": self.lanzador, "mic_app": self.mic,
                 "supervisor": {"pid": os.getpid(), "ident": self.ident},
                 "listo_s": self.listo_s, "hammerspoon": self.hs_ok,
                 "hijos": {n: {"pid": h.proc.pid if h.vivo() else None, "ident": h.ident if h.vivo() else None,
                               "intentos": h.intentos, "error": h.error,
                               "reinicio_en_s": round(h.siguiente - time.monotonic(), 1) if h.siguiente else None}
                           for n, h in self.hijos.items()}}
        clave = json.dumps(datos, sort_keys=True)
        if clave != self.ultimo:
            self.ultimo = clave
            datos["actualizado"] = time.strftime("%F %T")
            escribir_estado(datos)

    def apagar(self):
        """Voz y agenda primero (SIGTERM a su grupo: la voz suelta el micrófono y calla sus reproductores),
        caffeinate al final. SIGKILL a lo que no salga a tiempo. Ningún reinicio pendiente sobrevive."""
        self.parar = True
        for h in self.hijos.values():
            h.siguiente = None
        self.publicar()
        orden = [self.hijos[n] for n in ("voz", "agenda", "caffeinate") if n in self.hijos]
        for h in orden:
            matar_grupo(h, signal.SIGTERM)
        limite = time.monotonic() + self.gracia
        while time.monotonic() < limite and any(h.vivo() or grupo_vivo(h) for h in orden):
            time.sleep(0.1)
        forzados = [h.nombre for h in orden if h.vivo() or grupo_vivo(h)]
        for h in orden:
            matar_grupo(h, signal.SIGKILL)
            if h.proc is not None:
                try:
                    h.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        if forzados:
            anotar(f"no salieron a tiempo (SIGKILL): {', '.join(forzados)}")
            matar_voces_huerfanas()
        LISTA.unlink(missing_ok=True)
        self.publicar()
        anotar("supervisor detenido: voz, agenda y caffeinate terminados", eco=self.terminal)


def matar_grupo(h, sig):
    """Cada hijo es líder de su sesión: su grupo es su PID. Solo hijos con Popen propio (PID no reciclable)."""
    if h.proc is None:
        return
    try:
        os.killpg(h.proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def grupo_vivo(h):
    if h.proc is None:
        return False
    try:
        os.killpg(h.proc.pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def matar_voces_huerfanas():
    """Solo si la voz no salió por las buenas: los `decir.py` de streaming viven en su propia sesión.
    Se identifican por la ruta exacta de NUESTRO decir.py y por ser líderes de su grupo; nunca `say` a secas."""
    decir = str(JARVIS / "bin" / "decir.py")
    r = subprocess.run(["/bin/ps", "-axo", "pid=,pgid=,command="], capture_output=True, text=True)
    for linea in r.stdout.splitlines():
        partes = linea.split(None, 2)
        if len(partes) == 3 and partes[0] == partes[1] and decir in partes[2]:
            try:
                os.killpg(int(partes[0]), signal.SIGKILL)
                anotar(f"voz de streaming huérfana terminada (pid {partes[0]})")
            except (ProcessLookupError, PermissionError):
                pass


# ---------------------------------------------------------------- comandos de control
def _vivo_con_identidad(info):
    return bool(info and info.get("pid") and info.get("ident") and identidad(info["pid"]) == info["ident"])


def cmd_estado():
    st = leer_estado()
    libre = candado_libre()
    if libre:
        print("Jarvis: detenido." + (f" Último estado: {st['estado']} ({st.get('actualizado', '?')})." if st else ""))
        return 1
    if not st or not _vivo_con_identidad(st.get("supervisor")):
        print("Jarvis: hay procesos de una instancia sin supervisor (o el modo antiguo de Terminal). "
              "Use «Detener Jarvis» antes de abrir otro.")
        return 2
    voz = st["hijos"].get("voz", {})
    linea = {"iniciando": "iniciando (cargando la voz)", "escuchando": "escuchando",
             "integracion_pendiente": "escuchando; Hammerspoon pendiente (sin atajos)",
             "error": "error", "deteniendo": "deteniéndose", "detenido": "detenido"}.get(st["estado"], st["estado"])
    print(f"Jarvis: {linea}. Desde {st['lanzador']}." +
          (f" Listo en {st['listo_s']} s." if st.get("listo_s") is not None else "") +
          (f" Voz: {voz['error']}" if voz.get("error") else ""))
    return 0


def cmd_detener(espera=20):
    """Ruta normal y de emergencia: no depende de la app. Termina SOLO procesos verificados de Jarvis."""
    st = leer_estado() or {}
    sup = st.get("supervisor")
    if _vivo_con_identidad(sup):
        os.kill(sup["pid"], signal.SIGTERM)
        limite = time.monotonic() + espera
        while time.monotonic() < limite and identidad(sup["pid"]) == sup["ident"]:
            time.sleep(0.2)
        if identidad(sup["pid"]) == sup["ident"]:
            anotar("detener: el supervisor no respondió en 20 s; SIGKILL")
            os.kill(sup["pid"], signal.SIGKILL)
            time.sleep(0.5)
    sobrantes = []
    for nombre, h in (st.get("hijos") or {}).items():
        if _vivo_con_identidad(h):
            sobrantes.append(nombre)
            try:
                os.killpg(h["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    if sobrantes:
        anotar(f"detener: hijos sin supervisor terminados: {', '.join(sobrantes)}")
        limite = time.monotonic() + (config_prueba() or {}).get("gracia", GRACIA)
        while time.monotonic() < limite and any(_vivo_con_identidad(st["hijos"][n]) for n in sobrantes):
            time.sleep(0.2)
        for n in sobrantes:
            if _vivo_con_identidad(st["hijos"][n]):
                try:
                    os.killpg(st["hijos"][n]["pid"], signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        matar_voces_huerfanas()
    limite = time.monotonic() + 3
    while time.monotonic() < limite and not candado_libre():
        time.sleep(0.2)
    if candado_libre():
        print("Jarvis detenido, señor. Micrófono libre.")
        return 0
    print("Jarvis sigue con el candado tomado por un proceso que no reconozco como suyo; no lo toqué. "
          "Revise ~/.jarvis/arranque.log.")
    return 1


def cmd_abrir(abrir=None):
    if not candado_libre():
        print("Jarvis ya está activo, señor.")
        return 0
    if not APP.exists():
        print(f"No encuentro {APP}. Respaldo: abra {COMANDO}.")
        return 1
    (abrir or (lambda: subprocess.run(["/usr/bin/open", str(APP)], check=False)))()
    print("Abriendo Jarvis, señor.")
    return 0


# ---------------------------------------------------------------- elemento de inicio de sesión
NOMBRES_JARVIS = ("Jarvis.command", "Jarvis")


def osa(script):
    r = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout.strip() or r.stderr.strip()


def elementos(osa=osa):
    c, out = osa('tell application "System Events" to set l to every login item\n'
                 'set s to ""\nrepeat with i in l\nset s to s & (name of i) & tab & (path of i) & linefeed\n'
                 'end repeat\nreturn s')
    if c != 0:
        raise RuntimeError(f"System Events no respondió: {out[:120]}")
    return [tuple(x.split("\t", 1)) for x in out.splitlines() if "\t" in x]


def cmd_inicio(modo, osa=osa):
    """Cambia SOLO el elemento de Jarvis (mismo mecanismo que scripts/instalar_todo.sh). Hammerspoon y los
    demás se quedan. Repetible: borra las dos variantes de Jarvis y deja exactamente una."""
    if modo not in ("ver", "app", "terminal"):
        print("uso: arranque inicio ver|app|terminal")
        return 2
    if modo != "ver":
        ruta = APP if modo == "app" else COMANDO
        if not ruta.exists():
            print(f"No existe {ruta}: no cambio nada.")
            return 1
        for n in NOMBRES_JARVIS:
            osa(f'tell application "System Events" to delete (every login item whose name is "{n}")')
        c, out = osa(f'tell application "System Events" to make login item at end with properties '
                     f'{{path:"{ruta}", hidden:false}}')
        if c != 0:
            print(f"No pude registrar {ruta.name}: {out[:120]}")
            return 1
        anotar(f"elemento de inicio de Jarvis: {ruta}")
    lista = elementos(osa)
    for nombre, ruta in lista:
        print(f"{nombre}\t{ruta}")
    jarvis = [x for x in lista if x[0] in NOMBRES_JARVIS]
    if modo != "ver" and len(jarvis) != 1:
        print(f"Atención: {len(jarvis)} elementos de Jarvis registrados.")
        return 1
    return 0


def main(argv):
    if not argv:
        print(__doc__.split("Comandos", 1)[1])
        return 2
    c, resto = argv[0], argv[1:]
    if c == "supervisar":
        lanzador = resto[resto.index("--lanzador") + 1] if "--lanzador" in resto else "?"
        return Supervisor(lanzador, os.environ.get("JARVIS_MIC_APP", "no aplica")).correr()
    if c == "estado":
        return cmd_estado()
    if c == "detener":
        return cmd_detener()
    if c == "abrir":
        return cmd_abrir()
    if c == "inicio":
        return cmd_inicio(resto[0] if resto else "ver")
    print(f"comando desconocido: {c}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
