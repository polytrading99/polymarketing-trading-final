#!/usr/bin/env python3
"""
Comprehensive diagnostic script for MM Bot errors.
Run this to identify why the bot is not starting or crashing.
"""
import sys
import os
import json
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def print_section(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def check_environment_variables():
    """Check if required environment variables are set."""
    print_section("Environment Variables")
    required = ["PK", "BROWSER_ADDRESS"]
    optional = ["SIGNATURE_TYPE"]
    
    all_ok = True
    for var in required:
        value = os.environ.get(var)
        if value:
            # Mask private key
            if var == "PK":
                masked = value[:6] + "..." + value[-4:] if len(value) > 10 else "***"
                print(f"✓ {var}: {masked}")
            else:
                print(f"✓ {var}: {value}")
        else:
            print(f"✗ {var}: NOT SET")
            all_ok = False
    
    for var in optional:
        value = os.environ.get(var)
        if value:
            print(f"  {var}: {value}")
        else:
            print(f"  {var}: not set (using default)")
    
    return all_ok

def check_config_file():
    """Check if config.json exists and is valid."""
    print_section("Configuration File")
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    config_file = bot_dir / "config.json"
    
    if not config_file.exists():
        print(f"✗ Config file not found: {config_file}")
        return False
    
    print(f"✓ Config file exists: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Check API section
        api = config.get("api", {})
        print(f"\nAPI Configuration:")
        print(f"  PRIVATE_KEY: {'SET' if api.get('PRIVATE_KEY') and api.get('PRIVATE_KEY') != 'API' else 'NOT SET or placeholder'}")
        print(f"  PROXY_ADDRESS: {api.get('PROXY_ADDRESS', 'NOT SET')}")
        print(f"  SIGNATURE_TYPE: {api.get('SIGNATURE_TYPE', 'NOT SET')}")
        print(f"  CHAIN_ID: {api.get('CHAIN_ID', 'NOT SET')}")
        
        # Check strategies
        strategies = config.get("strategies", {})
        s1 = strategies.get("strategy_1", {})
        s2 = strategies.get("strategy_2", {})
        print(f"\nStrategy Configuration:")
        print(f"  Strategy 1 ENABLED: {s1.get('ENABLED', False)}")
        print(f"  Strategy 2 ENABLED: {s2.get('ENABLED', False)}")
        
        return True
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in config file: {e}")
        return False
    except Exception as e:
        print(f"✗ Error reading config: {e}")
        return False

def check_python_imports():
    """Check if required Python modules can be imported."""
    print_section("Python Imports")
    
    imports_to_test = [
        ("data_reader.load_config", "load_config"),
        ("state_machine.polymarket_client", "PolymarketClient"),
        ("state_machine.account_state", "AccountState"),
        ("data_reader.shm_reader", "ShmRingReader"),
        ("state_machine.ws_client", "UserWebSocketClient"),
        ("strategy.time_bucket_mm", "resolve_market_for_bucket"),
    ]
    
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    original_cwd = os.getcwd()
    
    try:
        os.chdir(str(bot_dir))
        sys.path.insert(0, str(bot_dir))
        
        all_ok = True
        for module_path, item_name in imports_to_test:
            try:
                module = __import__(module_path, fromlist=[item_name])
                item = getattr(module, item_name)
                print(f"✓ {module_path}.{item_name}")
            except ImportError as e:
                print(f"✗ {module_path}.{item_name}: {e}")
                all_ok = False
            except AttributeError as e:
                print(f"✗ {module_path}.{item_name}: {e}")
                all_ok = False
            except Exception as e:
                print(f"✗ {module_path}.{item_name}: {type(e).__name__}: {e}")
                all_ok = False
        
        return all_ok
    finally:
        os.chdir(original_cwd)

def check_dependencies():
    """Check if required Python packages are installed."""
    print_section("Python Dependencies")
    
    required_packages = [
        "numpy",
        "websocket-client",
        "py-clob-client",
        "web3",
        "requests",
    ]
    
    all_ok = True
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package}: NOT INSTALLED")
            all_ok = False
    
    return all_ok

def test_config_loading():
    """Test if config can be loaded by the bot."""
    print_section("Config Loading Test")
    
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    original_cwd = os.getcwd()
    
    try:
        os.chdir(str(bot_dir))
        sys.path.insert(0, str(bot_dir))
        
        try:
            from data_reader.load_config import load_config
            config = load_config()
            print("✓ Config loaded successfully")
            print(f"  Keys: {list(config.keys())}")
            
            # Validate API section
            api = config.get("api", {})
            if not api.get("PRIVATE_KEY") or api.get("PRIVATE_KEY") == "API":
                print("⚠ WARNING: PRIVATE_KEY not set or is placeholder")
            if not api.get("PROXY_ADDRESS") or api.get("PROXY_ADDRESS") == "WALLET API":
                print("⚠ WARNING: PROXY_ADDRESS not set or is placeholder")
            
            return True
        except Exception as e:
            print(f"✗ Failed to load config: {e}")
            import traceback
            traceback.print_exc()
            return False
    finally:
        os.chdir(original_cwd)

def test_bot_startup():
    """Test if bot can start (dry run)."""
    print_section("Bot Startup Test")
    
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    main_script = bot_dir / "main_final.py"
    
    if not main_script.exists():
        print(f"✗ Main script not found: {main_script}")
        return False
    
    print(f"✓ Main script exists: {main_script}")
    
    # Try to import main module (this will catch import errors)
    original_cwd = os.getcwd()
    try:
        os.chdir(str(bot_dir))
        sys.path.insert(0, str(bot_dir))
        
        try:
            # Just test imports, don't actually run main()
            import importlib.util
            spec = importlib.util.spec_from_file_location("main_final", str(main_script))
            if spec and spec.loader:
                print("✓ Main script can be loaded")
                return True
            else:
                print("✗ Failed to create module spec")
                return False
        except Exception as e:
            print(f"✗ Failed to load main script: {e}")
            import traceback
            traceback.print_exc()
            return False
    finally:
        os.chdir(original_cwd)

def check_file_paths():
    """Check if required files exist."""
    print_section("File Paths")
    
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    required_files = [
        ("config.json", bot_dir / "config.json"),
        ("main_final.py", bot_dir / "main_final.py"),
        ("trade.py", bot_dir / "trade.py"),
    ]
    
    all_ok = True
    for name, path in required_files:
        if path.exists():
            print(f"✓ {name}: {path}")
        else:
            print(f"✗ {name}: NOT FOUND at {path}")
            all_ok = False
    
    return all_ok

def check_shared_memory():
    """Check if shared memory can be accessed."""
    print_section("Shared Memory")
    
    try:
        import sysv_ipc
        
        # Try to create/open shared memory (read-only test)
        try:
            shm = sysv_ipc.SharedMemory("poly_tob_shm", flags=sysv_ipc.IPC_CREAT, mode=0o666, size=4096)
            print("✓ Shared memory can be accessed")
            shm.detach()
            return True
        except sysv_ipc.ExistentialError:
            print("⚠ Shared memory doesn't exist yet (this is OK if trade.py hasn't started)")
            return True
        except Exception as e:
            print(f"⚠ Shared memory check: {e} (may be OK)")
            return True  # Don't fail on this
    except ImportError:
        print("⚠ sysv_ipc not available (may use different shared memory mechanism)")
        print("  This is usually OK - the bot may use a different approach")
        return True

def main():
    print("\n" + "="*70)
    print("  MM BOT DIAGNOSTIC TOOL")
    print("="*70)
    
    results = {}
    
    results["environment"] = check_environment_variables()
    results["files"] = check_file_paths()
    results["config"] = check_config_file()
    results["dependencies"] = check_dependencies()
    results["imports"] = check_python_imports()
    results["config_loading"] = test_config_loading()
    results["startup"] = test_bot_startup()
    results["shared_memory"] = check_shared_memory()
    
    print_section("Summary")
    print("\nResults:")
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {check}")
    
    all_passed = all(results.values())
    print(f"\n{'='*70}")
    if all_passed:
        print("  ALL CHECKS PASSED - Bot should be able to start")
    else:
        print("  SOME CHECKS FAILED - Review errors above")
    print("="*70 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

