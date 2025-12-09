# BTC 15m Up/Down Time-Bucket MM

This repo is a small market-making bot for Polymarket 15m BTC up/down contracts.

- Market data: shared memory `poly_tob_shm` (via `shm_reader.py`)
- Execution: Polymarket CLOB REST + user WebSocket
- Strategy: **single round per 15m bucket**, only **one leg (YES or NO)** per round
- All key parameters are in `config.json`

---

## 1. Files

- `time_bucket_mm.py`  
  Core single-round strategy (entry / TP / SL / late window / dust handling).

- `mm_main.py`  
  Main loop: one round per 15m bucket, reuses one `ShmRingReader`, calls `run_single_round()`.

- `trade.py`  
  Market-data → shared memory writer (feeds `poly_tob_shm`).

- `load_config.py`  
  Loads and validates `config.json` into a global `CONFIG` dict.

- `config.json`  
  All tunable parameters (API keys, thresholds, caps, etc.).

- `start_mm.sh` / `stop_mm.sh` (optional helper scripts)  
  Example scripts to start/stop `trade.py` and `mm_main.py` with logs and PID files.

---

## 2. Config overview (`config.json`)

All numbers / modes are controlled here — you should rarely touch the Python code.

### 2.1 API

```json
"api": {
  "PRIVATE_KEY": "...",
  "PROXY_ADDRESS": "... or null",
  "SIGNATURE_TYPE": 1,
  "CHAIN_ID": 137
}
```

- `PRIVATE_KEY` / `PROXY_ADDRESS` — signing identity for Polymarket CLOB.
- `SIGNATURE_TYPE` / `CHAIN_ID` — client config for the network.

### 2.2 Entry & TP/SL

```json
"entry_exit": {
  "ENTRY_BID_THRESHOLD": 0.6,
  "MIN_TP_INCREMENT": 0.01,
  "SL_OFFSET": 0.2,
  "SL_FLOOR": 0.5,
  "MAX_TP_PRICE": 0.99,
  "SL_ORDER_PRICE": 0.01
}
```

- `ENTRY_BID_THRESHOLD` — minimum bid to allow entry.
- `MIN_TP_INCREMENT` — minimal profit step above entry before TP.
- `SL_OFFSET` / `SL_FLOOR` — stop loss trigger: `max(entry - SL_OFFSET, SL_FLOOR)`.
- `MAX_TP_PRICE` — cap TP price to avoid CLOB max-price errors.
- `SL_ORDER_PRICE` — actual stop order price (taker-style, very aggressive).

### 2.3 Time windows

```json
"time_windows": {
  "CONTRACT_DURATION_SEC": 900,
  "LATE_WINDOW_SEC": 120,
  "ENTRY_REQUOTE_WAIT_SEC": 2.0
}
```

- `CONTRACT_DURATION_SEC` — 15m bucket length.
- `LATE_WINDOW_SEC` — last N seconds (default 2 minutes) enters **late mode**.
- `ENTRY_REQUOTE_WAIT_SEC` — how long to wait before cancel/re-enter if no fill.

### 2.4 Late mode

```json
"late_mode": {
  "LATE_SL_TRIGGER": 0.7,
  "LATE_REENTRY_ENTRY_THRESHOLD": 0.9,
  "ENABLE_LATE_REENTRY": true,
  "MAX_LATE_REENTRIES": 1
}
```

- In the last `LATE_WINDOW_SEC` and entry ≥ `LATE_REENTRY_ENTRY_THRESHOLD`:
  - No TP, only SL triggered at `LATE_SL_TRIGGER`  
    (order price is always `SL_ORDER_PRICE`).
  - If fully stopped out and `ENABLE_LATE_REENTRY` is true:
    - Allow up to `MAX_LATE_REENTRIES` re-entries when bid ≥ threshold.
    - Recompute size each time via `cap_usd / price`.

### 2.5 Position / cap control

```json
"position_control": {
  "CAP_SCHEDULE": [
    {"start_sec": 0, "end_sec": 300, "cap_usd": 7.0},
    {"start_sec": 300, "end_sec": 600, "cap_usd": 7.5},
    {"start_sec": 600, "end_sec": 900, "cap_usd": 8.0}
  ],
  "MIN_TRADE_SIZE": 5.0,
  "ENABLE_DUST_MERGE": true
}
```

- `CAP_SCHEDULE` — time-based USD cap; size = `floor(cap / price)`.
- `MIN_TRADE_SIZE` — minimum size we consider “worth trading” on Polymarket.
- `ENABLE_DUST_MERGE` — whether to aggregate tiny residual positions across rounds.

