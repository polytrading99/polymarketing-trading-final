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
    
    # Ensure api section exists
    if "api" not in config:
        config["api"] = {}
    
    # Update API credentials from environment (environment takes precedence)
    if "PK" in os.environ and os.environ["PK"]:
        pk = os.environ["PK"].strip()
        if pk and pk.upper() not in ("API", "NOT SET", "NONE", ""):
            config["api"]["PRIVATE_KEY"] = pk
            logger.info("Updated PRIVATE_KEY from environment")
        else:
            logger.warning("PK environment variable is set but appears to be a placeholder")
    
    if "BROWSER_ADDRESS" in os.environ and os.environ["BROWSER_ADDRESS"]:
        proxy = os.environ["BROWSER_ADDRESS"].strip()
        if proxy and proxy.upper() not in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
            config["api"]["PROXY_ADDRESS"] = proxy
            logger.info("Updated PROXY_ADDRESS from environment")
        else:
            logger.warning("BROWSER_ADDRESS environment variable is set but appears to be a placeholder")
    
    # Update signature type if provided
    if "SIGNATURE_TYPE" in os.environ:
        try:
            sig_type = int(os.environ["SIGNATURE_TYPE"])
            config["api"]["SIGNATURE_TYPE"] = sig_type
            logger.info(f"Updated SIGNATURE_TYPE from environment: {sig_type}")
        except ValueError:
            logger.warning(f"Invalid SIGNATURE_TYPE: {os.environ['SIGNATURE_TYPE']}")
    
    # Validate config before saving
    api_cfg = config["api"]
    if not api_cfg.get("PRIVATE_KEY") or api_cfg.get("PRIVATE_KEY", "").upper() in ("API", "NOT SET", "NONE", ""):
        raise ValueError("PRIVATE_KEY is not set or is a placeholder. Set PK environment variable.")
    
    if not api_cfg.get("PROXY_ADDRESS") or api_cfg.get("PROXY_ADDRESS", "").upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
        raise ValueError("PROXY_ADDRESS is not set or is a placeholder. Set BROWSER_ADDRESS environment variable.")
    
    save_config(config)
    logger.info("Config updated successfully from environment variables")


def start_bot() -> bool:
    """Start the market making bot."""
    global _bot_process, _trade_process, _is_running
    
    with _process_lock:
        if _is_running:
            logger.warning("Bot is already running")
            return False
        
        try:
            # Update config from environment (this validates and saves config)
            try:
                update_config_from_env()
            except ValueError as e:
                logger.error(f"Config validation failed: {e}")
                logger.error("Cannot start bot with invalid config. Please set PK and BROWSER_ADDRESS environment variables.")
                return False
            
            # Start trade.py (data feed) first
            logger.info("Starting trade.py (data feed)...")
            
            # Create log directory if it doesn't exist
            log_dir = BOT_DIR.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            # Open log file for trade.py
            trade_log = open(log_dir / "trade.log", "a")
            
            # Use python3 explicitly and ensure proper environment
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BOT_DIR.parent.parent) + ":" + env.get("PYTHONPATH", "")
            
            _trade_process = subprocess.Popen(
                ["python3", str(TRADE_SCRIPT)],
                cwd=str(BOT_DIR),
                stdout=trade_log,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                env=env,
                bufsize=1  # Line buffered
            )
            
            # Wait a moment for trade.py to initialize
            import time
            time.sleep(2)
            
            # Start main_final.py (trading bot)
            logger.info("Starting main_final.py (trading bot)...")
            
            # Create log directory if it doesn't exist
            log_dir = BOT_DIR.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            # Open log file for main bot
            main_log = open(log_dir / "mm_main.log", "a")
            
            # Use python3 explicitly and ensure proper environment
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BOT_DIR.parent.parent) + ":" + env.get("PYTHONPATH", "")
            
            _bot_process = subprocess.Popen(
                ["python3", str(MAIN_SCRIPT)],
                cwd=str(BOT_DIR),
                stdout=main_log,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                env=env,
                bufsize=1  # Line buffered
            )
            
            # Check if process immediately crashed
            import time
            time.sleep(1)
            if _bot_process.poll() is not None:
                # Process crashed immediately, read the log file
                main_log.close()
                try:
                    with open(log_dir / "mm_main.log", "r") as f:
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
                if _trade_process:
                    _trade_process.terminate()
                    _trade_process.wait(timeout=5)
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

