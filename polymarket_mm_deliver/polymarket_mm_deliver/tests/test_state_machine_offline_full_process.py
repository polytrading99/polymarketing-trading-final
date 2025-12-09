# tests/test_state_machine_offline_full_process.py
"""
Offline full-process test for the state machine using a synthetic
100 -> 30 -> 70 example with a full on-chain lifecycle.

Scenario:
- Place BUY 100 YES @ 0.57 (one order_id)
- First trade: trade_A MATCHED 30, then MINED, then CONFIRMED
- Order UPDATE: size_matched = 30
- Second trade: trade_B MATCHED 70, then MINED, then CONFIRMED
- Order UPDATE: size_matched = 100

We verify:
- Intermediate position_risk / pending_exposure are as expected
- Final order status is FILLED, size_unmatched = 0
- Final position_risk = +100 (BUY 100)
- Final pending_exposure = 0
- Two trades attached to the order, both CONFIRMED,
  trade_risk_size = 100, confirmed_size = 100
"""

import os
import sys
import logging

# Ensure project root (containing `state_machine/`) is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from state_machine import AccountState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fake messages for the 100 -> 30 -> 70 scenario
# ---------------------------------------------------------------------------

ORDER_ID = "order_full_process_1"
MARKET_ID = "0xmarket_full_process"
OUTCOME = "YES"
PRICE = "0.57"

TRADE_ID_A = "trade_A_30"
TRADE_ID_B = "trade_B_70"


def base_order_msg():
    """Base template for order messages in this test."""
    return {
        "asset_id": "0xasset_full_process",
        "associate_trades": None,
        "event_type": "order",
        "id": ORDER_ID,
        "market": MARKET_ID,
        "order_owner": "user-123",
        "original_size": "100",
        "outcome": OUTCOME,
        "owner": "user-123",
        "price": PRICE,
        "side": "BUY",
        "size_matched": "0",
        "timestamp": "1670000000",
        "type": "PLACEMENT",
    }


def base_trade_msg(trade_id: str, size: str, status: str):
    """Base template for trade messages in this test."""
    return {
        "asset_id": "0xasset_full_process",
        "event_type": "trade",
        "id": trade_id,
        "last_update": "1670000001",
        "maker_orders": [
            {
                "asset_id": "0xasset_full_process",
                "matched_amount": size,
                "order_id": ORDER_ID,
                "outcome": OUTCOME,
                "owner": "user-123",
                "price": PRICE,
            }
        ],
        "market": MARKET_ID,
        "matchtime": "1670000001",
        "outcome": OUTCOME,
        "owner": "user-123",
        "price": PRICE,
        "side": "BUY",  # from our account's perspective, we are BUYing YES
        "size": size,
        "status": status,
        "taker_order_id": "0xother_order",
        "timestamp": "1670000001",
        "trade_owner": "user-123",
        "type": "TRADE",
    }


def print_snapshot(label: str, state: AccountState):
    """
    Log a human-readable snapshot of the current account state.

    This is intended for manual inspection when running this file directly.
    In normal test runs, it stays at DEBUG level.
    """
    logger.debug("=== %s ===", label)

    # Positions
    logger.debug("Positions (risk view):")
    for key, value in state.position_risk.items():
        market, outcome = key
        logger.debug(
            "  market=%s, outcome=%s, position_risk=%s",
            market,
            outcome,
            value,
        )

    # Pending exposure
    logger.debug("Pending exposure (unmatched orders):")
    for key, value in state.pending_exposure.items():
        market, outcome = key
        logger.debug(
            "  market=%s, outcome=%s, pending_exposure=%s",
            market,
            outcome,
            value,
        )

    # Orders
    logger.debug("Orders:")
    for oid, order in state.orders.items():
        logger.debug(
            "  order_id=%s, side=%s, price=%s, "
            "original_size=%s, size_matched=%s, "
            "size_unmatched=%s, status=%s",
            oid,
            order.side,
            order.price,
            order.original_size,
            order.size_matched,
            order.size_unmatched,
            order.order_status,
        )
        logger.debug(
            "    trades_count=%d, trade_risk_size=%s, confirmed_size=%s",
            len(order.trades),
            order.trade_risk_size,
            order.confirmed_size,
        )


