# time_bucket_mm.py
# -*- coding: utf-8 -*-
"""
Single-round time-bucket MM strategy on 15m BTC up/down contracts.

- Market data: read yes/no bid/ask from shm_ring("poly_tob_shm")
- Orders & fills: via AccountState + user WS
- Each run only does a single "round", and only trades on ONE leg (YES or NO).

Core rules (parameters are now configurable via load_config):

1) Only place BUY orders:
    - YES leg: buy Up token
    - NO  leg: buy Down token

2) Only allow entry when bid >= ENTRY_BID_THRESHOLD (default 0.6).

3) Time-bucket caps (USD) to control max notional (CAP_SCHEDULE):
    - Default:
        - 0-5 min   : cap = 7
        - 5-10 min  : cap = 7.5
        - 10-15 min : cap = 8
      size = floor(cap / price)

4) Stop loss logic:
    - Trigger threshold (based on entry_price):
        * entry <= 0.7 -> stop_loss_trigger = SL_FLOOR (default 0.5)
        * entry >  0.7 -> stop_loss_trigger = max(entry - SL_OFFSET, SL_FLOOR)
                         (default SL_OFFSET = 0.2, SL_FLOOR = 0.5)
    - Trigger condition: bid <= stop_loss_trigger
    - When triggered:
        * cancel any TP order
        * place a SELL stop-loss order at price = SL_ORDER_PRICE
          (default 0.01, taker style)

5) Take profit logic (not in last LATE_WINDOW_SEC & not the special >=0.9 late case):
    - If bid >= entry_price + MIN_TP_INCREMENT (default 0.01):
        * TP price = current bid (taker style, capped at MAX_TP_PRICE)
    - Otherwise:
        * TP price = ceil(entry_price + MIN_TP_INCREMENT, 2 decimals, only upwards)
        * and capped at MAX_TP_PRICE (default 0.99)

6) ENTRY re-quote:
    - If the entry order has no fill for ENTRY_REQUOTE_WAIT_SEC (default 2.0s),
    - and risk_pos == 0 & on_pos == 0 (no matched volume),
    - and current bid >= entry_price + ENTRY_REQUOTE_MIN_IMPROVE (default 0.03),
    => cancel and re-enter once at the improved price (to avoid constant repricing).

7) Once there is any matched volume (risk_pos > 0) for ENTRY, do not cancel/re-quote.
   Just wait for MINED.

8) EXIT state machine guarantees:
    - Never exceed cap
    - Only flatten on-chain positions (no over-hedging)
    - For stop loss: cancel TP first, then place SL at price SL_ORDER_PRICE
    - If EXIT is FILLED off-chain but on_pos > 0, go to EXIT_WAIT_ONCHAIN and only wait
      for on-chain updates (no more TP spam).

9) Last LATE_WINDOW_SEC (default 120s) special rule:
    - round_deadline = bucket_ts + CONTRACT_DURATION_SEC (default 900s)
    - If in the last LATE_WINDOW_SEC and current round entry_price
      >= LATE_REENTRY_ENTRY_THRESHOLD (default 0.9):
        * Do NOT place TP. Enter LATE_HOLD mode:
            - Fixed stop_loss trigger threshold = LATE_SL_TRIGGER (default 0.7)
            - Hold to contract expiration, only place SL when bid <= LATE_SL_TRIGGER
            - SL order price = SL_ORDER_PRICE (default 0.01, taker)
        * If in LATE_HOLD we get fully stopped out once:
            - Allow up to MAX_LATE_REENTRIES (default 1) re-entries in the last window
              when bid >= LATE_REENTRY_ENTRY_THRESHOLD:
                - Recompute size via cap_usd / price and BUY again
                - After the max count is reached, no more re-entry is allowed.

10) Cross-round residual position ("dust") handling (controlled by ENABLE_DUST_MERGE):
    - At the beginning of each round, read YES/NO positions (size & avgPrice)
      from data-api for the current market, store in dust_*.
    - On EXIT, use total_size = dust_size + current round on_pos:
        * If total_size < MIN_TRADE_SIZE (default 5.0): this round will NOT place TP/SL.
          Instead, merge on_pos into dust and mark this round as DONE,
          leaving it for future rounds to accumulate.
        * If total_size >= MIN_TRADE_SIZE: compute a size-weighted average price across
          dust+on_pos, use it as entry_price and stop_loss_trigger, and place TP/SL once
          on total_size. After that, dust is cleared (this round is responsible for
          carrying away historical residual positions).
"""

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from data_reader.shm_reader import ShmRingReader
from state_machine import AccountState
from state_machine.ws_client import UserWebSocketClient
from state_machine.polymarket_client import PolymarketClient
from state_machine.enums import ORDER_STATUS_OPEN, ORDER_STATUS_PART_FILLED
from data_reader.load_config import CONFIG


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

API_CFG = CONFIG["api"]

# !!! Local test private key, DO NOT use in production !!!
PRIVATE_KEY: str = API_CFG["PRIVATE_KEY"]
PROXY_ADDRESS: Optional[str] = API_CFG.get("PROXY_ADDRESS") or None
SIGNATURE_TYPE: Optional[int] = API_CFG.get("SIGNATURE_TYPE")
CHAIN_ID = int(API_CFG["CHAIN_ID"])

SHM_NAME = "poly_tob_shm"

LIVE_ORDER_STATUSES = {ORDER_STATUS_OPEN, ORDER_STATUS_PART_FILLED}
EPS_POS = 1e-6

# Whether to print detailed SUPER_ORDER snapshots (for debugging)
PRINT_SUPER_ORDERS = False

# ---- config aliases -------------------------------------------------------

ENTRY_CFG = CONFIG["entry_exit"]
TIME_CFG = CONFIG["time_windows"]
LATE_CFG = CONFIG["late_mode"]
POS_CFG = CONFIG["position_control"]
TUNE_CFG = CONFIG["micro_tuning"]

