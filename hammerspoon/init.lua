-- J.A.R.V.I.S. — atajos, ventanita, HUD y menú
-- Ctrl+Opción+J      → hablarle (sin decir "Hey Jarvis")
-- Ctrl+Opción+Espacio → escribirle
-- Ctrl+Opción+H      → abrir el panel HQ
-- Ctrl+Opción+.      → callarlo

local HOME   = os.getenv("HOME")
local JARVIS = HOME .. "/Documents/Jarvis"
local CASA   = HOME .. "/.jarvis"
local JV     = JARVIS .. "/bin/jv"
local CIAN   = { red = 0.31, green = 0.82, blue = 1.0, alpha = 1 }

hs.console.clearConsole()
hs.window.animationDuration = 0

---------------------------------------------------------------- HUD
local hud = nil
local hudTimer = nil
local ETIQUETAS = {
  escuchando = "Te escucho, señor…",
  pensando   = "Procesando…",
  hablando   = "",
}

local function ocultarHud()
  if hud then hud:delete(); hud = nil end
end

local function mostrarHud(estado, texto)
  ocultarHud()
  if estado == "listo" or estado == "apagado" then return end
  local etiqueta = ETIQUETAS[estado] or estado
  if estado == "hablando" and texto and texto ~= "" then etiqueta = texto end
  if estado == "pensando" and texto and texto ~= "" and texto ~= "transcribiendo…" then
    etiqueta = "Procesando: " .. texto
  end
  if #etiqueta > 140 then etiqueta = etiqueta:sub(1, 137) .. "…" end

  local pantalla = hs.screen.mainScreen():frame()
  local ancho, alto = math.min(620, pantalla.w - 80), 64
  local x = pantalla.x + (pantalla.w - ancho) / 2
  local y = pantalla.y + pantalla.h - alto - 40
  hud = hs.canvas.new({ x = x, y = y, w = ancho, h = alto })
  hud:level(hs.canvas.windowLevels.overlay)
  hud:behavior({ "canJoinAllSpaces", "stationary" })
  hud:appendElements(
    { type = "rectangle", action = "fill", roundedRectRadii = { xRadius = 18, yRadius = 18 },
      fillColor = { red = 0.02, green = 0.05, blue = 0.09, alpha = 0.92 } },
    { type = "rectangle", action = "stroke", roundedRectRadii = { xRadius = 18, yRadius = 18 },
      strokeColor = { red = 0.31, green = 0.82, blue = 1.0, alpha = 0.55 }, strokeWidth = 1.5 },
    { type = "circle", center = { x = 34, y = alto / 2 }, radius = 14, action = "stroke",
      strokeColor = CIAN, strokeWidth = 3,
      withShadow = true, shadow = { blurRadius = 12, color = CIAN, offset = { h = 0, w = 0 } } },
    { type = "circle", center = { x = 34, y = alto / 2 }, radius = 5, action = "fill", fillColor = CIAN },
    { type = "text", text = etiqueta, frame = { x = 62, y = 12, w = ancho - 78, h = alto - 16 },
      textColor = { white = 0.92, alpha = 1 }, textSize = 15, textFont = ".AppleSystemUIFont" }
  )
  hud:show(0.15)
  if hudTimer then hudTimer:stop() end
  hudTimer = hs.timer.doAfter(estado == "hablando" and 30 or 120, ocultarHud)
end

local function leerEstado()
  local f = io.open(CASA .. "/estado.json", "r")
  if not f then return end
  local contenido = f:read("*a"); f:close()
  local ok, datos = pcall(hs.json.decode, contenido)
  if ok and datos then mostrarHud(datos.estado, datos.texto) end
end

estadoWatcher = hs.pathwatcher.new(CASA, function(archivos)
  for _, a in ipairs(archivos) do
    if a:match("estado%.json$") then leerEstado(); return end
  end
end):start()

