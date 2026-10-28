// J.A.R.V.I.S. — lanzador nativo (upgrade 08). Se compila UNA vez: toda la lógica vive en el proyecto.
// Pide el micrófono con el mecanismo normal de macOS, arranca `bin/arranque.sh app` como hijo (su propio
// grupo de procesos), le reenvía SIGTERM/SIGINT/SIGHUP y la salida de la app (cierre de sesión), y termina
// cuando termina el hijo. Si el hijo sale con error, lo dice en una alerta; nunca lo reinicia.
// Recompilar cambia el cdhash (firma ad-hoc): macOS puede volver a pedir micrófono y Automatización.
import AppKit
import AVFoundation

let SCRIPT = NSHomeDirectory() + "/Documents/Jarvis/bin/arranque.sh"
var hijo: pid_t = 0
var saliendo = false
var esperandoSalida = false               // applicationShouldTerminate respondió .terminateLater

func avisarHijo(_ sig: Int32) {
    if hijo > 0 { kill(-hijo, sig) }          // al grupo: el supervisor y lo que no se haya separado
}

func lanzar(mic: String) -> pid_t {
    var env = ProcessInfo.processInfo.environment
    env["JARVIS_LANZADOR"] = "app"
    env["JARVIS_MIC_APP"] = mic
    let envp = env.map { strdup("\($0.key)=\($0.value)") } + [nil]
    let argv = [strdup("/bin/bash"), strdup(SCRIPT), strdup("app"), nil]
    var attr: posix_spawnattr_t? = nil
    posix_spawnattr_init(&attr)
    posix_spawnattr_setflags(&attr, Int16(POSIX_SPAWN_SETPGROUP))
    posix_spawnattr_setpgroup(&attr, 0)
    var pid: pid_t = 0
    let r = posix_spawn(&pid, "/bin/bash", nil, &attr, argv, envp)
    posix_spawnattr_destroy(&attr)
    return r == 0 ? pid : -1
}

func alerta(_ texto: String) {
    NSApp.activate(ignoringOtherApps: true)
    let a = NSAlert()
    a.messageText = "J.A.R.V.I.S."
    a.informativeText = texto
    a.runModal()
}

class Delegado: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        let estado = AVCaptureDevice.authorizationStatus(for: .audio)
        if estado == .notDetermined {
            AVCaptureDevice.requestAccess(for: .audio) { ok in
                DispatchQueue.main.async { self.arrancar(ok ? "autorizado" : "denegado") }
            }
        } else {
            arrancar(estado == .authorized ? "autorizado" : (estado == .denied ? "denegado" : "restringido"))
        }
    }

    func arrancar(_ mic: String) {
        hijo = lanzar(mic: mic)
        if hijo <= 0 {
            alerta("No pude arrancar \(SCRIPT).")
            NSApp.terminate(nil); return
        }
        DispatchQueue.global().async {
            var st: Int32 = 0
            while waitpid(hijo, &st, 0) == -1 && errno == EINTR {}
            let codigo = (st & 0x7f) == 0 ? (st >> 8) & 0xff : 128 + (st & 0x7f)
            DispatchQueue.main.async {
                hijo = 0
                if codigo != 0 && !saliendo {
                    alerta("Jarvis se detuvo con error (código \(codigo)).\nRegistro: ~/.jarvis/arranque.log")
                }
                saliendo = true
                if esperandoSalida {
                    esperandoSalida = false
                    NSApp.reply(toApplicationShouldTerminate: true)
                } else {
                    NSApp.terminate(nil)
                }
            }
        }
    }

    // Salir (Monitor de Actividad, cierre de sesión, apagado): el supervisor limpia y luego salimos.
    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        if hijo <= 0 { return .terminateNow }
        saliendo = true
        esperandoSalida = true
        avisarHijo(SIGTERM)
        DispatchQueue.main.asyncAfter(deadline: .now() + 15) {   // tope: si no terminó, se acabó
            guard esperandoSalida else { return }
            esperandoSalida = false
            avisarHijo(SIGKILL)
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}

var señales: [DispatchSourceSignal] = []
for s in [SIGTERM, SIGINT, SIGHUP] {
    signal(s, SIG_IGN)
    let fuente = DispatchSource.makeSignalSource(signal: s, queue: .main)
    fuente.setEventHandler { saliendo = true; avisarHijo(SIGTERM) }
    fuente.resume()
    señales.append(fuente)
}

let app = NSApplication.shared
let delegado = Delegado()
app.delegate = delegado
app.setActivationPolicy(.accessory)
app.run()
