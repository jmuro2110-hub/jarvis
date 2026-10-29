#!/bin/bash
# J.A.R.V.I.S. — instalación completa. Se puede correr las veces que quieras.
JARVIS="$HOME/Documents/Jarvis"
CASA="$HOME/.jarvis"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$JARVIS" || { echo "No encuentro $JARVIS"; exit 1; }
mkdir -p "$CASA" .claude
ok(){ echo "  ✅ $1"; }
aviso(){ echo "  ⚠️  $1"; }
paso(){ echo; echo "▸ $1"; }

paso "Permisos y archivos base"
chmod +x bin/jv bin/*.py voz/iniciar.sh Jarvis.command scripts/*.sh 2>/dev/null
cp scripts/permisos.json .claude/settings.json 2>/dev/null && ok "Permisos de Claude"
ln -sf CLAUDE.md AGENTS.md && ok "Personalidad compartida con ChatGPT (AGENTS.md)"
[ -f "$CASA/secretos.env" ] || { printf '# Llaves privadas de Jarvis (no se suben a ningún lado)\n' > "$CASA/secretos.env"; chmod 600 "$CASA/secretos.env"; }

paso "uv (motor de Python)"
if ! command -v uv >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
command -v uv >/dev/null && ok "uv $(uv --version | cut -d' ' -f2)" || aviso "uv no se instaló"

paso "Comandos en la Terminal (jarvis, jarvis-voz, jv)"
ZRC="$HOME/.zshrc"; touch "$ZRC"
sed -i '' '/# >>> jarvis >>>/,/# <<< jarvis <<</d' "$ZRC" 2>/dev/null
sed -i '' '/^jarvis() {/d;/^alias jarvis-voz=/d' "$ZRC" 2>/dev/null
cat >> "$ZRC" <<'ZEOF'
# >>> jarvis >>>
export PATH="$HOME/.local/bin:$HOME/Documents/Jarvis/bin:$PATH"
jarvis() { cd ~/Documents/Jarvis && claude "$@"; }
alias jarvis-voz="open ~/Documents/Jarvis/Jarvis.command"
# <<< jarvis <<<
ZEOF
ok "Listo (abre una Terminal nueva para usarlos)"

paso "Cerebro de respaldo: ChatGPT (Codex)"
codex_valido(){ [ -x "$1" ] && "$1" login --help >/dev/null 2>&1; }
CODEX=""
for c in "$(command -v codex)" "$HOME/.local/bin/codex" /Applications/ChatGPT.app/Contents/Resources/codex /Applications/Codex.app/Contents/Resources/codex; do
  [ -n "$c" ] && codex_valido "$c" && CODEX="$c" && break
done
if [ -z "$CODEX" ]; then
  [ -f "$HOME/.local/bin/codex" ] && mv "$HOME/.local/bin/codex" "$HOME/.local/bin/codex.malo"
  URL=$(curl -fsSL https://api.github.com/repos/openai/codex/releases/latest | grep -o 'https://[^"]*/codex-x86_64-apple-darwin\.tar\.gz' | head -1)
  URL=${URL:-https://github.com/openai/codex/releases/latest/download/codex-x86_64-apple-darwin.tar.gz}
  echo "    descargando $URL"
  TMP=$(mktemp -d)
  if curl -fL --progress-bar "$URL" -o "$TMP/codex.tgz" && tar -xzf "$TMP/codex.tgz" -C "$TMP"; then
    BIN=$(find "$TMP" -type f -name 'codex-x86_64-apple-darwin' | head -1)
    [ -z "$BIN" ] && BIN=$(find "$TMP" -type f -name 'codex' | head -1)
    if [ -n "$BIN" ]; then
      mkdir -p "$HOME/.local/bin" && mv "$BIN" "$HOME/.local/bin/codex" && chmod +x "$HOME/.local/bin/codex"
      xattr -d com.apple.quarantine "$HOME/.local/bin/codex" 2>/dev/null
      codex_valido "$HOME/.local/bin/codex" && CODEX="$HOME/.local/bin/codex"
    fi
  fi
  rm -rf "$TMP"
fi
if [ -x "$CODEX" ]; then
  ok "Codex: $CODEX"
  if "$CODEX" login status 2>&1 | grep -qi "logged in"; then ok "Sesión de ChatGPT activa"
  else aviso "Falta iniciar sesión → al final corre:  codex login"; fi
else aviso "No pude instalar Codex (Jarvis funciona igual, solo sin respaldo)"; fi

paso "Hammerspoon (atajos, ventanita, HUD)"
HS_APP=""
for d in /Applications/Hammerspoon.app "$HOME/Applications/Hammerspoon.app"; do [ -d "$d" ] && HS_APP="$d"; done
if [ -z "$HS_APP" ]; then
  TMP=$(mktemp -d)
  for URL in \
    "$(curl -fsSL https://api.github.com/repos/Hammerspoon/hammerspoon/releases/latest 2>/dev/null | grep -o 'https://[^"]*Hammerspoon-[^"]*\.zip' | head -1)" \
    "https://github.com/Hammerspoon/hammerspoon/releases/download/1.0.0/Hammerspoon-1.0.0.zip"; do
    [ -z "$URL" ] && continue
    echo "    descargando $URL"
    if curl -fL --progress-bar "$URL" -o "$TMP/hs.zip" && ditto -xk "$TMP/hs.zip" "$TMP/x" && [ -d "$TMP/x/Hammerspoon.app" ]; then
      xattr -dr com.apple.quarantine "$TMP/x/Hammerspoon.app" 2>/dev/null
      if mv "$TMP/x/Hammerspoon.app" /Applications/ 2>/dev/null; then HS_APP=/Applications/Hammerspoon.app
      else mkdir -p "$HOME/Applications" && mv "$TMP/x/Hammerspoon.app" "$HOME/Applications/" && HS_APP="$HOME/Applications/Hammerspoon.app"; fi
      break
    fi
  done
  rm -rf "$TMP"
fi
mkdir -p "$HOME/.hammerspoon"
[ -f "$HOME/.hammerspoon/init.lua" ] && [ ! -L "$HOME/.hammerspoon/init.lua" ] && mv "$HOME/.hammerspoon/init.lua" "$HOME/.hammerspoon/init.lua.antes"
ln -sf "$JARVIS/hammerspoon/init.lua" "$HOME/.hammerspoon/init.lua"
defaults write org.hammerspoon.Hammerspoon MJShowDockIconKey -bool false
defaults write org.hammerspoon.Hammerspoon HSUploadCrashData -bool false
if [ -n "$HS_APP" ]; then ok "Hammerspoon: $HS_APP"; open "$HS_APP"; else aviso "Hammerspoon no se instaló (mándale captura a Claude)"; fi

paso "Avisos al iPhone (ntfy, gratis)"
if ! grep -q '^NTFY_TOPIC=' "$CASA/secretos.env"; then
  echo "NTFY_TOPIC=jarvis-jp-$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 12)" >> "$CASA/secretos.env"
fi
TOPIC=$(grep '^NTFY_TOPIC=' "$CASA/secretos.env" | cut -d= -f2)
ok "Canal privado: $TOPIC"

paso "Arranque automático al prender la Mac"
# Upgrade 08: arranca Jarvis.app (sin ventana). Jarvis.command queda de respaldo y NO se registra: un solo modo.
# El binario se compila solo si no existe (recompilar puede volver a pedir micrófono y Automatización).
[ -x "$HOME/Applications/Jarvis.app/Contents/MacOS/Jarvis" ] || bash "$JARVIS/app/construir.sh"
/usr/bin/python3 -I "$JARVIS/bin/arranque.py" inicio app >/dev/null 2>&1 \
  && ok "Jarvis.app arranca sola al iniciar sesión" || aviso "Agrégalo a mano: Ajustes → General → Ítems de inicio → + → Inicio/Aplicaciones/Jarvis.app"
if [ -n "$HS_APP" ]; then
  osascript -e "tell application \"System Events\" to delete (every login item whose name is \"Hammerspoon\")" >/dev/null 2>&1
  osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$HS_APP\", hidden:true}" >/dev/null 2>&1
fi

paso "Preparando herramientas (primera vez tarda un poco)"
bin/jv hq >/dev/null 2>&1 && ok "Panel HQ"
bin/jv resumen --plantilla >/dev/null 2>&1 && ok "Resumen matutino"

echo
echo "═══════════════════════════════════════════════"
echo "  J.A.R.V.I.S. instalado"
echo "═══════════════════════════════════════════════"
echo "  iPhone: instala la app 'ntfy' y suscríbete a:  $TOPIC"
[ -x "$CODEX" ] && ! "$CODEX" login status 2>&1 | grep -qi "logged in" && echo "  ChatGPT: corre  codex login  y entra con tu cuenta"
echo "  Hammerspoon: dale permiso de Accesibilidad cuando lo pida"
echo
bin/jv decir "Instalación completa, señor. Todos los sistemas listos." >/dev/null 2>&1 &
