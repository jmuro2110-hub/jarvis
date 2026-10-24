#!/bin/bash
# Fase 1 — instala Claude Code y deja a Jarvis listo
set -e
echo "== Jarvis: instalación Fase 1 =="
sw_vers
if ! command -v claude >/dev/null 2>&1; then
  echo "Instalando Claude Code..."
  curl -fsSL https://claude.ai/install.sh | bash
else
  echo "Claude Code ya está instalado: $(claude --version)"
fi
cd "$(dirname "$0")/.."
if [ ! -d .git ]; then
  git init -q && git add . && git commit -qm "Jarvis: base inicial"
  echo "Repositorio local creado."
fi
say -v "Jorge" "Sistemas en línea, señor." 2>/dev/null || say "Systems online, sir."
echo "Listo. Para hablar con Jarvis:  cd ~/Documents/Jarvis && claude"
