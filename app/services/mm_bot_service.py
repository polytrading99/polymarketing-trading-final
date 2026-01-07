"""
Service to manage the Polymarket Market Making bot.
Handles starting/stopping the bot process and managing its lifecycle.
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

logger = logging.getLogger(__name__)

# Path to the bot directory (root of project)
PROJECT_ROOT = Path(__file__).parent.parent.parent
MAIN_SCRIPT = PROJECT_ROOT / "main.py"

# Process management
_bot_process: Optional[subprocess.Popen] = None
_process_lock = Lock()
_is_running = False


def validate_credentials() -> bool:
    """Validate that required credentials are set in environment."""
    pk = os.environ.get("PK", "").strip()
    browser_address = os.environ.get("BROWSER_ADDRESS", "").strip()
    
    if not pk or pk.upper() in ("API", "NOT SET", "NONE", ""):
        logger.error("PK environment variable is not set or is a placeholder")
        return False
    
    if not browser_address or browser_address.upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
        logger.error("BROWSER_ADDRESS environment variable is not set or is a placeholder")
        return False
    
    return True


def start_bot() -> bool:
    """Start the market making bot."""
    global _bot_process, _is_running
    
    with _process_lock:
        if _is_running:
            logger.warning("Bot is already running")
            return False
        
        try:
            # Validate credentials
            if not validate_credentials():
                logger.error("Cannot start bot with invalid credentials. Please set PK and BROWSER_ADDRESS environment variables.")
                return False
            
            if not MAIN_SCRIPT.exists():
                logger.error(f"Main script not found: {MAIN_SCRIPT}")
                return False
            
            # Create log directory if it doesn't exist
            log_dir = PROJECT_ROOT / "logs"
            log_dir.mkdir(exist_ok=True)
            
            # Open log file for bot
            main_log = open(log_dir / "bot.log", "a")
            
            # Use uv run python main.py (as per new bot structure)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT) + ":" + env.get("PYTHONPATH", "")
            
            logger.info("Starting market making bot (main.py)...")
            
            _bot_process = subprocess.Popen(
                ["uv", "run", "python", str(MAIN_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                stdout=main_log,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                env=env,
                bufsize=1  # Line buffered
            )
            
            # Check if process immediately crashed
            import time
            time.sleep(2)
            if _bot_process.poll() is not None:
                # Process crashed immediately, read the log file
                main_log.close()
                try:
                    with open(log_dir / "bot.log", "r") as f:
                        # Read last 2000 chars
                        f.seek(0, 2)  # Seek to end
                        file_size = f.tell()
                        f.seek(max(0, file_size - 2000))  # Read last 2000 chars
                        error_output = f.read()
                except Exception as e:
                    error_output = f"Could not read log file: {e}"
                
                logger.error(f"Bot process crashed immediately with code {_bot_process.returncode}")
                logger.error(f"Error output (last 2000 chars): {error_output}")
                _bot_process = None
                _is_running = False
                return False
            
            _is_running = True
            logger.info("Bot started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            stop_bot()
            return False


def stop_bot() -> bool:
    """Stop the market making bot."""
    global _bot_process, _is_running
    
    with _process_lock:
        if not _is_running:
            logger.warning("Bot is not running")
            return False
        
        try:
            # Stop main bot
            if _bot_process:
                logger.info("Stopping bot process...")
                _bot_process.terminate()
                try:
                    _bot_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Bot process did not terminate, killing...")
                    _bot_process.kill()
                    _bot_process.wait()
                _bot_process = None
            
            _is_running = False
            logger.info("Bot stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}", exc_info=True)
            _is_running = False
            return False


def get_bot_status() -> Dict[str, Any]:
    """Get the current status of the bot."""
    global _bot_process, _is_running
    
    with _process_lock:
        status = {
            "is_running": _is_running,
            "main_process": None,
            "current_market": None,
            "recent_errors": [],
        }
        
        if _bot_process:
            status["main_process"] = {
                "pid": _bot_process.pid,
                "returncode": _bot_process.returncode,
                "alive": _bot_process.poll() is None,
            }
        
        # Parse log to get current market info and errors
        try:
            log_file = PROJECT_ROOT / "logs" / "bot.log"
            if log_file.exists():
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                
                # Get last 200 lines
                recent_lines = lines[-200:] if len(lines) > 200 else lines
                
                # Find current market info (look for market-related log entries)
                market_info = {}
                for line in reversed(recent_lines):
                    # Look for market mentions in logs
                    if "market" in line.lower() and ("condition" in line.lower() or "token" in line.lower()):
                        # Try to extract market info
                        if "condition_id" in line:
                            try:
                                parts = line.split("condition_id")
                                if len(parts) > 1:
                                    condition_part = parts[1].split()[0].strip().rstrip("',\"")
                                    market_info["condition_id"] = condition_part
                            except:
                                pass
                        if market_info:
                            break
                
                if market_info:
                    status["current_market"] = market_info
                
                # Get recent errors
                errors = []
                for line in reversed(recent_lines[-50:]):
                    if "error" in line.lower() or "exception" in line.lower() or "failed" in line.lower():
                        error_msg = line.strip()[:200]
                        if "Size" in error_msg and "lower than the minimum" in error_msg:
                            try:
                                if "minimum:" in error_msg:
                                    min_size = error_msg.split("minimum:")[-1].strip().rstrip("'}]")
                                    errors.append({
                                        "type": "Minimum Order Size",
                                        "message": f"Market requires minimum order size of ${min_size}",
                                        "full_error": error_msg
                                    })
                            except:
                                errors.append({
                                    "type": "Order Error",
                                    "message": error_msg,
                                    "full_error": error_msg
                                })
                        elif "invalid signature" in error_msg.lower():
                            errors.append({
                                "type": "Invalid Signature",
                                "message": "Order signature validation failed",
                                "full_error": error_msg
                            })
                        elif "not enough balance" in error_msg.lower() or "allowance" in error_msg.lower():
                            errors.append({
                                "type": "Balance/Allowance",
                                "message": "Insufficient balance or contract not approved",
                                "full_error": error_msg
                            })
                        elif len(error_msg) > 20:  # Only add substantial error messages
                            errors.append({
                                "type": "Error",
                                "message": error_msg,
                                "full_error": error_msg
                            })
                        if len(errors) >= 3:
                            break
                
                if errors:
                    status["recent_errors"] = errors
        except Exception as e:
            logger.debug(f"Could not parse market info from logs: {e}")
        
        return status


def get_config() -> Dict[str, Any]:
    """Get the current bot configuration (from environment variables)."""
    return {
        "api": {
            "PRIVATE_KEY": "***" if os.environ.get("PK") else None,
            "PROXY_ADDRESS": os.environ.get("BROWSER_ADDRESS"),
            "SIGNATURE_TYPE": int(os.environ.get("SIGNATURE_TYPE", "2")),
        },
        "spreadsheet_url": os.environ.get("SPREADSHEET_URL"),
    }


def update_config(config_updates: Dict[str, Any]) -> None:
    """Update the bot configuration (not used - bot uses environment variables)."""
    logger.warning("update_config called but bot uses environment variables. Use update_credentials instead.")
    # This is kept for API compatibility but doesn't do anything
    pass


def update_credentials(private_key: str, proxy_address: str, signature_type: int = 2) -> None:
    """Update bot credentials (stores in environment for current session, but should be set in .env file)."""
    # Validate inputs
    if not private_key or private_key.strip().upper() in ("API", "NOT SET", "NONE", ""):
        raise ValueError("Private key cannot be empty or placeholder")
    
    if not proxy_address or proxy_address.strip().upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
        raise ValueError("Proxy address cannot be empty or placeholder")
    
    # Validate signature_type
    try:
        signature_type = int(signature_type)
        if signature_type not in (1, 2):
            signature_type = 2  # Default to 2
    except (ValueError, TypeError):
        signature_type = 2
    
    # Update environment variables for current session
    os.environ["PK"] = private_key.strip()
    os.environ["BROWSER_ADDRESS"] = proxy_address.strip()
    os.environ["SIGNATURE_TYPE"] = str(signature_type)
    
    logger.info("Credentials updated in environment. Note: For persistence, update .env file or docker-compose.yml")
    logger.warning("Credentials are updated for current session only. Restart the service to persist changes.")


def restart_bot() -> bool:
    """Restart the bot."""
    logger.info("Restarting bot...")
    stop_bot()
    import time
    time.sleep(2)
    return start_bot()
