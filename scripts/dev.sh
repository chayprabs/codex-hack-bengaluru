#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Could not find python or python3. Install Python 3.11+ first." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/dev.py" "$@"
