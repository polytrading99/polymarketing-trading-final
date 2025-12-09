# test_strategy_entry.py
# -*- coding: utf-8 -*-
# Ensure project root (containing `state_machine/`) is on sys.path
import os
import sys
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import time

import pytest

from state_machine.strategy_entry import (
    EntryManager,
    ENTRY_STATUS_NEW,
    ENTRY_STATUS_WAIT_ENTRY_FILLS,
    ENTRY_STATUS_COOLING,
    ENTRY_STATUS_READY,
    ENTRY_STATUS_DONE,
)
from state_machine import AccountState
from state_machine.enums import SIDE_BUY, SIDE_SELL


def _make_trade_msg(
    *,
    trade_id: str,
    status: str,
    market_id: str,
    outcome: str,
    side: str,
    size: float,
    price: float,
    taker_order_id: str,
) -> dict:
    """
    Helper: build a minimal trade WS message that AccountState can understand.
    """
    return {
        "id": trade_id,
        "status": status,
        "market": market_id,
        "outcome": outcome,
        "side": side,
        "size": str(size),
        "price": str(price),
        "taker_order_id": taker_order_id,
        "maker_orders": [],
    }


def test_entry_lifecycle_cooldown_ready_done():
    """
    Full happy path:

    NEW -> WAIT_ENTRY_FILLS (attach order)
         -> COOLING (first fill)
         -> READY (after cooldown)
         -> DONE (position goes back to 0)
    """
    market_id = "m1"
    outcome = "YES"

    state = AccountState()
    mgr = EntryManager()

    # 1) Create logical entry
    entry = mgr.create_entry(
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        cooldown_sec=1.0,      # short cooldown for test
        min_exit_size=1.0,
        strategy_tag="test_entry_lifecycle",
    )

    assert entry.status == ENTRY_STATUS_NEW

    # 2) Register a local BUY entry order and bind it to this entry
    order_entry = state.register_local_order(
        order_id="order-entry-1",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        price=0.50,
        size=10.0,
        is_entry=True,
        strategy_tag="test_entry_lifecycle",
    )
    mgr.attach_entry_order(entry.entry_id, order_entry.order_id)

    assert entry.status == ENTRY_STATUS_WAIT_ENTRY_FILLS

    # 3) Simulate a MINED BUY trade (position +10)
    msg_buy = _make_trade_msg(
        trade_id="trade-1",
        status="MINED",          # counted in on-chain stats
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        size=10.0,
        price=0.50,
        taker_order_id=order_entry.order_id,
    )

    state.handle_trade_message(msg_buy)

    # Strategy-level "we had a fill at t0"
    t0 = time.time()
    entry.on_fill(t0)

    # Immediately update from AccountState: should be COOLING, pos ~ +10
    mgr.update_all_from_account_state(state, now_ts=t0)

    assert entry.status == ENTRY_STATUS_COOLING
    assert entry.last_known_pos == pytest.approx(10.0, rel=1e-6)
    assert entry.is_in_cooldown(t0) is True
    assert entry.is_ready_to_exit(t0) is False

    # 4) After cooldown_sec has passed -> READY
    t1 = t0 + 2.0  # > cooldown_sec=1.0
    mgr.update_all_from_account_state(state, now_ts=t1)

    assert entry.status == ENTRY_STATUS_READY
    assert entry.is_in_cooldown(t1) is False
    assert entry.is_ready_to_exit(t1) is True

    # 5) Simulate a SELL that fully closes the position (-10)
    order_exit = state.register_local_order(
        order_id="order-exit-1",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_SELL,
        price=0.50,
        size=10.0,
        is_exit=True,
        strategy_tag="test_entry_lifecycle",
    )

    msg_sell = _make_trade_msg(
        trade_id="trade-2",
        status="MINED",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_SELL,
        size=10.0,
        price=0.50,
        taker_order_id=order_exit.order_id,
    )

    state.handle_trade_message(msg_sell)

    # t2: after closing trade
    t2 = t1 + 1.0
    mgr.update_all_from_account_state(state, now_ts=t2)

    # Position should be flat, and since we had fills before, status -> DONE
    assert entry.is_fully_closed(state) is True
    assert entry.last_known_pos == pytest.approx(0.0, abs=1e-9)
    assert entry.status == ENTRY_STATUS_DONE


