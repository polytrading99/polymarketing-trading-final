#!/usr/bin/env python3
"""
Check if bot processes are actually running and what they're doing.
"""
import subprocess
import sys
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent / "polymarket_mm_deliver" / "polymarket_mm_deliver"
LOG_DIR = BOT_DIR.parent / "logs"

print("="*70)
print("  CHECKING BOT PROCESSES")
print("="*70)

# Check for running Python processes
print("\n1. Checking for running Python processes...")
try:
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    lines = result.stdout.split('\n')
    bot_processes = [l for l in lines if 'main_final.py' in l or 'trade.py' in l]
    
    if bot_processes:
        print("Found bot processes:")
        for proc in bot_processes:
            print(f"  {proc}")
    else:
        print("✗ No bot processes found running")
except Exception as e:
    print(f"Error checking processes: {e}")

# Check log files
print("\n2. Checking log files...")
if LOG_DIR.exists():
    trade_log = LOG_DIR / "trade.log"
    main_log = LOG_DIR / "mm_main.log"
    
    if trade_log.exists():
        print(f"\n✓ trade.log exists ({trade_log.stat().st_size} bytes)")
        print("Last 20 lines of trade.log:")
        try:
            with open(trade_log, 'r') as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    print(f"  {line.rstrip()}")
        except Exception as e:
            print(f"  Error reading: {e}")
    else:
        print(f"✗ trade.log not found: {trade_log}")
    
    if main_log.exists():
        print(f"\n✓ mm_main.log exists ({main_log.stat().st_size} bytes)")
        print("Last 20 lines of mm_main.log:")
        try:
            with open(main_log, 'r') as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    print(f"  {line.rstrip()}")
        except Exception as e:
            print(f"  Error reading: {e}")
    else:
        print(f"✗ mm_main.log not found: {main_log}")
else:
    print(f"✗ Log directory not found: {LOG_DIR}")

# Check if files exist
print("\n3. Checking bot files...")
main_file = BOT_DIR / "main_final.py"
trade_file = BOT_DIR / "trade.py"

print(f"main_final.py: {'✓' if main_file.exists() else '✗'} {main_file}")
print(f"trade.py: {'✓' if trade_file.exists() else '✗'} {trade_file}")

# Check config
print("\n4. Checking config...")
config_file = BOT_DIR / "config.json"
if config_file.exists():
    import json
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        api_cfg = config.get("api", {})
        print(f"PRIVATE_KEY: {'SET' if api_cfg.get('PRIVATE_KEY') and api_cfg.get('PRIVATE_KEY') != 'API' else 'NOT SET'}")
        print(f"PROXY_ADDRESS: {api_cfg.get('PROXY_ADDRESS', 'NOT SET')}")
        print(f"SIGNATURE_TYPE: {api_cfg.get('SIGNATURE_TYPE', 'NOT SET')}")
    except Exception as e:
        print(f"Error reading config: {e}")
else:
    print(f"✗ Config file not found: {config_file}")

print("\n" + "="*70)

