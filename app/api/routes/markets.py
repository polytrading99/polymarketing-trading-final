from typing import Optional, TYPE_CHECKING
import asyncio

from fastapi import APIRouter, HTTPException, Response, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.utils import decimal_to_float
from app.config import ConfigRepository
from app.database.models import Market, MetricSnapshot, Position
from app.database.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class MarketSummary(BaseModel):
    id: str
    condition_id: str
    question: str
    status: str
    neg_risk: bool
    token_yes: str
    token_no: str
    active_strategy: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    pnl_total: Optional[float] = None
    fees_paid: Optional[float] = None
    position_count: int = 0


class MarketUpdateRequest(BaseModel):
    status: Optional[str] = Field(default=None)
    activate_strategy: Optional[str] = Field(default=None)
    deactivate: bool = Field(default=False)


async def _summarize_market(market: Market, session: Optional["AsyncSession"] = None) -> MarketSummary:
    active_config = next((cfg for cfg in market.strategy_configs if cfg.is_active), None)
    
    # Get PnL data
    if session is None:
        async with get_session() as session:
            return await _summarize_market(market, session)
    
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
    
    pnl_total = None
    fees_paid = None
    
    if latest_snapshot:
        pnl_total = decimal_to_float(latest_snapshot.pnl_total)
        fees_paid = decimal_to_float(latest_snapshot.fees_paid)
    else:
        # Fallback to positions
        positions = (await session.scalars(
            select(Position).where(Position.market_id == market.id)
        )).all()
        if positions:
            pnl_total = sum(decimal_to_float(p.unrealized_pnl) or 0.0 for p in positions)
            fees_paid = sum(decimal_to_float(p.fees_paid) or 0.0 for p in positions)
    
    return MarketSummary(
        id=str(market.id),
        condition_id=market.condition_id,
        question=market.question,
        status=market.status,
        neg_risk=market.neg_risk,
        token_yes=market.token_yes,
        token_no=market.token_no,
        active_strategy=active_config.strategy.name if active_config and active_config.strategy else None,
        metadata=market.meta or {},
        pnl_total=pnl_total,
        fees_paid=fees_paid,
        position_count=position_count,
    )


@router.get("", response_model=list[MarketSummary], summary="List markets")
async def list_markets(active_only: bool = False) -> list[MarketSummary]:
    """List all markets. Set active_only=True to only show active markets."""
    repository = ConfigRepository()
    markets = await repository.list_markets(active_only=active_only)
    
    # Use a single session for all PnL queries
    async with get_session() as session:
        summaries = []
        for market in markets:
            summary = await _summarize_market(market, session)
            summaries.append(summary)
        return summaries


@router.post("/{market_id}/status", status_code=status.HTTP_204_NO_CONTENT, summary="Update market status")
async def update_market_status(market_id: str, request: MarketUpdateRequest) -> Response:
    repository = ConfigRepository()
    markets = await repository.list_markets()
    market = next((m for m in markets if str(m.id) == market_id), None)

    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")

    if request.status:
        market.status = request.status

    if request.deactivate:
        for cfg in market.strategy_configs:
            cfg.is_active = False

    if request.activate_strategy:
        for cfg in market.strategy_configs:
            cfg.is_active = cfg.strategy and cfg.strategy.name == request.activate_strategy
            if cfg.is_active:
                market.status = "active"

    await repository.upsert_market(market)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PolymarketMarketInfo(BaseModel):
    """Information about a market from Polymarket API."""
    question: str
    condition_id: str
    market_slug: Optional[str] = None
    end_date_iso: Optional[str] = None
    token_yes: Optional[str] = None
    token_no: Optional[str] = None
    outcome_yes: Optional[str] = None
    outcome_no: Optional[str] = None
    rewards_daily_rate: Optional[float] = None
    min_size: Optional[float] = None
    max_spread: Optional[float] = None


@router.get("/current", response_model=list[PolymarketMarketInfo], summary="Fetch current open markets from Polymarket")
async def fetch_current_polymarket_markets(
    limit: Optional[int] = Query(default=100, description="Maximum number of markets to fetch")
) -> list[PolymarketMarketInfo]:
    """
    Fetch currently open/active markets directly from Polymarket API.
    
    This endpoint connects to Polymarket's API and fetches all currently active markets.
    Useful for discovering new markets or checking what's available on Polymarket.
    """
    def _fetch_markets_sync(limit: int):
        """Synchronous function to fetch markets (runs in thread pool)."""
        try:
            from data_updater.trading_utils import get_clob_client
            import pandas as pd
            
            client = get_clob_client()
            if client is None:
                return []
            
            cursor = ""
            all_markets = []
            count = 0
            
            while count < limit:
                try:
                    markets = client.get_sampling_markets(next_cursor=cursor)
                    
                    if not markets or 'data' not in markets:
                        break
                    
                    all_markets.extend(markets['data'])
                    count = len(all_markets)
                    
                    cursor = markets.get('next_cursor')
                    if cursor is None:
                        break
                        
                except Exception as e:
                    break
            
            # Limit results
            if len(all_markets) > limit:
                all_markets = all_markets[:limit]
            
            # Convert to response format
            result = []
            for market in all_markets:
                # Extract token information
                token_yes = None
                token_no = None
                outcome_yes = None
                outcome_no = None
                
                if 'tokens' in market and isinstance(market['tokens'], list):
                    if len(market['tokens']) > 0:
                        token_yes = market['tokens'][0].get('token_id')
                        outcome_yes = market['tokens'][0].get('outcome')
                    if len(market['tokens']) > 1:
                        token_no = market['tokens'][1].get('token_id')
                        outcome_no = market['tokens'][1].get('outcome')
                
                # Extract reward information
                rewards_daily_rate = None
                min_size = None
                max_spread = None
                
                if 'rewards' in market and isinstance(market['rewards'], dict):
                    rewards = market['rewards']
                    rewards_daily_rate = rewards.get('rewards_daily_rate')
                    min_size = rewards.get('min_size')
                    max_spread = rewards.get('max_spread')
                
                result.append(PolymarketMarketInfo(
                    question=market.get('question', ''),
                    condition_id=market.get('condition_id', ''),
                    market_slug=market.get('market_slug'),
                    end_date_iso=market.get('end_date_iso'),
                    token_yes=token_yes,
                    token_no=token_no,
                    outcome_yes=outcome_yes,
                    outcome_no=outcome_no,
                    rewards_daily_rate=rewards_daily_rate,
                    min_size=min_size,
                    max_spread=max_spread,
                ))
            
            return result
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching markets from Polymarket: {str(e)}"
            )
    
    # Run the synchronous function in a thread pool
    loop = asyncio.get_event_loop()
    markets = await loop.run_in_executor(None, _fetch_markets_sync, limit)
    
    return markets

