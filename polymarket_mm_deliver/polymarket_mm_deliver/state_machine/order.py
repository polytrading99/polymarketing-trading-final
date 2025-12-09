# state_machine/order.py
"""
Order-level state: a "super order" object that knows:
- basic order info (id, market, outcome, side, price)
- how much was originally placed and how much has been matched
- its derived order status (OPEN / PART_FILLED / FILLED / CANCELED)
- all related trades (trade id, size, trade status)

For maker orders created from WS `event_type="order"` messages:
- original_size / size_matched are driven by order WS.

For taker orders created locally via REST + `register_local_order`:
- original_size is set from REST response + local logic
- size_matched / status are updated only from trade WS
  (MATCHED / MINED / CONFIRMED / FAILED)

This object does NOT modify account-level positions directly.
AccountState is responsible for updating positions and pending exposure.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

import logging
import time  # <<< added

from .enums import (
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PART_FILLED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_CANCELED,
    STATUS_RANK,
)

logger = logging.getLogger(__name__)


@dataclass
class TradeInfo:
    """A single trade attached to an order."""
    trade_id: str
    size: float
    status: str  # MATCHED / MINED / CONFIRMED / RETRYING / FAILED


@dataclass
class SuperOrder:
    """
    "Super order" representation for a single order_id.

    It aggregates:
    - Order-level data from `event_type = "order"` messages (for maker orders).
    - Trade-level data from `event_type = "trade"` messages that reference this order.
    """

    # Basic order info
    order_id: str
    market_id: str
    outcome: str          # e.g. "YES" / "NO" / "Up" / "Down"
    side: str             # "BUY" / "SELL"
    price: float

    # Order size info
    original_size: float = 0.0   # Total requested size
    size_matched: float = 0.0    # How much has been matched

    # If True, this order was created locally (REST resp + register_local_order),
    # and we expect NO reliable order WS for it. In that case:
    # - size_matched / order_status are driven by trades only.
    # If False, we trust order WS for size_matched / status (maker-style orders).
    local_only: bool = False

    # Role & meta information (used by strategy / helpers)
    is_entry: bool = False        # True if this is an entry (open-position) order
    is_exit: bool = False         # True if this is an exit (close-position) order
    strategy_tag: str = ""        # Optional: which strategy created this order
    client_id: Optional[int] = None  # Optional: local client order id in your engine
    # --- New: timing & price management for entry/exit ---
    entry_order_price: Optional[float] = None      # Current entry order price
    entry_last_action_ts: Optional[float] = None   # Timestamp of last action (place/cancel/modify) on entry order
    # Timing & exit management helpers (for fast MM exit logic)
    first_fill_ts: Optional[float] = None        # Time of first fill (epoch seconds)
    last_exit_attempt_ts: Optional[float] = None # Timestamp of last attempt to place/cancel exit order
    exit_order_id: Optional[str] = None          # Current exit order id (if any)
    exit_order_price: Optional[float] = None     # Current exit order price (if any)
    # Derived order status
    order_status: str = ORDER_STATUS_OPEN

    # All trades attached to this order: trade_id -> TradeInfo
    trades: Dict[str, TradeInfo] = field(default_factory=dict)

    # -------------------------------------------------------------------------
    # Derived properties
    # -------------------------------------------------------------------------

    @property
    def size_unmatched(self) -> float:
        """
        Remaining size that is not yet matched (>= 0).

        - For local_only orders (taker): based on trade-driven size_matched.
        - For WS-maker orders: based on WS-driven size_matched.
        """
        remaining = self.original_size - self.size_matched
        return remaining if remaining > 0 else 0.0

    @property
    def trade_risk_size(self) -> float:
        """
        From a risk perspective: total size of trades that still count as risky
        (i.e. everything except FAILED trades).

        This is just a size sum; direction (BUY/SELL) is applied at account level.
        """
        total = 0.0
        for t in self.trades.values():
            if t.status != "FAILED":
                total += t.size
        return total

    @property
    def confirmed_size(self) -> float:
        """
        Total size of trades that have reached CONFIRMED on-chain state.

        Useful for comparing against on-chain /positions APIs.
        """
        total = 0.0
        for t in self.trades.values():
            if t.status == "CONFIRMED":
                total += t.size
        return total

    # -------------------------------------------------------------------------
    # Order WS (maker orders)
    # -------------------------------------------------------------------------

    def apply_order_message(self, msg: dict) -> None:
        """
        Apply an `event_type = "order"` message to this SuperOrder.

        Expected fields:
        - id            (order id)         -> used outside to route to this object
        - market        (condition id)
        - outcome       (e.g. "YES"/"NO")
        - side          ("BUY"/"SELL")
        - price
        - original_size (string)
        - size_matched  (string)
        - type          ("PLACEMENT" / "UPDATE" / "CANCELLATION")

        For local_only orders (taker), we ignore order WS completely.
        """
        logger.debug(
            "apply_order_message: order_id=%s local_only=%s raw_msg=%s",
            self.order_id,
            self.local_only,
            msg,
        )

        if self.local_only:
            # In taker mode we don't rely on order WS, we only trust trade WS.
            logger.debug(
                "Ignoring order WS for local-only order: order_id=%s",
                self.order_id,
            )
            return

        # Update size fields from message (strings -> float)
        if "original_size" in msg:
            self.original_size = float(msg["original_size"])
        if "size_matched" in msg:
            self.size_matched = float(msg["size_matched"])

        logger.debug(
            "Order sizes updated from WS: order_id=%s original_size=%s size_matched=%s",
            self.order_id,
            self.original_size,
            self.size_matched,
        )

        msg_type = msg["type"]  # PLACEMENT / UPDATE / CANCELLATION

        # Derive order_status
        if msg_type == "CANCELLATION":
            # Once canceled, we treat the remaining unmatched size as gone from the book.
            self.order_status = ORDER_STATUS_CANCELED
            logger.info(
                "Order canceled from WS: order_id=%s original_size=%s size_matched=%s",
                self.order_id,
                self.original_size,
                self.size_matched,
            )
        else:
            if self.size_matched <= 0:
                self.order_status = ORDER_STATUS_OPEN
            elif self.size_matched < self.original_size:
                self.order_status = ORDER_STATUS_PART_FILLED
            else:
                self.order_status = ORDER_STATUS_FILLED

            logger.debug(
                "Order status updated from WS: order_id=%s status=%s original_size=%s size_matched=%s",
                self.order_id,
                self.order_status,
                self.original_size,
                self.size_matched,
            )

    # -------------------------------------------------------------------------
    # Trade WS (both taker & maker)
    # -------------------------------------------------------------------------

    def apply_trade_message(self, msg: dict) -> None:
        """
        Attach or update a trade under this order using
        an `event_type = "trade"` message.

        Expected fields:
        - id     (trade id)
        - size   (string)  # taker side size
        - status (MATCHED / MINED / CONFIRMED / RETRYING / FAILED)

        For local_only orders (taker):
        - size_matched / order_status are updated based on trades only.

        NOTE: This function does NOT update account-level positions.
        It only updates the per-order trade status. AccountState will
        use these trades to compute positions and confirmed exposure.
        """
        trade_id = msg["id"]
        size = float(msg["size"])
        status = msg["status"]

        logger.debug(
            "apply_trade_message: order_id=%s trade_id=%s size=%s status=%s local_only=%s",
            self.order_id,
            trade_id,
            size,
            status,
            self.local_only,
        )

        if trade_id not in self.trades:
            # New trade for this order
            self.trades[trade_id] = TradeInfo(
                trade_id=trade_id,
                size=size,
                status=status,
            )

            # For local-only orders, a new non-FAILED trade increases matched size
            if self.local_only and status != "FAILED":
                prev_matched = self.size_matched
                self.size_matched += size
                logger.debug(
                    "Local-only order matched size increased: order_id=%s trade_id=%s size=%s prev_matched=%s new_matched=%s",
                    self.order_id,
                    trade_id,
                    size,
                    prev_matched,
                    self.size_matched,
                )
        else:
            # Existing trade: update status if this is a "later" status
            t = self.trades[trade_id]
            old_status = t.status
            old_rank = STATUS_RANK.get(old_status, 0.0)
            new_rank = STATUS_RANK.get(status, 0.0)

            if new_rank >= old_rank:
                t.status = status
                logger.debug(
                    "Trade status updated: order_id=%s trade_id=%s old_status=%s new_status=%s",
                    self.order_id,
                    trade_id,
                    old_status,
                    status,
                )

                # For local-only orders: if a previously risky trade becomes FAILED,
                # we roll back its contribution to size_matched.
                if self.local_only and old_status != "FAILED" and status == "FAILED":
                    prev_matched = self.size_matched
                    self.size_matched -= t.size
                    logger.debug(
                        "Local-only order trade FAILED, rolling back matched size: "
                        "order_id=%s trade_id=%s trade_size=%s prev_matched=%s new_matched=%s",
                        self.order_id,
                        trade_id,
                        t.size,
                        prev_matched,
                        self.size_matched,
                    )

        # Clamp & derive order_status for local-only orders
        if self.local_only and self.order_status != ORDER_STATUS_CANCELED:
            prev_matched = self.size_matched
            prev_status = self.order_status

            if self.size_matched < 0:
                self.size_matched = 0.0
            if self.original_size > 0 and self.size_matched > self.original_size:
                self.size_matched = self.original_size

            if self.size_matched <= 0:
                self.order_status = ORDER_STATUS_OPEN
            elif self.size_matched < self.original_size:
                self.order_status = ORDER_STATUS_PART_FILLED
            else:
                self.order_status = ORDER_STATUS_FILLED

            if (
                self.size_matched != prev_matched
                or self.order_status != prev_status
            ):
                logger.debug(
                    "Local-only order state updated from trades: "
                    "order_id=%s size_matched=%s status=%s (prev_size_matched=%s prev_status=%s)",
                    self.order_id,
                    self.size_matched,
                    self.order_status,
                    prev_matched,
                    prev_status,
                )
                # If this is the first fill, record first_fill_ts
                if self.size_matched > 0 and self.first_fill_ts is None:
                    self.first_fill_ts = time.time()