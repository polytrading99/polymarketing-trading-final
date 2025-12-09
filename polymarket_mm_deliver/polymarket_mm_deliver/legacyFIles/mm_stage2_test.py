#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import logging
import requests

from time_bucket_mm import (
    resolve_market_for_bucket,
    CLOB_HOST,
    PRIVATE_KEY,
    PROXY_ADDRESS,
    SIGNATURE_TYPE,
    CHAIN_ID,
)

from state_machine.account_state import AccountState
from state_machine.order import SuperOrder
from state_machine.polymarket_client import PolymarketClient

LOG = logging.getLogger("mm_stage2_test")

# ========= Strategy parameters =========
ENTRY_REQUOTE_DELAY_SEC = 1.0      # Check entry order for repricing every 1 second
EXIT_DELAY_SEC = 0.5               # Start trying to exit 0.5 seconds after first fill
EXIT_RETRY_DELAY_SEC = 1.0         # Retry exit 1 second after a failed attempt
PRICE_DRIFT_THRESHOLD = 0.02       # Price drift threshold: 2 cents
MAX_RUNTIME_SEC = 60               # Test script exits after running at most 60 seconds
SIMULATE_INSTANT_FILL = True       # For testing exit: simulate instant full fill on entry
EXIT_TEST_PRICE = 0.01             # Exit price used in the test
# ======================================


def get_best_price_from_clob(token_id: str, side: str) -> float | None:
    """
    Call CLOB /price API to get current best price.

    side: "buy"  -> as a buyer, we care about best ask
          "sell" -> as a seller, we care about best bid
    """
    url = f"{CLOB_HOST}/price"
    try:
        resp = requests.get(
            url,
            params={"token_id": token_id, "side": side.lower()},
            timeout=2.0,
        )
        resp.raise_for_status()
        data = resp.json()
        price_str = data.get("price")
        if price_str is None:
            return None
        return float(price_str)
    except Exception as e:
        LOG.warning("get_best_price_from_clob error: %s", e)
        return None


def cancel_clob_order(client: PolymarketClient, order_id: str):
    """
    Adapt to different cancel method names on the client.
    """
    if hasattr(client, "cancel_order"):
        return client.cancel_order(order_id)
    if hasattr(client, "cancel"):
        return client.cancel(order_id)
    raise RuntimeError("PolymarketClient has no cancel_order/cancel method")


# ============ Extracted helper functions ============

def reprice_entry_if_drifted(
    so: SuperOrder,
    now_ts: float,
    token_id: str,
    client: PolymarketClient,
):
    """
    Repricing logic for entry orders:

    - Order is not fully filled yet (size_matched < original_size)
    - At least ENTRY_REQUOTE_DELAY_SEC has passed since last action
    - Current best ask deviates from entry_order_price by >= PRICE_DRIFT_THRESHOLD
      => cancel old order + re-place remaining size at new price
    """
    if so.size_matched >= so.original_size:
        return  # Already fully filled, no need to reprice

    # Throttle frequency
    if (
        so.entry_last_action_ts is not None
        and now_ts - so.entry_last_action_ts < ENTRY_REQUOTE_DELAY_SEC
    ):
        return

    best_ask = get_best_price_from_clob(token_id, "buy")
    if best_ask is None:
        so.entry_last_action_ts = now_ts
        return

    if so.entry_order_price is None:
        so.entry_order_price = so.price

    diff = abs(best_ask - so.entry_order_price)
    if diff < PRICE_DRIFT_THRESHOLD:
        # Drift too small, do nothing
        return

    print(
        f"[ENTRY] price drift detected: best_ask={best_ask}, "
        f"old_price={so.entry_order_price}, diff={diff}"
    )

    # 1) Cancel old entry order
    try:
        cancel_clob_order(client, so.order_id)
        print(f"[ENTRY] canceled old entry order: {so.order_id}")
    except Exception as e:
        print(f"[ENTRY][WARN] cancel entry failed: {e}")

    # 2) Re-place remaining unfilled size at new price
    remaining = so.original_size - so.size_matched
    if remaining <= 0:
        so.entry_last_action_ts = now_ts
        return

    new_price = best_ask
    new_resp = client.place_limit(
        token_id=token_id,
        side="BUY",
        price=new_price,
        size=remaining,
    )
    print("[ENTRY] re-place entry_resp =", new_resp)

    so.entry_last_action_ts = now_ts

    if not new_resp.get("success", False):
        return

    new_order_id = (
        new_resp.get("orderID")
        or new_resp.get("orderId")
        or new_resp.get("order_id")
        or (new_resp.get("data") or {}).get("orderID")
        or (new_resp.get("data") or {}).get("orderId")
    )
    if new_order_id:
        so.order_id = new_order_id
        so.price = new_price
        so.entry_order_price = new_price
        print(
            f"[ENTRY] entry re-placed: order_id={new_order_id}, "
            f"price={new_price}, remaining={remaining}"
        )


