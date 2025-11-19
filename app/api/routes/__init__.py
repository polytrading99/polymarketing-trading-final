from fastapi import APIRouter

from .health import router as health_router
from .markets import router as markets_router
from .strategies import router as strategies_router
from .orders import router as orders_router
from .positions import router as positions_router
from .metrics import router as metrics_router
from .bot import router as bot_router
from .pnl import router as pnl_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(markets_router, prefix="/markets", tags=["markets"])
api_router.include_router(strategies_router, prefix="/strategies", tags=["strategies"])
api_router.include_router(orders_router, prefix="/orders", tags=["orders"])
api_router.include_router(positions_router, prefix="/positions", tags=["positions"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
api_router.include_router(bot_router, prefix="/bot", tags=["bot"])
api_router.include_router(pnl_router, prefix="/pnl", tags=["pnl"])

__all__ = ["api_router"]

