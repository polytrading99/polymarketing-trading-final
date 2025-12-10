"""
Service to get account balance and positions from Polymarket.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the bot directory
BOT_DIR = Path(__file__).parent.parent.parent / "polymarket_mm_deliver" / "polymarket_mm_deliver"
CONFIG_FILE = BOT_DIR / "config.json"

def get_polymarket_client():
    """Create a PolymarketClient instance from config."""
    import json
    import sys
    
    try:
        # Add bot directory to path
        if str(BOT_DIR) not in sys.path:
            sys.path.insert(0, str(BOT_DIR))
        
        # Load config
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")
        
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        if "api" not in config:
            raise ValueError("Config file missing 'api' section")
        
        api_cfg = config.get("api", {})
        
        # Get values from environment or config
        private_key = os.environ.get("PK") or api_cfg.get("PRIVATE_KEY")
        proxy_address = os.environ.get("BROWSER_ADDRESS") or api_cfg.get("PROXY_ADDRESS")
        signature_type = os.environ.get("SIGNATURE_TYPE") or api_cfg.get("SIGNATURE_TYPE", 1)
        chain_id = api_cfg.get("CHAIN_ID", 137)
        
        if not private_key or private_key == "API":
            raise ValueError("PRIVATE_KEY not set or is placeholder")
        
        if not proxy_address or proxy_address in ["WALLET API", "null", "None"]:
            raise ValueError("PROXY_ADDRESS not set or is placeholder")
        
        # Ensure signature_type is int
        try:
            signature_type = int(signature_type)
        except (ValueError, TypeError):
            signature_type = 1
        
        from state_machine.polymarket_client import PolymarketClient
        
        # Use CLOB host directly instead of importing from time_bucket_mm
        # (which tries to access CONFIG["api"] at import time)
        CLOB_HOST = "https://clob.polymarket.com"
        
        client = PolymarketClient(
            host=CLOB_HOST,
            private_key=private_key,
            chain_id=chain_id,
            signature_type=signature_type,
            funder=proxy_address,
        )
        
        return client
    except Exception as e:
        logger.error(f"Failed to create PolymarketClient: {e}", exc_info=True)
        raise

def get_account_balance() -> Dict[str, Any]:
    """Get USDC balance for the account."""
    try:
        from web3 import Web3
        
        # Polygon RPC endpoint
        polygon_rpc = "https://polygon-rpc.com"
        w3 = Web3(Web3.HTTPProvider(polygon_rpc))
        
        # USDC token contract on Polygon
        USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        
        # Get wallet address
        client = get_polymarket_client()
        wallet_address = client.wallet_address
        
        if not wallet_address:
            return {
                "success": False,
                "error": "Wallet address not configured",
            }
        
        # ERC20 ABI for balanceOf
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            }
        ]
        
        # Get USDC contract
        usdc_contract = w3.eth.contract(
            address=Web3.to_checksum_address(USDC_ADDRESS),
            abi=erc20_abi
        )
        
        # Get balance
        balance_wei = usdc_contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        
        # Get decimals (USDC has 6 decimals)
        try:
            decimals = usdc_contract.functions.decimals().call()
        except:
            decimals = 6  # USDC default
        
        # Convert to human readable
        balance_usdc = balance_wei / (10 ** decimals)
        
        return {
            "success": True,
            "balance": {
                "usdc": round(balance_usdc, 2),
                "currency": "USDC",
            },
            "wallet_address": wallet_address,
        }
    except Exception as e:
        logger.error(f"Failed to get account balance: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }

def get_account_positions() -> Dict[str, Any]:
    """Get all positions for the account."""
    try:
        client = get_polymarket_client()
        
        # Get all positions
        positions = client.get_positions(
            user=None,  # Use wallet_address from client
            market_id=None,
            size_threshold=0.0,
            limit=100,
        )
        
        # Calculate total value
        total_value = 0.0
        position_count = 0
        
        for pos in positions:
            try:
                size = float(pos.get("size", 0.0) or 0.0)
                avg_price = pos.get("avgPrice") or pos.get("avg_price")
                if avg_price is not None:
                    avg_price = float(avg_price)
                    total_value += size * avg_price
                if size > 0:
                    position_count += 1
            except (ValueError, TypeError):
                continue
        
        return {
            "success": True,
            "positions": positions,
            "total_positions": position_count,
            "total_value_usd": round(total_value, 2),
        }
    except Exception as e:
        logger.error(f"Failed to get account positions: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "positions": [],
            "total_positions": 0,
            "total_value_usd": 0.0,
        }

def get_open_orders() -> Dict[str, Any]:
    """Get all open orders for the account."""
    try:
        client = get_polymarket_client()
        
        # Try to get open orders using py-clob-client directly first
        try:
            # Use the underlying client's methods
            clob_client = client.client
            
            # Try different methods based on py-clob-client version
            orders_list = []
            
            # Method 1: Try get_orders() without parameters
            if hasattr(clob_client, "get_orders"):
                try:
                    all_orders = clob_client.get_orders()
                    if isinstance(all_orders, list):
                        orders_list = [o for o in all_orders if isinstance(o, dict) and o.get("status", "").upper() in ("OPEN", "LIVE", "PART_FILLED", "PENDING")]
                    elif isinstance(all_orders, dict):
                        orders = all_orders.get("orders") or all_orders.get("data") or []
                        if isinstance(orders, list):
                            orders_list = [o for o in orders if isinstance(o, dict) and o.get("status", "").upper() in ("OPEN", "LIVE", "PART_FILLED", "PENDING")]
                except Exception as e:
                    logger.debug(f"get_orders() failed: {e}")
            
            # Method 2: Try get_open_orders_raw as fallback
            if not orders_list:
                orders = client.get_open_orders_raw(limit=100)
                if isinstance(orders, dict):
                    orders_list = orders.get("orders") or orders.get("data") or []
                elif isinstance(orders, list):
                    orders_list = orders
                else:
                    orders_list = []
            
            # Ensure we have a list
            if not isinstance(orders_list, list):
                orders_list = []
            
            return {
                "success": True,
                "orders": orders_list,
                "total_orders": len(orders_list),
            }
        except Exception as e:
            logger.warning(f"Direct client method failed: {e}, trying alternative")
            # Fallback: return empty but successful
            return {
                "success": True,
                "orders": [],
                "total_orders": 0,
                "note": "Could not fetch orders (API endpoint may not be available)",
            }
    except Exception as e:
        logger.error(f"Failed to get open orders: {e}", exc_info=True)
        # Return success with empty list instead of error to avoid breaking UI
        return {
            "success": True,
            "orders": [],
            "total_orders": 0,
            "error": str(e)[:100],  # Truncate long errors
        }

def get_account_summary() -> Dict[str, Any]:
    """Get complete account summary: balance, positions, and orders."""
    try:
        balance = get_account_balance()
        positions = get_account_positions()
        orders = get_open_orders()
        
        wallet_address = os.environ.get("BROWSER_ADDRESS")
        if not wallet_address:
            # Try to get from config
            try:
                import json
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                wallet_address = config.get("api", {}).get("PROXY_ADDRESS")
            except:
                pass
        
        return {
            "balance": balance,
            "positions": positions,
            "orders": orders,
            "wallet_address": wallet_address or "Unknown",
        }
    except Exception as e:
        logger.error(f"Failed to get account summary: {e}", exc_info=True)
        return {
            "balance": {"success": False, "error": str(e)},
            "positions": {"success": False, "error": str(e), "positions": [], "total_positions": 0, "total_value_usd": 0.0},
            "orders": {"success": False, "error": str(e), "orders": [], "total_orders": 0},
            "wallet_address": os.environ.get("BROWSER_ADDRESS") or "Unknown",
        }

