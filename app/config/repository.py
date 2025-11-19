from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.config.models import BotConfigSnapshot, MarketConfig, StrategyParameters
from app.database.models import Market, MarketConfig as MarketConfigModel, Strategy
from app.database.session import get_session


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _decimal_to_float_zero(value: Optional[Decimal]) -> float:
    return float(value or 0)


@dataclass
class LoadedConfiguration:
    markets: Iterable[Market]
    strategies: Iterable[Strategy]


class ConfigRepository:
    """Data access layer for configuration entities."""

    def __init__(self, session_factory: AbstractAsyncContextManager = get_session) -> None:
        self._session_factory = session_factory

    async def load_configuration(self, active_only: bool = True) -> LoadedConfiguration:
        async with self._session_factory() as session:
            from app.database.models import BotRun, BotRunStatus
            
            market_stmt = (
                select(Market)
                .options(
                    selectinload(Market.strategy_configs).selectinload(
                        MarketConfigModel.strategy
                    )
                )
            )
            
            # Filter to only active markets if requested
            if active_only:
                # Only load markets that are active AND have a running bot
                market_stmt = market_stmt.where(Market.status == "active")
                # Check for running bot runs - cast enum to text for comparison
                from sqlalchemy import exists, cast, String, text
                running_bots = (
                    select(BotRun.id)
                    .where(
                        BotRun.market_id == Market.id,
                        text("CAST(bot_run.status AS TEXT) = 'running'")
                    )
                    .exists()
                )
                market_stmt = market_stmt.where(running_bots)
            
            market_stmt = market_stmt.order_by(Market.question.asc())
            strategy_stmt = select(Strategy)

            markets = (await session.scalars(market_stmt)).all()
            strategies = (await session.scalars(strategy_stmt)).all()

        return LoadedConfiguration(markets=markets, strategies=strategies)

    async def list_markets(self, active_only: bool = False) -> list[Market]:
        config = await self.load_configuration(active_only=active_only)
        return list(config.markets)

    async def upsert_market(
        self,
        market: Market,
    ) -> Market:
        async with self._session_factory() as session:
            persisted = await session.merge(market)
            return persisted

    async def apply_snapshot(self, snapshot: BotConfigSnapshot) -> None:
        async with self._session_factory() as session:
            strategy_lookup: dict[str, Strategy] = {}

            # Ensure strategies exist/update defaults
            for strategy in snapshot.strategies.values():
                stmt = select(Strategy).where(Strategy.name == strategy.name)
                existing = await session.scalar(stmt)
                if existing is None:
                    existing = Strategy(
                        name=strategy.name,
                        default_params=strategy.values or {},
                    )
                    session.add(existing)
                else:
                    existing.default_params = strategy.values or {}
                strategy_lookup[strategy.name] = existing

            await session.flush()

            for market_config in snapshot.markets:
                stmt = select(Market).where(Market.condition_id == market_config.condition_id)
                market = await session.scalar(stmt)

                metadata = market_config.metadata or {}

                if market is None:
                    market = Market(
                        condition_id=market_config.condition_id,
                        question=market_config.question,
                        neg_risk=market_config.neg_risk,
                        token_yes=market_config.token_yes,
                        token_no=market_config.token_no,
                        meta=metadata,
                    )
                    session.add(market)
                    await session.flush()
                else:
                    market.question = market_config.question
                    market.neg_risk = market_config.neg_risk
                    market.token_yes = market_config.token_yes
                    market.token_no = market_config.token_no
                    existing_metadata = market.meta or {}
                    existing_metadata.update(metadata)
                    market.meta = existing_metadata

                strategy_name = market_config.param_type
                strategy = strategy_lookup.get(strategy_name) if strategy_name else None

                if strategy_name and strategy is None:
                    strategy = Strategy(name=strategy_name, default_params={})
                    session.add(strategy)
                    await session.flush()
                    strategy_lookup[strategy_name] = strategy

                if strategy:
                    config_stmt = select(MarketConfigModel).where(
                        MarketConfigModel.market_id == market.id,
                        MarketConfigModel.strategy_id == strategy.id,
                    )
                    config = await session.scalar(config_stmt)

                    if config is None:
                        config = MarketConfigModel(market=market, strategy=strategy)
                        session.add(config)

                    config.is_active = True
                    config.tick_size = _to_decimal(market_config.tick_size)
                    config.trade_size = _to_decimal(market_config.trade_size)
                    config.min_size = _to_decimal(market_config.min_size)
                    config.max_size = _to_decimal(market_config.max_size)
                    config.max_spread = _to_decimal(market_config.max_spread)
                    config.params = strategy.default_params or {}

                    await session.execute(
                        update(MarketConfigModel)
                        .where(
                            MarketConfigModel.market_id == market.id,
                            MarketConfigModel.strategy_id != strategy.id,
                        )
                        .values(is_active=False)
                    )

            await session.commit()


def to_snapshot(config: LoadedConfiguration) -> BotConfigSnapshot:
    strategies = {
        strategy.name: StrategyParameters(
            name=strategy.name,
            values=strategy.default_params or {},
        )
        for strategy in config.strategies
    }

    markets: list[MarketConfig] = []
    for market in config.markets:
        active_config = next(
            (cfg for cfg in market.strategy_configs if cfg.is_active), None
        )

        tick_size = active_config.tick_size if active_config else None
        trade_size = active_config.trade_size if active_config else None
        min_size = active_config.min_size if active_config else None
        max_size = active_config.max_size if active_config else None
        max_spread = active_config.max_spread if active_config else None
        strategy_name = (
            active_config.strategy.name if active_config and active_config.strategy else None
        )

        markets.append(
            MarketConfig(
                condition_id=market.condition_id,
                question=market.question,
                token_yes=market.token_yes,
                token_no=market.token_no,
                neg_risk=market.neg_risk,
                tick_size=_decimal_to_float(tick_size) or 0.01,
                trade_size=_decimal_to_float(trade_size) or 1.0,
                min_size=_decimal_to_float_zero(min_size),
                max_size=_decimal_to_float(max_size),
                max_spread=_decimal_to_float(max_spread) or 5.0,
                param_type=strategy_name,
                metadata=market.meta or {},
            )
        )

    return BotConfigSnapshot(markets=markets, strategies=strategies)


def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


__all__ = ["ConfigRepository", "LoadedConfiguration", "to_snapshot"]

