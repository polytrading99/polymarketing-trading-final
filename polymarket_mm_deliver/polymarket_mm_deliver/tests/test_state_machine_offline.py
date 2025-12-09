# tests/test_state_machine_offline.py
"""
Offline test for the state machine using real-looking Polymarket WS messages.

We simulate:
1) An order PLACEMENT (SELL 10 YES @ 0.57)
2) A trade MATCHED that fully fills 10 size against that order

The goal is to verify:
- SuperOrder is created from the order message
- pending_exposure is updated from the order message
- position_risk is updated from the trade message
- the trade is attached to the correct order
"""

import os
import sys
import logging

# Make sure the project root (the directory containing `state_machine/`) is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from state_machine import AccountState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fake messages copied from sample Polymarket traffic
# ---------------------------------------------------------------------------

ORDER_MSG_PLACEMENT = {
    "asset_id": "52114319501245915516055106046884209969926127482827954674443846427813813222426",
    "associate_trades": None,
    "event_type": "order",
    "id": "0xff354cd7ca7539dfa9c28d90943ab5779a4eac34b9b37a757d7b32bdfb11790b",
    "market": "0xbd31dc8a20211944f6b70f31557f1001557b59905b7738480ca09bd4532f84af",
    "order_owner": "9180014b-33c8-9240-a14b-bdca11c0a465",
    "original_size": "10",
    "outcome": "YES",
    "owner": "9180014b-33c8-9240-a14b-bdca11c0a465",
    "price": "0.57",
    "side": "SELL",
    "size_matched": "0",
    "timestamp": "1672290687",
    "type": "PLACEMENT",
}

TRADE_MSG_MATCHED = {
    "asset_id": "52114319501245915516055106046884209969926127482827954674443846427813813222426",
    "event_type": "trade",
    "id": "28c4d2eb-bbea-40e7-a9f0-b2fdb56b2c2e",
    "last_update": "1672290701",
    "maker_orders": [
        {
            "asset_id": "52114319501245915516055106046884209969926127482827954674443846427813813222426",
            "matched_amount": "10",
            "order_id": "0xff354cd7ca7539dfa9c28d90943ab5779a4eac34b9b37a757d7b32bdfb11790b",
            "outcome": "YES",
            "owner": "9180014b-33c8-9240-a14b-bdca11c0a465",
            "price": "0.57",
        }
    ],
    "market": "0xbd31dc8a20211944f6b70f31557f1001557b59905b7738480ca09bd4532f84af",
    "matchtime": "1672290701",
    "outcome": "YES",
    "owner": "9180014b-33c8-9240-a14b-bdca11c0a465",
    "price": "0.57",
    "side": "BUY",
    "size": "10",
    "status": "MATCHED",
    "taker_order_id": "0x06bc63e346ed4ceddce9efd6b3af37c8f8f440c92fe7da6b2d0f9e4ccbc50c42",
    "timestamp": "1672290701",
    "trade_owner": "9180014b-33c8-9240-a14b-bdca11c0a465",
    "type": "TRADE",
}


# ---------------------------------------------------------------------------
# Helper for logging state (for manual inspection)
# ---------------------------------------------------------------------------

def print_snapshot(label: str, state: AccountState):
    """
    Log a human-readable snapshot of the current account state.

    This is intended for manual inspection when running this file directly.
    Logged at DEBUG level to avoid noise in normal test runs.
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


# ---------------------------------------------------------------------------
# Pytest-style test function (also works as a simple script check)
# ---------------------------------------------------------------------------

def test_state_machine_offline_scenario():
    state = AccountState()

    market = ORDER_MSG_PLACEMENT["market"]
    outcome = ORDER_MSG_PLACEMENT["outcome"]
    key = (market, outcome)

    # 1) Feed the PLACEMENT order message
    state.handle_order_message(ORDER_MSG_PLACEMENT)

    # Basic checks after PLACEMENT
    assert ORDER_MSG_PLACEMENT["id"] in state.orders
    order = state.orders[ORDER_MSG_PLACEMENT["id"]]

    # Order-level expectations
    assert order.original_size == 10.0
    assert order.size_matched == 0.0
    assert order.size_unmatched == 10.0

    # After a SELL placement of 10, pending_exposure should be negative 10
    # (SELL = negative exposure, BUY = positive exposure)
    assert state.position_risk[key] == 0.0
    assert state.pending_exposure[key] == -10.0

    # 2) Feed the MATCHED trade message (full fill of 10)
    state.handle_trade_message(TRADE_MSG_MATCHED)

    # After the trade, from a risk perspective, we have +10 size
    # (using the trade's "side" field directly)
    assert state.position_risk[key] == 10.0

    # NOTE:
    # At this point, the order WS has not yet sent an UPDATE with size_matched=10,
    # so from the order's perspective it still thinks size_matched=0, size_unmatched=10.
    # That means pending_exposure is still -10.0.
    # This short-lived inconsistency is expected in a live system and will be
    # resolved once the next order UPDATE message arrives.
    assert state.pending_exposure[key] == -10.0

    # The trade should also be attached to the maker order from maker_orders[]
    assert len(order.trades) == 1
    trade = next(iter(order.trades.values()))
    assert trade.size == 10.0
    assert trade.status == "MATCHED"

    # For manual debugging, log a snapshot at DEBUG level
    print_snapshot("after PLACEMENT + MATCHED trade", state)


# ---------------------------------------------------------------------------
# Allow running this file directly: `python tests/test_state_machine_offline.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_state_machine_offline_scenario()