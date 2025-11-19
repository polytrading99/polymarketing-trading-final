from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.utils import decimal_to_float
from app.database.models import Market, MetricSnapshot, Position
from app.database.session import get_session

router = APIRouter()


class MarketPnLSummary(BaseModel):
    market_id: str
    condition_id: str
    question: str
    pnl_total: float
    pnl_realized: float
    pnl_unrealized: float
    inventory_value: float
    fees_paid: float
    position_count: int
    last_updated: Optional[str]


@router.get("/market/{market_id}", response_model=MarketPnLSummary, summary="Get PnL summary for a market")
async def get_market_pnl(market_id: UUID) -> MarketPnLSummary:
    """Get aggregated PnL and performance metrics for a specific market."""
    async with get_session() as session:
        market = await session.get(Market, market_id)
        
        if market is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
        
        # Get latest metrics snapshot
        latest_snapshot = await session.scalar(
            select(MetricSnapshot)
            .where(MetricSnapshot.market_id == market_id)
            .order_by(MetricSnapshot.timestamp.desc())
            .limit(1)
        )
        
        # Get position count
        position_count = await session.scalar(
            select(func.count(Position.id))
            .where(Position.market_id == market_id)
        ) or 0
        
        # Calculate aggregated values from positions if no snapshot
        if latest_snapshot:
            pnl_total = decimal_to_float(latest_snapshot.pnl_total) or 0.0
            pnl_realized = decimal_to_float(latest_snapshot.pnl_realized) or 0.0
            pnl_unrealized = decimal_to_float(latest_snapshot.pnl_unrealized) or 0.0
            inventory_value = decimal_to_float(latest_snapshot.inventory_value) or 0.0
            fees_paid = decimal_to_float(latest_snapshot.fees_paid) or 0.0
            last_updated = latest_snapshot.timestamp.isoformat()
        else:
            # Aggregate from positions
            positions = (await session.scalars(
                select(Position).where(Position.market_id == market_id)
            )).all()
            
            pnl_total = sum(decimal_to_float(p.unrealized_pnl) or 0.0 for p in positions)
            pnl_realized = 0.0  # Would need trade history to calculate
            pnl_unrealized = pnl_total
            inventory_value = sum(
                (decimal_to_float(p.size) or 0.0) * (decimal_to_float(p.avg_price) or 0.0)
                for p in positions
            )
            fees_paid = sum(decimal_to_float(p.fees_paid) or 0.0 for p in positions)
            last_updated = None
        
        return MarketPnLSummary(
            market_id=str(market_id),
            condition_id=market.condition_id,
            question=market.question,
            pnl_total=pnl_total,
            pnl_realized=pnl_realized,
            pnl_unrealized=pnl_unrealized,
            inventory_value=inventory_value,
            fees_paid=fees_paid,
            position_count=position_count,
            last_updated=last_updated,
        )


@router.get("", response_model=list[MarketPnLSummary], summary="Get PnL summary for all markets")
async def get_all_markets_pnl(
    min_pnl: Optional[float] = Query(default=None, description="Filter by minimum total PnL"),
    max_pnl: Optional[float] = Query(default=None, description="Filter by maximum total PnL"),
) -> list[MarketPnLSummary]:
    """Get aggregated PnL for all markets, optionally filtered by PnL range."""
    async with get_session() as session:
        markets = (await session.scalars(select(Market))).all()
        
        summaries = []
        for market in markets:
            # Get latest snapshot
            latest_snapshot = await session.scalar(
                select(MetricSnapshot)
                .where(MetricSnapshot.market_id == market.id)
                .order_by(MetricSnapshot.timestamp.desc())
                .limit(1)
            )
            
            position_count = await session.scalar(
                select(func.count(Position.id))
                .where(Position.market_id == market.id)
            ) or 0
            
            if latest_snapshot:
                pnl_total = decimal_to_float(latest_snapshot.pnl_total) or 0.0
                pnl_realized = decimal_to_float(latest_snapshot.pnl_realized) or 0.0
                pnl_unrealized = decimal_to_float(latest_snapshot.pnl_unrealized) or 0.0
                inventory_value = decimal_to_float(latest_snapshot.inventory_value) or 0.0
                fees_paid = decimal_to_float(latest_snapshot.fees_paid) or 0.0
                last_updated = latest_snapshot.timestamp.isoformat()
            else:
                positions = (await session.scalars(
                    select(Position).where(Position.market_id == market.id)
                )).all()
                
                pnl_total = sum(decimal_to_float(p.unrealized_pnl) or 0.0 for p in positions)
                pnl_realized = 0.0
                pnl_unrealized = pnl_total
                inventory_value = sum(
                    (decimal_to_float(p.size) or 0.0) * (decimal_to_float(p.avg_price) or 0.0)
                    for p in positions
                )
                fees_paid = sum(decimal_to_float(p.fees_paid) or 0.0 for p in positions)
                last_updated = None
            
            # Apply filters
            if min_pnl is not None and pnl_total < min_pnl:
                continue
            if max_pnl is not None and pnl_total > max_pnl:
                continue
            
            summaries.append(
                MarketPnLSummary(
                    market_id=str(market.id),
                    condition_id=market.condition_id,
                    question=market.question,
                    pnl_total=pnl_total,
                    pnl_realized=pnl_realized,
                    pnl_unrealized=pnl_unrealized,
                    inventory_value=inventory_value,
                    fees_paid=fees_paid,
                    position_count=position_count,
                    last_updated=last_updated,
                )
            )
        
        return summaries