---------------------------------------------------------------- respuesta en pantalla
local panel = nil
local function mostrarRespuesta(pregunta, respuesta)
  if panel then panel:delete() end
  local esc = function(s) return (s or ""):gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;") end
  local html = [[<html><head><meta charset="utf-8"><style>
    body{margin:0;padding:22px 24px;background:#05080d;color:#d7e7f3;font:15px/1.55 -apple-system,sans-serif}
    .q{color:#7f98ad;font-size:13px;margin-bottom:12px}.q b{color:#4fd1ff;letter-spacing:.15em;font-size:11px}
    pre{white-space:pre-wrap;font:inherit;margin:0}
    </style></head><body><div class="q"><b>J.A.R.V.I.S.</b> &nbsp;· ]] .. esc(pregunta) ..
    [[</div><pre>]] .. esc(respuesta) .. [[</pre></body></html>]]
  local p = hs.screen.mainScreen():frame()
  panel = hs.webview.new({ x = p.x + p.w - 520, y = p.y + 40, w = 480, h = 420 })
    :windowStyle({ "titled", "closable", "resizable", "utility" })
    :windowTitle("Jarvis")
    :closeOnEscape(true)
    :allowTextEntry(true)
    :level(hs.drawing.windowLevels.floating)
    :html(html)
    :show()
  panel:bringToFront(true)
end

---------------------------------------------------------------- acciones
local function escuchar()
  local f = io.open(CASA .. "/escuchar", "w"); if f then f:write("1"); f:close() end
  mostrarHud("escuchando")
end

local function escribir()
  hs.focus()
  local boton, texto = hs.dialog.textPrompt("J.A.R.V.I.S.", "¿Qué necesita, señor?", "", "Enviar", "Cancelar")
  if boton ~= "Enviar" or not texto or texto == "" then return end
  mostrarHud("pensando", texto)
  hs.task.new(JV, function(codigo, salida, err)
    ocultarHud()
    local r = (salida and salida ~= "") and salida or ("Error: " .. (err or "sin respuesta"))
    mostrarRespuesta(texto, r)
  end, { "pensar", texto, "--hablar" }):start()
end

local function correr(args) hs.task.new(JV, nil, args):start() end

hs.hotkey.bind({ "ctrl", "alt" }, "J", escuchar)
hs.hotkey.bind({ "ctrl", "alt" }, "space", escribir)
hs.hotkey.bind({ "ctrl", "alt" }, "H", function() correr({ "hq", "--abrir" }) end)
hs.hotkey.bind({ "ctrl", "alt" }, ".", function() correr({ "decir", "--callar" }); ocultarHud() end)

---------------------------------------------------------------- menú en la barra
local menu = hs.menubar.new()
local function iconoMenu()
  local c = hs.canvas.new({ x = 0, y = 0, w = 18, h = 18 })
  c:appendElements(
    { type = "circle", center = { x = 9, y = 9 }, radius = 7, action = "stroke", strokeColor = { white = 0 }, strokeWidth = 1.6 },
    { type = "circle", center = { x = 9, y = 9 }, radius = 2.6, action = "fill", fillColor = { white = 0 } })
  local img = c:imageFromCanvas(); c:delete()
  return img:template(true)
end
menu:setIcon(iconoMenu())
menu:setTooltip("J.A.R.V.I.S.")
menu:setMenu(function()
  return {
    { title = "Hablarle            ⌃⌥J", fn = escuchar },
    { title = "Escribirle          ⌃⌥Espacio", fn = escribir },
    { title = "Panel HQ            ⌃⌥H", fn = function() correr({ "hq", "--abrir" }) end },
    { title = "-" },
    { title = "Resumen del día", fn = function() correr({ "resumen" }) end },
    { title = "Modo gamer", fn = function() correr({ "modo", "gamer", "--hablar" }) end },
    { title = "Modo estudio", fn = function() correr({ "modo", "estudio", "--hablar" }) end },
    { title = "Modo trabajo", fn = function() correr({ "modo", "trabajo", "--hablar" }) end },
    { title = "Modo dormir", fn = function() correr({ "modo", "dormir", "--hablar" }) end },
    { title = "-" },
    { title = "Callar                ⌃⌥.", fn = function() correr({ "decir", "--callar" }) end },
    { title = "Abrir carpeta Jarvis", fn = function() hs.execute("open '" .. JARVIS .. "'") end },
    { title = "Ver registro", fn = function() hs.execute("open -a Console '" .. CASA .. "/jarvis.log'") end },
    { title = "Recargar atajos", fn = hs.reload },
  }
end)

hs.alert.show("J.A.R.V.I.S. en línea", 1.5)