def try_exit_once(
    so: SuperOrder,
    now_ts: float,
    token_id: str,
    client: PolymarketClient,
    exit_price: float,
):
    """
    Try placing an exit order once:

    Conditions:
    - first_fill_ts is not None && there has been some fill && not exit_fully_filled
    - At least EXIT_DELAY_SEC has passed since first_fill_ts
    - No active exit_order_id
    - At least EXIT_RETRY_DELAY_SEC since last_exit_attempt_ts

    Behavior:
    - If exit fails (including not enough balance / allowance) =>
      only update last_exit_attempt_ts, retry after EXIT_RETRY_DELAY_SEC.
    - If exit succeeds with status == "matched" =>
      set exit_fully_filled = True.
    """
    if getattr(so, "exit_fully_filled", False):
        return
    if so.first_fill_ts is None or so.size_matched <= 0:
        return
    if now_ts - so.first_fill_ts < EXIT_DELAY_SEC:
        return
    if so.exit_order_id is not None:
        return
    if (
        so.last_exit_attempt_ts is not None
        and now_ts - so.last_exit_attempt_ts < EXIT_RETRY_DELAY_SEC
    ):
        return

    print(
        f"[EXIT-TRY] try EXIT: order_id={so.order_id}, "
        f"filled_size={so.size_matched}, exit_price={exit_price}"
    )

    try:
        exit_resp = client.place_limit(
            token_id=token_id,
            side="SELL",
            price=exit_price,
            size=so.size_matched,
        )
    except Exception as e:
        print(
            f"[EXIT-TRY][WARN] exit order exception "
            f"(treat as failure, will retry after {EXIT_RETRY_DELAY_SEC}s): {e}"
        )
        so.last_exit_attempt_ts = now_ts
        return

    print("[EXIT-TRY] exit_resp =", exit_resp)
    so.last_exit_attempt_ts = now_ts

    if not exit_resp.get("success", False):
        print(f"[EXIT-TRY][WARN] exit order failed, will retry after {EXIT_RETRY_DELAY_SEC}s")
        return

    status = exit_resp.get("status")
    exit_order_id = (
        exit_resp.get("orderID")
        or exit_resp.get("orderId")
        or exit_resp.get("order_id")
        or (exit_resp.get("data") or {}).get("orderID")
        or (exit_resp.get("data") or {}).get("orderId")
    )

    if status == "matched":
        # Immediately fully closed
        so.exit_fully_filled = True
        print(
            f"[EXIT-TRY] exit fully filled immediately: "
            f"exit_order_id={exit_order_id}, exit_price={exit_price}"
        )
        return

    if exit_order_id:
        so.exit_order_id = exit_order_id
        so.exit_order_price = exit_price
        print(
            f"[EXIT-TRY] exit order placed (live): "
            f"exit_order_id={exit_order_id}, exit_price={exit_price}"
        )


def reprice_exit_if_drifted(
    so: SuperOrder,
    now_ts: float,
    token_id: str,
    client: PolymarketClient,
):
    """
    Exit repricing logic:

    - exit_order_id & exit_order_price exist
    - Not exit_fully_filled
    - At least EXIT_RETRY_DELAY_SEC since last_exit_attempt_ts
    - Current best_bid deviates from exit_order_price by >= PRICE_DRIFT_THRESHOLD
      => cancel old exit order + re-place at new price
    """
    if getattr(so, "exit_fully_filled", False):
        return
    if so.exit_order_id is None or so.exit_order_price is None:
        return
    if (
        so.last_exit_attempt_ts is not None
        and now_ts - so.last_exit_attempt_ts < EXIT_RETRY_DELAY_SEC
    ):
        return

    best_bid = get_best_price_from_clob(token_id, "sell")
    if best_bid is None:
        return

    diff = abs(best_bid - so.exit_order_price)
    if diff < PRICE_DRIFT_THRESHOLD:
        return

    print(
        f"[EXIT-REPRICE] exit price drift detected: "
        f"best_bid={best_bid}, old_exit_price={so.exit_order_price}, diff={diff}"
    )

    # 1) Cancel old exit order
    try:
        cancel_clob_order(client, so.exit_order_id)
        print(f"[EXIT-REPRICE] canceled old exit order: {so.exit_order_id}")
    except Exception as e:
        print(f"[EXIT-REPRICE][WARN] cancel exit failed: {e}")

    new_exit_price = best_bid
    try:
        new_exit_resp = client.place_limit(
            token_id=token_id,
            side="SELL",
            price=new_exit_price,
            size=so.size_matched,  # Simplification: assume we want to close the entire position
        )
    except Exception as e:
        print(
            f"[EXIT-REPRICE][WARN] re-place exit failed with exception: {e}"
        )
        so.last_exit_attempt_ts = now_ts
        return

    print("[EXIT-REPRICE] re-place exit_resp =", new_exit_resp)
    so.last_exit_attempt_ts = now_ts

    if not new_exit_resp.get("success", False):
        return

    new_exit_order_id = (
        new_exit_resp.get("orderID")
        or new_exit_resp.get("orderId")
        or new_exit_resp.get("order_id")
        or (new_exit_resp.get("data") or {}).get("orderID")
        or (new_exit_resp.get("data") or {}).get("orderId")
    )
    status2 = new_exit_resp.get("status")

    if new_exit_order_id:
        so.exit_order_id = new_exit_order_id
        so.exit_order_price = new_exit_price
        print(
            f"[EXIT-REPRICE] exit order re-placed: "
            f"exit_order_id={new_exit_order_id}, exit_price={new_exit_price}, status={status2}"
        )

    if status2 == "matched":
        so.exit_fully_filled = True
        print("[EXIT-REPRICE] exit fully filled after reprice.")


