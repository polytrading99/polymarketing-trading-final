from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def default_uuid() -> uuid.UUID:
    return uuid.uuid4()


class BotRunStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class BotRunStatusType(TypeDecorator):
    """Custom type to handle BotRunStatus enum conversion with native PostgreSQL enum."""
    impl = String
    cache_ok = True
    
    def __init__(self):
        super().__init__(length=32)
        self.enum_name = "bot_run_status"
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use String type and handle enum conversion manually to avoid SQLAlchemy enum validation issues
            # The database has native enum, but we'll read it as text and convert
            return String(length=32)
        return super().load_dialect_impl(dialect)
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, BotRunStatus):
            return value.value  # Return lowercase string
        return str(value).lower()
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # Database returns lowercase string, convert to enum immediately
        # This must happen before SQLAlchemy tries to validate
        if isinstance(value, str):
            value_lower = value.lower().strip()
            # Direct mapping to enum values
            if value_lower == "running":
                return BotRunStatus.RUNNING
            elif value_lower == "stopped":
                return BotRunStatus.STOPPED
            elif value_lower == "failed":
                return BotRunStatus.FAILED
            # Try enum lookup as fallback
            try:
                return BotRunStatus(value_lower)
            except ValueError:
                # If all else fails, return the string and let Python handle it
                return value
        # If it's already an enum, return as-is
        if isinstance(value, BotRunStatus):
            return value
        return value


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Market(Base):
    """Tracked Polymarket market."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    condition_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    neg_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    token_yes: Mapped[str] = mapped_column(String(128), nullable=False)
    token_no: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    strategy_configs: Mapped[list["MarketConfig"]] = relationship(
        back_populates="market", cascade="all, delete-orphan"
    )
    runs: Mapped[list["BotRun"]] = relationship(back_populates="market")
    orders: Mapped[list["Order"]] = relationship(back_populates="market")
    positions: Mapped[list["Position"]] = relationship(back_populates="market")


class Strategy(Base):
    """Trading strategy template."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_params: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    market_configs: Mapped[list["MarketConfig"]] = relationship(back_populates="strategy")


class MarketConfig(Base):
    """Per-market configuration overrides."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market.id", ondelete="cascade"), nullable=False
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy.id", ondelete="cascade"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    tick_size: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    trade_size: Mapped[Optional[float]] = mapped_column(Numeric(14, 6))
    min_size: Mapped[Optional[float]] = mapped_column(Numeric(14, 6))
    max_size: Mapped[Optional[float]] = mapped_column(Numeric(14, 6))
    max_spread: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    market: Mapped[Market] = relationship(back_populates="strategy_configs")
    strategy: Mapped[Strategy] = relationship(back_populates="market_configs")

    __table_args__ = (
        UniqueConstraint("market_id", "strategy_id", name="uq_market_strategy"),
    )


class BotRun(Base):
    """Lifecycle tracking for bot instances per market."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market.id", ondelete="cascade"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32),
        default="running", 
        nullable=False
    )
    stop_reason: Mapped[Optional[str]] = mapped_column(Text)
    operator: Mapped[Optional[str]] = mapped_column(String(64))
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    market: Mapped[Market] = relationship(back_populates="runs")


class Order(Base):
    """Order lifecycle tracking."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market.id", ondelete="cascade"), nullable=False
    )
    bot_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_run.id", ondelete="set null"), nullable=True
    )
    token_id: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide, name="order_side"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    size: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    filled_size: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), default=OrderStatus.OPEN, nullable=False
    )
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128))
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(256))
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    market: Mapped[Market] = relationship(back_populates="orders")
    bot_run: Mapped[Optional[BotRun]] = relationship()
    fills: Mapped[list["Fill"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class Fill(Base):
    """Order fills / trades."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order.id", ondelete="cascade"), nullable=False
    )
    trade_id: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    pnl_delta: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    order: Mapped[Order] = relationship(back_populates="fills")


class Position(Base):
    """Real-time inventory tracking per market outcome."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market.id", ondelete="cascade"), nullable=False
    )
    token_id: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    avg_price: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    fees_paid: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    market: Mapped[Market] = relationship(back_populates="positions")

    __table_args__ = (UniqueConstraint("market_id", "token_id", name="uq_market_token_position"),)


class MetricSnapshot(Base):
    """Aggregated metrics for dashboards."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market.id", ondelete="cascade"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    pnl_total: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    pnl_unrealized: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    pnl_realized: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    inventory_value: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    fees_paid: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    market: Mapped[Market] = relationship()


__all__ = [
    "Market",
    "Strategy",
    "MarketConfig",
    "BotRun",
    "Order",
    "Fill",
    "Position",
    "MetricSnapshot",
    "BotRunStatus",
    "OrderSide",
    "OrderStatus",
]

