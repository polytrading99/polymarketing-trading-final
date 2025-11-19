from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.database.models import Market, Order, OrderSide, OrderStatus, Position
from app.database.session import get_session
from app.metrics import registry as metrics_registry

ORDER_STATUS_MAP = {
    "OPEN": OrderStatus.OPEN,
    "PARTIAL": OrderStatus.PARTIAL,
    "PARTIALLY_FILLED": OrderStatus.PARTIAL,
    "MATCHED": OrderStatus.PARTIAL,
    "FILLED": OrderStatus.FILLED,
    "MINED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.FAILED,
    "REJECTED": OrderStatus.FAILED,
}

ORDER_SIDE_MAP = {
    "BUY": OrderSide.BUY,
    "SELL": OrderSide.SELL,
}


def _schedule(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)


def _to_decimal(value: Optional[float], default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return default


def persist_order_event(event: Dict[str, Any]) -> None:
    _schedule(_persist_order_event(event))


def persist_position_state(condition_id: str, token_id: str, size: float, avg_price: float) -> None:
    _schedule(_persist_position_state(condition_id, token_id, size, avg_price))


async def _persist_order_event(event: Dict[str, Any]) -> None:
    condition_id = str(event.get("market"))
    order_id = str(event.get("id"))
    if not condition_id or not order_id:
        return

    side_raw = str(event.get("side", "")).upper()
    status_raw = str(event.get("status", "")).upper()

    async with get_session() as session:
        market = await session.scalar(select(Market).where(Market.condition_id == condition_id))
        if market is None:
            return

        order = await session.scalar(
            select(Order).where(Order.exchange_order_id == order_id)
        )

        side = ORDER_SIDE_MAP.get(side_raw, OrderSide.BUY)
        status = ORDER_STATUS_MAP.get(status_raw, OrderStatus.OPEN)

        if order is None:
            price = _to_decimal(event.get("price"), Decimal("0")) or Decimal("0")
            original_size = _to_decimal(event.get("original_size"), Decimal("0")) or Decimal("0")
            matched = _to_decimal(event.get("size_matched"), Decimal("0")) or Decimal("0")

            order = Order(
                market_id=market.id,
                exchange_order_id=order_id,
                token_id=str(event.get("asset_id")),
                side=side,
                price=price,
                size=original_size,
                filled_size=matched,
                status=status,
            )
            session.add(order)
        else:
            price = _to_decimal(event.get("price"), order.price)
            original_size = _to_decimal(event.get("original_size"), order.size)
            matched = _to_decimal(event.get("size_matched"), order.filled_size)

            order.token_id = str(event.get("asset_id")) or order.token_id
            order.side = side
            order.price = price if price is not None else order.price
            order.size = original_size if original_size is not None else order.size
            order.filled_size = matched if matched is not None else order.filled_size
            order.status = status

        if metrics_registry.order_gauge is not None:
            metrics_registry.order_gauge.labels(
                market=market.condition_id,
                token=order.token_id,
                side=order.side.value,
            ).set(float(max(Decimal("0"), order.size - order.filled_size)))


async def _persist_position_state(condition_id: str, token_id: str, size: float, avg_price: float) -> None:
    async with get_session() as session:
        market = await session.scalar(select(Market).where(Market.condition_id == condition_id))
        if market is None:
            return

        position = await session.scalar(
            select(Position).where(
                Position.market_id == market.id,
                Position.token_id == str(token_id),
            )
        )

        if position is None:
            position = Position(
                market_id=market.id,
                token_id=str(token_id),
                size=_to_decimal(size, Decimal("0")) or Decimal("0"),
                avg_price=_to_decimal(avg_price, Decimal("0")) or Decimal("0"),
            )
            session.add(position)
        else:
            new_size = _to_decimal(size, position.size) or position.size
            new_avg = _to_decimal(avg_price, position.avg_price) or position.avg_price
            position.size = new_size
            position.avg_price = new_avg

        if metrics_registry.position_gauge is not None:
            metrics_registry.position_gauge.labels(
                market=market.condition_id,
                token=position.token_id,
            ).set(float(position.size))


