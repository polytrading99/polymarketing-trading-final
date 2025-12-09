#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Elon Tweet Parent Theme Bot

- Monitors all active, open events on Polymarket (via Gamma API)
- Filters for parent events related to "Elon Musk tweets"
- For every NEW parent event:
    * scans its markets (tweet-count ranges)
    * selects eligible brackets according to config:
        - TEST_TOP_BRACKET_ONLY = true:
            -> only place orders in the top bracket, e.g. "500+ tweets"
        - TEST_TOP_BRACKET_ONLY = false:
            -> place orders in all brackets starting at MIN_BRACKET_START
              (e.g. 40-59, 50-69, ... depending on how markets are defined)
    * places a BUY limit order on the YES side at LIMIT_PRICE
      with notional INVEST_PER_MARKET_USD

Remote position alignment:
- For every parent event (new or seen):
    * for each eligible market we ALREADY traded (or detected remote position in):
        - fetch current YES position from Polymarket (get_positions)
        - target_size = floor(INVEST_PER_MARKET_USD / LIMIT_PRICE)
            * normal mode: INVEST_PER_MARKET_USD > 0    -> target_size > 0
            * clear mode : INVEST_PER_MARKET_USD == 0   -> target_size = 0
        - if REMOTE ~= target_size: reset mismatch counter
        - if REMOTE < target_size: mark as SHORT vs config
        - if REMOTE > target_size: mark as LONG  vs config
        - only if the mismatch persists for 3 consecutive polls:
            -> BUY or SELL to realign to target_size
        - if orderbook for a token_id does not exist:
            -> mark this token as realign_disabled, never try again

Safety / bookkeeping:
- Uses existing PolymarketClient + PRIVATE_KEY from config["api"]
- Maintains a local JSON "order_state" file:
    - "placed_yes_tokens": any YES token_id that has been traded is recorded
    - "mismatch_counts": per-token consecutive mismatch counter
- On restart, the bot will NOT place a fresh "new-market" order
  for any YES token_id that is already recorded in "placed_yes_tokens"
- Can be run in "monitor only" mode by setting ENABLE_TRADING = false
- Clear mode: if INVEST_PER_MARKET_USD == 0, bot will NOT open new positions,
  but will gradually realign existing positions down to 0 (flat) after
  3 consecutive mismatch detections (except those with missing orderbook).
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from data_reader.load_config import CONFIG
from state_machine.polymarket_client import PolymarketClient

# ---------------------------------------------------------------------------
# Config & constants
# ---------------------------------------------------------------------------

GAMMA_BASE = "https://gamma-api.polymarket.com"

API_CFG = CONFIG["api"]
ELON_CFG = CONFIG["elon_tweet_bot"]

PRIVATE_KEY: str = API_CFG["PRIVATE_KEY"]
PROXY_ADDRESS: Optional[str] = API_CFG.get("PROXY_ADDRESS") or None
SIGNATURE_TYPE: Optional[int] = API_CFG.get("SIGNATURE_TYPE")
CHAIN_ID: int = int(API_CFG["CHAIN_ID"])

ENABLE_TRADING: bool = bool(ELON_CFG.get("ENABLE_TRADING", True))
TEST_TOP_BRACKET_ONLY: bool = bool(ELON_CFG.get("TEST_TOP_BRACKET_ONLY", True))

POLL_INTERVAL_SEC: int = int(ELON_CFG.get("POLL_INTERVAL_SEC", 30))
SEARCH_KEYWORDS: List[str] = [str(x).lower() for x in ELON_CFG.get("SEARCH_KEYWORDS", ["elon", "musk", "tweet"])]

LIMIT_PRICE: float = float(ELON_CFG.get("LIMIT_PRICE", 0.04))
INVEST_PER_MARKET_USD: float = float(ELON_CFG.get("INVEST_PER_MARKET_USD", 2.0))
MIN_BRACKET_START: int = int(ELON_CFG.get("MIN_BRACKET_START", 40))

