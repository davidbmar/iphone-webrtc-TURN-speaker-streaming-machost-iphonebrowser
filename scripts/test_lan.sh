#!/usr/bin/env bash
#
# test_lan.sh — Print LAN URL + QR code for iPhone testing on same Wi-Fi.
#
# Usage: bash scripts/test_lan.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8080}"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/server.log"

mkdir -p "$LOG_DIR"

echo "=== LAN Test (Same Wi-Fi) ==="

# ── Detect local IP ──────────────────────────────────────────
LOCAL_IP=""

# macOS: use ipconfig
if command -v ipconfig >/dev/null 2>&1; then
  # Try en0 (Wi-Fi) first, then en1
  LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
fi

# Linux fallback: use hostname -I
if [ -z "$LOCAL_IP" ] && command -v hostname >/dev/null 2>&1; then
  LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "")
fi

if [ -z "$LOCAL_IP" ]; then
  echo "ERROR: Could not detect local IP address"
  echo "  Make sure you're connected to Wi-Fi"
  exit 1
fi

URL="https://$LOCAL_IP:$PORT"
echo ""
echo "  Local IP:  $LOCAL_IP"
echo "  URL:       $URL  (self-signed HTTPS)"
echo ""

# ── Check if server is running ────────────────────────────────
if ! lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  Starting HTTPS server on 0.0.0.0:$PORT..."
  cd "$REPO_ROOT"
  HTTPS=1 LOCAL_IP="$LOCAL_IP" /usr/bin/python3 -m gateway.server > "$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  echo "  Server PID: $SERVER_PID"

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

  trap "echo 'Stopping server (PID $SERVER_PID)...'; kill $SERVER_PID 2>/dev/null || true" EXIT
else
  echo "  Server already running on port $PORT"
fi

# ── QR code ───────────────────────────────────────────────────
echo ""
echo "  Scan this QR code on your iPhone:"
echo ""

if command -v qrencode >/dev/null 2>&1; then
  qrencode -t ANSIUTF8 "$URL"
elif python3 -c "import qrcode" 2>/dev/null; then
  python3 -c "
import qrcode
qr = qrcode.QRCode(border=1)
qr.add_data('$URL')
qr.print_ascii(invert=True)
"
else
  echo "  (Install qrencode for QR: brew install qrencode)"
  echo "  Or: pip install qrcode"
  echo ""
  echo "  Manual URL: $URL"
fi

# ── Important note ────────────────────────────────────────────
echo ""
echo "  NOTE: Using self-signed HTTPS for mic access (getUserMedia)."
echo "  On first visit, Safari will show a certificate warning."
echo "  Tap 'Show Details' → 'visit this website' → 'Visit Website' to proceed."
echo ""

# ── Tail logs ─────────────────────────────────────────────────
echo "=== Server Log (Ctrl+C to stop) ==="
echo ""
tail -f "$LOG_FILE"
