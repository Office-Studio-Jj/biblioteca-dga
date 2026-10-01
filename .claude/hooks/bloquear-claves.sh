#!/bin/bash
# PreToolUse (Bash): bloquea un `git commit` si lo preparado contiene claves o un .env.
# Regla del proyecto: las claves solo viven en .env (laptop) y en Railway (Ley 172-13; Ley 168-21 Art. 10).
set -uo pipefail

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)
case "$cmd" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}"
archivos=$(git diff --cached --name-only 2>/dev/null || true)
if printf '%s\n' "$archivos" | grep -Eq '(^|/)\.env($|\.)'; then
  echo "Commit bloqueado: hay un archivo .env preparado. Sácalo con: git restore --staged <archivo>" >&2
  exit 2
fi
hallazgos=$(git diff --cached -U0 2>/dev/null | grep -E '^\+' \
  | grep -Eo 'sk-ant-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|(secret_|ntn_)[A-Za-z0-9]{30,}' | head -3)
if [ -n "$hallazgos" ]; then
  echo "Commit bloqueado: el cambio contiene lo que parece una clave API (${#hallazgos} caracteres detectados). Quítala y usa la variable de entorno." >&2
  exit 2
fi
exit 0
