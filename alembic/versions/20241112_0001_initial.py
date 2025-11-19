"""Initial database schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision = "20241112_0001"
down_revision = None
branch_labels = None
depends_on = None


bot_run_status_enum = sa.Enum(
    "running",
    "stopped",
    "failed",
    name="bot_run_status",
)

order_side_enum = sa.Enum(
    "BUY",
    "SELL",
    name="order_side",
)

order_status_enum = sa.Enum(
    "open",
    "partial",
    "filled",
    "cancelled",
    "failed",
    name="order_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    # Drop types if they exist (cleanup from previous failed migrations)
    op.execute(sa.text("DROP TYPE IF EXISTS bot_run_status CASCADE"))
    op.execute(sa.text("DROP TYPE IF EXISTS order_side CASCADE"))
    op.execute(sa.text("DROP TYPE IF EXISTS order_status CASCADE"))
    # SQLAlchemy will create the enums automatically when creating tables

    op.create_table(
        "market",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("neg_risk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_yes", sa.String(length=128), nullable=False),
        sa.Column("token_no", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="inactive"),
        sa.Column("meta", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "strategy",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_params", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bot_run",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", bot_run_status_enum, nullable=False, server_default="running"),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("meta", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "market_config",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tick_size", sa.Numeric(10, 6), nullable=True),
        sa.Column("trade_size", sa.Numeric(14, 6), nullable=True),
        sa.Column("min_size", sa.Numeric(14, 6), nullable=True),
        sa.Column("max_size", sa.Numeric(14, 6), nullable=True),
        sa.Column("max_spread", sa.Numeric(10, 6), nullable=True),
        sa.Column("params", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"], ondelete="cascade"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategy.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "strategy_id", name="uq_market_strategy"),
    )

    op.create_table(
        "order",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_run_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("token_id", sa.String(length=128), nullable=False),
        sa.Column("side", order_side_enum, nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("size", sa.Numeric(18, 8), nullable=False),
        sa.Column("filled_size", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("status", order_status_enum, nullable=False, server_default="open"),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("transaction_hash", sa.String(length=256), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bot_run_id"], ["bot_run.id"], ondelete="set null"),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "position",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_id", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("fees_paid", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "token_id", name="uq_market_token_position"),
    )

    op.create_table(
        "metric_snapshot",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("pnl_total", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("pnl_unrealized", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("pnl_realized", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("inventory_value", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("fees_paid", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("extra", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "fill",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Numeric(18, 8), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("fee", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("pnl_delta", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("fill")
    op.drop_table("metric_snapshot")
    op.drop_table("position")
    op.drop_table("order")
    op.drop_table("market_config")
    op.drop_table("bot_run")
    op.drop_table("strategy")
    op.drop_table("market")

    bind = op.get_bind()
    order_status_enum.drop(bind, checkfirst=True)
    order_side_enum.drop(bind, checkfirst=True)
    bot_run_status_enum.drop(bind, checkfirst=True)

