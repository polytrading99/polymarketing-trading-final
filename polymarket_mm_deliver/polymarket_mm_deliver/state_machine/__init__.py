# state_machine/__init__.py
"""
Core state management for a Polymarket market-making bot.

This package currently provides:
- enums: basic constants and status ranking
- order: SuperOrder and TradeInfo to track a single order and its trades
- account_state: AccountState to maintain account-level positions and pending exposure
"""

from .enums import STATUS_RANK
from .order import SuperOrder, TradeInfo
from .account_state import AccountState
from .strategy_entry import EntryOrderState
__all__ = [
    "STATUS_RANK",
    "SuperOrder",
    "TradeInfo",
    "AccountState",
]