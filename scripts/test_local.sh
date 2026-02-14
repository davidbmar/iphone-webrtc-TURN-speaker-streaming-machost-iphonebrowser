#!/usr/bin/env bash
#
# test_local.sh — Start the server and open localhost:8080 for local testing.
#
# Usage: bash scripts/test_local.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8080}"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/server.log"

mkdir -p "$LOG_DIR"

echo "=== Local Test ==="

# ── Check dependencies ────────────────────────────────────────
echo "Checking dependencies..."
python3 -c "import aiohttp, aiortc" 2>/dev/null || {
  echo "ERROR: Missing Python deps. Run: pip install -r requirements.txt"
  exit 1
}
echo "  Dependencies OK"

# ── Check if server is already running ────────────────────────
if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  Server already running on port $PORT"
else
  echo "  Starting server on port $PORT..."
  cd "$REPO_ROOT"
  python3 -m gateway.server > "$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  echo "  Server PID: $SERVER_PID"

  # Wait for server to be ready
  for i in $(seq 1 10); do
    if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "  Server ready"
      break
    fi
    sleep 0.5
  done

  if ! lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: Server failed to start. Check $LOG_FILE"
    exit 1
  fi

  # Ensure server is stopped on script exit
  trap "echo 'Stopping server (PID $SERVER_PID)...'; kill $SERVER_PID 2>/dev/null || true" EXIT
fi

# ── Open browser ──────────────────────────────────────────────
URL="http://localhost:$PORT"
echo ""
echo "  URL: $URL"
echo ""

if command -v open >/dev/null 2>&1; then
  open "$URL"
  echo "  Opened in default browser"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
fi

# ── Tail logs ─────────────────────────────────────────────────
echo ""
echo "=== Server Log (Ctrl+C to stop) ==="
echo ""
tail -f "$LOG_FILE"
