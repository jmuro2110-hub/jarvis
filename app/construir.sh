#!/bin/bash
# Compila y firma (ad-hoc) ~/Applications/Jarvis.app. Hacerlo UNA vez: cada recompilación cambia el cdhash
# y macOS puede volver a pedir micrófono, Documentos y Automatización. La lógica vive en bin/arranque.sh.
set -euo pipefail
cd "$(dirname "$0")"
DEST="$HOME/Applications/Jarvis.app"
if [ -e "$DEST" ] && [ "${1:-}" != "--forzar" ]; then
  echo "Ya existe $DEST. Recompilar puede pedir otra vez los permisos: usa --forzar si de verdad hace falta."; exit 1
fi
TMP=$(mktemp -d)
swiftc -O -target x86_64-apple-macos13.0 -framework AppKit -framework AVFoundation Jarvis.swift -o "$TMP/Jarvis"
mkdir -p "$TMP/Jarvis.app/Contents/MacOS"
cp Info.plist "$TMP/Jarvis.app/Contents/Info.plist"
mv "$TMP/Jarvis" "$TMP/Jarvis.app/Contents/MacOS/Jarvis"
codesign --force --sign - --identifier mx.jpmuro.jarvis "$TMP/Jarvis.app"   # sin hardened runtime
rm -rf "$DEST"; mv "$TMP/Jarvis.app" "$DEST"; rmdir "$TMP"
codesign -dv "$DEST" 2>&1 | grep -E "Identifier|CDHash|Signature"
shasum -a 256 "$DEST/Contents/MacOS/Jarvis"
