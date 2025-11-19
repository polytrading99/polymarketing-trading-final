from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.api.utils import decimal_to_float
from app.database.models import Market, Position
from app.database.session import get_session

router = APIRouter()


class PositionSummary(BaseModel):
    id: str
    market_id: str
    condition_id: str
    token_id: str
    size: float
    avg_price: float
    unrealized_pnl: float
    fees_paid: float


async def _build_position_query(
    market_id: Optional[UUID],
    condition_id: Optional[str],
) -> Select:
    stmt = (
        select(Position)
        .options(selectinload(Position.market))
        .order_by(Position.updated_at.desc())
    )

    if market_id:
        stmt = stmt.where(Position.market_id == market_id)
    if condition_id:
        stmt = stmt.join(Market).where(Market.condition_id == condition_id)

    return stmt


async def _fetch_positions(
    market_id: Optional[UUID],
    condition_id: Optional[str],
) -> list[PositionSummary]:
    stmt = await _build_position_query(market_id, condition_id)
    async with get_session() as session:
        positions = (await session.scalars(stmt)).all()

    summaries: list[PositionSummary] = []
    for position in positions:
        market = position.market
        if market is None:
            continue
        summaries.append(
            PositionSummary(
                id=str(position.id),
                market_id=str(position.market_id),
                condition_id=market.condition_id,
                token_id=position.token_id,
                size=decimal_to_float(position.size) or 0.0,
                avg_price=decimal_to_float(position.avg_price) or 0.0,
                unrealized_pnl=decimal_to_float(position.unrealized_pnl) or 0.0,
                fees_paid=decimal_to_float(position.fees_paid) or 0.0,
            )
        )
    return summaries


@router.get("", response_model=list[PositionSummary], summary="List positions")
async def list_positions(
    market_id: Optional[UUID] = Query(default=None),
    condition_id: Optional[str] = Query(default=None),
) -> list[PositionSummary]:
    return await _fetch_positions(market_id, condition_id)


@router.get(
    "/market/{market_id}",
    response_model=list[PositionSummary],
    summary="List positions for a market",
)
async def list_positions_for_market(market_id: UUID) -> list[PositionSummary]:
    return await _fetch_positions(market_id, None)


@router.get(
    "/condition/{condition_id}",
    response_model=list[PositionSummary],
    summary="List positions for a condition id",
)
async def list_positions_for_condition(condition_id: str) -> list[PositionSummary]:
    return await _fetch_positions(None, condition_id)


@router.get(
    "/{position_id}",
    response_model=PositionSummary,
    summary="Get position details",
)
async def get_position(position_id: UUID) -> PositionSummary:
    async with get_session() as session:
        position = await session.get(Position, position_id, options=[selectinload(Position.market)])

    if position is None or position.market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    return PositionSummary(
        id=str(position.id),
        market_id=str(position.market_id),
        condition_id=position.market.condition_id,
        token_id=position.token_id,
        size=decimal_to_float(position.size) or 0.0,
        avg_price=decimal_to_float(position.avg_price) or 0.0,
        unrealized_pnl=decimal_to_float(position.unrealized_pnl) or 0.0,
        fees_paid=decimal_to_float(position.fees_paid) or 0.0,
    )

