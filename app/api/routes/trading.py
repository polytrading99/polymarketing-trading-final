"""
API routes for real-time trading status.
"""
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

router = APIRouter()


@router.get("/status", summary="Get real-time trading status")
async def get_trading_status() -> Dict[str, Any]:
    """Get real-time trading status from the bot's global state."""
    try:
        # Try to import global_state
        import poly_data.global_state as global_state
        
        # Get current state
        positions = {}
        orders = {}
        
        # Convert positions to list format
        if hasattr(global_state, 'positions') and global_state.positions:
            for token, pos in global_state.positions.items():
                if pos and isinstance(pos, dict):
                    positions[token] = {
                        "size": float(pos.get("size", 0)),
                        "avgPrice": float(pos.get("avgPrice", 0)),
                        "value": float(pos.get("size", 0)) * float(pos.get("avgPrice", 0))
                    }
        
        # Convert orders to list format
        if hasattr(global_state, 'orders') and global_state.orders:
            for token, order_data in global_state.orders.items():
                if order_data and isinstance(order_data, dict):
                    buy = order_data.get("buy", {})
                    sell = order_data.get("sell", {})
                    orders[token] = {
                        "buy": {
                            "price": float(buy.get("price", 0)) if buy else 0,
                            "size": float(buy.get("size", 0)) if buy else 0,
                        },
                        "sell": {
                            "price": float(sell.get("price", 0)) if sell else 0,
                            "size": float(sell.get("size", 0)) if sell else 0,
                        }
                    }
        
        # Get performing trades
        performing = {}
        if hasattr(global_state, 'performing') and global_state.performing:
            for key, trades in global_state.performing.items():
                if trades:
                    performing[key] = list(trades) if isinstance(trades, set) else trades
        
        # Get market data
        market_data = {}
        if hasattr(global_state, 'all_data') and global_state.all_data:
            for asset, data in global_state.all_data.items():
                if data and isinstance(data, dict):
                    bids = data.get("bids", {})
                    asks = data.get("asks", {})
                    market_data[asset] = {
                        "asset_id": data.get("asset_id"),
                        "best_bid": float(list(bids.keys())[-1]) if bids else 0,
                        "best_ask": float(list(asks.keys())[0]) if asks else 0,
                        "bid_size": float(list(bids.values())[-1]) if bids else 0,
                        "ask_size": float(list(asks.values())[0]) if asks else 0,
                    }
        
        return {
            "success": True,
            "positions": positions,
            "orders": orders,
            "performing_trades": performing,
            "market_data": market_data,
            "total_positions": len(positions),
            "total_orders": sum(1 for o in orders.values() if (o.get("buy", {}).get("size", 0) > 0 or o.get("sell", {}).get("size", 0) > 0)),
            "active_markets": len(market_data),
        }
    except ImportError:
        return {
            "success": False,
            "error": "Bot global state not available. Bot may not be running.",
            "positions": {},
            "orders": {},
            "performing_trades": {},
            "market_data": {},
            "total_positions": 0,
            "total_orders": 0,
            "active_markets": 0,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trading status: {str(e)}"
        )

