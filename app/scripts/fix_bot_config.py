#!/usr/bin/env python3
"""
Fix bot configuration to ensure signature_type and funder are set correctly.
"""
import sys
import os
import json
from pathlib import Path
from web3 import Web3

project_root = Path(__file__).parent.parent.parent
config_file = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver" / "config.json"

print("="*70)
print("  FIXING BOT CONFIGURATION")
print("="*70)

# Load current config
if not config_file.exists():
    print(f"\n✗ Config file not found: {config_file}")
    sys.exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

print(f"\n✓ Loaded config from: {config_file}")

# Check and fix API section
if "api" not in config:
    config["api"] = {}

api = config["api"]

# Get values from environment or config
pk = os.environ.get("PK") or api.get("PRIVATE_KEY")
browser_addr = os.environ.get("BROWSER_ADDRESS") or api.get("PROXY_ADDRESS")
sig_type = os.environ.get("SIGNATURE_TYPE") or api.get("SIGNATURE_TYPE", 1)

# Ensure signature_type is an integer
try:
    sig_type = int(sig_type)
except (ValueError, TypeError):
    print(f"\n⚠ Invalid SIGNATURE_TYPE: {sig_type}, defaulting to 1")
    sig_type = 1

# Checksum the address
if browser_addr and browser_addr.lower() not in ["null", "none", ""]:
    try:
        browser_addr = Web3.to_checksum_address(browser_addr)
    except Exception as e:
        print(f"\n⚠ Could not checksum address {browser_addr}: {e}")
        # Try lowercase first
        try:
            browser_addr = Web3.to_checksum_address(browser_addr.lower())
        except:
            pass

# Update config
api["PRIVATE_KEY"] = pk if pk else "API"
api["PROXY_ADDRESS"] = browser_addr if browser_addr and browser_addr.lower() not in ["null", "none", ""] else None
api["SIGNATURE_TYPE"] = sig_type
api["CHAIN_ID"] = api.get("CHAIN_ID", 137)

print("\nUpdated API configuration:")
print(f"  PRIVATE_KEY: {'SET' if pk and pk != 'API' else 'NOT SET or placeholder'}")
print(f"  PROXY_ADDRESS: {api['PROXY_ADDRESS']}")
print(f"  SIGNATURE_TYPE: {api['SIGNATURE_TYPE']} (type: {type(api['SIGNATURE_TYPE']).__name__})")
print(f"  CHAIN_ID: {api['CHAIN_ID']}")

# Verify signature_type is integer
if not isinstance(api["SIGNATURE_TYPE"], int):
    print(f"\n⚠ WARNING: SIGNATURE_TYPE is {type(api['SIGNATURE_TYPE']).__name__}, converting to int")
    api["SIGNATURE_TYPE"] = int(api["SIGNATURE_TYPE"])

# Save config
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f"\n✓ Config saved to: {config_file}")

# Verify the config can be loaded by the bot
print("\n" + "="*70)
print("  VERIFYING CONFIG LOAD")
print("="*70)

try:
    import sys
    bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
    sys.path.insert(0, str(bot_dir))
    os.chdir(str(bot_dir))
    
    from data_reader.load_config import load_config
    loaded = load_config()
    
    api_loaded = loaded.get("api", {})
    print("\n✓ Config loaded successfully by bot")
    print(f"  PRIVATE_KEY: {'SET' if api_loaded.get('PRIVATE_KEY') and api_loaded.get('PRIVATE_KEY') != 'API' else 'NOT SET'}")
    print(f"  PROXY_ADDRESS: {api_loaded.get('PROXY_ADDRESS')}")
    print(f"  SIGNATURE_TYPE: {api_loaded.get('SIGNATURE_TYPE')} (type: {type(api_loaded.get('SIGNATURE_TYPE')).__name__})")
    
    if api_loaded.get("SIGNATURE_TYPE") != sig_type:
        print(f"\n⚠ WARNING: Loaded SIGNATURE_TYPE ({api_loaded.get('SIGNATURE_TYPE')}) != expected ({sig_type})")
    
except Exception as e:
    print(f"\n✗ Error loading config: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("  CONFIGURATION FIXED")
print("="*70)
print("\nNext steps:")
print("1. Restart the bot to pick up the new configuration")
print("2. Check logs to see if 'invalid signature' error is resolved")
print("="*70 + "\n")

