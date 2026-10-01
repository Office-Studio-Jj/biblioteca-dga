#!/bin/bash
# Instala las dependencias de Python para que pytest y la app funcionen en Claude Code on the web.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
# blinker viene de Debian sin RECORD y pip no puede actualizarlo: se reinstala por encima.
pip install -q -r requirements.txt pytest 2>/dev/null \
  || pip install -q --ignore-installed blinker -r requirements.txt pytest
