#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$BASE_DIR/run"

stop_one() {
  local NAME="$1"      # logical process name (for printing)
  local PID_FILE="$2"

  if [[ ! -f "$PID_FILE" ]]; then
    echo "[STOP] $NAME: pid file not found: $PID_FILE (maybe not started?)"
    return
  fi

  local PID
  PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"

  if [[ -z "$PID" ]]; then
    echo "[STOP] $NAME: pid file is empty: $PID_FILE"
    return
  fi

  # Check if the process is still running
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "[STOP] $NAME: process $PID not running, removing pid file."
    rm -f "$PID_FILE"
    return
  fi

  echo "[STOP] $NAME: sending SIGINT to PID $PID ..."
  # Use SIGINT (2) instead of SIGTERM so Python can handle KeyboardInterrupt
  kill -INT "$PID" || true

  # Wait for a short grace period to let it exit cleanly
  for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      echo "[STOP] $NAME: PID $PID exited gracefully."
      rm -f "$PID_FILE"
      return
    fi
    sleep 0.5
  done

  # If still alive after the grace period, do NOT force-kill automatically.
  # You can decide manually whether to use kill -9.
  echo "[STOP] $NAME: PID $PID is still alive after grace period."
  echo "        If you really want to force kill: run 'kill -9 $PID' manually."
}

echo "===================="
echo "[STOP] stopping processes..."
echo "BASE_DIR = $BASE_DIR"
echo "PID_DIR  = $PID_DIR"
echo "===================="

stop_one "trade.py"   "$PID_DIR/trade.pid"
stop_one "mm_main.py" "$PID_DIR/mm_main.pid"

echo "===================="
echo "[STOP] done."
echo "===================="