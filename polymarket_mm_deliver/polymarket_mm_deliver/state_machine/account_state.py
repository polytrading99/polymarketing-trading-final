# state_machine/account_state.py
"""
Account-level state aggregation.

AccountState is responsible for:
- maintaining all SuperOrder instances (order_id -> SuperOrder)
- maintaining risk positions per (market, outcome)
- maintaining pending exposure (unmatched order size) per (market, outcome)
- handling WS messages from the user channel:
    - order messages -> update SuperOrder + pending exposure (mainly for maker orders)
    - trade messages -> update positions + attach trades to orders

For taker-style orders created locally via REST:
- use `register_local_order(...)` right after place_order resp
- there may be NO reliable order WS messages for these orders
- their SuperOrder will be updated only from trade WS
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

import logging

from .enums import (
    SIDE_BUY,
    SIDE_SELL,
    STATUS_RANK,
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PART_FILLED,
    ORDER_STATUS_FILLED,
)
from .order import SuperOrder


logger = logging.getLogger(__name__)

Key = Tuple[str, str]  # (market_id, outcome)

# Order statuses that are considered "live" on the book (still contributing pending)
LIVE_ORDER_STATUSES = {ORDER_STATUS_OPEN, ORDER_STATUS_PART_FILLED}

DUST_EPS = 1.0


@dataclass
class AccountState:
    """
    High-level state container for the whole account.

    You feed WS messages into:
    - handle_order_message(msg) for event_type == "order"
    - handle_trade_message(msg) for event_type == "trade"

    Then strategy / risk modules can read:
    - position_risk[(market, outcome)]
    - pending_exposure[(market, outcome)]
    - orders[order_id]
    """

    # All known orders by order_id
    orders: Dict[str, SuperOrder] = field(default_factory=dict)

    # Risk positions per (market, outcome)
    # This is from a "risk" perspective: MATCHED+MINED+CONFIRMED+RETRYING trades
    position_risk: Dict[Key, float] = field(default_factory=lambda: defaultdict(float))

    # Pending exposure per (market, outcome) from unmatched order size.
    # For taker local-only orders this stays 0 (they do not rest on the book).
    pending_exposure: Dict[Key, float] = field(default_factory=lambda: defaultdict(float))

    # Global trade index by trade_id, used to avoid double-counting in position_risk.
    # Each entry:
    #   {
    #       "size": float,
    #       "status": str,
    #       "side": "BUY"/"SELL",
    #       "market": str,
    #       "outcome": str,
    #       "price": float,
    #   }
    trades: Dict[str, dict] = field(default_factory=dict)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _key(order: SuperOrder) -> Key:
        """Key for aggregations: (market_id, outcome)."""
        return (order.market_id, order.outcome)

    @staticmethod
    def _key_from_msg(msg: dict) -> Key:
        """Key from a trade message: (market, outcome)."""
        return (msg["market"], msg["outcome"])

    @staticmethod
    def _signed(side: str, size: float) -> float:
        """Return signed size: BUY = +size, SELL = -size."""
        return size if side == SIDE_BUY else -size

    # -------------------------------------------------------------------------
    # Order messages (mainly maker orders)
    # -------------------------------------------------------------------------
    DUST_EPS = 1.0

    def handle_order_message(self, msg: dict) -> None:
        """
        Handle an `event_type = "order"` message from the user WebSocket channel.

        For CANCELLATION / CANCELED messages we do a special handling:
        - force SuperOrder.order_status to CANCELED (or msg_status)
        - remove its contribution from pending_exposure using the previous unmatched size
        """

        order_id = msg["id"]
        msg_type = (msg.get("type") or "").upper()
        msg_status = (msg.get("status") or "").upper()

        logger.debug(
            "handle_order_message: order_id=%s type=%s status=%s raw_msg=%s",
            order_id,
            msg_type,
            msg_status,
            msg,
        )

        # Get or create the SuperOrder for this order_id
        if order_id not in self.orders:
            order = SuperOrder(
                order_id=order_id,
                market_id=msg["market"],
                outcome=msg["outcome"],
                side=msg["side"],  # "BUY" / "SELL"
                price=float(msg["price"]),
            )
            self.orders[order_id] = order
            logger.debug(
                "Created new SuperOrder in AccountState: order_id=%s market=%s outcome=%s side=%s price=%s",
                order_id,
                order.market_id,
                order.outcome,
                order.side,
                order.price,
            )
        else:
            order = self.orders[order_id]

        key = self._key(order)

        # ============= Special case: cancellation message =============
        is_cancel = (
            msg_type == "CANCELLATION"
            or msg_status.startswith("CANCEL")  # CANCELED / CANCELLED
        )
        if is_cancel:
            old_unmatched = order.size_unmatched if order.original_size > 0 else 0.0

            # Force local status (only status, do not touch read-only properties)
            order.order_status = msg_status or "CANCELED"

            # Fix pending_exposure by removing the previous unmatched size
            if old_unmatched != 0.0:
                self.pending_exposure[key] += self._signed(order.side, -old_unmatched)
                logger.info(
                    "Order canceled: order_id=%s status=%s old_unmatched=%s new_pending=%s",
                    order_id,
                    order.order_status,
                    old_unmatched,
                    self.pending_exposure[key],
                )
            else:
                logger.info(
                    "Order canceled with zero unmatched: order_id=%s status=%s",
                    order_id,
                    order.order_status,
                )

            return

        # ============= Normal non-cancel order updates =============

        # Compute old_unmatched and apply dust threshold (avoid counting tiny leftovers)
        old_unmatched = order.size_unmatched if order.original_size > 0 else 0.0
        if old_unmatched < DUST_EPS:
            old_unmatched = 0.0

        # Update SuperOrder internal state from the message
        order.apply_order_message(msg)

        # Read new unmatched size and apply dust threshold
        raw_unmatched = order.size_unmatched if order.original_size > 0 else 0.0
        if raw_unmatched < DUST_EPS:
            new_unmatched = 0.0
            # From the dust perspective, if status is still PART_FILLED,
            # we treat this as FILLED locally.
            if order.order_status == ORDER_STATUS_PART_FILLED:
                order.order_status = ORDER_STATUS_FILLED
                logger.debug(
                    "Dust threshold turned PART_FILLED -> FILLED: order_id=%s raw_unmatched=%s",
                    order_id,
                    raw_unmatched,
                )
        else:
            new_unmatched = raw_unmatched

        # Delta of unmatched size (using dust-adjusted values)
        delta_unmatched = new_unmatched - old_unmatched

        # Update pending_exposure
        if delta_unmatched != 0:
            self.pending_exposure[key] += self._signed(order.side, delta_unmatched)
            logger.debug(
                "Pending exposure updated on order message: order_id=%s key=%s side=%s delta_unmatched=%s new_pending=%s",
                order_id,
                key,
                order.side,
                delta_unmatched,
                self.pending_exposure[key],
            )

    # -------------------------------------------------------------------------
    # Trade messages
    # -------------------------------------------------------------------------

    def handle_trade_message(self, msg: dict) -> None:
        """
        Handle an `event_type = "trade"` message from the user WebSocket channel.

        Two cases are handled:
        1) We are the taker: taker_order_id is in self.orders.
        2) We are a maker: in msg["maker_orders"] there is an entry whose order_id is ours.

        For every fill that is related to our account, we create a unique trade key:
            trade_key = f"{trade_id}:taker:{order_id}"
            or
            trade_key = f"{trade_id}:maker:{order_id}"

        This ensures:
        - multiple of our orders in a single trade_id do not overwrite each other
        - we only count our portion of the trade volume into position_risk
        """

        trade_id = msg["id"]
        status = msg["status"]
        status_rank_new = STATUS_RANK.get(status, 0.0)

        logger.debug(
            "handle_trade_message: trade_id=%s status=%s raw_msg=%s",
            trade_id,
            status,
            msg,
        )

        def _upsert_trade(
            tkey: str,
            *,
            market: str,
            outcome: str,
            side: str,
            size: float,
            price: float,
        ) -> None:
            key = (market, outcome)
            info = self.trades.get(tkey)

            if info is None:
                # First time we see this (trade_id, our_order_id) fill
                self.trades[tkey] = {
                    "size": size,
                    "status": status,
                    "side": side,
                    "market": market,
                    "outcome": outcome,
                    "price": price,
                }
                if status != "FAILED":
                    self.position_risk[key] += self._signed(side, size)
                logger.debug(
                    "New trade inserted: tkey=%s market=%s outcome=%s side=%s size=%s price=%s status=%s new_pos=%s",
                    tkey,
                    market,
                    outcome,
                    side,
                    size,
                    price,
                    status,
                    self.position_risk[key],
                )
            else:
                # Forward-only status progression (e.g. MATCHED -> MINED -> CONFIRMED)
                old_status = info["status"]
                old_rank = STATUS_RANK.get(old_status, 0.0)
                if status_rank_new >= old_rank:
                    # If we downgrade from non-FAILED to FAILED, roll back the risk impact
                    if status == "FAILED" and old_status != "FAILED":
                        self.position_risk[key] -= self._signed(info["side"], info["size"])
                        logger.debug(
                            "Trade status downgraded to FAILED, rolling back risk: tkey=%s old_status=%s new_status=%s new_pos=%s",
                            tkey,
                            old_status,
                            status,
                            self.position_risk[key],
                        )
                    info["status"] = status
                    logger.debug(
                        "Trade status updated: tkey=%s old_status=%s new_status=%s",
                        tkey,
                        old_status,
                        status,
                    )

        # -----------------------
        # 1) taker side
        # -----------------------
        taker_oid = msg.get("taker_order_id")
        if isinstance(taker_oid, str) and taker_oid in self.orders:
            market = msg["market"]
            outcome = msg["outcome"]
            side = msg["side"]
            size = float(msg["size"])
            price = float(msg["price"])

            trade_key = f"{trade_id}:taker:{taker_oid}"
            _upsert_trade(
                trade_key,
                market=market,
                outcome=outcome,
                side=side,
                size=size,
                price=price,
            )

            # Update the corresponding SuperOrder as well
            self.orders[taker_oid].apply_trade_message(msg)

        # -----------------------
        # 2) maker side
        # -----------------------
        maker_orders = msg.get("maker_orders") or []
        for m in maker_orders:
            if not isinstance(m, dict):
                continue
            m_oid = m.get("order_id")
            if not isinstance(m_oid, str) or m_oid not in self.orders:
                continue

            order = self.orders[m_oid]

            # This maker fill's size and side from our perspective
            try:
                m_size = float(m.get("matched_amount", "0") or 0.0)
            except Exception:
                m_size = 0.0
            if m_size <= 0.0:
                continue

            m_side = m.get("side") or order.side
            try:
                m_price = float(m.get("price") or msg.get("price") or 0.0)
            except Exception:
                m_price = 0.0

            # Use local SuperOrder market / outcome to avoid being misled by top-level fields
            market = order.market_id
            outcome = order.outcome

            trade_key = f"{trade_id}:maker:{m_oid}"
            _upsert_trade(
                trade_key,
                market=market,
                outcome=outcome,
                side=m_side,
                size=m_size,
                price=m_price,
            )

            # Build a trade message that is specific to this order
            # so SuperOrder can track its own fills.
            msg_for_order = dict(msg)
            msg_for_order["side"] = m_side
            msg_for_order["size"] = str(m_size)
            msg_for_order["outcome"] = outcome
            msg_for_order["asset_id"] = m.get("asset_id", msg.get("asset_id"))

            self.orders[m_oid].apply_trade_message(msg_for_order)

    # -------------------------------------------------------------------------
    # Local order registration (taker orders)
    # -------------------------------------------------------------------------

    def register_local_order(
        self,
        order_id: str,
        market_id: str,
        outcome: str,
        side: str,
        price: float,
        size: float,
        *,
        is_entry: bool = False,
        is_exit: bool = False,
        strategy_tag: str = "",
        client_id: Optional[int] = None,
    ) -> SuperOrder:
        """
        Register an order that we just placed via REST (place_limit),
        for which we DO NOT expect reliable order WS (typical taker order).

        - Uses `order_id` from REST response.
        - `original_size` is our requested size.
        - `size_matched` will be driven purely by trade WS via apply_trade_message.
        - pending_exposure is NOT updated, because taker orders do not rest on the book.
        """
        if order_id in self.orders:
            logger.debug(
                "register_local_order: reuse existing SuperOrder order_id=%s market=%s outcome=%s",
                order_id,
                self.orders[order_id].market_id,
                self.orders[order_id].outcome,
            )
            return self.orders[order_id]

        order = SuperOrder(
            order_id=order_id,
            market_id=market_id,
            outcome=outcome,
            side=side,
            price=price,
            original_size=size,
            local_only=True,
            is_entry=is_entry,
            is_exit=is_exit,
            strategy_tag=strategy_tag,
            client_id=client_id,
        )
        self.orders[order_id] = order
        logger.info(
            "Registered local-only order: order_id=%s market=%s outcome=%s side=%s size=%s price=%s is_entry=%s is_exit=%s strategy_tag=%s",
            order_id,
            market_id,
            outcome,
            side,
            size,
            price,
            is_entry,
            is_exit,
            strategy_tag,
        )
        return order

    # -------------------------------------------------------------------------
    # Position helpers (pos only)
    # -------------------------------------------------------------------------

    def get_risk_pos(self, market_id: str, outcome: str) -> float:
        """
        Risk perspective position: basically position_risk[(market, outcome)].
        Includes all trades with status >= MATCHED and status != FAILED.
        """
        return self.position_risk.get((market_id, outcome), 0.0)

    def get_onchain_pos(self, market_id: str, outcome: str) -> float:
        """
        On-chain perspective position: only trades that have reached
        MINED / CONFIRMED are counted.

        This returns only the position size; for average price use get_onchain_stats.
        """
        stats = self.get_onchain_stats(market_id, outcome)
        return stats["pos"]

    # -------------------------------------------------------------------------
    # Position + average price helpers
    # -------------------------------------------------------------------------

    def _agg_stats_for_trades(
        self,
        market_id: str,
        outcome: str,
        *,
        min_status_rank: float,
        exclude_failed: bool = True,
    ) -> Dict[str, float]:
        """
        Aggregate all trades for (market_id, outcome) and compute:
        - pos       : current signed position size
        - cash      : cash flow from trades
                      (BUY pays cash => negative, SELL receives cash => positive)
        - avg_price : average cost of the current position, -cash / pos (0 if no pos)
        """
        pos = 0.0
        cash = 0.0

        for info in self.trades.values():
            if info["market"] != market_id or info["outcome"] != outcome:
                continue

            status = info["status"]
            if exclude_failed and status == "FAILED":
                continue

            status_rank = STATUS_RANK.get(status, 0.0)
            if status_rank < min_status_rank:
                continue

            size = float(info["size"])
            side = info["side"]
            price = float(info["price"])

            sign = 1.0 if side == SIDE_BUY else -1.0

            pos += sign * size
            cash -= sign * size * price

        if abs(pos) > 1e-9:
            avg_price = -cash / pos
        else:
            avg_price = 0.0

        return {
            "pos": pos,
            "cash": cash,
            "avg_price": avg_price,
        }

    def get_risk_stats(self, market_id: str, outcome: str) -> Dict[str, float]:
        """
        Risk-view position and average price:
        - Count all trades with status >= MATCHED and status != FAILED.
        - Returns dict: {"pos", "cash", "avg_price"}.
        """
        min_rank = STATUS_RANK.get("MATCHED", 0.0)
        return self._agg_stats_for_trades(
            market_id,
            outcome,
            min_status_rank=min_rank,
            exclude_failed=True,
        )

    def get_onchain_stats(self, market_id: str, outcome: str) -> Dict[str, float]:
        """
        On-chain-view position and average price:
        - Count all trades with status >= MINED and status != FAILED.
        - Returns dict: {"pos", "cash", "avg_price"}.
        """
        min_rank = STATUS_RANK.get("MINED", 0.0)
        return self._agg_stats_for_trades(
            market_id,
            outcome,
            min_status_rank=min_rank,
            exclude_failed=True,
        )

    # -------------------------------------------------------------------------
    # Pending entry / exit helpers
    # -------------------------------------------------------------------------

    def get_pending_entry(self, market_id: str, outcome: str) -> float:
        """
        Sum of unmatched size of all entry orders (is_entry=True) for a given
        (market_id, outcome) that are still live on the book
        (OPEN / PART_FILLED and size_unmatched > 0).
        """
        total = 0.0
        for o in self.orders.values():
            if o.market_id != market_id or o.outcome != outcome:
                continue
            if not o.is_entry:
                continue
            if o.order_status not in LIVE_ORDER_STATUSES:
                continue
            if o.size_unmatched <= 0:
                continue
            total += o.size_unmatched
        return total

    def get_pending_exit(self, market_id: str, outcome: str) -> float:
        """
        Sum of unmatched size of all exit orders (is_exit=True) for a given
        (market_id, outcome) that are still live on the book
        (OPEN / PART_FILLED and size_unmatched > 0).
        """
        total = 0.0
        for o in self.orders.values():
            if o.market_id != market_id or o.outcome != outcome:
                continue
            if not o.is_exit:
                continue
            if o.order_status not in LIVE_ORDER_STATUSES:
                continue
            if o.size_unmatched <= 0:
                continue
            total += o.size_unmatched
        return total