# strategy_entry.py
# -*- coding: utf-8 -*-
"""
Strategy-level entry & exit state machine.

This module sits *on top of* AccountState:

- AccountState:
    - Knows all orders (SuperOrder)
    - Knows all trades
    - Can answer "what is my risk/on-chain position for (market, outcome)?"

- StrategyEntryManager / EntryOrderState:
    - Adds strategy semantics on top of that, for each *entry idea*:
        * When was this entry first/last filled?
        * When does cooldown end?
        * Has TP/SL been placed?
        * Is this entry fully closed from a strategy perspective?

Typical usage pattern:

1) When strategy decides to open a new entry:
    - Place a BUY via REST (using PolymarketClient).
    - Call `account_state.register_local_order(...)` so AccountState knows this order.
    - Call `entry_mgr.create_entry(...)` to create a new EntryOrderState.
    - Call `entry_mgr.attach_entry_order(entry_id, order_id)` to bind that REST order
      to this logical entry.

2) For every WS trade message:
    - First call `account_state.handle_trade_message(msg)` (to update orders & positions).
    - Then call `entry_mgr.on_trade_message(msg, account_state)` so entries can update
      their fill timestamps, cooldown, etc.

3) In the strategy main loop:
    - For each active entry, call:
        entry.update_from_account_state(now_ts, account_state)
      to sync size/avgPrice/cooldown readiness from AccountState.

    - Use helper predicates:
        * entry.is_in_cooldown(now_ts)
        * entry.is_ready_to_exit(now_ts)
        * entry.is_fully_closed(account_state)
      to decide whether to place TP/SL / clean up.

This module does NOT talk to Polymarket REST or WS by itself.
It only holds metadata and provides helper methods for the strategy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from state_machine import AccountState
from state_machine.enums import (
    SIDE_BUY,
    SIDE_SELL,
)


# ---------------------------------------------------------------------------
# Entry / Exit status enums (simple strings for now)
# ---------------------------------------------------------------------------

ENTRY_STATUS_NEW = "NEW"                  # Just created, no orders attached yet
ENTRY_STATUS_WAIT_ENTRY_FILLS = "WAIT_ENTRY_FILLS"  # Entry orders live / being filled
ENTRY_STATUS_COOLING = "COOLING"          # Filled, but still in cooldown window
ENTRY_STATUS_READY = "READY"              # Okay to manage exit (TP/SL)
ENTRY_STATUS_EXIT_PLACED = "EXIT_PLACED"  # Some exit order(s) placed
ENTRY_STATUS_DONE = "DONE"                # Fully closed (strategy perspective)
ENTRY_STATUS_CANCELED = "CANCELED"        # Strategy decided to abandon this entry
ENTRY_STATUS_ERROR = "ERROR"              # Some unrecoverable error / inconsistent state

EXIT_KIND_TP = "TP"
EXIT_KIND_SL = "SL"


# ---------------------------------------------------------------------------
# EntryOrderState
# ---------------------------------------------------------------------------

@dataclass
class EntryOrderState:
    """
    Strategy-level tracking for a single logical "entry".

    One logical entry can be backed by:
    - one or more REST orders (for example: initial order + re-quotes)
    - one or more exit orders (TP / SL)

    We do NOT duplicate low-level info like size or avg price.
    Those are always derived from AccountState + list of order_ids.
    """

    # Identity / routing
    entry_id: int
    market_id: str
    outcome: str
    side: str = SIDE_BUY             # Usually LONG (BUY) in your MM, but kept generic
    leg_label: Optional[str] = None  # e.g. "YES" / "NO" if useful for logging

    # Strategy parameters
    target_size: float = 0.0         # Intended total size (for reference)
    cooldown_sec: float = 5.0        # Cooling period after (last) fill before we may exit
    min_exit_size: float = 1.0       # Minimal size to bother placing exit orders
    sl_trigger: Optional[float] = None   # Stop-loss trigger price (strategy-level)
    tp_trigger: Optional[float] = None   # Optional take-profit trigger level (not required)

    # Bound order ids
    entry_order_ids: List[str] = field(default_factory=list)
    exit_tp_order_ids: List[str] = field(default_factory=list)
    exit_sl_order_ids: List[str] = field(default_factory=list)

    # Fill / timing info (strategy-level)
    first_fill_ts: Optional[float] = None
    last_fill_ts: Optional[float] = None
    cooldown_until: Optional[float] = None

    # Bookkeeping
    status: str = ENTRY_STATUS_NEW
    error_msg: Optional[str] = None
    strategy_tag: str = ""              # For logging / metrics (e.g. "time_bucket_v2")

    # Cached aggregates (for convenience; always recomputed from AccountState)
    last_known_pos: float = 0.0
    last_known_avg_price: float = 0.0

    # ---------------------------------------------------------------------
    # Helpers: binding orders
    # ---------------------------------------------------------------------

    def attach_entry_order(self, order_id: str) -> None:
        """
        Attach a new entry order_id to this logical entry.
        You should call this right after placing a REST entry order.
        """
        if order_id not in self.entry_order_ids:
            self.entry_order_ids.append(order_id)
        if self.status == ENTRY_STATUS_NEW:
            self.status = ENTRY_STATUS_WAIT_ENTRY_FILLS

    def attach_exit_order(self, order_id: str, kind: str) -> None:
        """
        Attach an exit order_id:
            kind == "TP" -> exit_tp_order_ids
            kind == "SL" -> exit_sl_order_ids
        """
        if kind == EXIT_KIND_TP:
            if order_id not in self.exit_tp_order_ids:
                self.exit_tp_order_ids.append(order_id)
        elif kind == EXIT_KIND_SL:
            if order_id not in self.exit_sl_order_ids:
                self.exit_sl_order_ids.append(order_id)
        else:
            # Unknown type, just stash it into TP bucket
            if order_id not in self.exit_tp_order_ids:
                self.exit_tp_order_ids.append(order_id)

        # If we are ready, move to EXIT_PLACED
        if self.status in (ENTRY_STATUS_READY, ENTRY_STATUS_COOLING, ENTRY_STATUS_WAIT_ENTRY_FILLS):
            self.status = ENTRY_STATUS_EXIT_PLACED

    # ---------------------------------------------------------------------
    # Fill / cooldown logic
    # ---------------------------------------------------------------------

    def on_fill(self, fill_ts: float) -> None:
        """
        Called by the manager when a trade related to this entry is detected.
        It only records timestamps; size/avg_price are computed via AccountState.
        """
        if self.first_fill_ts is None:
            self.first_fill_ts = fill_ts
        self.last_fill_ts = fill_ts
        self.cooldown_until = fill_ts + self.cooldown_sec

        # If we were still waiting, move into COOLING
        if self.status in (ENTRY_STATUS_NEW, ENTRY_STATUS_WAIT_ENTRY_FILLS):
            self.status = ENTRY_STATUS_COOLING

    def is_in_cooldown(self, now_ts: float) -> bool:
        """
        True if this entry is still in cooldown window (has fills, but cooldown not over).
        """
        if self.cooldown_until is None:
            return False
        return now_ts < self.cooldown_until

    def is_ready_to_exit(self, now_ts: float) -> bool:
        """
        Whether we are allowed to start exit logic.

        Conditions:
        - No error_msg
        - Current position >= min_exit_size
        - We have had at least one fill (first_fill_ts is not None)
        - Cooldown is over (now_ts >= cooldown_until)
        """
        if self.error_msg:
            return False

        # Position too small, no need to exit
        if abs(self.last_known_pos) < self.min_exit_size:
            return False

        # Never actually filled
        if self.first_fill_ts is None:
            return False

        # If cooldown_until is not set, treat it as already cooled down
        if self.cooldown_until is None:
            return True

        if now_ts < self.cooldown_until:
            return False

        # Optionally require status == READY
        return self.status == ENTRY_STATUS_READY

    # ---------------------------------------------------------------------
    # Integration with AccountState
    # ---------------------------------------------------------------------

    def _aggregate_entry_pos_from_orders(self, state: AccountState) -> float:
        """
        Sum of size_matched across all entry_order_ids, using SuperOrder.
        This is a *risk* perspective (not strictly on-chain).
        """
        total = 0.0
        for oid in self.entry_order_ids:
            o = state.orders.get(oid)
            if not o:
                continue
            # signed by side
            sign = 1.0 if o.side == SIDE_BUY else -1.0
            total += sign * o.size_matched
        return total

    def update_from_account_state(self, now_ts: float, state: "AccountState") -> None:
        """
        Refresh this entry from AccountState:

        - last_known_pos / last_known_avg_price
        - status (WAIT_ENTRY_FILLS / COOLING / READY / DONE)
        - cooldown_until

        Convention:
        - No fills, but there are live orders / positions -> WAIT_ENTRY_FILLS
        - Has position and in cooldown -> COOLING
        - Has position and cooldown finished -> READY
        - Position == 0 and there has been at least one fill -> DONE
        """

        key = (self.market_id, self.outcome)

        # 1) Refresh position
        try:
            pos = float(state.position_risk.get(key, 0.0) or 0.0)
        except Exception:
            pos = 0.0
        self.last_known_pos = pos

        # 2) Refresh avg price (if available)
        avg = 0.0
        if hasattr(state, "position_avg"):
            try:
                avg = float(state.position_avg.get(key, 0.0) or 0.0)
            except Exception:
                avg = 0.0
        self.last_known_avg_price = avg

        eps = 1e-9

        # ------------------------------------------------------------------
        # Phase A: no fills yet (first_fill_ts is None)
        # ------------------------------------------------------------------
        if self.first_fill_ts is None:
            # See if there are still live entry orders
            has_live_entry_order = False
            for oid in self.entry_order_ids:
                o = state.orders.get(oid)
                if not o:
                    continue
                st = (getattr(o, "order_status", "") or "").upper()
                # On Polymarket we currently see OPEN / FILLED
                # Treat OPEN / LIVE / PARTIALLY_FILLED as "alive"
                if st in ("OPEN", "LIVE", "PARTIALLY_FILLED"):
                    has_live_entry_order = True
                    break

            if has_live_entry_order or abs(pos) >= eps:
                # There are open orders or there is already a position
                # (for example synced from elsewhere) -> still waiting for fills
                self.status = "WAIT_ENTRY_FILLS"
            else:
                # No orders, no position, no fills yet: keep NEW
                # (or you can set it to DONE if you prefer)
                self.status = ENTRY_STATUS_NEW

            self.cooldown_until = None
            return

        # ------------------------------------------------------------------
        # Phase B: there has been at least one fill (first_fill_ts is not None)
        # ------------------------------------------------------------------

        # No position anymore -> consider the entry lifecycle finished
        if abs(pos) < eps:
            self.status = ENTRY_STATUS_DONE
            return

        # There is a position, ensure cooldown_until is set
        if self.cooldown_until is None:
            self.cooldown_until = self.first_fill_ts + self.cooldown_sec

        if now_ts < self.cooldown_until:
            self.status = ENTRY_STATUS_COOLING
        else:
            self.status = ENTRY_STATUS_READY

    def is_fully_closed(self, state: AccountState) -> bool:
        """
        True if on-chain pos is effectively 0 (with small epsilon).
        """
        stats = state.get_onchain_stats(self.market_id, self.outcome)
        return abs(stats["pos"]) < 1e-9

    def has_enough_size_for_exit(self, state: AccountState) -> bool:
        """
        True if absolute position size (on-chain) >= min_exit_size.
        """
        stats = state.get_onchain_stats(self.market_id, self.outcome)
        return abs(stats["pos"]) >= self.min_exit_size

    # ---------------------------------------------------------------------
    # Strategy-level mark helpers
    # ---------------------------------------------------------------------

    def mark_canceled(self, reason: str = "") -> None:
        self.status = ENTRY_STATUS_CANCELED
        if reason:
            self.error_msg = reason

    def mark_error(self, reason: str) -> None:
        self.status = ENTRY_STATUS_ERROR
        self.error_msg = reason


# ---------------------------------------------------------------------------
# EntryManager
# ---------------------------------------------------------------------------

class EntryManager:
    """
    Container / coordinator for multiple EntryOrderState instances.

    Responsibilities:
    - Provide unique entry_id values.
    - Maintain lookup from order_id -> entry_id, so we can route fills.
    - Expose helper methods to query active entries for a given (market, outcome).
    """

    def __init__(self):
        self._entries: Dict[int, EntryOrderState] = {}
        self._order_to_entry: Dict[str, int] = {}
        self._next_entry_id: int = 1

    # ---------------------------------------------------------------------
    # Entry lifecycle
    # ---------------------------------------------------------------------

    def create_entry(
        self,
        market_id: str,
        outcome: str,
        *,
        side: str = SIDE_BUY,
        leg_label: Optional[str] = None,
        target_size: float = 0.0,
        cooldown_sec: float = 5.0,
        min_exit_size: float = 1.0,
        sl_trigger: Optional[float] = None,
        tp_trigger: Optional[float] = None,
        strategy_tag: str = "",
    ) -> EntryOrderState:
        """
        Create a new logical entry and return it.
        You still need to attach actual order_ids via attach_entry_order().
        """
        entry_id = self._next_entry_id
        self._next_entry_id += 1

        entry = EntryOrderState(
            entry_id=entry_id,
            market_id=market_id,
            outcome=outcome,
            side=side,
            leg_label=leg_label,
            target_size=target_size,
            cooldown_sec=cooldown_sec,
            min_exit_size=min_exit_size,
            sl_trigger=sl_trigger,
            tp_trigger=tp_trigger,
            strategy_tag=strategy_tag,
        )
        self._entries[entry_id] = entry
        return entry

    def get_entry(self, entry_id: int) -> Optional[EntryOrderState]:
        return self._entries.get(entry_id)

    def all_entries(self) -> List[EntryOrderState]:
        return list(self._entries.values())

    # ---------------------------------------------------------------------
    # Order binding
    # ---------------------------------------------------------------------

    def attach_entry_order(self, entry_id: int, order_id: str) -> None:
        """
        Bind a REST entry order to an existing EntryOrderState.
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return
        entry.attach_entry_order(order_id)
        self._order_to_entry[order_id] = entry_id

    def attach_exit_order(self, entry_id: int, order_id: str, kind: str) -> None:
        """
        Bind a REST exit order (TP/SL) to an existing EntryOrderState.
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return
        entry.attach_exit_order(order_id, kind)
        self._order_to_entry[order_id] = entry_id

    # ---------------------------------------------------------------------
    # WS trade routing
    # ---------------------------------------------------------------------

    def on_trade_message(self, msg: dict, state: AccountState) -> None:
        """
        Use trade WS messages to update an entry's first_fill_ts / last_fill_ts / cooldown.

        Rules:
        - Only consider messages where event_type/type == "trade"
        - Only treat "real fills" as updates (e.g. match / success);
          mined / mined_* / failed / canceled / rejected are ignored
        - Only fills from entry orders affect cooldown:
          fills from exit orders do not change entry cooldown
        """

        etype = msg.get("event_type") or msg.get("type")
        if etype != "trade":
            return

        # ---- 1) Filter out trade statuses that do NOT count as “new fills” ----
        status_raw = str(msg.get("status", "") or "")
        status = status_raw.upper()

        # Explicitly ignored:
        if (
            "MINED" in status               # MINED / MINED_PENDING / MINED_CONFIRMED etc.
            or status in {"FAILED", "FAIL", "REJECTED", "CANCELLED", "CANCELED"}
        ):
            return

        # Other statuses (empty string, SUCCESS, MATCHED, FILLED, PARTIAL, etc.)
        # are treated as "there is a fill", and allowed to trigger on_fill.

        # ---- 2) Extract order_ids (only care about ones that exist in state.orders) ----
        order_ids: Set[str] = set()

        taker_id = msg.get("taker_order_id") or msg.get("takerOrderId")
        if isinstance(taker_id, str) and taker_id in state.orders:
            order_ids.add(taker_id)

        maker_orders = msg.get("maker_orders") or msg.get("makerOrders")
        if isinstance(maker_orders, list):
            for mo in maker_orders:
                if not isinstance(mo, dict):
                    continue
                moid = mo.get("order_id") or mo.get("orderID") or mo.get("id")
                if isinstance(moid, str) and moid in state.orders:
                    order_ids.add(moid)

        if not order_ids:
            return

        # ---- 3) Choose a reasonable timestamp for the fill ----
        ts = None
        for key in ("timestamp", "block_time", "time", "ts", "created_at"):
            v = msg.get(key)
            if isinstance(v, (int, float)):
                ts = float(v)
                # Guard against ms/us timestamps
                if ts > 1e12:   # very likely milliseconds
                    ts = ts / 1000.0
                break

        if ts is None:
            ts = time.time()

        # ---- 4) Dispatch the fill event to the corresponding Entry, but only
        #         allow entry orders to affect cooldown. Exit orders do not.
        touched_entry_ids: Set[int] = set()

        for oid in order_ids:
            entry_id = self._order_to_entry.get(oid)
            if entry_id is None:
                continue

            entry = self._entries.get(entry_id)
            if entry is None:
                continue

            # Only fills from entry orders update first/last_fill_ts and cooldown.
            # Fills from exit_tp_order_ids / exit_sl_order_ids do not affect cooldown.
            if oid not in entry.entry_order_ids:
                continue

            entry.on_fill(ts)
            touched_entry_ids.add(entry_id)

        if not touched_entry_ids:
            return

        # ---- 5) Refresh these entries from AccountState (pos / avg / cooldown) ----
        for eid in touched_entry_ids:
            entry = self._entries.get(eid)
            if entry is None:
                continue
            entry.update_from_account_state(now_ts=ts, state=state)

        # After updating fill times, we can also refresh each touched entry from AccountState
        # (but for simplicity, caller can also periodically call update_all_from_account_state)

    # ---------------------------------------------------------------------
    # Periodic maintenance
    # ---------------------------------------------------------------------

    def update_all_from_account_state(self, state: AccountState, now_ts: Optional[float] = None) -> None:
        """
        Periodically called by the strategy main loop to sync all entries from AccountState.
        """
        if now_ts is None:
            now_ts = time.time()
        for entry in self._entries.values():
            entry.update_from_account_state(now_ts, state)

    def get_active_entries_for_market(
        self,
        market_id: str,
        outcome: str,
        *,
        include_done: bool = False,
    ) -> List[EntryOrderState]:
        """
        Return active entries for a given (market, outcome).
        """
        res: List[EntryOrderState] = []
        for entry in self._entries.values():
            if entry.market_id != market_id or entry.outcome != outcome:
                continue
            if not include_done and entry.status in (ENTRY_STATUS_DONE, ENTRY_STATUS_CANCELED, ENTRY_STATUS_ERROR):
                continue
            res.append(entry)
        return res

    def cleanup_finished_entries(self) -> None:
        """
        Remove entries that are DONE / CANCELED / ERROR and no longer have any
        relevant orders bound, to avoid unbounded memory growth.

        This is optional; you may keep them forever if you want a full audit history.
        """
        to_delete: List[int] = []
        for entry_id, entry in self._entries.items():
            if entry.status not in (ENTRY_STATUS_DONE, ENTRY_STATUS_CANCELED, ENTRY_STATUS_ERROR):
                continue
            if entry.entry_order_ids or entry.exit_tp_order_ids or entry.exit_sl_order_ids:
                # If you want to be stricter, you can check that all these orders are
                # fully filled/canceled in AccountState before deleting.
                pass
            to_delete.append(entry_id)

        for entry_id in to_delete:
            # also remove from order -> entry mapping
            entry = self._entries.pop(entry_id, None)
            if not entry:
                continue
            for oid in entry.entry_order_ids + entry.exit_tp_order_ids + entry.exit_sl_order_ids:
                self._order_to_entry.pop(oid, None)