def test_entry_waiting_never_filled_stays_wait_or_new():
    """
    If we create an entry, attach an order, but never get any fills:
    - pos stays 0
    - first_fill_ts is None
    - status stays NEW or WAIT_ENTRY_FILLS
    - from strategy perspective it's "never opened", caller may cancel/cleanup.
    """
    market_id = "m2"
    outcome = "YES"

    state = AccountState()
    mgr = EntryManager()

    entry = mgr.create_entry(
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        cooldown_sec=1.0,
        min_exit_size=1.0,
        strategy_tag="test_entry_no_fills",
    )

    assert entry.status == ENTRY_STATUS_NEW

    # Attach a local order but no trades come in
    order_entry = state.register_local_order(
        order_id="order-entry-2",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        price=0.40,
        size=5.0,
        is_entry=True,
        strategy_tag="test_entry_no_fills",
    )
    mgr.attach_entry_order(entry.entry_id, order_entry.order_id)

    assert entry.status == ENTRY_STATUS_WAIT_ENTRY_FILLS

    # Advance time a lot, but still no fills -> pos remains 0
    t_future = time.time() + 10.0
    mgr.update_all_from_account_state(state, now_ts=t_future)

    stats = state.get_onchain_stats(market_id, outcome)
    assert stats["pos"] == pytest.approx(0.0, abs=1e-9)

    # Because first_fill_ts is None, we do NOT force DONE.
    # Caller will decide whether to cancel / drop this entry.
    assert entry.first_fill_ts is None
    assert entry.status in (ENTRY_STATUS_NEW, ENTRY_STATUS_WAIT_ENTRY_FILLS)

    # From a "position" perspective it's closed, but that's because it never opened.
    assert entry.is_fully_closed(state) is True


def test_has_enough_size_for_exit_threshold():
    """
    has_enough_size_for_exit() should reflect on-chain position >= min_exit_size.
    """
    market_id = "m3"
    outcome = "YES"

    state = AccountState()
    mgr = EntryManager()

    entry = mgr.create_entry(
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        cooldown_sec=0.0,
        min_exit_size=5.0,
        strategy_tag="test_min_exit_size",
    )

    # Register entry order and simulate a partial small fill (< min_exit_size)
    order_entry = state.register_local_order(
        order_id="order-entry-3",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        price=0.30,
        size=10.0,
        is_entry=True,
        strategy_tag="test_min_exit_size",
    )
    mgr.attach_entry_order(entry.entry_id, order_entry.order_id)

    msg_small_fill = _make_trade_msg(
        trade_id="trade-3",
        status="MINED",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        size=3.0,  # < min_exit_size
        price=0.30,
        taker_order_id=order_entry.order_id,
    )

    state.handle_trade_message(msg_small_fill)

    t0 = time.time()
    entry.on_fill(t0)
    mgr.update_all_from_account_state(state, now_ts=t0)

    assert entry.last_known_pos == pytest.approx(3.0, rel=1e-6)
    assert entry.has_enough_size_for_exit(state) is False

    # Another fill to reach >= min_exit_size
    msg_more_fill = _make_trade_msg(
        trade_id="trade-4",
        status="MINED",
        market_id=market_id,
        outcome=outcome,
        side=SIDE_BUY,
        size=2.0,  # total now 5.0
        price=0.30,
        taker_order_id=order_entry.order_id,
    )
    state.handle_trade_message(msg_more_fill)

    t1 = t0 + 1.0
    mgr.update_all_from_account_state(state, now_ts=t1)

    assert entry.last_known_pos == pytest.approx(5.0, rel=1e-6)
    assert entry.has_enough_size_for_exit(state) is True