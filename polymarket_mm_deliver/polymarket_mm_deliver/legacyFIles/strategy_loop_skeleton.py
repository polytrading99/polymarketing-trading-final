#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
strategy_loop_skeleton.py

Dry-run demo of how AccountState, EntryManager, and ExitManager work together.

This script does NOT:
- connect to real WebSockets
- talk to Polymarket REST
- place any orders

It only simulates:
1) Creating a logical entry (EntryOrderState) for (market, outcome).
2) Registering a local BUY order in AccountState.
3) Feeding a fake trade message into AccountState + EntryManager
   (as if the entry order was filled).
4) Running a small "main loop" where:
   - EntryManager syncs from AccountState (positions / cooldown).
   - ExitManager is asked: "what would you do at this mid price?"
   - The script prints "would TP" / "would SL" instead of placing orders.

Use this as a wiring reference when you later plug real WS + REST
into a proper strategy loop.
"""

import time
from typing import Optional

from state_machine import AccountState
from state_machine.enums import SIDE_BUY, SIDE_SELL

from state_machine.strategy_entry import (
    EntryManager,
    EntryOrderState,
    ENTRY_STATUS_NEW,
    ENTRY_STATUS_WAIT_ENTRY_FILLS,
    ENTRY_STATUS_COOLING,
    ENTRY_STATUS_READY,
    ENTRY_STATUS_EXIT_PLACED,
    ENTRY_STATUS_DONE,
)
from state_machine.strategy_exit import ExitManager  # adjust name/import if different


# ---------------------------------------------------------------------------
# Helpers to pretty print
# ---------------------------------------------------------------------------

def _fmt_status(entry: EntryOrderState) -> str:
    return (
        f"Entry#{entry.entry_id} "
        f"[{entry.market_id}/{entry.outcome}] "
        f"status={entry.status}, "
        f"pos={entry.last_known_pos:.4f} @ {entry.last_known_avg_price:.4f}"
    )


# ---------------------------------------------------------------------------
# Main demo logic
# ---------------------------------------------------------------------------

def simulate_one_entry_and_exit_loop() -> None:
    """
    Simulate:
      - One logical entry (long 10@0.50)
      - Cooldown 2 seconds
      - SL trigger 0.40, TP trigger 0.60
    Then run a loop where mid price moves and ExitManager is asked what it would do.
    """

    # 1) Core containers
    state = AccountState()
    entry_mgr = EntryManager()

    # ExitManager: adjust constructor args to your real implementation.
    # If your ExitManager requires parameters (min_trade_size, sl_order_price, ...),
    # fill them here.
    exit_mgr = ExitManager()  # type: ignore[arg-type]

    market_id = "TEST-MARKET"
    outcome = "YES"

    # 2) Create a logical entry
    print("\n[DEMO] Creating logical entry...")
    entry = entry_mgr.create_entry(
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        leg_label="YES",
        target_size=10.0,
        cooldown_sec=2.0,     # short cooldown so we can see READY quickly
        min_exit_size=1.0,
        sl_trigger=0.40,      # strategy-level trigger values, ExitManager may or may not use them
        tp_trigger=0.60,
        strategy_tag="demo",
    )
    print(f"[DEMO] New entry created: { _fmt_status(entry) }")

    # 3) Register a local BUY order in AccountState, as if we placed a REST order
    order_id = "demo-order-1"
    order = state.register_local_order(
        order_id=order_id,
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        price=0.50,
        size=10.0,
        is_entry=True,
        is_exit=False,
        strategy_tag="demo",
    )
    # Bind this order to the logical entry
    entry_mgr.attach_entry_order(entry.entry_id, order_id)
    print(f"[DEMO] Local entry order registered: order_id={order_id}, size=10 @ 0.50")

    # 4) Simulate a trade fill via a fake trade message.
    #    This goes through the same path as real WS messages:
    #    - state.handle_trade_message(...)
    #    - entry_mgr.on_trade_message(...)

    trade_msg = {
        "id": "trade-1",
        "status": "MATCHED",     # or "MINED"/"CONFIRMED" depending on your STATUS_RANK
        "market": market_id,
        "outcome": outcome,
        "side": SIDE_BUY,
        "size": "10",            # WS sends strings; AccountState casts to float
        "price": "0.50",
        "taker_order_id": order_id,
        "maker_orders": [],      # not used for our taker-only demo
    }

    print("\n[DEMO] Feeding fake trade (10@0.50 BUY) into AccountState + EntryManager...")
    state.handle_trade_message(trade_msg)
    entry_mgr.on_trade_message(trade_msg, state)

    # After this, AccountState should see pos=+10, and entry should have fill timestamps.
    # Let's sync entry from AccountState once.
    now = time.time()
    entry.update_from_account_state(now, state)
    print(f"[DEMO] After fill: { _fmt_status(entry) }")

    # 5) Run a small "main loop" where mid price moves and ExitManager is consulted.

    print("\n[DEMO] Starting main loop: ask ExitManager what it *would* do (no orders placed).")
    print("       Price path: starts at 0.50, then moves up by 0.02 every second.")
    print("       We run 15 steps; watch when TP/SL conditions are met.\n")

    mid_price = 0.50
    steps = 15

    for step in range(steps):
        now = time.time()

        # Update all entries from AccountState (positions, cooldown, status)
        entry_mgr.update_all_from_account_state(state, now)

        # Refresh local reference (entry object is the same instance).
        print(f"[LOOP] step={step}, mid_price={mid_price:.4f}")
        print(f"       { _fmt_status(entry) }")

        # Ask ExitManager what it *would* do at this price.
        # Adjust method name / signature to match your ExitManager implementation.
        try:
            decision = exit_mgr.evaluate_exit_for_entry(
                entry=entry,
                mid_price=mid_price,
                state=state,
            )
        except TypeError:
            # If your ExitManager has a different signature, you can adjust here.
            print("       [WARN] ExitManager.evaluate_exit_for_entry signature mismatch, "
                  "please adapt call in strategy_loop_skeleton.py")
            decision = None

        if decision is None:
            print("       [EXIT] No action (None returned).")
        else:
            # The exact fields depend on your ExitDecision dataclass.
            # Here we assume:
            #   decision.kind   -> "TP" / "SL" / "NONE"
            #   decision.place  -> bool (should place an order)
            #   decision.side   -> "BUY"/"SELL"
            #   decision.size   -> float
            #   decision.price  -> float
            #   decision.reason -> str
            kind = getattr(decision, "kind", None)
            place = bool(getattr(decision, "place", False))
            side = getattr(decision, "side", None)
            size = getattr(decision, "size", 0.0)
            price = getattr(decision, "price", 0.0)
            reason = getattr(decision, "reason", "")

            if not place or kind is None or kind == "NONE":
                print(f"       [EXIT] No exit order suggested (kind={kind}, place={place}).")
            else:
                print(
                    f"       [EXIT] WOULD PLACE {kind} order: side={side}, "
                    f"size={size:.4f}, price={price:.4f}, reason='{reason}'"
                )

        print()
        # Move price up a bit so TP will eventually trigger
        mid_price += 0.02
        time.sleep(1.0)


def main() -> None:
    print("=== Strategy loop skeleton demo (no real trading) ===")
    simulate_one_entry_and_exit_loop()
    print("=== Demo finished ===\n")


if __name__ == "__main__":
    main()