ENTRY_BID_THRESHOLD = float(ENTRY_CFG["ENTRY_BID_THRESHOLD"])
MIN_TP_INCREMENT = float(ENTRY_CFG["MIN_TP_INCREMENT"])
SL_OFFSET = float(ENTRY_CFG["SL_OFFSET"])
SL_FLOOR = float(ENTRY_CFG["SL_FLOOR"])
MAX_TP_PRICE = float(ENTRY_CFG["MAX_TP_PRICE"])
SL_ORDER_PRICE = float(ENTRY_CFG["SL_ORDER_PRICE"])

CONTRACT_DURATION_SEC = int(TIME_CFG["CONTRACT_DURATION_SEC"])
LATE_WINDOW_SEC = int(TIME_CFG["LATE_WINDOW_SEC"])
ENTRY_REQUOTE_WAIT_SEC = float(TIME_CFG["ENTRY_REQUOTE_WAIT_SEC"])

LATE_SL_TRIGGER = float(LATE_CFG["LATE_SL_TRIGGER"])
LATE_REENTRY_ENTRY_THRESHOLD = float(LATE_CFG["LATE_REENTRY_ENTRY_THRESHOLD"])
ENABLE_LATE_REENTRY = bool(LATE_CFG.get("ENABLE_LATE_REENTRY", True))
MAX_LATE_REENTRIES = int(LATE_CFG.get("MAX_LATE_REENTRIES", 1))

CAP_SCHEDULE = list(POS_CFG["CAP_SCHEDULE"])
MIN_TRADE_SIZE = float(POS_CFG["MIN_TRADE_SIZE"])
ENABLE_DUST_MERGE = bool(POS_CFG.get("ENABLE_DUST_MERGE", True))

ENTRY_REQUOTE_MIN_IMPROVE = float(TUNE_CFG["ENTRY_REQUOTE_MIN_IMPROVE"])
REMOTE_POS_SIZE_THRESHOLD = float(TUNE_CFG["REMOTE_POS_SIZE_THRESHOLD"])
LEG_SELECTION_MODE = str(TUNE_CFG["LEG_SELECTION_MODE"]).upper().strip()


# ---------------------------------------------------------------------------
# Gamma helpers
# ---------------------------------------------------------------------------

def build_btc_15m_slug_from_bucket(bucket: int) -> str:
    return f"btc-updown-15m-{bucket}"


def _ensure_list(x: Any) -> list:
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            j = json.loads(x)
            if isinstance(j, list):
                return j
        except Exception:
            pass
        return [s.strip() for s in x.split(",") if s.strip()]
    return []


def resolve_market_for_bucket(bucket_ts: int) -> Tuple[str, str, str]:
    """
    Resolve market for a given time bucket.

    Returns: (market_id, yes_token_id, no_token_id)
    """
    slug = build_btc_15m_slug_from_bucket(bucket_ts)
    url = f"{GAMMA_BASE}/events/slug/{slug}"
    print(f"[RESOLVE] bucket_ts={bucket_ts} slug={slug} url={url}")

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    ev = data
    markets = ev.get("markets") or []
    if not markets:
        raise RuntimeError(f"no markets in event json: {ev!r}")

    m0 = markets[0]
    market_id = (
        m0.get("conditionId")
        or m0.get("condition_id")
        or m0.get("id")
    )
    if not market_id:
        raise RuntimeError(f"no conditionId/condition_id/id in market: {m0!r}")

    outcomes_raw = m0.get("outcomes")
    tokens_raw = m0.get("clobTokenIds") or m0.get("clob_token_ids")

    outcomes = _ensure_list(outcomes_raw)
    tokens = _ensure_list(tokens_raw)

    if not outcomes or not tokens or len(outcomes) != len(tokens):
        raise RuntimeError(
            f"cannot parse outcomes/tokens: outcomes={outcomes_raw!r}, tokens={tokens_raw!r}"
        )

    up_idx = down_idx = None
    for i, name in enumerate(outcomes):
        if not isinstance(name, str):
            continue
        lower = name.lower()
        if "up" in lower and up_idx is None:
            up_idx = i
        if "down" in lower and down_idx is None:
            down_idx = i

    if up_idx is None:
        up_idx = 0
    if down_idx is None:
        down_idx = 1 if len(tokens) > 1 else 0

    yes_token = str(tokens[up_idx])
    no_token = str(tokens[down_idx])

    print(
        f"[RESOLVE-OK] market_id={market_id} yes_token={yes_token} "
        f"no_token={no_token} outcomes={outcomes}"
    )

    return str(market_id), yes_token, no_token


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------

def print_super_order_snapshot(order_id: str, order_obj) -> None:
    """
    Print a summarized view of an order and its trades.
    Controlled by the global PRINT_SUPER_ORDERS flag.
    """
    if not PRINT_SUPER_ORDERS:
        return

    print(f"[SUPER_ORDER] order_id={order_id}")
    print(
        f"  side={order_obj.side}, price={order_obj.price}, "
        f"original_size={order_obj.original_size}, size_matched={order_obj.size_matched}, "
        f"size_unmatched={order_obj.size_unmatched}, status={order_obj.order_status}"
    )
    if order_obj.trades:
        print("  trades:")
        for tid, t in order_obj.trades.items():
            print(f"    trade_id={tid}, size={t.size}, status={t.status}")
    else:
        print("  trades: {}")


def is_order_live(state: AccountState, order_id: Optional[str]) -> bool:
    if not order_id:
        return False
    o = state.orders.get(order_id)
    if not o:
        return False
    return o.order_status in LIVE_ORDER_STATUSES and o.size_unmatched > 0.0


def cancel_order(poly: PolymarketClient, order_id: Optional[str]):
    """
    PolymarketClient cancel compatibility:
      - cancel_order(order_id)
      - cancel(order_id)
    """
    if not order_id:
        return None
    if hasattr(poly, "cancel_order"):
        return poly.cancel_order(order_id)
    if hasattr(poly, "cancel"):
        return poly.cancel(order_id)
    raise AttributeError("PolymarketClient has no cancel/cancel_order method")


# ---------------------------------------------------------------------------
# Leg state
# ---------------------------------------------------------------------------

