"""
API routes for the Market Making bot control.
"""
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.mm_bot_service import (
    start_bot,
    stop_bot,
    get_bot_status,
    get_config,
    update_config,
    restart_bot,
)
from app.services.account_service import (
    get_account_balance,
    get_account_positions,
    get_open_orders,
    get_account_summary,
)

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Partial config update model."""
    config: Dict[str, Any]


@router.post("/start", status_code=status.HTTP_200_OK, summary="Start the MM bot")
async def start_mm_bot() -> Dict[str, Any]:
    """Start the market making bot."""
    success = start_bot()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to start bot or bot is already running"
        )
    return {"status": "started", "message": "Bot started successfully"}


@router.post("/stop", status_code=status.HTTP_200_OK, summary="Stop the MM bot")
async def stop_mm_bot() -> Dict[str, Any]:
    """Stop the market making bot."""
    success = stop_bot()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to stop bot or bot is not running"
        )
    return {"status": "stopped", "message": "Bot stopped successfully"}


@router.post("/restart", status_code=status.HTTP_200_OK, summary="Restart the MM bot")
async def restart_mm_bot() -> Dict[str, Any]:
    """Restart the market making bot."""
    success = restart_bot()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to restart bot"
        )
    return {"status": "restarted", "message": "Bot restarted successfully"}


@router.get("/status", summary="Get bot status")
async def get_mm_bot_status() -> Dict[str, Any]:
    """Get the current status of the bot."""
    return get_bot_status()


@router.get("/config", summary="Get bot configuration")
async def get_mm_bot_config() -> Dict[str, Any]:
    """Get the current bot configuration."""
    return get_config()


@router.put("/config", summary="Update bot configuration")
async def update_mm_bot_config(update: ConfigUpdate) -> Dict[str, Any]:
    """Update the bot configuration."""
    try:
        update_config(update.config)
        return {"status": "updated", "message": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update config: {str(e)}"
        )


@router.get("/account/balance", summary="Get account balance")
async def get_account_balance_endpoint() -> Dict[str, Any]:
    """Get USDC balance for the trading account."""
    return get_account_balance()


@router.get("/account/positions", summary="Get account positions")
async def get_account_positions_endpoint() -> Dict[str, Any]:
    """Get all positions for the trading account."""
    return get_account_positions()


@router.get("/account/orders", summary="Get open orders")
async def get_open_orders_endpoint() -> Dict[str, Any]:
    """Get all open orders for the trading account."""
    return get_open_orders()


@router.get("/account/summary", summary="Get account summary")
async def get_account_summary_endpoint() -> Dict[str, Any]:
    """Get complete account summary: balance, positions, and orders."""
    return get_account_summary()

