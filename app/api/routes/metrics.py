from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.utils import decimal_to_float
from app.database.models import Market, MetricSnapshot
from app.database.session import get_session

router = APIRouter()


class MetricSummary(BaseModel):
    id: str
    market_id: str
    condition_id: str
    timestamp: datetime
    pnl_total: Optional[float]
    pnl_unrealized: Optional[float]
    pnl_realized: Optional[float]
    inventory_value: Optional[float]
    fees_paid: Optional[float]
    extra: dict


@router.get(
    "/market/{market_id}/latest",
    response_model=MetricSummary,
    summary="Get latest metrics for a market",
)
async def latest_metrics_for_market(market_id: UUID) -> MetricSummary:
    async with get_session() as session:
        snapshot = await session.scalar(
            select(MetricSnapshot)
            .where(MetricSnapshot.market_id == market_id)
            .order_by(MetricSnapshot.timestamp.desc())
            .limit(1)
        )

        market = await session.get(Market, market_id) if snapshot else None

    if snapshot is None or market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics not found")

    return MetricSummary(
        id=str(snapshot.id),
        market_id=str(snapshot.market_id),
        condition_id=market.condition_id,
        timestamp=snapshot.timestamp,
        pnl_total=decimal_to_float(snapshot.pnl_total),
        pnl_unrealized=decimal_to_float(snapshot.pnl_unrealized),
        pnl_realized=decimal_to_float(snapshot.pnl_realized),
        inventory_value=decimal_to_float(snapshot.inventory_value),
        fees_paid=decimal_to_float(snapshot.fees_paid),
        extra=snapshot.extra or {},
    )


@router.get(
    "/condition/{condition_id}/latest",
    response_model=MetricSummary,
    summary="Get latest metrics for a condition id",
)
async def latest_metrics_for_condition(condition_id: str) -> MetricSummary:
    async with get_session() as session:
        market = await session.scalar(
            select(Market).where(Market.condition_id == condition_id).limit(1)
        )
        if market is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")

        snapshot = await session.scalar(
            select(MetricSnapshot)
            .where(MetricSnapshot.market_id == market.id)
            .order_by(MetricSnapshot.timestamp.desc())
            .limit(1)
        )

    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics not found")

    return MetricSummary(
        id=str(snapshot.id),
        market_id=str(snapshot.market_id),
        condition_id=condition_id,
        timestamp=snapshot.timestamp,
        pnl_total=decimal_to_float(snapshot.pnl_total),
        pnl_unrealized=decimal_to_float(snapshot.pnl_unrealized),
        pnl_realized=decimal_to_float(snapshot.pnl_realized),
        inventory_value=decimal_to_float(snapshot.inventory_value),
        fees_paid=decimal_to_float(snapshot.fees_paid),
        extra=snapshot.extra or {},
    )