@dataclass
class LegRoundState:
    label: str          # "YES" / "NO"
    outcome: str        # "Up" / "Down"
    token_id: str

    # State machine:
    # "IDLE" -> "LOOK_FOR_ENTRY" -> "ENTRY_PLACED" -> "ENTRY_CANCEL_WAIT"
    #       -> ("PREP_EXIT" | "LATE_HOLD")
    #       -> "EXIT_PLACED"/"EXIT_WAIT_ONCHAIN"/"EXIT_CANCEL_FOR_SL"/"EXIT_SL_PLACED"
    #       -> ("LATE_HOLD"/"LATE_SL_PLACED") -> "DONE"
    stage: str = "IDLE"

    entry_order_id: Optional[str] = None
    entry_price: float = 0.0
    entry_placed_at: float = 0.0

    # Stop loss trigger threshold (price).
    # The actual SL order price is always SL_ORDER_PRICE for this strategy.
    stop_loss: float = 0.0

    exit_order_id: Optional[str] = None
    exit_placed_at: float = 0.0

    # Last-window special logic
    late_hold: bool = False              # whether we are in the "hold to expiry" mode
    late_sl_hit: bool = False            # whether SL fully closed the position once in LATE_HOLD
    late_reentry_done: bool = False      # whether we have reached max late re-entries
    late_reentry_count: int = 0          # actual number of late re-entries used

    # Cross-round residual on-chain position (from previous rounds)
    dust_size: float = 0.0
    dust_avg_price: float = 0.0


# ---------------------------------------------------------------------------
# WS callbacks
# ---------------------------------------------------------------------------

def make_ws_on_message(state: AccountState, last_pos_cache: Dict[Tuple[str, str], Tuple[float, float]]):
    """
    user WS on_message:
    - Update AccountState
    - Optionally print SUPER_ORDER snapshots (controlled by PRINT_SUPER_ORDERS)
    - Print [POS] only when risk_pos / on_pos changes
    """

    def ws_on_message(msg: Dict[str, Any]) -> None:
        # No raw WS message printing to keep logs clean

        etype = msg.get("event_type") or msg.get("type")

        if etype == "order":
            state.handle_order_message(msg)
            oid = msg.get("id")
            if oid in state.orders:
                print_super_order_snapshot(oid, state.orders[oid])

        elif etype == "trade":
            state.handle_trade_message(msg)

            order_ids = set()
            taker_id = msg.get("taker_order_id")
            if isinstance(taker_id, str) and taker_id in state.orders:
                order_ids.add(taker_id)
            for m in msg.get("maker_orders") or []:
                if not isinstance(m, dict):
                    continue
                oid = m.get("order_id") or m.get("id")
                if isinstance(oid, str) and oid in state.orders:
                    order_ids.add(oid)

            for oid in order_ids:
                print_super_order_snapshot(oid, state.orders[oid])

            mkt = msg.get("market")
            outcome = msg.get("outcome")
            if isinstance(mkt, str) and isinstance(outcome, str):
                key = (mkt, outcome)
                risk_stats = state.get_risk_stats(mkt, outcome)
                on_stats = state.get_onchain_stats(mkt, outcome)
                risk_pos = risk_stats["pos"]
                risk_avg = risk_stats["avg_price"]
                on_pos = on_stats["pos"]
                on_avg = on_stats["avg_price"]

                old = last_pos_cache.get(key)
                new = (risk_pos, on_pos)
                if old is None or abs(new[0] - old[0]) > 1e-9 or abs(new[1] - old[1]) > 1e-9:
                    print(
                        f"[POS] [{mkt} / {outcome}] risk_pos={risk_pos:.1f}, "
                        f"risk_avg={risk_avg:.4f}, on_pos={on_pos:.1f}, "
                        f"on_avg={on_avg:.4f}"
                    )
                    last_pos_cache[key] = new

    return ws_on_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_cap_usd(now: float, bucket_ts: int) -> float:
    """
    Compute cap in USD based on elapsed time and CAP_SCHEDULE.

    CAP_SCHEDULE is a list of:
        {"start_sec": int, "end_sec": int, "cap_usd": float}

    We pick the first interval where start_sec <= elapsed < end_sec.
    If none matches, fall back to the last interval's cap (if any),
    otherwise 0.0.
    """
    elapsed = max(0, int(now - bucket_ts))
    cap: Optional[float] = None

    for item in CAP_SCHEDULE:
        start = int(item.get("start_sec", 0))
        end = int(item.get("end_sec", start))
        cap_val = float(item.get("cap_usd", 0.0))
        if start <= elapsed < end:
            cap = cap_val
            break

    if cap is None:
        if CAP_SCHEDULE:
            cap = float(CAP_SCHEDULE[-1].get("cap_usd", 0.0))
        else:
            cap = 0.0

    return cap


def compute_stop_loss_trigger(entry_price: float) -> float:
    """
    Stop-loss trigger logic:

        if entry_price > 0.7:
            stop_loss = max(entry_price - SL_OFFSET, SL_FLOOR)
        else:
            stop_loss = SL_FLOOR
    """
    if entry_price > 0.7:
        sl = entry_price - SL_OFFSET
        if sl < SL_FLOOR:
            sl = SL_FLOOR
    else:
        sl = SL_FLOOR
    return sl


def compute_tp_price(entry_price: float, bid: float) -> float:
    """
    Compute TP price given entry_price and current bid:

        min_tp = entry_price + MIN_TP_INCREMENT
        if bid >= min_tp:
            tp = bid
        else:
            tp = ceil(min_tp * 100) / 100

        tp is capped at MAX_TP_PRICE.
    """
    min_tp = entry_price + MIN_TP_INCREMENT

    if min_tp >= MAX_TP_PRICE:
        # Very high entry (e.g. 0.99): close at MAX_TP_PRICE / near break-even
        return MAX_TP_PRICE

    if bid >= min_tp:
        tp = bid
    else:
        tp = math.ceil(min_tp * 100.0 - 1e-9) / 100.0

    if tp > MAX_TP_PRICE:
        tp = MAX_TP_PRICE

    return tp


# ---------------------------------------------------------------------------
# Single-round strategy
# ---------------------------------------------------------------------------

