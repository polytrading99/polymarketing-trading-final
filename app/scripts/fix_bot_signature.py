#!/usr/bin/env python3
"""
Fix the bot's config to ensure signature_type and PROXY_ADDRESS are correct.
This is the same issue we had before - the bot needs proper config values.
"""
import json
import os
import sys
from pathlib import Path
from web3 import Web3

# Get paths
project_root = Path(__file__).parent.parent.parent
config_file = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver" / "config.json"

print("="*70)
print("  FIXING BOT CONFIG FOR SIGNATURE")
print("="*70)

# Load config
if not config_file.exists():
    print(f"✗ Config file not found: {config_file}")
    sys.exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

print(f"\nCurrent config:")
print(f"  PRIVATE_KEY: {'SET' if config.get('api', {}).get('PRIVATE_KEY') and config['api']['PRIVATE_KEY'] != 'API' else 'NOT SET'}")
print(f"  PROXY_ADDRESS: {config.get('api', {}).get('PROXY_ADDRESS', 'NOT SET')}")
print(f"  SIGNATURE_TYPE: {config.get('api', {}).get('SIGNATURE_TYPE', 'NOT SET')} (type: {type(config.get('api', {}).get('SIGNATURE_TYPE'))})")

# Get from environment
pk = os.environ.get("PK")
proxy = os.environ.get("BROWSER_ADDRESS")
sig_type = os.environ.get("SIGNATURE_TYPE", "2")

print(f"\nEnvironment variables:")
print(f"  PK: {'SET' if pk else 'NOT SET'}")
print(f"  BROWSER_ADDRESS: {proxy or 'NOT SET'}")
print(f"  SIGNATURE_TYPE: {sig_type}")

# Ensure api section exists
if "api" not in config:
    config["api"] = {}

# Update from environment
if pk and pk.strip() and pk.upper() not in ("API", "NOT SET", "NONE", ""):
    config["api"]["PRIVATE_KEY"] = pk.strip()
    print(f"\n✓ Updated PRIVATE_KEY from environment")

if proxy and proxy.strip() and proxy.upper() not in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
    # Checksum the address
    try:
        checksummed = Web3.to_checksum_address(proxy.strip())
        config["api"]["PROXY_ADDRESS"] = checksummed
        print(f"✓ Updated PROXY_ADDRESS from environment: {checksummed}")
    except Exception as e:
        print(f"✗ Failed to checksum PROXY_ADDRESS: {e}")
        config["api"]["PROXY_ADDRESS"] = proxy.strip()

# Ensure signature_type is an integer
try:
    sig_type_int = int(sig_type)
    config["api"]["SIGNATURE_TYPE"] = sig_type_int
    print(f"✓ Updated SIGNATURE_TYPE: {sig_type_int}")
except ValueError:
    # Try to get from existing config
    existing = config.get("api", {}).get("SIGNATURE_TYPE")
    if existing is not None:
        try:
            config["api"]["SIGNATURE_TYPE"] = int(existing)
            print(f"✓ Fixed SIGNATURE_TYPE from existing: {int(existing)}")
        except:
            config["api"]["SIGNATURE_TYPE"] = 2
            print(f"✓ Set SIGNATURE_TYPE to default: 2")
    else:
        config["api"]["SIGNATURE_TYPE"] = 2
        print(f"✓ Set SIGNATURE_TYPE to default: 2")

# Validate
api_cfg = config["api"]
if not api_cfg.get("PRIVATE_KEY") or api_cfg.get("PRIVATE_KEY", "").upper() in ("API", "NOT SET", "NONE", ""):
    print(f"\n✗ ERROR: PRIVATE_KEY is still not set!")
    sys.exit(1)

if not api_cfg.get("PROXY_ADDRESS") or api_cfg.get("PROXY_ADDRESS", "").upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
    print(f"\n✗ ERROR: PROXY_ADDRESS is still not set!")
    sys.exit(1)

# Save config
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f"\n✓ Config saved successfully!")
print(f"\nFinal config:")
print(f"  PRIVATE_KEY: {'SET' if api_cfg.get('PRIVATE_KEY') else 'NOT SET'}")
print(f"  PROXY_ADDRESS: {api_cfg.get('PROXY_ADDRESS')}")
print(f"  SIGNATURE_TYPE: {api_cfg.get('SIGNATURE_TYPE')} (type: {type(api_cfg.get('SIGNATURE_TYPE'))})")
print(f"\n" + "="*70)
print("  RESTART THE BOT FOR CHANGES TO TAKE EFFECT")
print("="*70)

