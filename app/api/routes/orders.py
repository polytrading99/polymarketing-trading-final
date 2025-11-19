from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.api.utils import decimal_to_float
from app.database.models import Market, Order, OrderStatus
from app.database.session import get_session

router = APIRouter()


class OrderSummary(BaseModel):
    id: str
    exchange_order_id: Optional[str] = None
    market_id: str
    condition_id: str
    token_id: str
    side: str
    price: Optional[float]
    size: Optional[float]
    filled_size: Optional[float]
    status: str


async def _build_order_query(
    market_id: Optional[UUID] = None,
    condition_id: Optional[str] = None,
    status_filter: Optional[list[OrderStatus]] = None,
) -> Select:
    stmt = (
        select(Order)
        .options(selectinload(Order.market))
        .order_by(Order.created_at.desc())
    )

    if market_id:
        stmt = stmt.where(Order.market_id == market_id)
    if condition_id:
        stmt = stmt.join(Market).where(Market.condition_id == condition_id)
    if status_filter:
        stmt = stmt.where(Order.status.in_(status_filter))

    return stmt.limit(200)


async def _fetch_orders(
    market_id: Optional[UUID],
    condition_id: Optional[str],
    status_filter: Optional[list[OrderStatus]],
) -> list[OrderSummary]:
    stmt = await _build_order_query(market_id, condition_id, status_filter)
    async with get_session() as session:
        orders = (await session.scalars(stmt)).all()

    summaries: list[OrderSummary] = []
    for order in orders:
        market = order.market
        if market is None:
            continue
        summaries.append(
            OrderSummary(
                id=str(order.id),
                exchange_order_id=order.exchange_order_id,
                market_id=str(order.market_id),
                condition_id=market.condition_id,
                token_id=order.token_id,
                side=order.side.value,
                price=decimal_to_float(order.price),
                size=decimal_to_float(order.size),
                filled_size=decimal_to_float(order.filled_size),
                status=order.status.value,
            )
        )
    return summaries


@router.get("", response_model=list[OrderSummary], summary="List recent orders")
async def list_orders(
    market_id: Optional[UUID] = Query(default=None, description="Market UUID"),
    condition_id: Optional[str] = Query(default=None, description="Polymarket condition id"),
    status: Optional[list[OrderStatus]] = Query(default=None),
) -> list[OrderSummary]:
    status_filter = list(status) if status else None
    return await _fetch_orders(market_id, condition_id, status_filter)


@router.get(
    "/market/{market_id}",
    response_model=list[OrderSummary],
    summary="List orders for a market",
)
async def list_orders_for_market(market_id: UUID) -> list[OrderSummary]:
    return await _fetch_orders(market_id, None, None)


@router.get(
    "/condition/{condition_id}",
    response_model=list[OrderSummary],
    summary="List orders for a condition id",
)
async def list_orders_for_condition(condition_id: str) -> list[OrderSummary]:
    return await _fetch_orders(None, condition_id, None)


@router.get(
    "/{order_id}",
    response_model=OrderSummary,
    summary="Get order details",
)
async def get_order(order_id: UUID) -> OrderSummary:
    async with get_session() as session:
        order = await session.get(Order, order_id, options=[selectinload(Order.market)])

    if order is None or order.market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return OrderSummary(
        id=str(order.id),
        exchange_order_id=order.exchange_order_id,
        market_id=str(order.market_id),
        condition_id=order.market.condition_id,
        token_id=order.token_id,
        side=order.side.value,
        price=decimal_to_float(order.price),
        size=decimal_to_float(order.size),
        filled_size=decimal_to_float(order.filled_size),
        status=order.status.value,
    )

