#!/usr/bin/env bash
#
# run.sh — Launch the voice assistant REPL with the correct Python.
#
# Usage: bash voice_assistant/run.sh [--debug]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Python detection ─────────────────────────────────────────
# Try candidates in order, verify each can import our deps.
find_python() {
  local candidates=(
    "/opt/homebrew/bin/python3"
    "python3"
    "python"
    "/usr/local/bin/python3"
  )

  for py in "${candidates[@]}"; do
    if command -v "$py" >/dev/null 2>&1 || [ -x "$py" ]; then
      if "$py" -c "import pydantic_settings, httpx, rich" 2>/dev/null; then
        echo "$py"
        return 0
      fi
    fi
  done
  return 1
}

echo "Finding Python with required dependencies..."

PYTHON=$(find_python) || {
  echo ""
  echo "ERROR: No Python found with voice_assistant dependencies."
  echo ""
  echo "Fix:  /opt/homebrew/bin/pip3 install -r voice_assistant/requirements.txt"
  echo "  or: pip3 install --break-system-packages -r voice_assistant/requirements.txt"
  exit 1
}

echo "  Using: $PYTHON ($($PYTHON --version 2>&1))"
echo ""

cd "$REPO_ROOT"
exec "$PYTHON" -m voice_assistant.main "$@"
