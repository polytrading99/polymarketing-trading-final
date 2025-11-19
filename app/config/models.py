from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, NonNegativeFloat, PositiveFloat


class MarketConfig(BaseModel):
    """Normalized configuration for a single Polymarket market."""

    condition_id: str = Field(description="Polymarket condition identifier")
    question: str = Field(description="Human readable market question")
    token_yes: str = Field(description="Token identifier for the YES outcome")
    token_no: str = Field(description="Token identifier for the NO outcome")
    neg_risk: bool = Field(default=False, description="Whether the market is negative risk")
    tick_size: NonNegativeFloat = Field(default=0.01, description="Minimum price increment")
    trade_size: PositiveFloat = Field(default=1.0, description="Default trade size in USDC equivalents")
    min_size: NonNegativeFloat = Field(default=0.0, description="Minimum order size")
    max_size: Optional[NonNegativeFloat] = Field(
        default=None, description="Optional maximum inventory size"
    )
    max_spread: NonNegativeFloat = Field(default=5.0, description="Maximum allowed spread in cents")
    param_type: Optional[str] = Field(default=None, description="Strategy parameter template id")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional per-market metadata")


class StrategyParameters(BaseModel):
    """Parameter bundle for a given strategy / market type."""

    name: str
    values: Dict[str, Any] = Field(default_factory=dict)


class BotConfigSnapshot(BaseModel):
    """Full configuration snapshot used by the trading engine."""

    markets: List[MarketConfig] = Field(default_factory=list)
    strategies: Dict[str, StrategyParameters] = Field(default_factory=dict)


__all__ = ["MarketConfig", "StrategyParameters", "BotConfigSnapshot"]

