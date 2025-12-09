# state_machine/enums.py
"""
Basic enums / constants for Polymarket state management.
We keep it simple: mostly string-based, but centralized here for consistency.
"""

from typing import Dict

# Side of an order / trade
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

# Trade status lifecycle (from Polymarket docs)
TRADE_STATUS_MATCHED = "MATCHED"
TRADE_STATUS_MINED = "MINED"
TRADE_STATUS_CONFIRMED = "CONFIRMED"
TRADE_STATUS_RETRYING = "RETRYING"
TRADE_STATUS_FAILED = "FAILED"

# Order status (internal, derived from original_size / size_matched / cancellation)
ORDER_STATUS_OPEN = "OPEN"
ORDER_STATUS_PART_FILLED = "PART_FILLED"
ORDER_STATUS_FILLED = "FILLED"
ORDER_STATUS_CANCELED = "CANCELED"

# A simple rank for trade status so we can ignore out-of-order / older updates.
STATUS_RANK: Dict[str, float] = {
    TRADE_STATUS_MATCHED: 1.0,
    TRADE_STATUS_RETRYING: 1.5,
    TRADE_STATUS_MINED: 2.0,
    TRADE_STATUS_CONFIRMED: 3.0,
    TRADE_STATUS_FAILED: 3.0,
}