### 2.6 Micro tuning / misc

```json
"micro_tuning": {
  "ENTRY_REQUOTE_MIN_IMPROVE": 0.03,
  "REMOTE_POS_SIZE_THRESHOLD": 0.0,
  "LEG_SELECTION_MODE": "HIGHEST_BID"
}
```

- `ENTRY_REQUOTE_MIN_IMPROVE` — minimal bid improvement to justify cancel/re-enter.
- `REMOTE_POS_SIZE_THRESHOLD` — minimum remote on-chain size to treat as real when reading positions from data-API.
- `LEG_SELECTION_MODE`:
  - `"HIGHEST_BID"` (default): pick YES/NO with highest bid ≥ `ENTRY_BID_THRESHOLD`.
  - `"YES_ONLY"` / `"NO_ONLY"`: restrict strategy to only one leg.

---

## 3. Edge-case protections

### 3.1 Dust (< MIN_TRADE_SIZE) protection

There are two main places where tiny residual positions (“dust”) are handled:

1. **Normal EXIT (non-late mode)**  
   - Effective size = previous dust + current on-chain pos.  
   - If `total_size < MIN_TRADE_SIZE`:
     - No TP/SL orders are placed.
     - If `ENABLE_DUST_MERGE` is true:
       - The current on-chain position is merged into `dust_size` / `dust_avg_price`
         with a weighted average.
     - The round is marked **DONE**.  
       Future rounds will re-read remote positions and try to close once the
       accumulated size ≥ `MIN_TRADE_SIZE`.

2. **Late SL (LATE_SL_PLACED)**  
   - When a late SL order finishes:
     - If `on_pos == 0` → fully flat, we may allow late re-entry.
     - If `0 < |on_pos| < MIN_TRADE_SIZE` → treated as dust for this round:
       - No more SL/TP in this bucket.
       - Round ends; next round will pick up the residual via remote positions.
     - If `|on_pos| ≥ MIN_TRADE_SIZE` → we stay in late mode and may place another SL later.

This prevents **infinite SL spam** and stops tiny leftovers from generating
extra orders inside the same round.

### 3.2 Hard stop-loss & price caps

- Every SL actually sends an order at `SL_ORDER_PRICE` (default 0.01) — highly
  aggressive exit to minimize tail risk.
- TP prices are always capped at `MAX_TP_PRICE`:
  - Avoid CLOB max price rejections.
  - Keep quotes within a sensible range.
- Stop-loss triggers always respect `SL_FLOOR` so the SL trigger never goes
  above a chosen minimum “panic” level.

---

## 4. How to run

Two simple ways to run the system:

1. Manual startup with `nohup`.
2. Using helper shell scripts.

### 4.1 Manual startup (nohup)

1. Make sure `config.json` is complete (especially `api.PRIVATE_KEY`).

2. Start `trade.py` (feeds shared memory):

```bash
mkdir -p logs run

nohup python trade.py   > logs/trade.log 2>&1 &

echo $! > run/trade.pid
```

3. Start `mm_main.py` (MM main loop):

```bash
nohup python mm_main.py   > logs/mm_main.log 2>&1 &

echo $! > run/mm_main.pid
```

4. Stop them manually:

```bash
kill "$(cat run/mm_main.pid)"
kill "$(cat run/trade.pid)"
```

(If PID files are missing, fall back to `ps aux | grep python`.)

### 4.2 Using helper scripts

Assuming you have:

- `start_mm.sh` — starts `trade.py` and `mm_main.py`, writes logs and PIDs.
- `stop_mm.sh` — reads PID file and stops both processes.

Make them executable:

```bash
chmod +x start_mm.sh stop_mm.sh
```

Then:

```bash
# Start data writer + MM loop
./start_mm.sh

# ... later, clean shutdown:
./stop_mm.sh
```

Typical behavior:

- `start_mm.sh`:
  - Creates `logs/` and a PID file directory.
  - `nohup` runs `trade.py` → `logs/trade.log`.
  - `nohup` runs `mm_main.py` → `logs/mm_main.log`.
  - Stores PIDs in a PID file.

- `stop_mm.sh`:
  - Reads PIDs from the PID file.
  - `kill` each PID if still running.
  - Removes the PID file when done.

---

## 5. Notes

- This is **not** a production-hardened system. Start with very small caps.
- Always test on a small account or a dev key you can afford to lose.
- When you change `config.json`, restart `mm_main.py` so new params are loaded.
- If shared memory or WS looks stuck or inconsistent, restart both `trade.py`
  and `mm_main.py`.

Use at your own risk.