ORDER_STATE_FILE: str = str(ELON_CFG.get("ORDER_STATE_FILE", "elon_tweet_orders.json"))


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def now_utc_str() -> str:
    """Return current UTC time string for logs."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ensure_list(x: Any) -> List[Any]:
    """Normalize a field to list."""
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


# ---------------------------------------------------------------------------
# Order state persistence
# ---------------------------------------------------------------------------

def load_order_state(path: str) -> Dict[str, Any]:
    """
    Load local order state from JSON file.

    Structure (example):
        {
            "placed_yes_tokens": {
                "1234": {
                    "event_id": "87321",
                    "market_id": "xxxxx",
                    "question": "500+ tweets",
                    "price": 0.04,
                    "size": 50.0,
                    "order_id": "abcd-efgh",
                    "placed_at": "2025-12-01 18:00:00 UTC"
                },
                ...
            },
            "mismatch_counts": {
                "1234": 2,
                ...
            }
        }
    """
    if not os.path.exists(path):
        return {
            "placed_yes_tokens": {},
            "mismatch_counts": {},
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        print(f"[ORDER-STATE][WARN] failed to load {path}: {e!r}, reset state.")
        data = {}

    if "placed_yes_tokens" not in data or not isinstance(data.get("placed_yes_tokens"), dict):
        data["placed_yes_tokens"] = {}

    if "mismatch_counts" not in data or not isinstance(data.get("mismatch_counts"), dict):
        data["mismatch_counts"] = {}

    return data


def save_order_state(path: str, state: Dict[str, Any]) -> None:
    """Persist order state to JSON file atomically (best-effort)."""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"[ORDER-STATE][ERROR] failed to save {path}: {e!r}")


# ---------------------------------------------------------------------------
# Parent-event detection
# ---------------------------------------------------------------------------

def is_elon_tweet_event(ev: Dict[str, Any]) -> bool:
    """
    Decide whether an event is related to "Elon Musk tweets" based on text fields.
    We only rely on local keyword matching, not Gamma's search.
    """
    title = (ev.get("title") or "") + " "
    question = (ev.get("question") or "") + " "
    description = (ev.get("description") or "") + ""

    text = f"{title}{question}{description}".lower()
    return all(kw in text for kw in SEARCH_KEYWORDS)


def fetch_active_events() -> List[Dict[str, Any]]:
    """
    Fetch all active, open events via paging:
        GET /events?active=true&closed=false&limit=200&offset=...
    """
    limit = 200
    offset = 0
    events: List[Dict[str, Any]] = []

    while True:
        url = f"{GAMMA_BASE}/events?active=true&closed=false&limit={limit}&offset={offset}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list):
            break
        events.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return events


def parse_bracket(question: str) -> Optional[Tuple[int, Optional[int], bool]]:
    """
    Parse a tweet-count bracket from a market question string.

    Examples:
        "40-59 tweets" -> (40, 59, False)
        "500+ tweets"  -> (500, None, True)

    Returns:
        (start, end, is_top_plus)
        or None if pattern not recognized.
    """
    s = (question or "").lower()

    # "40-59 tweets"
    m = re.search(r"(\d+)\s*-\s*(\d+)", s)
    if m:
        start = int(m.group(1))
        end = int(m.group(2))
        return start, end, False

    # "500+ tweets"
    m = re.search(r"(\d+)\s*\+", s)
    if m:
        start = int(m.group(1))
        return start, None, True

    return None


def pick_yes_token_id(market: Dict[str, Any]) -> Optional[str]:
    """
    From a market object, pick the YES token_id.

    - outcomes: ["Yes", "No"] (or similar)
    - clobTokenIds: ["token_yes", "token_no"]

    We look for outcome containing 'yes', otherwise fall back to index 0.
    """
    outcomes = _ensure_list(market.get("outcomes"))
    tokens = _ensure_list(
        market.get("clobTokenIds") or market.get("clob_token_ids")
    )
    if not tokens:
        return None

    yes_idx: Optional[int] = None
    for i, name in enumerate(outcomes):
        if isinstance(name, str) and "yes" in name.lower():
            yes_idx = i
            break

    if yes_idx is None:
        yes_idx = 0

    if yes_idx < 0 or yes_idx >= len(tokens):
        yes_idx = 0

    return str(tokens[yes_idx])


# ---------------------------------------------------------------------------
# Remote position helper
# ---------------------------------------------------------------------------

def fetch_remote_yes_position(
    poly: Optional[PolymarketClient],
    yes_token_id: str,
) -> float:
    """
    Fetch current YES position size for a given token_id from Polymarket.

    Implementation:
    - call get_positions() for current wallet
    - find entry where asset == yes_token_id
    - return its size; if none, return 0.0
    """
    if poly is None:
        return 0.0

    try:
        positions = poly.get_positions(
            user=None,          # current wallet / proxy
            market_id=None,     # don't filter by market_id
            size_threshold=0.0,
            limit=1000,
        )
    except Exception as e:
        print(f"[REMOTE-POS][ERROR] get_positions failed: {e!r}")
        return 0.0

    if not isinstance(positions, list):
        return 0.0

    for p in positions:
        try:
            asset = str(p.get("asset") or "")
            if asset == yes_token_id:
                size = float(p.get("size") or 0.0)
                title = p.get("title") or ""
                print(
                    f"    [REMOTE-POS] token={yes_token_id}, title='{title}', size={size}"
                )
                return size
        except Exception:
            continue

    print(f"    [REMOTE-POS] token={yes_token_id}, no position found (treat as 0).")
    return 0.0


# ---------------------------------------------------------------------------
# Trading logic for a NEW parent event
# ---------------------------------------------------------------------------

def handle_new_parent_event(
    ev: Dict[str, Any],
    poly: Optional[PolymarketClient],
    order_state: Dict[str, Any],
) -> None:
    """
    For a NEW parent event:
    - inspect its markets
    - pick eligible brackets
    - for each bracket:
        * find YES token_id
        * check local order_state to avoid duplicates
        * also read remote position (so we know existing manual exposure)
        * if eligible:
            - if we already have remote position > 0 but not recorded:
                -> record it as placed_yes_token, do NOT place a new order
            - else if no remote position and not traded before:
                -> if target_size > 0 and ENABLE_TRADING: place BUY limit order
                -> record in order_state

    Note: when INVEST_PER_MARKET_USD == 0 (clear mode), target_size == 0:
    - We will still record existing remote positions
    - But we will NOT open any new positions
    - Alignment logic will then try to gradually sell down to 0 (except tokens
      where orderbook no longer exists).
    """
    event_id = str(ev.get("id") or ev.get("event_id") or "")
    slug = ev.get("slug") or ""
    title = ev.get("title") or ev.get("question") or ""

    markets = ev.get("markets") or []
    if not isinstance(markets, list):
        print("    [WARN] event has no 'markets' list, skip.")
        return

    placed_yes_tokens: Dict[str, Any] = order_state.get("placed_yes_tokens", {})

    # target size per market according to config
    if LIMIT_PRICE <= 0:
        print("    [ERROR] LIMIT_PRICE <= 0, cannot compute target size (no new orders).")
        target_size = 0
    else:
        raw = INVEST_PER_MARKET_USD / LIMIT_PRICE
        target_size = int(raw) if raw >= 0 else 0

    clear_mode = (INVEST_PER_MARKET_USD <= 0)

    for m in markets:
        if not isinstance(m, dict):
            continue
        m_id = str(m.get("id") or m.get("conditionId") or m.get("condition_id") or "")
        m_question = m.get("question") or m.get("title") or ""

        bracket = parse_bracket(m_question)
        if not bracket:
            # Not a tweet-count bracket we recognize
            continue

        start, end, is_top = bracket

        # Filter by MIN_BRACKET_START
        if start < MIN_BRACKET_START:
            continue

        # Test mode: only place orders in the top bracket (e.g. "500+")
        if TEST_TOP_BRACKET_ONLY and not is_top:
            continue

        yes_token = pick_yes_token_id(m)
        if not yes_token:
            print(f"    [SKIP] market_id={m_id}, question='{m_question}' has no YES token.")
            continue

        # Read remote position regardless, for info / future alignment
        remote_size = fetch_remote_yes_position(poly, yes_token)

        # If this YES token already recorded locally, don't treat as new
        if yes_token in placed_yes_tokens:
            print(
                f"    [SKIP-PLACED] market_id={m_id}, q='{m_question}', YES={yes_token} "
                f"already in local state, remote_size={remote_size}."
            )
            continue

        # If we already have some remote size (manual trade), record it as initial state,
        # but do NOT place additional order now; alignment logic will handle it.
        if remote_size > 0:
            print(
                f"    [FOUND-REMOTE] market_id={m_id}, q='{m_question}', YES={yes_token}, "
                f"remote_size={remote_size} > 0. Record and skip fresh order."
            )
            placed_yes_tokens[yes_token] = {
                "event_id": event_id,
                "slug": slug,
                "market_id": m_id,
                "question": m_question,
                "price": LIMIT_PRICE,
                "size": float(remote_size),
                "notional_usd": float(remote_size) * LIMIT_PRICE,
                "order_id": None,
                "placed_at": now_utc_str(),
                "note": "imported_from_remote_position",
            }
            order_state["placed_yes_tokens"] = placed_yes_tokens
            save_order_state(ORDER_STATE_FILE, order_state)
            continue

        # No remote position and not recorded locally
        # If we are in clear mode (target_size == 0), do NOT open a new position
        if target_size == 0:
            print(
                f"    [CLEAR-MODE] market_id={m_id}, q='{m_question}', YES={yes_token}, "
                f"remote_size={remote_size}, target_size=0 -> no new order."
            )
            continue

        print(
            f"    [CANDIDATE] market_id={m_id}, q='{m_question}', "
            f"bracket_start={start}, bracket_end={end}, top_bracket={is_top}, "
            f"YES token_id={yes_token}, price={LIMIT_PRICE:.4f}, target_size={target_size} "
            f"(~${target_size * LIMIT_PRICE:.2f}), remote_size={remote_size}"
        )

        if not ENABLE_TRADING or poly is None:
            print("      -> ENABLE_TRADING is False, monitor-only (no order placed).")
            continue

        try:
            resp = poly.place_limit(
                token_id=yes_token,
                side="BUY",
                price=LIMIT_PRICE,
                size=float(target_size),
                order_type="GTC",
            )
            print(
                f"      [TRADE] place_limit BUY {target_size}@{LIMIT_PRICE:.4f} "
                f"YES token={yes_token}"
            )
            print(f"      [TRADE-RESP] {resp}")
        except Exception as e:
            print(f"      [ERROR] place_limit failed: {e!r}")
            continue

        order_id = (resp or {}).get("orderId") or (resp or {}).get("orderID") or ""
        placed_at = now_utc_str()

        placed_yes_tokens[yes_token] = {
            "event_id": event_id,
            "slug": slug,
            "market_id": m_id,
            "question": m_question,
            "price": LIMIT_PRICE,
            "size": float(target_size),
            "notional_usd": float(target_size) * LIMIT_PRICE,
            "order_id": order_id,
            "placed_at": placed_at,
        }

        # Persist after each successful order to avoid loss on crash
        order_state["placed_yes_tokens"] = placed_yes_tokens
        save_order_state(ORDER_STATE_FILE, order_state)
        print(f"      [STATE] recorded YES token_id={yes_token} into {ORDER_STATE_FILE}")


# ---------------------------------------------------------------------------
# Position alignment for existing events
# ---------------------------------------------------------------------------

def check_and_realign_positions_for_event(
    ev: Dict[str, Any],
    poly: Optional[PolymarketClient],
    order_state: Dict[str, Any],
) -> None:
    """
    For a parent event we already know:
    - For each eligible market where we have traded YES (or imported it):
        * fetch remote YES position
        * target_size = floor(INVEST_PER_MARKET_USD / LIMIT_PRICE)
            - normal mode: > 0
            - clear mode : = 0  (sell down to flat)
        * if remote_size ~= target_size: reset mismatch counter
        * if remote_size <  target_size: mark SHORT vs config
        * if remote_size >  target_size: mark LONG  vs config
        * only when the same direction mismatch persists for 3 polls:
            -> BUY or SELL to realign back to target_size
        * if orderbook does not exist for token:
            -> mark realign_disabled, never try again
    """

    markets = ev.get("markets") or []
    if not isinstance(markets, list) or not markets:
        return

    placed_yes_tokens: Dict[str, Any] = order_state.get("placed_yes_tokens", {})
    mismatch_counts: Dict[str, int] = order_state.get("mismatch_counts", {})

    if LIMIT_PRICE <= 0:
        # cannot compute target_size meaningfully, so skip
        return

    raw = INVEST_PER_MARKET_USD / LIMIT_PRICE
    target_size = int(raw) if raw >= 0 else 0  # allow 0 for clear mode

    event_id = str(ev.get("id") or ev.get("event_id") or "")
    slug = ev.get("slug") or ""
    title = ev.get("title") or ev.get("question") or ""

    for m in markets:
        if not isinstance(m, dict):
            continue

        m_id = str(m.get("id") or m.get("conditionId") or m.get("condition_id") or "")
        m_question = m.get("question") or m.get("title") or ""

        bracket = parse_bracket(m_question)
        if not bracket:
            continue
        start, end, is_top = bracket
        if start < MIN_BRACKET_START:
            continue
        if TEST_TOP_BRACKET_ONLY and not is_top:
            continue

        yes_token = pick_yes_token_id(m)
        if not yes_token:
            continue

        rec = placed_yes_tokens.get(yes_token) or {}

        # Only align tokens we've recorded locally
        if not rec:
            continue

        # if this token has been marked as realign_disabled, skip it
        if rec.get("realign_disabled"):
            print(
                f"    [REALIGN-DISABLED] event_id={event_id}, market_id={m_id}, "
                f"YES={yes_token}, skip alignment due to previous errors."
            )
            continue

        remote_yes_size = fetch_remote_yes_position(poly, yes_token)

        diff = float(remote_yes_size) - float(target_size)
        # Treat tiny diff as aligned
        if abs(diff) < 1e-6:
            if mismatch_counts.get(yes_token):
                print(
                    f"    [ALIGN] event_id={event_id}, market_id={m_id}, YES={yes_token}, "
                    f"remote_yes_size={remote_yes_size} ~ target_size={target_size}, "
                    f"reset mismatch counter."
                )
            mismatch_counts[yes_token] = 0
            continue

        direction = "SHORT" if diff < 0 else "LONG"  # SHORT=underweight, LONG=overweight
        # clamp counter to max 3, avoid 4/3, 5/3...
        mismatch_counts[yes_token] = min(mismatch_counts.get(yes_token, 0) + 1, 3)
        cnt = mismatch_counts[yes_token]

        print(
            f"    [MISMATCH] event_id={event_id}, market_id={m_id}, YES={yes_token}, "
            f"remote_yes_size={remote_yes_size}, target_size={target_size}, "
            f"direction={direction}, counter={cnt}/3"
        )

        # Need 3 consecutive mismatches + trading enabled
        if cnt < 3 or not ENABLE_TRADING or poly is None:
            continue

        # Third time still mismatched -> realign
        if diff < 0:
            # remote < target -> need BUY
            delta = -diff
            side = "BUY"
        else:
            # remote > target -> need SELL
            delta = diff
            side = "SELL"

        delta_int = int(delta)
        if delta_int <= 0:
            mismatch_counts[yes_token] = 0
            continue

        try:
            resp = poly.place_limit(
                token_id=yes_token,
                side=side,
                price=LIMIT_PRICE,   # 如果想卖用不同价格，可以改这里或加 SELL_LIMIT_PRICE 配置
                size=float(delta_int),
                order_type="GTC",
            )
            print(
                f"    [REALIGN] {side} {delta_int}@{LIMIT_PRICE:.4f} YES token={yes_token} "
                f"(event_id={event_id}, market_id={m_id})"
            )
            print(f"    [REALIGN-RESP] {resp}")
        except Exception as e:
            msg = repr(e)
            print(f"    [REALIGN][ERROR] place_limit failed: {msg}")

            # 如果是 orderbook 不存在，说明这个 token 已经不能交易了，标记熄火
            if "orderbook" in msg and "does not exist" in msg:
                rec = placed_yes_tokens.get(yes_token) or {}
                rec["realign_disabled"] = True
                rec["realign_disabled_at"] = now_utc_str()
                rec["realign_disabled_reason"] = "orderbook_not_exist"
                placed_yes_tokens[yes_token] = rec
                mismatch_counts[yes_token] = 0
                order_state["placed_yes_tokens"] = placed_yes_tokens
                order_state["mismatch_counts"] = mismatch_counts
                save_order_state(ORDER_STATE_FILE, order_state)
                print(
                    f"    [REALIGN-STOP] YES={yes_token} -> orderbook missing, "
                    f"disable further alignment attempts."
                )
            else:
                # 其他错误：稍微降一点计数，避免卡死在 3/3
                mismatch_counts[yes_token] = max(0, mismatch_counts.get(yes_token, 1) - 1)

            continue

        # Update local record
        rec = placed_yes_tokens.get(yes_token) or {}
        prev_size = float(rec.get("size") or 0.0)

        if side == "BUY":
            new_size = prev_size + float(delta_int)
        else:
            new_size = max(0.0, prev_size - float(delta_int))

        rec["size"] = new_size
        rec["notional_usd"] = new_size * LIMIT_PRICE
        rec["last_realign_at"] = now_utc_str()
        rec["last_realign_side"] = side
        rec["last_realign_size"] = float(delta_int)
        placed_yes_tokens[yes_token] = rec

        mismatch_counts[yes_token] = 0
        order_state["placed_yes_tokens"] = placed_yes_tokens
        order_state["mismatch_counts"] = mismatch_counts
        save_order_state(ORDER_STATE_FILE, order_state)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main_loop() -> None:
    print("=== Elon Tweet Parent Theme Bot ===")
    print(f"Gamma base     : {GAMMA_BASE}")
    print(f"Scan source    : /events?active=true&closed=false (local filter on text)")
    print(f"Poll interval  : {POLL_INTERVAL_SEC} seconds")
    print(f"Trading enabled: {ENABLE_TRADING}")
    print(f"Test top-only  : {TEST_TOP_BRACKET_ONLY} (only X+ bracket if True)")
    print(f"Limit price    : {LIMIT_PRICE:.4f}")
    print(f"Invest/market  : ${INVEST_PER_MARKET_USD:.2f}")
    print(f"Min bracket    : {MIN_BRACKET_START} tweets")
    print(f"Order state    : {ORDER_STATE_FILE}")
    print("----------------------------------------------------")

    # Local memory of which parent events we've already processed
    seen_event_ids: Set[str] = set()

    # Load order state (to avoid duplicate orders across restarts)
    order_state = load_order_state(ORDER_STATE_FILE)

    # PolymarketClient for real trading (or None if we are monitor-only)
    poly: Optional[PolymarketClient] = None
    if ENABLE_TRADING:
        poly = PolymarketClient(
            host="https://clob.polymarket.com",
            private_key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=SIGNATURE_TYPE,
            funder=PROXY_ADDRESS,
        )
        print("[INIT] PolymarketClient initialized for trading.\n")
    else:
        print("[INIT] ENABLE_TRADING is False, running in monitor-only mode.\n")

    while True:
        try:
            now_str = now_utc_str()
            events = fetch_active_events()
            elon_events = [e for e in events if is_elon_tweet_event(e)]

            print(f"[{now_str}] Found {len(elon_events)} Elon-tweet-related parent event(s).")

            for ev in elon_events:
                eid = str(ev.get("id") or ev.get("event_id") or "")
                is_new = eid not in seen_event_ids

                if is_new:
                    slug = ev.get("slug") or ""
                    title = ev.get("title") or ev.get("question") or ""
                    print(f"  [NEW] id={eid} | slug={slug} | title={title}")
                    handle_new_parent_event(ev, poly, order_state)
                    seen_event_ids.add(eid)
                else:
                    slug = ev.get("slug") or ""
                    title = ev.get("title") or ev.get("question") or ""
                    print(f"  [SEEN] id={eid} | slug={slug} | title={title}")

                # 对所有已知 event 做一次仓位对齐检查
                check_and_realign_positions_for_event(ev, poly, order_state)

        except KeyboardInterrupt:
            print("\n[MAIN] KeyboardInterrupt received, exiting gracefully.")
            break
        except Exception as e:
            print(f"[MAIN][ERROR] {e!r}")
            # Don't crash on one error; just wait and retry
        finally:
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main_loop()