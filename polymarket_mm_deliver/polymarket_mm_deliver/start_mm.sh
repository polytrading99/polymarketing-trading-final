#!/usr/bin/env bash
set -euo pipefail

# Use the directory of this script as the project root
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
PID_DIR="$BASE_DIR/run"

mkdir -p "$LOG_DIR" "$PID_DIR"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"

echo "===================="
echo "[START] launching processes at $TIMESTAMP"
echo "BASE_DIR = $BASE_DIR"
echo "LOG_DIR  = $LOG_DIR"
echo "PID_DIR  = $PID_DIR"
echo "===================="

########################################
# 1. Start trade.py
########################################

# If you use a virtualenv, you can change 'python3' to the appropriate python
# executable or source your venv before this script.

echo "[START] launching trade.py ..."

nohup python3 "$BASE_DIR/trade.py" \
  >> "$LOG_DIR/trade_${TIMESTAMP}.log" 2>&1 &

TRADE_PID=$!
echo "$TRADE_PID" > "$PID_DIR/trade.pid"

echo "[START] trade.py started with PID $TRADE_PID"
echo "        log: $LOG_DIR/trade_${TIMESTAMP}.log"

########################################
# 2. Start mm_main.py
########################################

echo "[START] launching mm_main.py ..."

nohup python3 "$BASE_DIR/mm_main.py" \
  >> "$LOG_DIR/mm_main_${TIMESTAMP}.log" 2>&1 &

MM_PID=$!
echo "$MM_PID" > "$PID_DIR/mm_main.pid"

echo "[START] mm_main.py started with PID $MM_PID"
echo "        log: $LOG_DIR/mm_main_${TIMESTAMP}.log"

echo "===================="
echo "[START] all processes launched."
echo "trade PID   = $TRADE_PID  (saved in $PID_DIR/trade.pid)"
echo "mm_main PID = $MM_PID     (saved in $PID_DIR/mm_main.pid)"
echo "===================="