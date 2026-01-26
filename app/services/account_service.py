"""
Service to get account balance and positions from Polymarket.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# Path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

def get_polymarket_client():
    """Create a PolymarketClient instance from environment variables."""
    try:
        # Add project root to path to import poly_data
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        
        # Get values from environment
        private_key = os.environ.get("PK")
        proxy_address = os.environ.get("BROWSER_ADDRESS")
        
        if not private_key or private_key.upper() in ("API", "NOT SET", "NONE", ""):
            raise ValueError("PRIVATE_KEY not set or is placeholder. Set PK environment variable.")
        
        if not proxy_address or proxy_address.upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
            raise ValueError("PROXY_ADDRESS not set or is placeholder. Set BROWSER_ADDRESS environment variable.")
        
        from poly_data.polymarket_client import PolymarketClient
        
        # New bot's client loads everything from environment
        client = PolymarketClient()
        
        return client
    except Exception as e:
        logger.error(f"Failed to create PolymarketClient: {e}")
        raise


def get_account_balance() -> Dict[str, Any]:
    """Get USDC balance for the trading account."""
    try:
        client = get_polymarket_client()
        
        # Use the correct method name: get_usdc_balance()
        usdc_balance = client.get_usdc_balance()
        
        if isinstance(usdc_balance, (int, float)):
            return {
                "success": True,
                "balance": {
                    "usdc": float(usdc_balance),
                    "currency": "USDC"
                }
            }
        
        return {
            "success": False,
            "error": "Could not retrieve balance",
            "balance": {
                "usdc": 0.0,
                "currency": "USDC"
            }
        }
    except Exception as e:
        logger.error(f"Error getting account balance: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "balance": {
                "usdc": 0.0,
                "currency": "USDC"
            }
        }


def get_account_positions() -> Dict[str, Any]:
    """Get all positions for the trading account."""
    try:
        client = get_polymarket_client()
        
        # Use get_all_positions() which returns a DataFrame
        positions_df = client.get_all_positions()
        
        # Convert DataFrame to list of dicts
        if positions_df is not None and not positions_df.empty:
            positions = positions_df.to_dict('records')
            # Calculate total value
            total_value = sum(float(pos.get("size", 0) or 0) * float(pos.get("avgPrice", 0) or 0) for pos in positions)
        else:
            positions = []
            total_value = 0.0
        
        return {
            "success": True,
            "positions": positions,
            "total_positions": len(positions),
            "total_value_usd": total_value
        }
    except Exception as e:
        logger.error(f"Error getting account positions: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "positions": [],
            "total_positions": 0,
            "total_value_usd": 0.0
        }


def get_open_orders() -> Dict[str, Any]:
    """Get all open orders for the trading account."""
    try:
        client = get_polymarket_client()
        
        # Use get_all_orders() which returns a DataFrame
        orders_df = client.get_all_orders()
        
        # Convert DataFrame to list of dicts
        if orders_df is not None and not orders_df.empty:
            orders = orders_df.to_dict('records')
        else:
            orders = []
        
        return {
            "success": True,
            "orders": orders,
            "total_orders": len(orders)
        }
    except Exception as e:
        logger.error(f"Error getting open orders: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "orders": [],
            "total_orders": 0
        }


def get_account_summary() -> Dict[str, Any]:
    """Get complete account summary: balance, positions, and orders."""
    balance = get_account_balance()
    positions = get_account_positions()
    orders = get_open_orders()
    
    # Get wallet address from environment
    wallet_address = os.environ.get("BROWSER_ADDRESS", "Not set")
    
    return {
        "balance": balance,
        "positions": positions,
        "orders": orders,
        "wallet_address": wallet_address
    }
