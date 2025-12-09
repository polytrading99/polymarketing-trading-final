#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
import logging
import threading
from collections import defaultdict
from typing import Dict

from data_reader.load_config import load_config
from strategy.time_bucket_mm import resolve_market_for_bucket, CLOB_HOST
from state_machine.account_state import AccountState
from state_machine.order import SuperOrder
from state_machine.polymarket_client import PolymarketClient
from data_reader.shm_reader import ShmRingReader
from state_machine.ws_client import UserWebSocketClient

LOG = logging.getLogger("main_final")

# SHM name must match the producer
SHM_NAME = "poly_tob_shm"


# ================== General Time Utilities ==================

def sleep_until(ts: float):
    """Block until the given absolute timestamp ts (seconds)."""
    now = time.time()
    if ts > now:
        time.sleep(ts - now)


def align_to_next_minute() -> float:
    """
    Wait until the next “minute boundary” and return that timestamp.

    Example: now = 12:34:17.3 -> sleep until 12:35:00.0, return 12:35:00.0.
    """
    now = time.time()
    next_minute = math.floor(now / 60.0) * 60.0 + 60.0
    sleep_until(next_minute)
    return next_minute


def get_bucket_start_for_now(now_ts: float) -> int:
    """
    Given a timestamp, compute the start of the 15-minute bucket (in epoch seconds).

    Example: now_ts = 12:34:17 → bucket_start = 12:30:00 epoch seconds.
    """
    return int(now_ts // 900) * 900


# ================== Ledger & Position Calculation ==================

def record_exit_fill(exit_value_book: Dict[str, float], strategy_tag: str, size: float, price: float):
    """
    Record one exit fill for a strategy:
    exit total value += size * price
    """
    if not strategy_tag:
        return
    exit_value_book[strategy_tag] += float(size) * float(price)


def compute_strategy_inventory_usd(
    strategy_tag: str,
    entry_value_book: Dict[str, float],
    exit_value_book: Dict[str, float],
) -> float:
    """
    Compute the net inventory value (USD) of a strategy using the ledger:

    entry_value = Σ(each entry size * price)
    exit_value  = Σ(each exit size * price)
    net_value   = max(entry_value - exit_value, 0)
    """
    entry_value = float(entry_value_book.get(strategy_tag, 0.0))
    exit_value = float(exit_value_book.get(strategy_tag, 0.0))
    net_value = entry_value - exit_value
    if net_value < 0:
        net_value = 0.0
    return net_value


def compute_leg_inventory_usd_from_orders(
    acct: AccountState,
    market_id: str,
    outcome: str,
    mark_price: float | None,
) -> float:
    """
    Compute leg-level inventory in USD using the same logic as our production exposure calculation.
    """
    if mark_price is None:
        return 0.0

    buy_total = 0.0
    sell_filled = 0.0

    for so in acct.orders.values():
        if getattr(so, "market_id", "") != market_id:
            continue
        if getattr(so, "outcome", "") != outcome:
            continue

        side = (getattr(so, "side", "") or "").upper()
        status = (getattr(so, "order_status", "") or "").upper()

        if side == "BUY":
            # 1) Completely unfilled & canceled orders → ignore
            if status == "CANCELED" and getattr(so, "size_matched", 0.0) == 0:
                continue

            filled = float(getattr(so, "size_matched", 0.0) or 0.0)

            # For open/partial orders: include unmatched as well
            if status in ("OPEN", "PART_FILLED", "LIVE"):
                original = float(
                    getattr(so, "original_size", getattr(so, "size", 0.0))
                    or 0.0
                )
                unmatched = max(original - filled, 0.0)
                eff_size = filled + unmatched
            else:
                eff_size = filled

            buy_total += eff_size

        elif side == "SELL":
            # Only counted matched sells offset buy exposure
            sell_filled += float(getattr(so, "size_matched", 0.0) or 0.0)

    net_size = buy_total - sell_filled
    if net_size < 0:
        net_size = 0.0

    return net_size * float(mark_price)


def compute_leg_position_size_from_orders(
    acct: AccountState,
    market_id: str,
    outcome: str,
) -> float:
    """
    Compute the net position size for a leg (units, not multiplied by price):
    buy_total (filled + open) - sell_filled (only filled sells)
    """
    buy_total = 0.0
    sell_filled = 0.0

    for so in acct.orders.values():
        if getattr(so, "market_id", "") != market_id:
            continue
        if getattr(so, "outcome", "") != outcome:
            continue

        side = (getattr(so, "side", "") or "").upper()
        status = (getattr(so, "order_status", "") or "").upper()

        if side == "BUY":
            if status == "CANCELED" and getattr(so, "size_matched", 0.0) == 0:
                continue

            filled = float(getattr(so, "size_matched", 0.0) or 0.0)

            if status in ("OPEN", "PART_FILLED", "LIVE"):
                original = float(
                    getattr(so, "original_size", getattr(so, "size", 0.0))
                    or 0.0
                )
                unmatched = max(original - filled, 0.0)
                eff_size = filled + unmatched
            else:
                eff_size = filled

            buy_total += eff_size

        elif side == "SELL":
            sell_filled += float(getattr(so, "size_matched", 0.0) or 0.0)

    net_size = buy_total - sell_filled
    return max(net_size, 0.0)


def debug_print_leg_inventory(
    tag: str,
    acct: AccountState,
    market_id: str,
    yes_bid: float | None,
    no_bid: float | None,
):
    """
    Debug: print inventory for Up / Down legs.
    """
    inv_up = compute_leg_inventory_usd_from_orders(
        acct=acct,
        market_id=market_id,
        outcome="Up",
        mark_price=yes_bid,
    )
    inv_down = compute_leg_inventory_usd_from_orders(
        acct=acct,
        market_id=market_id,
        outcome="Down",
        mark_price=no_bid,
    )
    print(
        f"[DEBUG-INV-{tag}] "
        f"yes_bid={yes_bid:.3f} no_bid={no_bid:.3f} "
        f"inv_up_usd={inv_up:.4f} inv_down_usd={inv_down:.4f}"
    )


def get_strategy_exposure_usd(acct: AccountState, strategy_tag: str) -> float:
    """
    Legacy exposure calculation (strategy-level).  
    We now use per-leg exposure limits but keep this for monitoring/statistics.
    """
    total_usd = 0.0

    for so in acct.orders.values():
        if getattr(so, "strategy_tag", "") != strategy_tag:
            continue
        if (getattr(so, "side", "") or "").upper() != "BUY":
            continue

        if getattr(so, "order_status", "") == "CANCELED" and getattr(so, "size_matched", 0.0) == 0:
            continue

        price = float(getattr(so, "price", 0.0) or 0.0)
        filled_val = float(getattr(so, "size_matched", 0.0) or 0.0) * price

        size_unmatched = getattr(so, "size_unmatched", None)
        if size_unmatched is None:
            original = float(getattr(so, "original_size", getattr(so, "size", 0.0)) or 0.0)
            size_unmatched = max(original - float(getattr(so, "size_matched", 0.0) or 0.0), 0.0)

        pending_val = 0.0
        if getattr(so, "order_status", "") in ["OPEN", "PART_FILLED", "LIVE"] and size_unmatched > 0:
            pending_val = size_unmatched * price

        total_usd += (filled_val + pending_val)

    return total_usd


# ================== New Entry / Exit Helper Functions ==================

def reprice_entry_if_drifted(
    so: SuperOrder,
    now_ts: float,
    best_ask: float | None,
    token_id: str,
    client: PolymarketClient,
    entry_requote_wait_sec: float,
    price_drift_threshold: float,
    min_improve: float,
):
    """
    Entry-order repricing logic (with cooldown):
    """
    if not getattr(so, "is_entry", False):
        return
    if (getattr(so, "side", "") or "").upper() != "BUY":
        return

    # Brake: if any fill happened, stop repricing
    if getattr(so, "size_matched", 0.0) > 0:
        return

    # Cooldown: only reprice if enough time passed
    last_ts = getattr(so, "entry_last_action_ts", None)
    if last_ts is not None and now_ts - last_ts < entry_requote_wait_sec:
        return

    if best_ask is None:
        so.entry_last_action_ts = now_ts
        return

    if getattr(so, "entry_order_price", None) is None:
        so.entry_order_price = so.price

    diff = abs(best_ask - so.entry_order_price)
    if diff < max(price_drift_threshold, min_improve):
        return

    print(
        f"[ENTRY] price drift detected: best_ask={best_ask}, "
        f"old_price={so.entry_order_price}, diff={diff}"
    )

    # Cancel old order
    try:
        if getattr(so, "order_id", None):
            client.cancel_order(so.order_id)
            print(f"[ENTRY] canceled old entry order: {so.order_id}")
    except Exception as e:
        print(f"[ENTRY][WARN] cancel entry failed: {e}")

    # Remaining unfilled size
    original_size = getattr(so, "original_size", getattr(so, "size", 0.0))
    remaining = original_size - getattr(so, "size_matched", 0.0)
    if remaining <= 0:
        so.entry_last_action_ts = now_ts
        return

    new_price = best_ask

    try:
        new_resp = client.place_limit(
            token_id=token_id,
            side="BUY",
            price=new_price,
            size=remaining,
        )
    except Exception as e:
        print(f"[ENTRY][WARN] re-place entry exception: {e}")
        so.entry_last_action_ts = now_ts
        return

    print("[ENTRY] re-place entry_resp =", new_resp)
    so.entry_last_action_ts = now_ts

    if not new_resp.get("success", False):
        return

    status = new_resp.get("status")

    if status == "matched":
        filled = remaining
        so.size_matched = getattr(so, "size_matched", 0.0) + filled
        so.price = new_price
        so.entry_order_price = new_price
        if getattr(so, "first_fill_ts", None) is None:
            so.first_fill_ts = now_ts
        print(
            f"[ENTRY] re-place matched immediately, "
            f"size_matched={so.size_matched}, price={new_price}"
        )
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
    exit_delay_sec: float,
    exit_retry_delay_sec: float,
    strategy_tag: str,
    exit_value_book: Dict[str, float],
    acct: AccountState,
):
    """
    Try submitting an exit order once (sell the remaining position of this leg).
    """
    if getattr(so, "exit_fully_filled", False):
        return
    if getattr(so, "first_fill_ts", None) is None or so.size_matched <= 0:
        return
    if now_ts - so.first_fill_ts < exit_delay_sec:
        return
    if getattr(so, "exit_order_id", None) is not None:
        return
    if (
        getattr(so, "last_exit_attempt_ts", None) is not None
        and now_ts - so.last_exit_attempt_ts < exit_retry_delay_sec
    ):
        return

    # Remaining size
    remaining_size = compute_leg_position_size_from_orders(
        acct=acct,
        market_id=getattr(so, "market_id", ""),
        outcome=getattr(so, "outcome", ""),
    )
    if remaining_size <= 0:
        so.exit_fully_filled = True
        return

    print(
        f"[EXIT-TRY] try EXIT: order_id={so.order_id}, "
        f"remaining_size={remaining_size}, exit_price={exit_price}"
    )

    try:
        exit_resp = client.place_limit(
            token_id=token_id,
            side="SELL",
            price=exit_price,
            size=remaining_size,
        )
    except Exception as e:
        print(
            f"[EXIT-TRY][WARN] exit order exception "
            f"(treat as failure, will retry later): {e}"
        )
        so.last_exit_attempt_ts = now_ts
        return

    print("[EXIT-TRY] exit_resp =", exit_resp)
    so.last_exit_attempt_ts = now_ts

    if not exit_resp.get("success", False):
        print("[EXIT-TRY][WARN] exit order failed, will retry later")
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
        record_exit_fill(
            exit_value_book=exit_value_book,
            strategy_tag=strategy_tag,
            size=remaining_size,
            price=exit_price,
        )
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
    best_bid: float | None,
    token_id: str,
    client: PolymarketClient,
    exit_retry_delay_sec: float,
    price_drift_threshold: float,
    min_exit_price: float,
    sl_order_price: float,
    strategy_tag: str,
    exit_value_book: Dict[str, float],
    acct: AccountState,
):
    """
    Exit order repricing (with minimum exit price):
    - Normal TP mode: min_exit_price > 0
    - Stop-loss mode: min_exit_price == 0, always use sl_order_price
    """
    if getattr(so, "exit_fully_filled", False):
        return
    if getattr(so, "exit_order_id", None) is None or getattr(so, "exit_order_price", None) is None:
        return
    if (
        getattr(so, "last_exit_attempt_ts", None) is not None
        and now_ts - so.last_exit_attempt_ts < exit_retry_delay_sec
    ):
        return

    # Remaining size
    remaining_size = compute_leg_position_size_from_orders(
        acct=acct,
        market_id=getattr(so, "market_id", ""),
        outcome=getattr(so, "outcome", ""),
    )
    if remaining_size <= 0:
        so.exit_fully_filled = True
        return

    current_exit_price = float(so.exit_order_price)

    if min_exit_price == 0:
        # Stop-loss mode: force use sl_order_price
        new_exit_price = float(sl_order_price)
        diff = abs(new_exit_price - current_exit_price)
        if diff < price_drift_threshold:
            return
        if abs(new_exit_price - current_exit_price) < 1e-9:
            return
        print(
            f"[EXIT-REPRICE] stop-loss mode: force new_exit_price={sl_order_price}, "
            f"old_exit_price={current_exit_price}, diff={diff}"
        )
    else:
        if best_bid is None:
            return

        diff = abs(best_bid - current_exit_price)
        if diff < price_drift_threshold:
            return

        new_exit_price = max(best_bid, min_exit_price)
        if abs(new_exit_price - current_exit_price) < 1e-9:
            return

        print(
            f"[EXIT-REPRICE] normal mode drift: "
            f"best_bid={best_bid}, min_exit_price={min_exit_price}, "
            f"old_exit_price={current_exit_price}, new_exit_price={new_exit_price}, diff={diff}"
        )

    # Cancel old exit order
    try:
        if getattr(so, "exit_order_id", None):
            client.cancel_order(so.exit_order_id)
            print(f"[EXIT-REPRICE] canceled old exit order: {so.exit_order_id}")
    except Exception as e:
        print(f"[EXIT-REPRICE][WARN] cancel exit failed: {e}")

    try:
        new_exit_resp = client.place_limit(
            token_id=token_id,
            side="SELL",
            price=new_exit_price,
            size=remaining_size,
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
        record_exit_fill(
            exit_value_book=exit_value_book,
            strategy_tag=strategy_tag,
            size=remaining_size,
            price=new_exit_price,
        )
        so.exit_fully_filled = True
        print("[EXIT-REPRICE] exit fully filled after reprice.")


# ================== Strategy Helpers ==================

def get_cap_for_time(schedule: list[Dict], sec_in_bucket: float) -> float:
    """Return the cap_usd for current time window."""
    for bucket in schedule:
        if bucket["start_sec"] <= sec_in_bucket < bucket["end_sec"]:
            return bucket["cap_usd"]
    return 0.0


def trigger_strategy_stop_loss(
    acct: AccountState,
    now_ts: float,
    strategy_tag: str,
    token_id: str,
    client: PolymarketClient,
    exit_delay_sec: float,
    exit_retry_delay_sec: float,
    price_drift_threshold: float,
    sl_order_price: float,
    exit_value_book: Dict[str, float],
    best_bid: float | None,
    leg_outcome: str,
):
    """
    Strategy-level stop loss for a single leg.
    Sell 100% of the net position at sl_order_price (recommended 0.01).
    """

    # Find a representative order to extract market_id
    market_id = None
    for so in acct.orders.values():
        if getattr(so, "strategy_tag", "") != strategy_tag:
            continue
        if getattr(so, "outcome", "") != leg_outcome:
            continue
        market_id = getattr(so, "market_id", None)
        if market_id:
            break

    if not market_id:
        return

    pos_size = compute_leg_position_size_from_orders(
        acct=acct,
        market_id=market_id,
        outcome=leg_outcome,
    )
    if pos_size <= 0:
        return

    print(
        f"[SL] Trigger stop-loss for strategy={strategy_tag}, "
        f"outcome={leg_outcome}, pos_size={pos_size:.4f}, "
        f"sl_price={sl_order_price}"
    )

    # Cancel all open orders for this strategy & leg
    for so in list(acct.orders.values()):
        if getattr(so, "strategy_tag", "") != strategy_tag:
            continue
        if getattr(so, "outcome", "") != leg_outcome:
            continue

        setattr(so, "sl_active", True)

        try:
            if getattr(so, "order_id", None):
                client.cancel_order(so.order_id)
                print(f"[SL] canceled entry order: {so.order_id}")
        except Exception as e:
            print(f"[SL][WARN] cancel entry failed: {e}")

        try:
            if getattr(so, "exit_order_id", None):
                client.cancel_order(so.exit_order_id)
                print(f"[SL] canceled exit order: {so.exit_order_id}")
        except Exception as e:
            print(f"[SL][WARN] cancel exit failed: {e}")

    # Sell full position instantly
    try:
        sl_resp = client.place_limit(
            token_id=token_id,
            side="SELL",
            price=sl_order_price,
            size=pos_size,
        )
    except Exception as e:
        print(f"[SL][WARN] stop-loss SELL failed with exception: {e}")
        return

    print("[SL] stop-loss sell_resp =", sl_resp)

    if not sl_resp.get("success", False):
        print("[SL][WARN] stop-loss SELL not successful (will not retry here)")
        return

    status = sl_resp.get("status")
    if status == "matched":
        record_exit_fill(
            exit_value_book=exit_value_book,
            strategy_tag=strategy_tag,
            size=pos_size,
            price=sl_order_price,
        )
        print(
            f"[SL] stop-loss fully filled: "
            f"size={pos_size:.4f} at price={sl_order_price}"
        )
    else:
        print(
            f"[SL] stop-loss order live: size={pos_size:.4f}, "
            f"price={sl_order_price}"
        )


def flatten_existing_positions_before_round(
    client: PolymarketClient,
    market_id: str,
    yes_token_id: str,
    no_token_id: str,
    yes_bid: float | None,
    no_bid: float | None,
    tp_increment: float,
    sl_price: float,
    poll_seconds: float = 10.0,
):
    """
    Before starting a new bucket, flatten any remote existing positions:

    - If bid >= entry_avg + tp_increment => TP at (entry_avg + tp_increment)
    - Else => stop-loss at sl_price (recommended 0.01)
    """
    try:
        pos = client.get_market_leg_positions(
            market_id=market_id,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            size_threshold=0.0,
            limit=100,
        )
    except Exception as e:
        print(f"[INIT-FLAT][WARN] get_market_leg_positions failed: {e}")
        return

    yes_size = float(pos.get("yes_size", 0.0) or 0.0)
    yes_avg = pos.get("yes_avg_price", None)
    no_size = float(pos.get("no_size", 0.0) or 0.0)
    no_avg = pos.get("no_avg_price", None)

    if yes_size <= 0.0 and no_size <= 0.0:
        print("[INIT-FLAT] no existing positions for this market, skip.")
        return

    print(
        "[INIT-FLAT] existing positions: "
        f"yes_size={yes_size:.4f}, yes_avg={yes_avg}, "
        f"no_size={no_size:.4f}, no_avg={no_avg}"
    )

    # Cancel all open orders for this market
    try:
        client.cancel_market_orders(market=market_id, asset_id=None)
        print(f"[INIT-FLAT] canceled open orders for market={market_id}")
    except Exception as e:
        print(f"[INIT-FLAT][WARN] cancel_market_orders failed: {e}")

    def close_leg(
        leg_name: str,
        size: float,
        avg_price: float | None,
        token_id: str,
        current_bid: float | None,
    ):
        if size <= 0.0:
            return

        if avg_price is None:
            avg_price = current_bid if current_bid is not None else sl_price

        target_tp = float(avg_price) + float(tp_increment)

        if current_bid is not None and current_bid >= target_tp:
            exit_price = target_tp
            mode = "TP"
        else:
            exit_price = sl_price
            mode = "SL"

        print(
            f"[INIT-FLAT-{leg_name}] size={size:.4f}, avg={avg_price:.4f}, "
            f"bid={current_bid}, mode={mode}, exit_price={exit_price}"
        )

        try:
            resp = client.place_limit(
                token_id=token_id,
                side="SELL",
                price=exit_price,
                size=size,
            )
        except Exception as e:
            print(f"[INIT-FLAT-{leg_name}][WARN] place_limit failed: {e}")
            return

        print(f"[INIT-FLAT-{leg_name}] sell_resp = {resp}")

    # Close Up / Down legs
    close_leg(
        leg_name="UP",
        size=yes_size,
        avg_price=yes_avg,
        token_id=yes_token_id,
        current_bid=yes_bid,
    )
    close_leg(
        leg_name="DOWN",
        size=no_size,
        avg_price=no_avg,
        token_id=no_token_id,
        current_bid=no_bid,
    )

    # Poll to check if flattened (best-effort)
    deadline = time.time() + float(poll_seconds)
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            pos2 = client.get_market_leg_positions(
                market_id=market_id,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                size_threshold=0.0,
                limit=100,
            )
        except Exception as e:
            print(f"[INIT-FLAT][WARN] re-check positions failed: {e}")
            return

        y2 = float(pos2.get("yes_size", 0.0) or 0.0)
        n2 = float(pos2.get("no_size", 0.0) or 0.0)
        print(
            f"[INIT-FLAT] re-check positions: "
            f"yes_size={y2:.4f}, no_size={n2:.4f}"
        )
        if y2 <= 0.0 and n2 <= 0.0:
            print("[INIT-FLAT] positions fully flattened, start round.")
            return

    print("[INIT-FLAT][WARN] positions not fully flattened before timeout, continue anyway.")


# ================== WebSocket on_message ==================

def make_ws_on_message(acct: AccountState):
    """
    Simplified user WebSocket on_message handler:
    - Feed order/trade messages into AccountState
    """
    def ws_on_message(msg: dict) -> None:
        etype = msg.get("event_type") or msg.get("type")
        if etype == "order":
            acct.handle_order_message(msg)
        elif etype == "trade":
            acct.handle_trade_message(msg)
    return ws_on_message


# ================== Main Program: main_final ==================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()

    api_cfg = config["api"]
    s1_cfg = config["strategies"]["strategy_1"]
    s2_cfg = config["strategies"]["strategy_2"]

    strategy_1_enabled = s1_cfg.get("ENABLED", True)
    strategy_2_enabled = s2_cfg.get("ENABLED", True)

    client = PolymarketClient(
        host=CLOB_HOST,
        private_key=api_cfg["PRIVATE_KEY"],
        chain_id=api_cfg["CHAIN_ID"],
        signature_type=api_cfg["SIGNATURE_TYPE"],
        funder=api_cfg["PROXY_ADDRESS"],
    )

    # ---- General Parameters ----
    CONTRACT_DURATION_SEC = s1_cfg["time_windows"]["CONTRACT_DURATION_SEC"]
    LATE_WINDOW_SEC = s1_cfg["time_windows"]["LATE_WINDOW_SEC"]
    ENTRY_REQUOTE_WAIT_SEC = s1_cfg["time_windows"]["ENTRY_REQUOTE_WAIT_SEC"]

    # Strategy 1 parameters
    s1_entry_exit = s1_cfg["entry_exit"]
    S1_ENTRY_BID_THRESHOLD = s1_entry_exit["ENTRY_BID_THRESHOLD"]
    S1_MIN_TP_INCREMENT = s1_entry_exit["MIN_TP_INCREMENT"]
    S1_SL_FLOOR = s1_entry_exit["SL_FLOOR"]
    S1_MAX_TP_PRICE = s1_entry_exit["MAX_TP_PRICE"]
    S1_SL_ORDER_PRICE = s1_entry_exit["SL_ORDER_PRICE"]
    S1_EXIT_DELAY_SEC = s1_entry_exit.get("EXIT_DELAY_SEC", 1.0)
    S1_EXIT_RETRY_DELAY_SEC = s1_entry_exit.get("EXIT_RETRY_DELAY_SEC", 1.0)
    S1_EXIT_DRIFT_THRESHOLD = s1_entry_exit.get("EXIT_PRICE_DRIFT_THRESHOLD", 0.02)

    s1_pos_ctrl = s1_cfg["position_control"]
    S1_CAP_SCHEDULE = s1_pos_ctrl["CAP_SCHEDULE"]
    S1_MIN_TRADE_SIZE = s1_pos_ctrl["MIN_TRADE_SIZE"]

    s1_micro = s1_cfg["micro_tuning"]
    ENTRY_REQUOTE_MIN_IMPROVE = s1_micro["ENTRY_REQUOTE_MIN_IMPROVE"]

    s1_late = s1_cfg["late_mode"]
    S1_LATE_REENTRY_THRESHOLD = s1_late["LATE_REENTRY_ENTRY_THRESHOLD"]

    # Strategy 2 parameters
    s2_core = s2_cfg["core"]
    S2_ASK_ENTRY_THRESHOLD = s2_core["ASK_ENTRY_THRESHOLD"]
    S2_TIME_TO_EXPIRY_SEC = s2_core["TIME_TO_EXPIRY_SEC"]
    S2_TARGET_POSITION_USD = s2_core["TARGET_POSITION_USD"]

    s2_risk = s2_cfg["risk"]
    S2_SL_PRICE = s2_risk["SL_PRICE"]

    s2_pos_ctrl = s2_cfg["position_control"]
    S2_MIN_TRADE_SIZE = s2_pos_ctrl["MIN_TRADE_SIZE"]

    s2_entry_exit = s2_cfg["entry_exit"]
    S2_SL_ORDER_PRICE = s2_entry_exit["SL_ORDER_PRICE"]
    S2_EXIT_DELAY_SEC = s2_entry_exit.get("EXIT_DELAY_SEC", 1.0)
    S2_EXIT_RETRY_DELAY_SEC = s2_entry_exit.get("EXIT_RETRY_DELAY_SEC", 1.0)
    S2_EXIT_DRIFT_THRESHOLD = s2_entry_exit.get("EXIT_PRICE_DRIFT_THRESHOLD", 0.02)

    # SHM attach once
    shm_reader = ShmRingReader(SHM_NAME)
    print(f"[MAIN] attached shm: {SHM_NAME}")

    current_bucket_ts: int | None = None
    market_id = None
    yes_token_id = None
    no_token_id = None

    acct: AccountState | None = None
    entry_value_book = defaultdict(float)
    exit_value_book = defaultdict(float)
    ws_client: UserWebSocketClient | None = None

    try:
        while True:
            # 1) Wait until next minute boundary as the round start
            round_start_ts = align_to_next_minute()
            round_end_ts = round_start_ts + 52.0  # 52s active, 8s idle buffer

            # 2) Determine current 15m bucket
            bucket_ts = get_bucket_start_for_now(round_start_ts)

            # If entering a new bucket: resolve new market, flatten old positions, reset state
            if current_bucket_ts is None or bucket_ts != current_bucket_ts:
                current_bucket_ts = bucket_ts

                # Resolve market based on bucket
                market_id, yes_token_id, no_token_id = resolve_market_for_bucket(bucket_ts)
                print(
                    f"[MAIN] new bucket: bucket_ts={bucket_ts}, "
                    f"market_id={market_id}, yes_token_id={yes_token_id}, no_token_id={no_token_id}"
                )

                # Read one TOB frame for initial price
                first_frame = shm_reader.read_next_blocking()
                yes_bid = float(first_frame["yes_bid"])
                yes_ask = float(first_frame["yes_ask"])
                no_bid = float(first_frame["no_bid"])
                no_ask = float(first_frame["no_ask"])
                print(
                    f"[SHM-FIRST] yes_bid={yes_bid:.2f}, yes_ask={yes_ask:.2f}, "
                    f"no_bid={no_bid:.2f}, no_ask={no_ask:.2f}"
                )

                # Flatten remote positions before starting bucket
                flatten_existing_positions_before_round(
                    client=client,
                    market_id=market_id,
                    yes_token_id=yes_token_id,
                    no_token_id=no_token_id,
                    yes_bid=yes_bid,
                    no_bid=no_bid,
                    tp_increment=S1_MIN_TP_INCREMENT,
                    sl_price=S1_SL_ORDER_PRICE,
                    poll_seconds=10.0,
                )

                # Reset local state
                acct = AccountState()
                entry_value_book = defaultdict(float)
                exit_value_book = defaultdict(float)

                # Restart user WS
                if ws_client is not None:
                    try:
                        ws_client.close()
                    except Exception as e:
                        print("[MAIN][WARN] close old ws failed:", repr(e))

                ws_client = UserWebSocketClient(
                    api_key=client.api_key,
                    api_secret=client.api_secret,
                    api_passphrase=client.api_passphrase,
                    markets=[market_id],
                    on_message=make_ws_on_message(acct),
                    verbose=False,
                )
                t = threading.Thread(target=ws_client.run_forever, daemon=True)
                t.start()
                time.sleep(0.3)

            # 3) Round-level bucket info (fixed for the round)
            sec_in_bucket = max(0.0, round_start_ts - current_bucket_ts)
            time_to_expiry = CONTRACT_DURATION_SEC - sec_in_bucket

            cap_usd_this_round = get_cap_for_time(S1_CAP_SCHEDULE, sec_in_bucket)
            is_s1_late_window = time_to_expiry <= LATE_WINDOW_SEC
            is_s2_last7 = time_to_expiry <= S2_TIME_TO_EXPIRY_SEC

            print(
                f"[ROUND] start={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(round_start_ts))}, "
                f"bucket_ts={current_bucket_ts}, sec_in_bucket={sec_in_bucket:.1f}, "
                f"time_to_expiry={time_to_expiry:.1f}, cap_usd={cap_usd_this_round:.2f}, "
                f"S1_late={is_s1_late_window}, S2_last7={is_s2_last7}"
            )

            # 4) 52s active loop
            while True:
                now_ts = time.time()
                if now_ts >= round_end_ts:
                    break  # End round, wait next minute

                # Read next TOB frame
                frame = shm_reader.read_next_blocking()
                yes_bid = float(frame["yes_bid"])
                yes_ask = float(frame["yes_ask"])
                no_bid = float(frame["no_bid"])
                no_ask = float(frame["no_ask"])
                frame_bucket_ts = int(frame["bucket_ts"])

                # If bucket rolled over mid-frame => end round early
                if frame_bucket_ts != current_bucket_ts:
                    print(
                        f"[ROUND] detected new bucket in-frame: "
                        f"old={current_bucket_ts}, new={frame_bucket_ts}, break this round."
                    )
                    break

                if acct is None:
                    continue

                # Update live time-to-expiry estimate
                now_sec_in_bucket = max(0.0, now_ts - current_bucket_ts)
                time_to_expiry_now = CONTRACT_DURATION_SEC - now_sec_in_bucket

                # Update first_fill_ts
                for so in acct.orders.values():
                    if getattr(so, "is_entry", False) and so.size_matched > 0 and getattr(so, "first_fill_ts", None) is None:
                        so.first_fill_ts = now_ts
                        print(f"[FILL] first fill detected for order_id={so.order_id}, size_matched={so.size_matched}")

                # ================== Strategy 1 ==================
                if strategy_1_enabled:
                    # Stop-loss: YES leg
                    if yes_bid < S1_SL_FLOOR:
                        trigger_strategy_stop_loss(
                            acct=acct,
                            now_ts=now_ts,
                            strategy_tag="S1",
                            token_id=yes_token_id,
                            client=client,
                            exit_delay_sec=S1_EXIT_DELAY_SEC,
                            exit_retry_delay_sec=S1_EXIT_RETRY_DELAY_SEC,
                            price_drift_threshold=S1_EXIT_DRIFT_THRESHOLD,
                            sl_order_price=S1_SL_ORDER_PRICE,
                            exit_value_book=exit_value_book,
                            best_bid=yes_bid,
                            leg_outcome="Up",
                        )
                    # Stop-loss: NO leg
                    if no_bid < S1_SL_FLOOR:
                        trigger_strategy_stop_loss(
                            acct=acct,
                            now_ts=now_ts,
                            strategy_tag="S1",
                            token_id=no_token_id,
                            client=client,
                            exit_delay_sec=S1_EXIT_DELAY_SEC,
                            exit_retry_delay_sec=S1_EXIT_RETRY_DELAY_SEC,
                            price_drift_threshold=S1_EXIT_DRIFT_THRESHOLD,
                            sl_order_price=S1_SL_ORDER_PRICE,
                            exit_value_book=exit_value_book,
                            best_bid=no_bid,
                            leg_outcome="Down",
                        )

                    # Per-leg inventory (cap control)
                    inv_up_usd = compute_leg_inventory_usd_from_orders(
                        acct=acct,
                        market_id=market_id,
                        outcome="Up",
                        mark_price=yes_bid,
                    )
                    inv_down_usd = compute_leg_inventory_usd_from_orders(
                        acct=acct,
                        market_id=market_id,
                        outcome="Down",
                        mark_price=no_bid,
                    )

                    # ===== S1 / YES leg entry =====
                    if yes_bid >= S1_ENTRY_BID_THRESHOLD and inv_up_usd < cap_usd_this_round:
                        trade_size = S1_MIN_TRADE_SIZE
                        est_notional = trade_size * yes_bid

                        if inv_up_usd + est_notional <= cap_usd_this_round:
                            price = yes_bid
                            print(f"[S1-ENTRY-YES] BUY {trade_size} @ {price}, cap={cap_usd_this_round}, inv_up={inv_up_usd}")

                            try:
                                entry_resp = client.place_limit(
                                    token_id=yes_token_id,
                                    side="BUY",
                                    price=price,
                                    size=trade_size,
                                )
                            except Exception as e:
                                print(f"[S1-ENTRY-YES][WARN] entry exception (treat as failure, no crash): {e}")
                                entry_resp = {"success": False}

                            print("[S1-ENTRY-YES] entry_resp =", entry_resp)

                            if entry_resp.get("success", False):
                                entry_order_id = (
                                    entry_resp.get("orderID")
                                    or entry_resp.get("orderId")
                                    or entry_resp.get("order_id")
                                    or (entry_resp.get("data") or {}).get("orderID")
                                    or (entry_resp.get("data") or {}).get("orderId")
                                )
                                if entry_order_id:
                                    entry_value_book["S1"] += est_notional

                                    so: SuperOrder = acct.register_local_order(
                                        order_id=entry_order_id,
                                        market_id=market_id,
                                        outcome="Up",
                                        side="BUY",
                                        price=price,
                                        size=trade_size,
                                        is_entry=True,
                                        strategy_tag="S1",
                                    )
                                    so.entry_order_price = price
                                    so.entry_last_action_ts = now_ts
                                    so.local_only = True
                                    status = entry_resp.get("status")
                                    if status == "matched":
                                        so.size_matched = trade_size
                                        so.price = price
                                        if getattr(so, "first_fill_ts", None) is None:
                                            so.first_fill_ts = now_ts
                                        print(
                                            f"[S1-ENTRY-YES] immediately filled: "
                                            f"order_id={entry_order_id}, size={trade_size}, price={price}"
                                        )

                                    debug_print_leg_inventory(
                                        tag="S1-ENTRY-YES",
                                        acct=acct,
                                        market_id=market_id,
                                        yes_bid=yes_bid,
                                        no_bid=no_bid,
                                    )

                    # ===== S1 / NO leg entry =====
                    if no_bid >= S1_ENTRY_BID_THRESHOLD and inv_down_usd < cap_usd_this_round:
                        trade_size = S1_MIN_TRADE_SIZE
                        est_notional = trade_size * no_bid

                        if inv_down_usd + est_notional <= cap_usd_this_round:
                            price = no_bid
                            print(f"[S1-ENTRY-NO] BUY {trade_size} @ {price}, cap={cap_usd_this_round}, inv_down={inv_down_usd}")

                            try:
                                entry_resp_no = client.place_limit(
                                    token_id=no_token_id,
                                    side="BUY",
                                    price=price,
                                    size=trade_size,
                                )
                            except Exception as e:
                                print(f"[S1-ENTRY-NO][WARN] entry exception (treat as failure, no crash): {e}")
                                entry_resp_no = {"success": False}

                            print("[S1-ENTRY-NO] entry_resp =", entry_resp_no)

                            if entry_resp_no.get("success", False):
                                entry_order_id_no = (
                                    entry_resp_no.get("orderID")
                                    or entry_resp_no.get("orderId")
                                    or entry_resp_no.get("order_id")
                                    or (entry_resp_no.get("data") or {}).get("orderID")
                                    or (entry_resp_no.get("data") or {}).get("orderId")
                                )
                                if entry_order_id_no:
                                    entry_value_book["S1"] += est_notional

                                    so_no: SuperOrder = acct.register_local_order(
                                        order_id=entry_order_id_no,
                                        market_id=market_id,
                                        outcome="Down",
                                        side="BUY",
                                        price=price,
                                        size=trade_size,
                                        is_entry=True,
                                        strategy_tag="S1",
                                    )
                                    so_no.entry_order_price = price
                                    so_no.entry_last_action_ts = now_ts
                                    so_no.local_only = True
                                    status_no = entry_resp_no.get("status")
                                    if status_no == "matched":
                                        so_no.size_matched = trade_size
                                        so_no.price = price
                                        if getattr(so_no, "first_fill_ts", None) is None:
                                            so_no.first_fill_ts = now_ts
                                        print(
                                            f"[S1-ENTRY-NO] immediately filled: "
                                            f"order_id={entry_order_id_no}, size={trade_size}, price={price}"
                                        )

                                    debug_print_leg_inventory(
                                        tag="S1-ENTRY-NO",
                                        acct=acct,
                                        market_id=market_id,
                                        yes_bid=yes_bid,
                                        no_bid=no_bid,
                                    )

                # ================== Strategy 2 ==================
                if strategy_2_enabled:
                    # S2 only enters within last 7 minutes (round-level decision)
                    time_cond = is_s2_last7

                    yes_mark = yes_bid if yes_bid is not None else yes_ask
                    no_mark = no_bid if no_bid is not None else no_ask

                    inv2_up_usd = compute_leg_inventory_usd_from_orders(
                        acct=acct,
                        market_id=market_id,
                        outcome="Up",
                        mark_price=yes_mark,
                    )
                    inv2_down_usd = compute_leg_inventory_usd_from_orders(
                        acct=acct,
                        market_id=market_id,
                        outcome="Down",
                        mark_price=no_mark,
                    )

                    # S2 / YES leg entry
                    if (
                        time_cond
                        and yes_ask >= S2_ASK_ENTRY_THRESHOLD
                        and inv2_up_usd < S2_TARGET_POSITION_USD
                    ):
                        trade_size2 = S2_MIN_TRADE_SIZE
                        price2 = yes_bid if yes_bid is not None else yes_ask
                        est_notional2 = trade_size2 * price2

                        if inv2_up_usd + est_notional2 <= S2_TARGET_POSITION_USD:
                            print(
                                f"[S2-ENTRY-YES] BUY {trade_size2} @ {price2}, "
                                f"target={S2_TARGET_POSITION_USD}, inv_up={inv2_up_usd}"
                            )

                            try:
                                entry_resp2 = client.place_limit(
                                    token_id=yes_token_id,
                                    side="BUY",
                                    price=price2,
                                    size=trade_size2,
                                )
                            except Exception as e:
                                print(f"[S2-ENTRY-YES][WARN] entry exception: {e}")
                                entry_resp2 = {"success": False}

                            print("[S2-ENTRY-YES] entry_resp =", entry_resp2)

                            if entry_resp2.get("success", False):
                                entry_order_id2 = (
                                    entry_resp2.get("orderID")
                                    or entry_resp2.get("orderId")
                                    or entry_resp2.get("order_id")
                                    or (entry_resp2.get("data") or {}).get("orderID")
                                    or (entry_resp2.get("data") or {}).get("orderId")
                                )
                                if entry_order_id2:
                                    entry_value_book["S2"] += est_notional2

                                    so2: SuperOrder = acct.register_local_order(
                                        order_id=entry_order_id2,
                                        market_id=market_id,
                                        outcome="Up",
                                        side="BUY",
                                        price=price2,
                                        size=trade_size2,
                                        is_entry=True,
                                        strategy_tag="S2",
                                    )
                                    so2.entry_order_price = price2
                                    so2.entry_last_action_ts = now_ts
                                    so2.local_only = True
                                    status2 = entry_resp2.get("status")
                                    if status2 == "matched":
                                        so2.size_matched = trade_size2
                                        so2.price = price2
                                        if getattr(so2, "first_fill_ts", None) is None:
                                            so2.first_fill_ts = now_ts
                                        print(
                                            f"[S2-ENTRY-YES] immediately filled: "
                                            f"order_id={entry_order_id2}, size={trade_size2}, price={price2}"
                                        )

                    # S2 / NO leg entry
                    if (
                        time_cond
                        and no_ask >= S2_ASK_ENTRY_THRESHOLD
                        and inv2_down_usd < S2_TARGET_POSITION_USD
                    ):
                        trade_size2 = S2_MIN_TRADE_SIZE
                        price2 = no_bid if no_bid is not None else no_ask
                        est_notional2 = trade_size2 * price2

                        if inv2_down_usd + est_notional2 <= S2_TARGET_POSITION_USD:
                            print(
                                f"[S2-ENTRY-NO] BUY {trade_size2} @ {price2}, "
                                f"target={S2_TARGET_POSITION_USD}, inv_down={inv2_down_usd}"
                            )

                            try:
                                entry_resp2_no = client.place_limit(
                                    token_id=no_token_id,
                                    side="BUY",
                                    price=price2,
                                    size=trade_size2,
                                )
                            except Exception as e:
                                print(f"[S2-ENTRY-NO][WARN] entry exception: {e}")
                                entry_resp2_no = {"success": False}

                            print("[S2-ENTRY-NO] entry_resp =", entry_resp2_no)

                            if entry_resp2_no.get("success", False):
                                entry_order_id2_no = (
                                    entry_resp2_no.get("orderID")
                                    or entry_resp2_no.get("orderId")
                                    or entry_resp2_no.get("order_id")
                                    or (entry_resp2_no.get("data") or {}).get("orderID")
                                    or (entry_resp2_no.get("data") or {}).get("orderId")
                                )
                                if entry_order_id2_no:
                                    entry_value_book["S2"] += est_notional2

                                    so2_no: SuperOrder = acct.register_local_order(
                                        order_id=entry_order_id2_no,
                                        market_id=market_id,
                                        outcome="Down",
                                        side="BUY",
                                        price=price2,
                                        size=trade_size2,
                                        is_entry=True,
                                        strategy_tag="S2",
                                    )
                                    so2_no.entry_order_price = price2
                                    so2_no.entry_last_action_ts = now_ts
                                    so2_no.local_only = True
                                    status2_no = entry_resp2_no.get("status")
                                    if status2_no == "matched":
                                        so2_no.size_matched = trade_size2
                                        so2_no.price = price2
                                        if getattr(so2_no, "first_fill_ts", None) is None:
                                            so2_no.first_fill_ts = now_ts
                                        print(
                                            f"[S2-ENTRY-NO] immediately filled: "
                                            f"order_id={entry_order_id2_no}, size={trade_size2}, price={price2}"
                                        )

                    # S2 Stop-loss: if price <= SL => flatten each leg
                    if yes_bid <= S2_SL_PRICE:
                        trigger_strategy_stop_loss(
                            acct=acct,
                            now_ts=now_ts,
                            strategy_tag="S2",
                            token_id=yes_token_id,
                            client=client,
                            exit_delay_sec=S2_EXIT_DELAY_SEC,
                            exit_retry_delay_sec=S2_EXIT_RETRY_DELAY_SEC,
                            price_drift_threshold=S2_EXIT_DRIFT_THRESHOLD,
                            sl_order_price=S2_SL_ORDER_PRICE,
                            exit_value_book=exit_value_book,
                            best_bid=yes_bid,
                            leg_outcome="Up",
                        )
                    if no_bid <= S2_SL_PRICE:
                        trigger_strategy_stop_loss(
                            acct=acct,
                            now_ts=now_ts,
                            strategy_tag="S2",
                            token_id=no_token_id,
                            client=client,
                            exit_delay_sec=S2_EXIT_DELAY_SEC,
                            exit_retry_delay_sec=S2_EXIT_RETRY_DELAY_SEC,
                            price_drift_threshold=S2_EXIT_DRIFT_THRESHOLD,
                            sl_order_price=S2_SL_ORDER_PRICE,
                            exit_value_book=exit_value_book,
                            best_bid=no_bid,
                            leg_outcome="Down",
                        )

                # ================== SuperOrder State Machine ==================
                for so in list(acct.orders.values()):
                    if not getattr(so, "is_entry", False):
                        continue

                    # Determine leg TOB
                    if getattr(so, "outcome", "") == "Up":
                        leg_bid = yes_bid
                        leg_ask = yes_ask
                        leg_token = yes_token_id
                    elif getattr(so, "outcome", "") == "Down":
                        leg_bid = no_bid
                        leg_ask = no_ask
                        leg_token = no_token_id
                    else:
                        continue

                    # Entry repricing
                    reprice_entry_if_drifted(
                        so=so,
                        now_ts=now_ts,
                        best_ask=leg_ask,
                        token_id=leg_token,
                        client=client,
                        entry_requote_wait_sec=ENTRY_REQUOTE_WAIT_SEC,
                        price_drift_threshold=0.02,
                        min_improve=ENTRY_REQUOTE_MIN_IMPROVE,
                    )

                    # Exit logic
                    if so.size_matched > 0 and not getattr(so, "exit_fully_filled", False):
                        strat = getattr(so, "strategy_tag", "")

                        if strat == "S1":
                            current_price = leg_bid if leg_bid is not None else leg_ask

                            # Late window special hold mode:
                            in_late_hold_mode = (
                                is_s1_late_window
                                and current_price is not None
                                and current_price >= S1_LATE_REENTRY_THRESHOLD
                            )
                            if not in_late_hold_mode:
                                tp_price = min(so.price + S1_MIN_TP_INCREMENT, S1_MAX_TP_PRICE)
                                min_exit_price = tp_price
                                try_exit_once(
                                    so=so,
                                    now_ts=now_ts,
                                    token_id=leg_token,
                                    client=client,
                                    exit_price=tp_price,
                                    exit_delay_sec=S1_EXIT_DELAY_SEC,
                                    exit_retry_delay_sec=S1_EXIT_RETRY_DELAY_SEC,
                                    strategy_tag="S1",
                                    exit_value_book=exit_value_book,
                                    acct=acct,
                                )
                                reprice_exit_if_drifted(
                                    so=so,
                                    now_ts=now_ts,
                                    best_bid=leg_bid,
                                    token_id=leg_token,
                                    client=client,
                                    exit_retry_delay_sec=S1_EXIT_RETRY_DELAY_SEC,
                                    price_drift_threshold=S1_EXIT_DRIFT_THRESHOLD,
                                    min_exit_price=min_exit_price,
                                    sl_order_price=S1_SL_ORDER_PRICE,
                                    strategy_tag="S1",
                                    exit_value_book=exit_value_book,
                                    acct=acct,
                                )

                        elif strat == "S2":
                            # S2 has no normal TP, only SL
                            if getattr(so, "exit_order_id", None) is not None or getattr(so, "last_exit_attempt_ts", None) is not None:
                                reprice_exit_if_drifted(
                                    so=so,
                                    now_ts=now_ts,
                                    best_bid=leg_bid,
                                    token_id=leg_token,
                                    client=client,
                                    exit_retry_delay_sec=S2_EXIT_RETRY_DELAY_SEC,
                                    price_drift_threshold=S2_EXIT_DRIFT_THRESHOLD,
                                    min_exit_price=0.0,
                                    sl_order_price=S2_SL_ORDER_PRICE,
                                    strategy_tag="S2",
                                    exit_value_book=exit_value_book,
                                    acct=acct,
                                )
                            else:
                                # S2 holds until expiry unless SL triggers
                                pass

            # End of round, 8s idle time handled by align_to_next_minute()

    finally:
        try:
            shm_reader.close()
        except Exception as e:
            print("[WARN] shm_reader.close failed:", repr(e))

    print("[MAIN] done.")


if __name__ == "__main__":
    main()