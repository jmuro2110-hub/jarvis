#!/bin/bash
# Arranca el módulo de voz de Jarvis
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "Instalando uv (maneja Python solo, sin ensuciar tu Mac)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$(dirname "$0")"
exec uv run --script jarvis_voz.py
