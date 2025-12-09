# main.py
"""
Legacy end-to-end integration script (manual testing only).

This script performs a minimal flow against Polymarket CLOB:

- Resolve the BTC 15m up/down market for the current time bucket via Gamma.
- Initialise:
    - PolymarketClient (REST, order placement)
    - AccountState (order/trade state machine)
    - UserWebSocketClient (user WS feed -> AccountState)
- Trading flow:
    1) Place a taker BUY order on the "Up" outcome for 10 units at a fixed price.
    2) Continuously watch on-chain position (MINED / CONFIRMED).
    3) As soon as an on-chain position appears for (market, "Up") and there is no
       live exit order, place a flattening order in the opposite direction.

For every user WebSocket message:
- Print the raw JSON payload.
- Feed it into AccountState.
- For any known order referenced by the message, print a SuperOrder snapshot.

Notes:
- This file is intended for local / manual testing and should be treated as legacy
  infrastructure. It is not used by the production strategy engine.
- A hard-coded test private key is used here purely as an example. Never commit a
  real key in version control.
"""

import json
import time
from typing import Any, Dict, Tuple, Optional

import requests

from state_machine import AccountState
from state_machine.ws_client import UserWebSocketClient
from state_machine.polymarket_client import PolymarketClient


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

# !!!! DO NOT COMMIT REAL PRIVATE KEY !!!!
# This key is only for local experiments with a test account.
PRIVATE_KEY: str = "0x61f56731f3809ab4fcb619cac9bf72e5b9209971e2dc11aab9bd278d64bc41e9"
PROXY_ADDRESS: Optional[str] = "0x677aCdb80221e0F6F38143a675549CD6eDAf88F5"
SIGNATURE_TYPE: Optional[int] = 1
CHAIN_ID = 137

# Duration of the BTC up/down contract bucket in seconds (15 minutes).
CONTRACT_DURATION_SEC = 15 * 60


# ---------------------------------------------------------------------------
# Gamma helpers
# ---------------------------------------------------------------------------

def build_btc_15m_slug_from_bucket(bucket: int) -> str:
    """
    Build the Gamma event slug for a BTC 15m up/down contract, given the bucket
    start timestamp (in seconds).
    """
    return f"btc-updown-15m-{bucket}"


def _ensure_list(x: Any) -> list:
    """
    Normalise a value to a list of strings.

    - If `x` is already a list, return it as-is.
    - If `x` is a JSON list encoded as a string, parse and return it.
    - Otherwise, treat it as a comma-separated string.
    """
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
    Resolve the BTC 15m up/down market for a given bucket timestamp.

    Args:
        bucket_ts: Bucket start timestamp in seconds.

    Returns:
        (market_id, yes_token_id, no_token_id) where:
            - yes_token_id corresponds to the "Up" outcome.
            - no_token_id corresponds to the "Down" outcome.

    Raises:
        RuntimeError: if the event/markets/outcomes cannot be parsed.
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

    # Fallbacks if outcome names are not cleanly "Up"/"Down"
    if up_idx is None:
        up_idx = 0
    if down_idx is None:
        down_idx = 1 if len(tokens) > 1 else 0

    yes_token = str(tokens[up_idx])
    no_token = str(tokens[down_idx])

    print(
        f"[RESOLVE-OK] market_id={market_id} yes_token={yes_token} no_token={no_token} outcomes={outcomes}"
    )

    return str(market_id), yes_token, no_token


def compute_current_bucket_ts() -> int:
    """
    Compute the start timestamp (in seconds) of the current 15-minute bucket.

    This is done by flooring the current Unix time by CONTRACT_DURATION_SEC.
    """
    now = int(time.time())
    bucket = now - (now % CONTRACT_DURATION_SEC)
    return bucket


# ---------------------------------------------------------------------------
# Pretty-print SuperOrder
# ---------------------------------------------------------------------------

