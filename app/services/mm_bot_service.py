"""
Service to manage the Polymarket Market Making bot.
Handles starting/stopping the bot process and managing its lifecycle.
"""
import os
import json
import subprocess
import signal
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

logger = logging.getLogger(__name__)

# Path to the bot directory
BOT_DIR = Path(__file__).parent.parent.parent / "polymarket_mm_deliver" / "polymarket_mm_deliver"
CONFIG_FILE = BOT_DIR / "config.json"
MAIN_SCRIPT = BOT_DIR / "main_final.py"
TRADE_SCRIPT = BOT_DIR / "trade.py"

# Process management
_bot_process: Optional[subprocess.Popen] = None
_trade_process: Optional[subprocess.Popen] = None
_process_lock = Lock()
_is_running = False


def load_config() -> Dict[str, Any]:
    """Load the bot configuration from config.json."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")
    
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(config: Dict[str, Any]) -> None:
    """Save the bot configuration to config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def update_config_from_env() -> None:
    """Update config.json with environment variables if they exist."""
    config = load_config()
    
    # Update API credentials from environment
    if "PK" in os.environ:
        config["api"]["PRIVATE_KEY"] = os.environ["PK"]
    
    if "BROWSER_ADDRESS" in os.environ:
        proxy = os.environ["BROWSER_ADDRESS"]
        config["api"]["PROXY_ADDRESS"] = proxy if proxy and proxy.lower() != "null" else None
    
    # Update signature type if provided
    if "SIGNATURE_TYPE" in os.environ:
        try:
            config["api"]["SIGNATURE_TYPE"] = int(os.environ["SIGNATURE_TYPE"])
        except ValueError:
            logger.warning(f"Invalid SIGNATURE_TYPE: {os.environ['SIGNATURE_TYPE']}")
    
    save_config(config)


def start_bot() -> bool:
    """Start the market making bot."""
    global _bot_process, _trade_process, _is_running
    
    with _process_lock:
        if _is_running:
            logger.warning("Bot is already running")
            return False
        
        try:
            # Update config from environment
            update_config_from_env()
            
            # Start trade.py (data feed) first
            logger.info("Starting trade.py (data feed)...")
            
            # Create log directory if it doesn't exist
            log_dir = BOT_DIR.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            # Open log file for trade.py
            trade_log = open(log_dir / "trade.log", "a")
            
            _trade_process = subprocess.Popen(
                ["python", str(TRADE_SCRIPT)],
                cwd=str(BOT_DIR),
                stdout=trade_log,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                env=os.environ.copy()
            )
            
            # Wait a moment for trade.py to initialize
            import time
            time.sleep(2)
            
            # Start main_final.py (trading bot)
            logger.info("Starting main_final.py (trading bot)...")
            
            # Create log directory if it doesn't exist
            log_dir = BOT_DIR.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            # Open log files
            main_log = open(log_dir / "mm_main.log", "a")
            trade_log = open(log_dir / "trade.log", "a")
            
            _bot_process = subprocess.Popen(
                ["python", str(MAIN_SCRIPT)],
                cwd=str(BOT_DIR),
                stdout=main_log,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                env=os.environ.copy()
            )
            
            # Check if process immediately crashed
            import time
            time.sleep(1)
            if _bot_process.poll() is not None:
                # Process crashed immediately, read the log
                main_log.flush()
                main_log.seek(0)
                error_output = main_log.read()
                main_log.close()
                trade_log.close()
                logger.error(f"Bot process crashed immediately with code {_bot_process.returncode}")
                logger.error(f"Error output: {error_output[:1000]}")  # First 1000 chars
                _bot_process = None
                _trade_process = None
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
    global _bot_process, _trade_process, _is_running
    
    with _process_lock:
        if not _is_running:
            logger.warning("Bot is not running")
            return False
        
        try:
            # Stop main bot
            if _bot_process:
                logger.info("Stopping main bot process...")
                _bot_process.terminate()
                try:
                    _bot_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Bot process did not terminate, killing...")
                    _bot_process.kill()
                    _bot_process.wait()
                _bot_process = None
            
            # Stop trade process
            if _trade_process:
                logger.info("Stopping trade process...")
                _trade_process.terminate()
                try:
                    _trade_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Trade process did not terminate, killing...")
                    _trade_process.kill()
                    _trade_process.wait()
                _trade_process = None
            
            _is_running = False
            logger.info("Bot stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}", exc_info=True)
            _is_running = False
            return False


def get_bot_status() -> Dict[str, Any]:
    """Get the current status of the bot."""
    global _bot_process, _trade_process, _is_running
    
    with _process_lock:
        status = {
            "is_running": _is_running,
            "main_process": None,
            "trade_process": None,
        }
        
        if _bot_process:
            status["main_process"] = {
                "pid": _bot_process.pid,
                "returncode": _bot_process.returncode,
                "alive": _bot_process.poll() is None,
            }
        
        if _trade_process:
            status["trade_process"] = {
                "pid": _trade_process.pid,
                "returncode": _trade_process.returncode,
                "alive": _trade_process.poll() is None,
            }
        
        return status


def get_config() -> Dict[str, Any]:
    """Get the current bot configuration."""
    return load_config()


def update_config(config_updates: Dict[str, Any]) -> None:
    """Update the bot configuration with partial updates."""
    config = load_config()
    
    def deep_update(base: Dict, updates: Dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                deep_update(base[key], value)
            else:
                base[key] = value
    
    deep_update(config, config_updates)
    save_config(config)
    
    # If bot is running, it will need to be restarted to pick up new config
    logger.info("Configuration updated. Restart bot to apply changes.")


def restart_bot() -> bool:
    """Restart the bot."""
    logger.info("Restarting bot...")
    stop_bot()
    import time
    time.sleep(2)
    return start_bot()

