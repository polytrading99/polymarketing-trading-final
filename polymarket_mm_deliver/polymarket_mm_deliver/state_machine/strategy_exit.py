# strategy_exit.py
# -*- coding: utf-8 -*-
"""
Strategy-level exit (TP/SL) decision engine.

This module sits on top of:

- AccountState:
    * Knows all SuperOrders and trades
    * Can compute on-chain stats (pos, avg_price) per (market, outcome)

- strategy_entry.EntryOrderState / EntryManager:
    * Knows "logical entries" (one entry may consist of several REST orders)
    * Tracks cooldown, whether the entry is ready to exit, etc.

This module does NOT talk to Polymarket REST or WS directly.
It only inspects:

    - current mid / bid / ask (provided by the caller)
    - current AccountState
    - current EntryOrderState

and returns *decisions* like:

    - "Place a TP order of size X at price P"
    - "Place an SL order of size X at price P"

The caller (main strategy loop) is responsible for:
    * actually placing the REST order via PolymarketClient
    * registering local orders in AccountState
    * attaching those orders back to EntryOrderState via EntryManager
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, List

from state_machine import AccountState
from state_machine.enums import (
    SIDE_BUY,
    SIDE_SELL,
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PART_FILLED,
)

from state_machine.strategy_entry import EntryOrderState


# ---------------------------------------------------------------------------
# Exit decision description
# ---------------------------------------------------------------------------

@dataclass
class ExitDecision:
    """
    A single exit decision for one EntryOrderState.

    The strategy loop can take this and translate it into a REST order
    via PolymarketClient:

        resp = poly.place_limit(
            token_id=...,
            side=decision.side,
            price=decision.price,
            size=decision.size,
            order_type="GTC",
        )

    Fields:
        entry_id : logical entry id (for logging / routing)
        kind     : "TP" or "SL"
        side     : "BUY" or "SELL" for the *exit* order
        size     : absolute size to exit (on-chain view)
        price    : limit price for the exit order
        reason   : human-readable reason (for logging)
    """

    entry_id: int
    kind: str           # "TP" or "SL"
    side: str           # "BUY" / "SELL"
    size: float
    price: float
    reason: str


# ---------------------------------------------------------------------------
# Exit engine configuration
# ---------------------------------------------------------------------------

@dataclass
class ExitConfig:
    """
    Configuration for StrategyExit.

    All prices here are *strategy-level* prices. You can choose to:

        - Use absolute price levels (e.g. sl_trigger in EntryOrderState)
        - Use dynamic levels computed from avg_price in your main strategy,
          and set them into EntryOrderState.sl_trigger / tp_trigger.

    Fields:
        sl_order_price   : Actual price used for SL orders (taker-style),
                           e.g. 0.01 or very aggressive.
        min_tp_increment : Minimal TP increment vs entry avg price. If
                           EntryOrderState.tp_trigger is None, we can
                           derive a TP trigger as (avg_price + min_tp_increment).
        max_tp_price     : Cap TP price to avoid hitting exchange bounds
                           (e.g. 0.99).
        prefer_sl        : If both TP and SL are technically triggered at
                           the same time, SL will win if this is True.
        eps_pos          : Position epsilon below which we treat pos as 0.
    """

    sl_order_price: float = 0.01
    min_tp_increment: float = 0.01
    max_tp_price: float = 0.99
    prefer_sl: bool = True
    eps_pos: float = 1e-9


# Order statuses that are considered "live" on the book
LIVE_ORDER_STATUSES = {ORDER_STATUS_OPEN, ORDER_STATUS_PART_FILLED}


# ---------------------------------------------------------------------------
# StrategyExit engine
# ---------------------------------------------------------------------------

class StrategyExit:
    """
    Stateless (apart from config) exit decision engine.

    Typical usage in your main loop:

        exit_engine = StrategyExit(ExitConfig(...))

        for entry in entry_manager.all_entries():
            decision = exit_engine.evaluate_entry(
                entry=entry,
                state=account_state,
                bid=current_bid,
                ask=current_ask,
            )
            if decision is None:
                continue

            # 1) actually place the REST order via PolymarketClient
            resp = poly.place_limit(
                token_id=...,
                side=decision.side,
                price=decision.price,
                size=decision.size,
                order_type="GTC",
            )

            # 2) register & attach order (example):
            order_id = resp.get("orderId") or resp.get("orderID")
            account_state.register_local_order(
                order_id=order_id,
                market_id=entry.market_id,
                outcome=entry.outcome,
                side=decision.side,
                price=decision.price,
                size=decision.size,
                is_exit=True,
                strategy_tag="your_strategy_name",
            )
            entry_manager.attach_exit_order(
                entry_id=entry.entry_id,
                order_id=order_id,
                kind=decision.kind,
            )
    """

    def __init__(self, config: Optional[ExitConfig] = None):
        self.config = config or ExitConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_entry(
        self,
        *,
        entry: EntryOrderState,
        state: AccountState,
        bid: float,
        ask: float,
        now_ts: Optional[float] = None,
    ) -> Optional[ExitDecision]:
        """
        Given a single EntryOrderState + current prices, decide whether
        to place a TP or SL order.

        Returns:
            ExitDecision or None (if no action should be taken now).
        """
        if now_ts is None:
            now_ts = time.time()

        # 1) Basic guards: status & position
        if entry.status in (
            "DONE",
            "CANCELED",
            "ERROR",
        ):
            # Strategy already considers this entry finished / unusable
            return None

        # Make sure we have up-to-date pos/avg_price from AccountState
        # (caller can also periodically call entry.update_from_account_state())
        entry.update_from_account_state(now_ts, state)

        stats = state.get_onchain_stats(entry.market_id, entry.outcome)
        pos = stats["pos"]
        avg_price = stats["avg_price"]

        if abs(pos) < self.config.eps_pos:
            # No on-chain position -> nothing to exit
            return None

        # Not enough size to bother exiting
        if abs(pos) < entry.min_exit_size:
            return None

        # Still within cooldown window -> do not exit yet
        if entry.is_in_cooldown(now_ts):
            return None

        # If there are already live exit orders bound to this entry,
        # we generally don't want to spam more exit orders.
        if self._has_live_exit_orders(entry, state):
            return None

        # 2) Decide whether SL or TP should trigger at current prices.
        # For a long (BUY) entry we usually look at bid.
        # For a short (SELL) entry we usually look at ask.
        ref_price = self._reference_price_for_exit(entry, bid=bid, ask=ask)

        # If ref_price is invalid (e.g. no bid/ask), do nothing
        if ref_price is None or ref_price <= 0:
            return None

        # Determine which side we should trade to EXIT:
        #   - If entry is BUY (long), exit is SELL
        #   - If entry is SELL (short), exit is BUY
        exit_side = SIDE_SELL if entry.side == SIDE_BUY else SIDE_BUY
        exit_size = abs(pos)

        # 3) Check SL / TP triggers
        sl_triggered, sl_price = self._check_sl_trigger(entry, ref_price, exit_side)
        tp_triggered, tp_price = self._check_tp_trigger(entry, ref_price, avg_price, exit_side)

        if not sl_triggered and not tp_triggered:
            return None

        # 4) If both triggered, resolve conflict (usually prefer SL for risk)
        if sl_triggered and tp_triggered:
            if self.config.prefer_sl:
                tp_triggered = False
            else:
                sl_triggered = False

        if sl_triggered:
            return ExitDecision(
                entry_id=entry.entry_id,
                kind="SL",
                side=exit_side,
                size=exit_size,
                price=sl_price,
                reason=f"SL_TRIGGER ref_price={ref_price:.4f} <= sl_level",
            )

        if tp_triggered:
            return ExitDecision(
                entry_id=entry.entry_id,
                kind="TP",
                side=exit_side,
                size=exit_size,
                price=tp_price,
                reason=f"TP_TRIGGER ref_price={ref_price:.4f} >= tp_level",
            )

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_live_exit_orders(self, entry: EntryOrderState, state: AccountState) -> bool:
        """
        True if this entry already has any exit orders (TP/SL) that are
        still live on the book (OPEN / PART_FILLED with size_unmatched > 0).
        """
        for oid in entry.exit_tp_order_ids + entry.exit_sl_order_ids:
            o = state.orders.get(oid)
            if not o:
                continue
            if o.order_status in LIVE_ORDER_STATUSES and o.size_unmatched > 0.0:
                return True
        return False

    @staticmethod
    def _reference_price_for_exit(
        entry: EntryOrderState,
        *,
        bid: float,
        ask: float,
    ) -> Optional[float]:
        """
        Decide which price we use for exit decisions.

        - For a long (BUY) entry we usually compare with *bid*.
        - For a short (SELL) entry we usually compare with *ask*.

        If the corresponding side is <= 0, we return None.
        """
        if entry.side == SIDE_BUY:
            return bid if bid and bid > 0 else None
        else:
            return ask if ask and ask > 0 else None

    def _check_sl_trigger(
        self,
        entry: EntryOrderState,
        ref_price: float,
        exit_side: str,
    ) -> tuple[bool, float]:
        """
        Check whether stop-loss should trigger.

        The trigger *level* is taken from entry.sl_trigger if present.
        If not present, you can either:
            - set entry.sl_trigger elsewhere in your strategy, OR
            - treat it as "no SL" from this engine.

        For a long (BUY) entry:
            - typical logic: SL triggers when ref_price <= sl_level.
            - order price for SL is self.config.sl_order_price (taker style).

        For a short (SELL) entry:
            - symmetric logic: SL triggers when ref_price >= sl_level.
        """
        if entry.sl_trigger is None:
            return False, 0.0

        sl_level = float(entry.sl_trigger)
        sl_order_px = float(self.config.sl_order_price)

        if entry.side == SIDE_BUY:
            # Long: price going DOWN triggers SL
            triggered = ref_price <= sl_level
        else:
            # Short: price going UP triggers SL
            triggered = ref_price >= sl_level

        if not triggered:
            return False, 0.0

        # We use a fixed SL order price (e.g. 0.01 for long or very aggressive for short).
        # If you want asymmetry for short, you can extend this logic later.
        return True, sl_order_px

    def _check_tp_trigger(
        self,
        entry: EntryOrderState,
        ref_price: float,
        avg_price: float,
        exit_side: str,
    ) -> tuple[bool, float]:
        """
        Check whether take-profit should trigger.

        TP trigger level:
            - If entry.tp_trigger is set: use that as the trigger level.
            - Else: derive a default from avg_price + min_tp_increment
              (for long) or avg_price - min_tp_increment (for short).

        For a long (BUY) entry:
            - TP triggers when ref_price >= tp_level.

        For a short (SELL) entry:
            - TP triggers when ref_price <= tp_level.

        TP order price:
            - For a long we usually place at min(ref_price, max_tp_price).
            - For a short we usually place at max(ref_price, 1 - max_tp_price)
              or some symmetric logic (kept simple here: also capped by max_tp_price).
        """
        # If avg_price is invalid and tp_trigger is not set, we cannot build a sensible TP
        if avg_price <= 0 and entry.tp_trigger is None:
            return False, 0.0

        # Determine trigger level
        if entry.tp_trigger is not None:
            tp_level = float(entry.tp_trigger)
        else:
            # Derive from avg_price and config
            if entry.side == SIDE_BUY:
                tp_level = avg_price + self.config.min_tp_increment
            else:
                tp_level = avg_price - self.config.min_tp_increment

        max_tp_px = float(self.config.max_tp_price)

        if entry.side == SIDE_BUY:
            # Long: price going UP triggers TP
            triggered = ref_price >= tp_level
            tp_price = min(ref_price, max_tp_px)
        else:
            # Short: price going DOWN triggers TP
            triggered = ref_price <= tp_level
            # For simplicity we also cap absolute price at max_tp_price on the "profitable side".
            # You can customize this if you have more complex bounds for < 0.5, etc.
            tp_price = max(ref_price, 1.0 - max_tp_px)  # simple symmetric cap

        if not triggered:
            return False, 0.0

        return True, tp_price