def run_single_round(
    shm_reader: Optional[ShmRingReader] = None,
    first_frame: Optional[Dict[str, Any]] = None,
    market_info: Optional[Tuple[str, str, str]] = None,
):
    """
    Entry point for a single trading round.

    - If main passes:
        * shm_reader: reuse main's shm_reader
        * first_frame: the first tick of this round (includes bucket_ts)
        * market_info: (market_id, yes_token_id, no_token_id)
      then this function will not resolve bucket/market by itself
      and will not close shm_reader.

    - If not provided (e.g. you run `python time_bucket_mm.py` directly):
        * This function creates its own ShmRingReader, reads the first frame,
          and calls resolve_market_for_bucket
        * It is responsible for closing shm_reader in finally.
    """
    created_local_reader = False
    if shm_reader is None:
        shm_reader = ShmRingReader(SHM_NAME)
        created_local_reader = True

    if first_frame is None:
        first_frame = shm_reader.read_next_blocking()

    bucket_ts = int(first_frame["bucket_ts"])
    yes_bid = float(first_frame["yes_bid"])
    yes_ask = float(first_frame["yes_ask"])
    no_bid = float(first_frame["no_bid"])
    no_ask = float(first_frame["no_ask"])
    print(f"[SHM] first frame bucket_ts={bucket_ts}, yes_bid={yes_bid:.2f}, no_bid={no_bid:.2f}")

    # Market resolution: prefer main-injected market_info if provided
    if market_info is not None:
        market_id, yes_token_id, no_token_id = market_info
        print(
            f"[RESOLVE] from main: bucket_ts={bucket_ts}, "
            f"market_id={market_id}, yes_token={yes_token_id}, no_token={no_token_id}"
        )
    else:
        market_id, yes_token_id, no_token_id = resolve_market_for_bucket(bucket_ts)

    # State machine + REST client + user WS
    state = AccountState()
    poly = PolymarketClient(
        host=CLOB_HOST,
        private_key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=SIGNATURE_TYPE,
        funder=PROXY_ADDRESS,
    )
    api_key = poly.api_key
    api_secret = poly.api_secret
    api_passphrase = poly.api_passphrase

    # Read remote positions as initial cross-round dust
    yes_dust_size = no_dust_size = 0.0
    yes_dust_avg = no_dust_avg = 0.0
    try:
        leg_pos = poly.get_market_leg_positions(
            market_id=market_id,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            size_threshold=REMOTE_POS_SIZE_THRESHOLD,
        )
        yes_dust_size = float(leg_pos.get("yes_size") or 0.0)
        no_dust_size = float(leg_pos.get("no_size") or 0.0)
        yes_dust_avg_raw = leg_pos.get("yes_avg_price")
        no_dust_avg_raw = leg_pos.get("no_avg_price")
        yes_dust_avg = float(yes_dust_avg_raw) if yes_dust_avg_raw is not None else 0.0
        no_dust_avg = float(no_dust_avg_raw) if no_dust_avg_raw is not None else 0.0

        print(
            f"[REMOTE POS] market={market_id} "
            f"YES size={yes_dust_size:.1f} avg={yes_dust_avg:.4f}, "
            f"NO size={no_dust_size:.1f} avg={no_dust_avg:.4f}"
        )
    except Exception as e:
        print("[WARN] get_market_leg_positions failed, treat as no initial dust:", repr(e))

    last_pos_cache: Dict[Tuple[str, str], Tuple[float, float]] = {}

    ws_client = UserWebSocketClient(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        markets=[market_id],
        on_message=make_ws_on_message(state, last_pos_cache),
        verbose=False,
    )
    t = threading.Thread(target=ws_client.run_forever, daemon=True)
    t.start()

    # Give WS a short time to connect and start delivering events
    time.sleep(0.3)

    # YES / NO legs (include dust info)
    yes_leg = LegRoundState(
        label="YES",
        outcome="Up",
        token_id=yes_token_id,
        stage="LOOK_FOR_ENTRY",
        dust_size=yes_dust_size,
        dust_avg_price=yes_dust_avg,
    )
    no_leg = LegRoundState(
        label="NO",
        outcome="Down",
        token_id=no_token_id,
        stage="LOOK_FOR_ENTRY",
        dust_size=no_dust_size,
        dust_avg_price=no_dust_avg,
    )
    active_leg: Optional[LegRoundState] = None

    print("[STRAT] === Single round start (either YES or NO) ===")
    for leg in (yes_leg, no_leg):
        rs = state.get_risk_stats(market_id, leg.outcome)
        os = state.get_onchain_stats(market_id, leg.outcome)
        print(
            f"[POS] [{market_id} / {leg.outcome}] risk_pos={rs['pos']:.1f}, "
            f"risk_avg={rs['avg_price']:.4f}, on_pos={os['pos']:.1f}, "
            f"on_avg={os['avg_price']:.4f}"
        )

    round_deadline = bucket_ts + CONTRACT_DURATION_SEC
    round_done = False

    last_bid_ask = {
        "YES": (yes_bid, yes_ask),
        "NO": (no_bid, no_ask),
    }

    try:
        while not round_done and time.time() < round_deadline:
            frame = shm_reader.read_next_blocking()
            yes_bid = float(frame["yes_bid"])
            yes_ask = float(frame["yes_ask"])
            no_bid = float(frame["no_bid"])
            no_ask = float(frame["no_ask"])

            last_bid_ask["YES"] = (yes_bid, yes_ask)
            last_bid_ask["NO"] = (no_bid, no_ask)

            now = time.time()
            cap_usd = compute_cap_usd(now, bucket_ts)

            # Leg selection at the start:
            #   - If LEG_SELECTION_MODE == "YES_ONLY": only consider YES
            #   - If LEG_SELECTION_MODE == "NO_ONLY": only consider NO
            #   - Else (HIGHEST_BID / default):
            #       choose the leg with higher bid among those with bid >= ENTRY_BID_THRESHOLD
            if active_leg is None:
                chosen_label: Optional[str] = None

                if LEG_SELECTION_MODE == "YES_ONLY":
                    if yes_bid >= ENTRY_BID_THRESHOLD:
                        chosen_label = "YES"
                elif LEG_SELECTION_MODE == "NO_ONLY":
                    if no_bid >= ENTRY_BID_THRESHOLD:
                        chosen_label = "NO"
                else:  # "HIGHEST_BID" or anything else -> default behavior
                    candidates = []
                    if yes_bid >= ENTRY_BID_THRESHOLD:
                        candidates.append(("YES", yes_bid))
                    if no_bid >= ENTRY_BID_THRESHOLD:
                        candidates.append(("NO", no_bid))
                    if candidates:
                        chosen_label = max(candidates, key=lambda x: x[1])[0]

                if chosen_label is not None:
                    active_leg = yes_leg if chosen_label == "YES" else no_leg
                    print(f"[STRAT] activate leg={active_leg.label}")
                else:
                    continue

            leg = active_leg
            bid, ask = last_bid_ask[leg.label]

            # Current risk / on-chain position for THIS leg (this round)
            risk_stats = state.get_risk_stats(market_id, leg.outcome)
            on_stats = state.get_onchain_stats(market_id, leg.outcome)
            risk_pos = risk_stats["pos"]
            on_pos = on_stats["pos"]
            on_avg = on_stats["avg_price"]

            # ================= ENTRY state machine =================

            if leg.stage == "LOOK_FOR_ENTRY":
                # Clean up stale entry if not LIVE anymore
                if leg.entry_order_id and not is_order_live(state, leg.entry_order_id):
                    leg.entry_order_id = None
                    leg.entry_placed_at = 0.0

                # If we already have on-chain position at start of round
                # (historical position is in dust; here we only inspect this-round on_pos)
                if abs(on_pos) > EPS_POS:
                    if on_avg > 0.0:
                        leg.entry_price = on_avg

                    # Last window + entry >= threshold -> LATE_HOLD mode
                    if now >= round_deadline - LATE_WINDOW_SEC and (
                        leg.entry_price >= LATE_REENTRY_ENTRY_THRESHOLD
                    ):
                        leg.stop_loss = LATE_SL_TRIGGER  # trigger threshold
                        leg.late_hold = True
                        print(
                            f"[STRAT] {leg.label} found existing on-chain pos={on_pos:.1f}, "
                            f"avg={leg.entry_price:.4f}, in last {LATE_WINDOW_SEC}s & "
                            f"entry>={LATE_REENTRY_ENTRY_THRESHOLD:.4f}, "
                            f"stop_loss_trigger={LATE_SL_TRIGGER:.4f} -> LATE_HOLD"
                        )
                        leg.stage = "LATE_HOLD"
                    else:
                        # Normal EXIT mode, stop_loss is trigger price only
                        leg.stop_loss = compute_stop_loss_trigger(leg.entry_price)
                        print(
                            f"[STRAT] {leg.label} found existing on-chain pos={on_pos:.1f}, "
                            f"avg={leg.entry_price:.4f}, stop_loss_trigger={leg.stop_loss:.4f} "
                            f"-> PREP_EXIT"
                        )
                        leg.stage = "PREP_EXIT"
                    continue

                # No position, no active ENTRY, and bid >= ENTRY_BID_THRESHOLD -> place ENTRY
                if leg.entry_order_id is None and bid >= ENTRY_BID_THRESHOLD:
                    price = bid
                    if price <= 0:
                        continue
                    size_float = cap_usd / price
                    size = math.floor(size_float)
                    if size <= 0:
                        continue

                    print(
                        f"[STRAT] ENTRY {leg.label}: bid={bid:.4f}, price={price:.4f}, "
                        f"cap={cap_usd:.1f}, size={size:.1f}"
                    )

                    try:
                        resp = poly.place_limit(
                            token_id=leg.token_id,
                            side="BUY",
                            price=price,
                            size=float(size),
                            order_type="GTC",
                        )
                        print("[ENTRY RESP]", resp)
                    except Exception as e:
                        print("[ERROR] ENTRY failed:", repr(e))
                        continue

                    order_id = resp.get("orderId") or resp.get("orderID")
                    leg.entry_order_id = order_id
                    leg.entry_price = price
                    leg.entry_placed_at = now

                    # Initial SL trigger price
                    leg.stop_loss = compute_stop_loss_trigger(price)

                    print(
                        f"[STRAT] {leg.label} ENTRY placed, order_id={order_id}, "
                        f"entry_price={price:.4f}, stop_loss_trigger={leg.stop_loss:.4f}"
                    )

                    state.register_local_order(
                        order_id=order_id,
                        market_id=market_id,
                        outcome=leg.outcome,
                        side="BUY",
                        price=price,
                        size=float(size),
                        is_entry=True,
                        strategy_tag="time_bucket_mm",
                    )

                    leg.stage = "ENTRY_PLACED"

            elif leg.stage == "ENTRY_PLACED":
                # Once we see on-chain position, ENTRY is effective; cancel remaining ENTRY
                if abs(on_pos) > EPS_POS:
                    if on_avg > 0.0:
                        leg.entry_price = on_avg

                    leg.stop_loss = compute_stop_loss_trigger(leg.entry_price)

                    print(
                        f"[STRAT] {leg.label} ENTRY MINED, pos={on_pos:.1f}, "
                        f"avg={leg.entry_price:.4f}, stop_loss_trigger={leg.stop_loss:.4f} "
                        f"-> cancel remaining ENTRY"
                    )

                    if is_order_live(state, leg.entry_order_id):
                        try:
                            cancel_order(poly, leg.entry_order_id)
                            print(f"[STRAT] {leg.label} cancel ENTRY order_id={leg.entry_order_id}")
                        except Exception as e:
                            print("[ERROR] cancel ENTRY failed:", repr(e))

                    leg.stage = "ENTRY_CANCEL_WAIT"

                else:
                    # No on-chain position yet
                    if abs(risk_pos) > EPS_POS:
                        # Some matched volume but not MINED yet: do not cancel/re-quote
                        pass
                    else:
                        # risk_pos==0, on_pos==0 ->
                        # after ENTRY_REQUOTE_WAIT_SEC + bid improved at least
                        # ENTRY_REQUOTE_MIN_IMPROVE, cancel and re-enter
                        if (
                            leg.entry_order_id
                            and is_order_live(state, leg.entry_order_id)
                            and now - leg.entry_placed_at > ENTRY_REQUOTE_WAIT_SEC
                        ):
                            improve = bid - leg.entry_price
                            if improve >= ENTRY_REQUOTE_MIN_IMPROVE:
                                try:
                                    cancel_order(poly, leg.entry_order_id)
                                    print(
                                        f"[STRAT] {leg.label} ENTRY no fill >"
                                        f"{ENTRY_REQUOTE_WAIT_SEC:.1f}s, "
                                        f"bid={bid:.4f} improved {improve:.4f} "
                                        f">= {ENTRY_REQUOTE_MIN_IMPROVE:.4f}, "
                                        f"cancel order_id={leg.entry_order_id} "
                                        f"to re-enter later"
                                    )
                                except Exception as e:
                                    print("[ERROR] cancel stale ENTRY failed:", repr(e))
                                leg.stage = "ENTRY_CANCEL_WAIT"

            elif leg.stage == "ENTRY_CANCEL_WAIT":
                # Wait until entry order is no longer LIVE
                if leg.entry_order_id and not is_order_live(state, leg.entry_order_id):
                    print(f"[STRAT] {leg.label} ENTRY order_id={leg.entry_order_id} not LIVE anymore")
                    leg.entry_order_id = None
                    leg.entry_placed_at = 0.0

                    on_stats = state.get_onchain_stats(market_id, leg.outcome)
                    on_pos = on_stats["pos"]
                    on_avg = on_stats["avg_price"]

                    if abs(on_pos) > EPS_POS:
                        if on_avg > 0.0:
                            leg.entry_price = on_avg

                        now2 = time.time()
                        if now2 >= round_deadline - LATE_WINDOW_SEC and (
                            leg.entry_price >= LATE_REENTRY_ENTRY_THRESHOLD
                        ):
                            leg.stop_loss = LATE_SL_TRIGGER
                            leg.late_hold = True
                            print(
                                f"[STRAT] {leg.label} ENTRY finalized late, pos={on_pos:.1f}, "
                                f"avg={leg.entry_price:.4f} >= "
                                f"{LATE_REENTRY_ENTRY_THRESHOLD:.4f} & last "
                                f"{LATE_WINDOW_SEC}s, stop_loss_trigger="
                                f"{LATE_SL_TRIGGER:.4f} -> LATE_HOLD"
                            )
                            leg.stage = "LATE_HOLD"
                        else:
                            leg.stop_loss = compute_stop_loss_trigger(leg.entry_price)

                            print(
                                f"[STRAT] {leg.label} ENTRY finalized, pos={on_pos:.1f}, "
                                f"avg={leg.entry_price:.4f}, stop_loss_trigger="
                                f"{leg.stop_loss:.4f} -> PREP_EXIT"
                            )
                            leg.stage = "PREP_EXIT"
                    else:
                        print(f"[STRAT] {leg.label} ENTRY fully cancelled, no pos -> LOOK_FOR_ENTRY")
                        leg.stage = "LOOK_FOR_ENTRY"

            # ================= EXIT / TP / SL state machine =================

            elif leg.stage == "PREP_EXIT":
                # Effective total position = cross-round dust + current on_pos
                if ENABLE_DUST_MERGE:
                    dust_sz = max(0.0, float(leg.dust_size))
                else:
                    dust_sz = 0.0
                on_abs = abs(on_pos)
                total_size = dust_sz + on_abs

                if total_size < MIN_TRADE_SIZE - 1e-6:
                    # Not enough size to place >= MIN_TRADE_SIZE,
                    # optionally merge on_pos into dust and end this round
                    if ENABLE_DUST_MERGE and on_abs > EPS_POS:
                        on_avg_eff = on_avg if on_avg and on_avg > 0 else (
                            leg.entry_price if leg.entry_price > 0 else 0.0
                        )
                        num = 0.0
                        if dust_sz > 0 and leg.dust_avg_price > 0:
                            num += dust_sz * leg.dust_avg_price
                        if on_abs > 0 and on_avg_eff > 0:
                            num += on_abs * on_avg_eff
                        new_total = dust_sz + on_abs
                        if new_total > 0 and num > 0:
                            new_avg = num / new_total
                        else:
                            new_avg = leg.dust_avg_price or on_avg_eff or 0.0
                        leg.dust_size = new_total
                        leg.dust_avg_price = new_avg

                    print(
                        f"[STRAT] {leg.label} total_size={total_size:.1f} "
                        f"< MIN_TRADE_SIZE={MIN_TRADE_SIZE}, "
                        f"treat current pos as dust and DONE for this round"
                    )
                    leg.stage = "DONE"
                    round_done = True
                    break

                # Enough size, we can try EXIT; if we already have an exit_order, treat as EXIT_PLACED
                if leg.exit_order_id is not None:
                    leg.stage = "EXIT_PLACED"
                    continue

                # Use a size-weighted average across dust + on_pos as effective entry_price
                num = 0.0
                if dust_sz > 0 and leg.dust_avg_price > 0:
                    num += dust_sz * leg.dust_avg_price
                if on_abs > 0 and on_avg and on_avg > 0:
                    num += on_abs * on_avg

                if num > 0 and total_size > 0:
                    entry_price = num / total_size
                else:
                    entry_price = (
                        leg.entry_price
                        or (on_avg if on_avg and on_avg > 0 else 0.0)
                        or (leg.dust_avg_price if leg.dust_avg_price > 0 else 0.0)
                    )

                leg.entry_price = entry_price

                # Stop-loss trigger also based on merged entry_price
                leg.stop_loss = compute_stop_loss_trigger(entry_price)

                # Calculate TP price, bounded by MAX_TP_PRICE
                exit_price = compute_tp_price(leg.entry_price, bid)

                size = total_size
                if size <= 0:
                    leg.stage = "DONE"
                    round_done = True
                    break

                side = "SELL" if size > 0 else "BUY"
                print(
                    f"[STRAT] {leg.label} first EXIT TP: "
                    f"dust={dust_sz:.1f}, on_pos={on_pos:.1f}, total_size={size:.1f}, "
                    f"entry_price={entry_price:.4f}, stop_loss_trigger={leg.stop_loss:.4f}, "
                    f"bid={bid:.4f}, exit_price={exit_price:.4f}"
                )

                try:
                    resp = poly.place_limit(
                        token_id=leg.token_id,
                        side=side,
                        price=exit_price,
                        size=float(size),
                        order_type="GTC",
                    )
                    print("[EXIT TP RESP]", resp)
                except Exception as e:
                    print("[ERROR] EXIT TP failed:", repr(e))
                    # not enough balance / allowance etc. Usually indicates we already matched something.
                    msg = str(e).lower()
                    if "not enough balance" in msg or "allowance" in msg:
                        print(
                            f"[STRAT] {leg.label} EXIT TP likely already matched, "
                            f"switch to EXIT_WAIT_ONCHAIN"
                        )
                        leg.stage = "EXIT_WAIT_ONCHAIN"
                    continue

                exit_order_id = resp.get("orderId") or resp.get("orderID")
                leg.exit_order_id = exit_order_id
                leg.exit_placed_at = now

                # Once we hand over dust + on_pos to this EXIT,
                # downstream logic should no longer use dust separately
                if ENABLE_DUST_MERGE:
                    leg.dust_size = 0.0
                    leg.dust_avg_price = 0.0

                state.register_local_order(
                    order_id=exit_order_id,
                    market_id=market_id,
                    outcome=leg.outcome,
                    side=side,
                    price=exit_price,
                    size=float(size),
                    is_exit=True,
                    strategy_tag="time_bucket_mm",
                )

                leg.stage = "EXIT_PLACED"

            elif leg.stage == "EXIT_PLACED":
                live = leg.exit_order_id and is_order_live(state, leg.exit_order_id)

                on_stats = state.get_onchain_stats(market_id, leg.outcome)
                on_pos = on_stats["pos"]

                if leg.exit_order_id and not live:
                    order_obj = state.orders.get(leg.exit_order_id)
                    status = getattr(order_obj, "order_status", "") if order_obj else ""
                    status_u = status.upper() if isinstance(status, str) else ""

                    if abs(on_pos) < EPS_POS:
                        print(f"[STRAT] {leg.label} EXIT finished, pos flat, DONE")
                        leg.exit_order_id = None
                        leg.exit_placed_at = 0.0
                        leg.stage = "DONE"
                        round_done = True
                        break

                    if "CANCEL" in status_u:
                        print(
                            f"[STRAT] {leg.label} EXIT order CANCELED with on_pos={on_pos:.1f} > 0, "
                            f"back to PREP_EXIT to re-TP"
                        )
                        leg.exit_order_id = None
                        leg.exit_placed_at = 0.0
                        leg.stage = "PREP_EXIT"
                        continue

                    print(
                        f"[STRAT] {leg.label} EXIT matched off-chain (status={status}), "
                        f"waiting on-chain position to flatten"
                    )
                    leg.stage = "EXIT_WAIT_ONCHAIN"
                    continue

                if abs(on_pos) < EPS_POS:
                    print(f"[STRAT] {leg.label} on_pos ~0 in EXIT_PLACED, DONE")
                    leg.stage = "DONE"
                    round_done = True
                    break

                if leg.exit_order_id and live:
                    # Stop loss trigger: bid <= stop_loss_trigger,
                    # actual SL order price is always SL_ORDER_PRICE
                    if bid <= leg.stop_loss:
                        print(
                            f"[STRAT] {leg.label} STOP LOSS trigger: bid={bid:.4f} "
                            f"<= {leg.stop_loss:.4f}, cancel TP then place "
                            f"SL@{SL_ORDER_PRICE:.4f}"
                        )
                        if leg.exit_order_id and is_order_live(state, leg.exit_order_id):
                            try:
                                cancel_order(poly, leg.exit_order_id)
                                print(f"[STRAT] {leg.label} cancel TP order_id={leg.exit_order_id}")
                            except Exception as e:
                                print("[ERROR] cancel TP before SL failed:", repr(e))
                        leg.stage = "EXIT_CANCEL_FOR_SL"

            elif leg.stage == "EXIT_WAIT_ONCHAIN":
                on_stats = state.get_onchain_stats(market_id, leg.outcome)
                on_pos = on_stats["pos"]
                if abs(on_pos) < EPS_POS:
                    print(f"[STRAT] {leg.label} EXIT on-chain finished, pos flat, DONE")
                    leg.stage = "DONE"
                    round_done = True
                    break

            # ================= Last window: LATE_HOLD / LATE_SL =================

            elif leg.stage == "LATE_HOLD":
                on_stats = state.get_onchain_stats(market_id, leg.outcome)
                on_pos = on_stats["pos"]

                if abs(on_pos) > EPS_POS:
                    # bid <= LATE_SL_TRIGGER triggers stop loss; actual SL price is SL_ORDER_PRICE
                    if bid <= LATE_SL_TRIGGER and leg.exit_order_id is None:
                        size = abs(on_pos)
                        if size > 0:
                            side = "SELL" if on_pos > 0 else "BUY"
                            sl_price = SL_ORDER_PRICE
                            print(
                                f"[STRAT] {leg.label} LATE_HOLD SL trigger: "
                                f"bid={bid:.4f} <= {LATE_SL_TRIGGER:.4f}, "
                                f"place LATE SL at {sl_price:.4f} size={size:.1f}"
                            )
                            try:
                                resp = poly.place_limit(
                                    token_id=leg.token_id,
                                    side=side,
                                    price=sl_price,
                                    size=float(size),
                                    order_type="GTC",
                                )
                                print("[LATE SL RESP]", resp)
                            except Exception as e:
                                print("[ERROR] LATE SL place failed:", repr(e))
                                continue

                            exit_order_id = resp.get("orderId") or resp.get("orderID")
                            leg.exit_order_id = exit_order_id
                            leg.exit_placed_at = time.time()

                            state.register_local_order(
                                order_id=exit_order_id,
                                market_id=market_id,
                                outcome=leg.outcome,
                                side=side,
                                price=sl_price,
                                size=float(size),
                                is_exit=True,
                                strategy_tag="time_bucket_mm_late",
                            )

                            leg.stage = "LATE_SL_PLACED"

                else:
                    # No on-chain position (possibly just fully stopped out)
                    can_reenter = (
                        ENABLE_LATE_REENTRY
                        and leg.late_hold
                        and leg.late_sl_hit
                        and (not leg.late_reentry_done)
                        and leg.late_reentry_count < MAX_LATE_REENTRIES
                        and now < round_deadline
                    )
                    if can_reenter and bid >= LATE_REENTRY_ENTRY_THRESHOLD:
                        price = bid
                        if price > 0:
                            size_float = cap_usd / price
                            size = math.floor(size_float)
                            if size > 0:
                                print(
                                    f"[STRAT] {leg.label} LATE re-entry: bid={bid:.4f} "
                                    f">= {LATE_REENTRY_ENTRY_THRESHOLD:.4f}, "
                                    f"price={price:.4f}, cap={cap_usd:.1f}, "
                                    f"size={size:.1f}"
                                )
                                try:
                                    resp = poly.place_limit(
                                        token_id=leg.token_id,
                                        side="BUY",
                                        price=price,
                                        size=float(size),
                                        order_type="GTC",
                                    )
                                    print("[LATE RE-ENTRY RESP]", resp)
                                except Exception as e:
                                    print("[ERROR] LATE RE-ENTRY failed:", repr(e))
                                    # Even if failed, count this attempt as used
                                    leg.late_reentry_count += 1
                                    if leg.late_reentry_count >= MAX_LATE_REENTRIES:
                                        leg.late_reentry_done = True
                                    continue

                                order_id = resp.get("orderId") or resp.get("orderID")
                                leg.entry_order_id = order_id
                                leg.entry_price = price
                                leg.entry_placed_at = time.time()

                                leg.stop_loss = LATE_SL_TRIGGER       # trigger threshold
                                leg.late_reentry_count += 1
                                if leg.late_reentry_count >= MAX_LATE_REENTRIES:
                                    leg.late_reentry_done = True
                                leg.late_sl_hit = False

                                state.register_local_order(
                                    order_id=order_id,
                                    market_id=market_id,
                                    outcome=leg.outcome,
                                    side="BUY",
                                    price=price,
                                    size=float(size),
                                    is_entry=True,
                                    strategy_tag="time_bucket_mm_late_reentry",
                                )

                                leg.stage = "ENTRY_PLACED"

            elif leg.stage == "LATE_SL_PLACED":
                if leg.exit_order_id and not is_order_live(state, leg.exit_order_id):
                    leg.exit_order_id = None
                    leg.exit_placed_at = 0.0

                    on_stats = state.get_onchain_stats(market_id, leg.outcome)
                    on_pos = on_stats["pos"]

                    if abs(on_pos) < EPS_POS:
                        print(f"[STRAT] {leg.label} LATE SL finished, pos flat")
                        leg.late_sl_hit = True
                    else:
                        print(
                            f"[STRAT] {leg.label} LATE SL finished but on_pos={on_pos:.1f} > 0, "
                            f"still LATE_HOLD"
                        )
                    leg.stage = "LATE_HOLD"

            elif leg.stage == "EXIT_CANCEL_FOR_SL":
                if leg.exit_order_id and not is_order_live(state, leg.exit_order_id):
                    print(f"[STRAT] {leg.label} TP order_id={leg.exit_order_id} not LIVE, ready for SL")
                    leg.exit_order_id = None
                    leg.exit_placed_at = 0.0

                    on_stats = state.get_onchain_stats(market_id, leg.outcome)
                    on_pos = on_stats["pos"]
                    if abs(on_pos) < EPS_POS:
                        print(f"[STRAT] {leg.label} position already flat after TP cancel, DONE")
                        leg.stage = "DONE"
                        round_done = True
                        break

                    size = abs(on_pos)
                    sl_price = SL_ORDER_PRICE      # all EXIT stop-loss orders use SL_ORDER_PRICE
                    side = "SELL" if on_pos > 0 else "BUY"

                    try:
                        resp = poly.place_limit(
                            token_id=leg.token_id,
                            side=side,
                            price=sl_price,
                            size=float(size),
                            order_type="GTC",
                        )
                        print("[EXIT SL RESP]", resp)
                    except Exception as e:
                        print("[ERROR] EXIT SL failed:", repr(e))
                        continue

                    exit_order_id = resp.get("orderId") or resp.get("orderID")
                    leg.exit_order_id = exit_order_id
                    leg.exit_placed_at = time.time()

                    state.register_local_order(
                        order_id=exit_order_id,
                        market_id=market_id,
                        outcome=leg.outcome,
                        side=side,
                        price=sl_price,
                        size=float(size),
                        is_exit=True,
                        strategy_tag="time_bucket_mm",
                    )

                    leg.stage = "EXIT_SL_PLACED"

            elif leg.stage == "EXIT_SL_PLACED":
                if leg.exit_order_id and not is_order_live(state, leg.exit_order_id):
                    leg.exit_order_id = None
                    leg.exit_placed_at = 0.0

                    on_stats = state.get_onchain_stats(market_id, leg.outcome)
                    on_pos = on_stats["pos"]

                    if abs(on_pos) < EPS_POS:
                        print(f"[STRAT] {leg.label} SL finished, pos flat, DONE")
                        leg.stage = "DONE"
                        round_done = True
                        break
                    else:
                        print(
                            f"[STRAT] {leg.label} SL finished but on_pos={on_pos:.1f} > 0, "
                            f"back to PREP_EXIT"
                        )
                        leg.stage = "PREP_EXIT"
                        continue

            if leg.stage == "DONE":
                round_done = True
                break

    finally:
        print("\n[FINAL SUMMARY]")
        for leg in (yes_leg, no_leg):
            rs = state.get_risk_stats(market_id, leg.outcome)
            os = state.get_onchain_stats(market_id, leg.outcome)
            print(
                f"  [{market_id} / {leg.outcome}] risk_pos={rs['pos']:.1f}, "
                f"risk_avg={rs['avg_price']:.4f}, on_pos={os['pos']:.1f}, "
                f"on_avg={os['avg_price']:.4f}"
            )

        for oid, order in state.orders.items():
            print_super_order_snapshot(oid, order)

        if created_local_reader:
            try:
                shm_reader.close()
            except Exception as e:
                print("[WARN] shm_reader.close failed:", repr(e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    run_single_round()


if __name__ == "__main__":
    main()