def print_super_order_snapshot(order_id: str, order_obj) -> None:
    """
    Helper to pretty-print the current snapshot of a SuperOrder instance.

    This is purely for debugging / manual inspection in the legacy script.
    """
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """
    Run the legacy integration test:

    - Start the account state machine and user WS client.
    - Place a taker BUY order on the "Up" outcome.
    - Wait for on-chain position to become non-zero.
    - Place a flattening order in the opposite direction.
    - Print final state summary and SuperOrder snapshots.

    This function is intended for manual runs only.
    """
    # 1) State machine (account-level order/trade aggregation)
    state = AccountState()

    # 2) Init Polymarket client (REST)
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

    # 3) Resolve market_id + YES/NO token_ids from Gamma for the current bucket
    bucket_ts = compute_current_bucket_ts()
    market_id, yes_token_id, no_token_id = resolve_market_for_bucket(bucket_ts)
    print(f"[MAIN] market_id={market_id}, yes_token_id={yes_token_id}, no_token_id={no_token_id}")

    # 4) Start user WS client, feed messages into AccountState
    def ws_on_message(msg: Dict[str, Any]) -> None:
        """
        User WebSocket callback.

        - Logs the raw message.
        - Dispatches to AccountState.
        - Prints SuperOrder snapshots for any known orders referenced.
        """
        print("\n[WS MSG]", json.dumps(msg, ensure_ascii=False))
        etype = msg.get("event_type")

        if etype == "order":
            state.handle_order_message(msg)
            oid = msg.get("id")
            if oid in state.orders:
                order = state.orders[oid]
                print_super_order_snapshot(oid, order)

        elif etype == "trade":
            state.handle_trade_message(msg)

            order_ids = set()
            taker_id = msg.get("taker_order_id")
            if isinstance(taker_id, str):
                order_ids.add(taker_id)
            for m in msg.get("maker_orders") or []:
                if not isinstance(m, dict):
                    continue
                oid = m.get("order_id") or m.get("id")
                if isinstance(oid, str):
                    order_ids.add(oid)

            for oid in order_ids:
                order = state.orders.get(oid)
                if order:
                    print_super_order_snapshot(oid, order)

        else:
            # Other user events (balances, etc.) are currently ignored in this legacy script.
            pass

    ws_client = UserWebSocketClient(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        markets=[market_id],
        on_message=ws_on_message,
        verbose=False,
    )

    import threading
    t = threading.Thread(target=ws_client.run_forever, daemon=True)
    t.start()

    print("[MAIN] Sleep 3s to let WS connect...")
    time.sleep(3.0)

    # 5) Entry leg: BUY 10 YES @ 0.05 as taker
    print("[MAIN] Placing BUY 10 YES @ 0.9")
    try:
        resp_buy = poly.place_limit(
            token_id=yes_token_id,
            side="BUY",
            price=0.05,
            size=10.0,
            order_type="GTC",
        )
        print("[PLACE BUY RESP]", resp_buy)
    except Exception as e:
        print("[ERROR] BUY failed:", repr(e))
        return

    buy_order_id = resp_buy.get("orderId") or resp_buy.get("orderID")
    print(f"[MAIN] BUY order_id={buy_order_id}")

    state.register_local_order(
        order_id=buy_order_id,
        market_id=market_id,
        outcome="Up",
        side="BUY",
        price=0.05,
        size=10.0,
        is_entry=True,
        strategy_tag="mm_v1",
    )

    # 6) Monitor on-chain position; once MINED/CONFIRMED, place flattening order.
    print("[MAIN] Waiting for on-chain position (MINED/CONFIRMED) on (market, 'Up') ...")
    deadline = time.time() + 60.0

    while time.time() < deadline:
        risk_stats = state.get_risk_stats(market_id, "Up")
        on_stats   = state.get_onchain_stats(market_id, "Up")
        pending_exit = state.get_pending_exit(market_id, "Up")

        risk_pos  = risk_stats["pos"]
        risk_avg  = risk_stats["avg_price"]
        on_pos    = on_stats["pos"]
        on_avg    = on_stats["avg_price"]

        print(
            f"[MAIN-LOOP] risk={risk_pos}, risk_avg={risk_avg}, "
            f"onchain={on_pos}, onchain_avg={on_avg}, pending_exit={pending_exit}"
        )

        # Keep the original trigger condition: only flatten after on-chain pos exists
        # and there is no live exit order on the book.
        if abs(on_pos) > 1e-6 and pending_exit < 1e-6:
            print(
                f"[MAIN] Detected on-chain pos={on_pos}, avg={on_avg}, "
                f"live_exit={pending_exit}, placing FLATTEN SELL {on_pos} ..."
            )

            side_flat = "SELL" if on_pos > 0 else "BUY"
            size_flat = abs(on_pos)

            # For now use a very aggressive price. In a real strategy you would
            # typically use a "do-not-lose" price derived from on_avg.
            flat_price = 0.1 if side_flat == "SELL" else 0.9

            try:
                resp_flat = poly.place_limit(
                    token_id=yes_token_id,
                    side=side_flat,
                    price=flat_price,
                    size=size_flat,
                    order_type="GTC",
                )
                print(f"[PLACE FLATTEN RESP] side={side_flat} size={size_flat}", resp_flat)
            except Exception as e:
                print("[ERROR] FLATTEN failed:", repr(e))
                break

            flatten_order_id = resp_flat.get("orderId") or resp_flat.get("orderID")
            print(f"[MAIN] FLATTEN order_id={flatten_order_id}")

            state.register_local_order(
                order_id=flatten_order_id,
                market_id=market_id,
                outcome="Up",
                side=side_flat,
                price=flat_price,
                size=size_flat,
                is_exit=True,
                strategy_tag="mm_v1",
            )
            break

        time.sleep(0.5)

    print("[MAIN] Wait 30s for WS messages after flatten...")
    time.sleep(30.0)

    # 7) Final summary of positions, pending exposure and all known orders
    print("\n[FINAL SUMMARY]")

    for (mkt, out), _pos in state.position_risk.items():
        risk_stats = state.get_risk_stats(mkt, out)
        on_stats   = state.get_onchain_stats(mkt, out)
        print(
            f"  [{mkt} / {out}] "
            f"risk_pos={risk_stats['pos']}, risk_avg={risk_stats['avg_price']}, "
            f"on_pos={on_stats['pos']}, on_avg={on_stats['avg_price']}"
        )

    for (mkt, out), pend in state.pending_exposure.items():
        print(f"  pending_exposure: market={mkt}, outcome={out}, pend={pend}")

    for oid, order in state.orders.items():
        print_super_order_snapshot(oid, order)


if __name__ == "__main__":
    main()