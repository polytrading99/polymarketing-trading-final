#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Basic tests for StrategyExit + EntryOrderState.

Run with:
    python3 -m unittest test_strategy_exit.py
"""

import time
import unittest
import os
import sys
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import time

import pytest

from state_machine.strategy_exit import StrategyExit, ExitConfig, ExitDecision
from state_machine.strategy_entry import EntryOrderState
from state_machine.enums import (
    SIDE_BUY,
    SIDE_SELL,
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PART_FILLED,
)


# ---------------------------------------------------------------------------
# Fake AccountState / Orders for testing
# ---------------------------------------------------------------------------

class FakeOrder:
    def __init__(self, status: str, unmatched: float):
        self.order_status = status
        self.size_unmatched = unmatched


class FakeAccountState:
    """
    Minimal stub of AccountState needed by StrategyExit / EntryOrderState:

    - get_onchain_stats(market_id, outcome) -> {"pos", "avg_price"}
    - orders dict for checking live exit orders
    """

    def __init__(self, pos: float, avg_price: float):
        self._stats = {
            ("m1", "YES"): {
                "pos": pos,
                "avg_price": avg_price,
            }
        }
        self.orders = {}

    def get_onchain_stats(self, market_id: str, outcome: str):
        return self._stats.get((market_id, outcome), {"pos": 0.0, "avg_price": 0.0})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStrategyExit(unittest.TestCase):
    def setUp(self):
        self.config = ExitConfig(
            sl_order_price=0.01,
            min_tp_increment=0.01,
            max_tp_price=0.99,
            prefer_sl=True,
            eps_pos=1e-9,
        )
        self.exit_engine = StrategyExit(self.config)

    def _make_ready_long_entry(self, pos: float, avg_price: float, *,
                               cooldown_sec: float = 0.0,
                               min_exit_size: float = 1.0,
                               sl_trigger: float | None = None,
                               tp_trigger: float | None = None) -> tuple[EntryOrderState, FakeAccountState, float]:
        """
        Helper: build a long entry that already has a position and whose cooldown has finished.
        """
        state = FakeAccountState(pos=pos, avg_price=avg_price)

        now = time.time()
        entry = EntryOrderState(
            entry_id=1,
            market_id="m1",
            outcome="YES",
            side=SIDE_BUY,
            leg_label="YES",
            target_size=pos,
            cooldown_sec=cooldown_sec,
            min_exit_size=min_exit_size,
            sl_trigger=sl_trigger,
            tp_trigger=tp_trigger,
            strategy_tag="test",
        )
        # Simulate that there have already been fills and cooldown is over
        entry.first_fill_ts = now - 10.0
        entry.last_fill_ts = now - 5.0
        entry.cooldown_until = now - 1.0
        entry.status = "READY"

        # Sync once (populate last_known_pos / avg_price)
        entry.update_from_account_state(now, state)

        return entry, state, now

    # ------------------ Tests ------------------

    def test_long_tp_triggers_when_price_above_level(self):
        """
        Long entry: avg=0.60, bid=0.62, no explicit tp_trigger -> use avg + min_tp_increment.
        Expect a TP SELL decision at ~bid (capped by max_tp_price).
        """
        entry, state, now = self._make_ready_long_entry(pos=10.0, avg_price=0.60)

        decision = self.exit_engine.evaluate_entry(
            entry=entry,
            state=state,
            bid=0.62,
            ask=0.63,
            now_ts=now,
        )

        self.assertIsNotNone(decision, "Expected a TP decision, got None")
        self.assertIsInstance(decision, ExitDecision)
        self.assertEqual(decision.kind, "TP")
        self.assertEqual(decision.side, SIDE_SELL)
        self.assertAlmostEqual(decision.size, 10.0, places=6)
        # TP price should be min(ref_price, max_tp_price) = 0.62
        self.assertAlmostEqual(decision.price, 0.62, places=6)
        self.assertIn("TP_TRIGGER", decision.reason)

    def test_long_sl_triggers_when_price_below_sl_level(self):
        """
        Long entry: avg=0.60, sl_trigger=0.50, bid=0.48 -> SL should trigger, TP not.
        """
        entry, state, now = self._make_ready_long_entry(
            pos=10.0,
            avg_price=0.60,
            sl_trigger=0.50,
        )

        decision = self.exit_engine.evaluate_entry(
            entry=entry,
            state=state,
            bid=0.48,
            ask=0.49,
            now_ts=now,
        )

        self.assertIsNotNone(decision, "Expected an SL decision, got None")
        self.assertEqual(decision.kind, "SL")
        self.assertEqual(decision.side, SIDE_SELL)
        self.assertAlmostEqual(decision.size, 10.0, places=6)
        # SL price should be fixed sl_order_price (0.01)
        self.assertAlmostEqual(decision.price, self.config.sl_order_price, places=6)
        self.assertIn("SL_TRIGGER", decision.reason)

    def test_no_decision_during_cooldown(self):
        """
        If entry is still in cooldown window, no TP/SL decision should be made.
        """
        state = FakeAccountState(pos=10.0, avg_price=0.60)
        now = time.time()

        entry = EntryOrderState(
            entry_id=1,
            market_id="m1",
            outcome="YES",
            side=SIDE_BUY,
            leg_label="YES",
            target_size=10.0,
            cooldown_sec=5.0,
            min_exit_size=1.0,
            sl_trigger=0.50,
            strategy_tag="test",
        )
        # Simulate a recent fill that is still within the cooldown window
        entry.first_fill_ts = now - 1.0
        entry.last_fill_ts = now - 1.0
        entry.cooldown_until = now + 4.0
        entry.status = "COOLING"

        entry.update_from_account_state(now, state)

        decision = self.exit_engine.evaluate_entry(
            entry=entry,
            state=state,
            bid=0.55,
            ask=0.56,
            now_ts=now,
        )

        self.assertIsNone(decision, "Should not exit during cooldown")

    def test_no_decision_if_pos_below_min_exit_size(self):
        """
        If absolute position size < entry.min_exit_size, no exit should be generated.
        """
        entry, state, now = self._make_ready_long_entry(
            pos=2.0,
            avg_price=0.60,
            min_exit_size=5.0,  # require at least 5 to exit
            sl_trigger=0.50,
        )

        decision = self.exit_engine.evaluate_entry(
            entry=entry,
            state=state,
            bid=0.48,  # SL condition satisfied, but size too small
            ask=0.49,
            now_ts=now,
        )

        self.assertIsNone(decision, "Should not exit if position < min_exit_size")

    def test_existing_live_exit_order_blocks_new_decision(self):
        """
        If there is already a live exit order for this entry (OPEN/PART_FILLED),
        StrategyExit should not propose another exit order.
        """
        entry, state, now = self._make_ready_long_entry(
            pos=10.0,
            avg_price=0.60,
            sl_trigger=0.50,
        )

        # Attach an existing exit order id
        exit_oid = "exit-1"
        entry.exit_tp_order_ids.append(exit_oid)

        # Add a live order in state.orders
        state.orders[exit_oid] = FakeOrder(
            status=ORDER_STATUS_OPEN,
            unmatched=10.0,
        )

        decision = self.exit_engine.evaluate_entry(
            entry=entry,
            state=state,
            bid=0.48,  # SL condition
            ask=0.49,
            now_ts=now,
        )

        self.assertIsNone(
            decision,
            "Should not create new exit decision when there is a live exit order",
        )


if __name__ == "__main__":
    unittest.main()