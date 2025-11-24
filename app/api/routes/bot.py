import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select, func, cast, String, text, update
from sqlalchemy.orm import selectinload

from app.database.models import BotRun, BotRunStatus, Market, MarketConfig as MarketConfigModel
from app.database.session import get_session

router = APIRouter()


class BotRunSummary(BaseModel):
    id: str
    market_id: str
    condition_id: str
    started_at: datetime
    stopped_at: Optional[datetime]
    status: str
    stop_reason: Optional[str]
    operator: Optional[str]


class StartBotRequest(BaseModel):
    strategy_name: Optional[str] = None
    operator: Optional[str] = None


class StopBotRequest(BaseModel):
    reason: Optional[str] = None
    operator: Optional[str] = None


@router.post("/{market_id}/start", status_code=status.HTTP_201_CREATED, summary="Start bot for a market")
async def start_bot(market_id: UUID, request: StartBotRequest) -> BotRunSummary:
    """Start a bot instance for a specific market."""
    async with get_session() as session:
        market = await session.get(
            Market, 
            market_id, 
            options=[
                selectinload(Market.strategy_configs).selectinload(MarketConfigModel.strategy)
            ]
        )
        
        if market is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
        
        # Check if there's already a running bot for this market
        from sqlalchemy import text
        existing_run = await session.scalar(
            select(BotRun)
            .where(
                BotRun.market_id == market_id,
                text("CAST(bot_run.status AS TEXT) = 'running'")
            )
            .order_by(BotRun.started_at.desc())
            .limit(1)
        )
        
        if existing_run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bot is already running for this market"
            )
        
        # Activate strategy if specified
        if request.strategy_name:
            for cfg in market.strategy_configs:
                cfg.is_active = cfg.strategy and cfg.strategy.name == request.strategy_name
                if cfg.is_active:
                    market.status = "active"
        else:
            # Activate first available strategy
            active_config = next((cfg for cfg in market.strategy_configs if cfg.is_active), None)
            if not active_config and market.strategy_configs:
                market.strategy_configs[0].is_active = True
                market.status = "active"
        
        # Update market status
        market.status = "active"
        session.add(market)
        await session.flush()
        
        # Create new bot run with explicit UUID
        bot_run = BotRun(
            id=uuid.uuid4(),
            market_id=market_id,
            status="running",  # Store as string
            operator=request.operator,
        )
        session.add(bot_run)
        await session.flush()
        
        await session.commit()
        
        return BotRunSummary(
            id=str(bot_run.id),
            market_id=str(market_id),
            condition_id=market.condition_id,
            started_at=bot_run.started_at,
            stopped_at=bot_run.stopped_at,
                        status=bot_run.status,
            stop_reason=bot_run.stop_reason,
            operator=bot_run.operator,
        )


@router.post("/{market_id}/stop", status_code=status.HTTP_200_OK, summary="Stop bot for a market")
async def stop_bot(market_id: UUID, request: StopBotRequest) -> BotRunSummary:
    """Stop a running bot instance for a specific market."""
    async with get_session() as session:
        market = await session.get(
            Market, 
            market_id,
            options=[selectinload(Market.strategy_configs)]
        )
        
        if market is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
        
        # Find the running bot instance
        from sqlalchemy import text
        bot_run = await session.scalar(
            select(BotRun)
            .where(
                BotRun.market_id == market_id,
                text("CAST(bot_run.status AS TEXT) = 'running'")
            )
            .order_by(BotRun.started_at.desc())
            .limit(1)
        )
        
        if not bot_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No running bot found for this market"
            )
        
        # Stop the bot
        bot_run.status = "stopped"
        bot_run.stopped_at = datetime.utcnow()
        bot_run.stop_reason = request.reason or "Stopped via API"
        bot_run.operator = request.operator
        
        # Deactivate market
        market.status = "inactive"
        
        # Update strategy configs directly via update query to avoid lazy loading issues
        from app.database.models import MarketConfig as MarketConfigModel
        await session.execute(
            update(MarketConfigModel)
            .where(MarketConfigModel.market_id == market_id)
            .values(is_active=False)
        )
        
        await session.flush()
        await session.commit()
        
        return BotRunSummary(
            id=str(bot_run.id),
            market_id=str(market_id),
            condition_id=market.condition_id,
            started_at=bot_run.started_at,
            stopped_at=bot_run.stopped_at,
                        status=bot_run.status,
            stop_reason=bot_run.stop_reason,
            operator=bot_run.operator,
        )


@router.get("/{market_id}/status", response_model=BotRunSummary, summary="Get bot status for a market")
async def get_bot_status(market_id: UUID) -> BotRunSummary:
    """Get the current bot run status for a market."""
    async with get_session() as session:
        market = await session.get(Market, market_id)
        
        if market is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
        
        bot_run = await session.scalar(
            select(BotRun)
            .where(BotRun.market_id == market_id)
            .order_by(BotRun.started_at.desc())
            .limit(1)
        )
        
        if not bot_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No bot run found for this market"
            )
        
        return BotRunSummary(
            id=str(bot_run.id),
            market_id=str(market_id),
            condition_id=market.condition_id,
            started_at=bot_run.started_at,
            stopped_at=bot_run.stopped_at,
                        status=bot_run.status,
            stop_reason=bot_run.stop_reason,
            operator=bot_run.operator,
        )