# ============ Test main program ============

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    client = PolymarketClient(
        host=CLOB_HOST,
        private_key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=SIGNATURE_TYPE,
        funder=PROXY_ADDRESS,
    )

    # 1) Resolve current 15-minute bucket's BTC up/down market
    now = int(time.time())
    bucket_ts = (now // 900) * 900
    print(f"[TEST] using bucket_ts={bucket_ts}")

    market_id, yes_token_id, no_token_id = resolve_market_for_bucket(bucket_ts)
    print(
        f"[TEST] resolved market: market_id={market_id}, "
        f"yes_token_id={yes_token_id}, no_token_id={no_token_id}"
    )

    # 2) Place BUY 10 shares of Up @ 0.99
    entry_price = 0.99
    entry_size = 10.0

    print(f"[TEST] placing entry BUY {entry_size} @ {entry_price} (Up leg)")
    entry_resp = client.place_limit(
        token_id=yes_token_id,
        side="BUY",
        price=entry_price,
        size=entry_size,
    )
    print("[TEST] entry_resp =", entry_resp)

    if not entry_resp.get("success", False):
        print("[TEST][ERROR] entry order failed, abort")
        return

    entry_order_id = (
        entry_resp.get("orderID")
        or entry_resp.get("orderId")
        or entry_resp.get("order_id")
        or (entry_resp.get("data") or {}).get("orderID")
        or (entry_resp.get("data") or {}).get("orderId")
    )
    if not entry_order_id:
        print("[TEST][ERROR] cannot find entry orderID in response, abort, resp=", entry_resp)
        return

    # 3) Register local SuperOrder
    acct = AccountState()

    so: SuperOrder = acct.register_local_order(
        order_id=entry_order_id,
        market_id=market_id,
        outcome="Up",
        side="BUY",
        price=entry_price,
        size=entry_size,
        is_entry=True,
        strategy_tag="test_fast_mm",
    )

    now_ts = time.time()
    so.entry_order_price = entry_price
    so.entry_last_action_ts = now_ts
    so.exit_order_id = None
    so.exit_order_price = None
    so.last_exit_attempt_ts = None
    so.exit_fully_filled = False

    # For testing exit: simulate immediate full fill on entry
    if SIMULATE_INSTANT_FILL:
        so.size_matched = so.original_size
        so.first_fill_ts = now_ts
        print(
            f"[TEST] SIMULATE_INSTANT_FILL: id={so.order_id}, "
            f"size_matched={so.size_matched}, first_fill_ts={so.first_fill_ts}"
        )

    print("[TEST] start polling SuperOrder...")

    start_ts = time.time()

    while True:
        now_ts = time.time()
        if now_ts - start_ts > MAX_RUNTIME_SEC:
            print("[TEST] max runtime reached, exit loop")
            break
        if so.exit_fully_filled:
            print("[TEST] exit_fully_filled=True, exit loop")
            break

        # 1) Entry repricing (currently all-filled in simulation, so no effect, but function is wired)
        reprice_entry_if_drifted(
            so=so,
            now_ts=now_ts,
            token_id=yes_token_id,
            client=client,
        )

        # 2) Exit: first attempt + retry on failure
        try_exit_once(
            so=so,
            now_ts=now_ts,
            token_id=yes_token_id,
            client=client,
            exit_price=EXIT_TEST_PRICE,
        )

        # 3) Exit repricing if an exit order is already live
        reprice_exit_if_drifted(
            so=so,
            now_ts=now_ts,
            token_id=yes_token_id,
            client=client,
        )

        time.sleep(0.1)

    print("[TEST] done.")


if __name__ == "__main__":
    main()