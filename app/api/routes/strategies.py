from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.models import Strategy
from app.database.session import get_session

router = APIRouter()


class StrategySummary(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    default_params: dict = Field(default_factory=dict)


@router.get("", response_model=list[StrategySummary], summary="List available strategies")
async def list_strategies() -> list[StrategySummary]:
    async with get_session() as session:
        strategies = (await session.scalars(select(Strategy).order_by(Strategy.name))).all()
    return [
        StrategySummary(
            id=str(strategy.id),
            name=strategy.name,
            version=strategy.version,
            description=strategy.description,
            default_params=strategy.default_params or {},
        )
        for strategy in strategies
    ]


@router.get("/{strategy_id}", response_model=StrategySummary, summary="Get strategy details")
async def get_strategy(strategy_id: str) -> StrategySummary:
    async with get_session() as session:
        strategy = await session.get(Strategy, strategy_id)

    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    return StrategySummary(
        id=str(strategy.id),
        name=strategy.name,
        version=strategy.version,
        description=strategy.description,
        default_params=strategy.default_params or {},
    )

