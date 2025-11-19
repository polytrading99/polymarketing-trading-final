from __future__ import annotations

import os
from typing import Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, multiprocess
from prometheus_client import make_asgi_app

_registry: Optional[CollectorRegistry] = None
trade_counter: Optional[Counter] = None
order_gauge: Optional[Gauge] = None
position_gauge: Optional[Gauge] = None
pnl_histogram: Optional[Histogram] = None


def get_registry() -> CollectorRegistry:
    global _registry, trade_counter, order_gauge, position_gauge, pnl_histogram
    if _registry is None:
        registry = CollectorRegistry()

        if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
            multiprocess.MultiProcessCollector(registry)

        trade_counter = Counter(
            "poly_trades_total",
            "Total number of trades executed",
            labelnames=("market", "token", "side"),
            registry=registry,
        )
        order_gauge = Gauge(
            "poly_orders_open",
            "Number of open orders",
            labelnames=("market", "token", "side"),
            registry=registry,
        )
        position_gauge = Gauge(
            "poly_positions_size",
            "Current position size",
            labelnames=("market", "token"),
            registry=registry,
        )
        pnl_histogram = Histogram(
            "poly_pnl_unrealized",
            "Distribution of unrealized PnL",
            labelnames=("market",),
            registry=registry,
        )

        _registry = registry

    return _registry


def metrics_app():
    registry = get_registry()
    return make_asgi_app(registry=registry)