def test_state_machine_offline_full_process():
    state = AccountState()
    key = (MARKET_ID, OUTCOME)

    # -----------------------------------------------------------------------
    # 1) Order PLACEMENT: BUY 100 YES @ 0.57
    # -----------------------------------------------------------------------
    msg_order_place = base_order_msg()
    state.handle_order_message(msg_order_place)

    order = state.orders[ORDER_ID]
    # After placement: no position, pending_exposure = +100 (BUY side)
    assert order.original_size == 100.0
    assert order.size_matched == 0.0
    assert order.size_unmatched == 100.0
    assert state.position_risk[key] == 0.0
    assert state.pending_exposure[key] == 100.0

    print_snapshot("after PLACEMENT", state)

    # -----------------------------------------------------------------------
    # 2) First trade: trade_A MATCHED 30
    # -----------------------------------------------------------------------
    msg_trade_A_matched = base_trade_msg(TRADE_ID_A, "30", "MATCHED")
    state.handle_trade_message(msg_trade_A_matched)

    # Position risk should now be +30 (BUY 30)
    assert state.position_risk[key] == 30.0
    # Pending exposure still 100 until we see order UPDATE
    assert state.pending_exposure[key] == 100.0

    print_snapshot("after trade_A MATCHED (30)", state)

    # -----------------------------------------------------------------------
    # 3) Order UPDATE: size_matched = 30 (PART_FILLED)
    # -----------------------------------------------------------------------
    msg_order_update_30 = base_order_msg()
    msg_order_update_30["type"] = "UPDATE"
    msg_order_update_30["size_matched"] = "30"
    state.handle_order_message(msg_order_update_30)

    order = state.orders[ORDER_ID]
    assert order.size_matched == 30.0
    assert order.size_unmatched == 70.0
    # Pending exposure should now be 70 (remaining BUY 70)
    assert state.pending_exposure[key] == 70.0

    print_snapshot("after ORDER UPDATE to size_matched=30", state)

    # -----------------------------------------------------------------------
    # 4) trade_A MINED (no change in position)
    # -----------------------------------------------------------------------
    msg_trade_A_mined = base_trade_msg(TRADE_ID_A, "30", "MINED")
    state.handle_trade_message(msg_trade_A_mined)

    assert state.position_risk[key] == 30.0  # unchanged
    print_snapshot("after trade_A MINED", state)

    # -----------------------------------------------------------------------
    # 5) trade_A CONFIRMED
    # -----------------------------------------------------------------------
    msg_trade_A_conf = base_trade_msg(TRADE_ID_A, "30", "CONFIRMED")
    state.handle_trade_message(msg_trade_A_conf)

    assert state.position_risk[key] == 30.0  # still unchanged
    # At order level, confirmed_size should now be 30
    order = state.orders[ORDER_ID]
    assert order.confirmed_size == 30.0

    print_snapshot("after trade_A CONFIRMED", state)

    # -----------------------------------------------------------------------
    # 6) Second trade: trade_B MATCHED 70
    # -----------------------------------------------------------------------
    msg_trade_B_matched = base_trade_msg(TRADE_ID_B, "70", "MATCHED")
    state.handle_trade_message(msg_trade_B_matched)

    # Now total position risk should be +100 (30 + 70)
    assert state.position_risk[key] == 100.0
    # Pending exposure is still 70 until order UPDATE says fully matched
    assert state.pending_exposure[key] == 70.0

    print_snapshot("after trade_B MATCHED (70)", state)

    # -----------------------------------------------------------------------
    # 7) Order UPDATE: size_matched = 100 (FILLED)
    # -----------------------------------------------------------------------
    msg_order_update_100 = base_order_msg()
    msg_order_update_100["type"] = "UPDATE"
    msg_order_update_100["size_matched"] = "100"
    state.handle_order_message(msg_order_update_100)

    order = state.orders[ORDER_ID]
    assert order.size_matched == 100.0
    assert order.size_unmatched == 0.0
    # Pending exposure should now be 0 (fully filled)
    assert state.pending_exposure[key] == 0.0

    print_snapshot("after ORDER UPDATE to size_matched=100", state)

    # -----------------------------------------------------------------------
    # 8) trade_B MINED
    # -----------------------------------------------------------------------
    msg_trade_B_mined = base_trade_msg(TRADE_ID_B, "70", "MINED")
    state.handle_trade_message(msg_trade_B_mined)

    assert state.position_risk[key] == 100.0  # unchanged
    print_snapshot("after trade_B MINED", state)

    # -----------------------------------------------------------------------
    # 9) trade_B CONFIRMED
    # -----------------------------------------------------------------------
    msg_trade_B_conf = base_trade_msg(TRADE_ID_B, "70", "CONFIRMED")
    state.handle_trade_message(msg_trade_B_conf)

    # Final position: +100
    assert state.position_risk[key] == 100.0
    # No pending exposure
    assert state.pending_exposure[key] == 0.0

    order = state.orders[ORDER_ID]
    # Order-level checks: fully filled, no unmatched size
    assert order.original_size == 100.0
    assert order.size_matched == 100.0
    assert order.size_unmatched == 0.0

    # Trades: two trades, both CONFIRMED, total size 100
    assert len(order.trades) == 2
    assert order.trade_risk_size == 100.0
    assert order.confirmed_size == 100.0
    for t in order.trades.values():
        assert t.status == "CONFIRMED"

    print_snapshot("final state after full process", state)


if __name__ == "__main__":
    # Allow running this file directly for manual inspection.
    logging.basicConfig(level=logging.DEBUG)
    test_state_machine_offline_full_process()