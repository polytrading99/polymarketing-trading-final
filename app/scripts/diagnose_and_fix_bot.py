#!/usr/bin/env python3
"""
Comprehensive diagnostic and fix for bot signature issues.
This checks everything and fixes the config properly.
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
print("  COMPREHENSIVE BOT DIAGNOSTIC AND FIX")
print("="*70)

# Step 1: Check environment variables
print("\n1. Checking environment variables...")
pk = os.environ.get("PK", "").strip()
proxy = os.environ.get("BROWSER_ADDRESS", "").strip()
sig_type = os.environ.get("SIGNATURE_TYPE", "2").strip()

print(f"   PK: {'✓ SET' if pk and pk.upper() not in ('API', 'NOT SET', 'NONE', '') else '✗ NOT SET or placeholder'}")
print(f"   BROWSER_ADDRESS: {'✓ SET' if proxy and proxy.upper() not in ('WALLET API', 'NOT SET', 'NONE', 'NULL', '') else '✗ NOT SET or placeholder'}")
print(f"   SIGNATURE_TYPE: {sig_type}")

if not pk or pk.upper() in ("API", "NOT SET", "NONE", ""):
    print("\n✗ ERROR: PK environment variable is not set or is a placeholder!")
    print("   Set it in docker-compose.yml or .env file")
    sys.exit(1)

if not proxy or proxy.upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
    print("\n✗ ERROR: BROWSER_ADDRESS environment variable is not set or is a placeholder!")
    print("   Set it in docker-compose.yml or .env file")
    sys.exit(1)

# Step 2: Load and check current config
print("\n2. Checking current config.json...")
if not config_file.exists():
    print(f"✗ Config file not found: {config_file}")
    sys.exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

if "api" not in config:
    config["api"] = {}

api_cfg = config["api"]
print(f"   PRIVATE_KEY: {api_cfg.get('PRIVATE_KEY', 'NOT SET')[:20]}... (first 20 chars)")
print(f"   PROXY_ADDRESS: {api_cfg.get('PROXY_ADDRESS', 'NOT SET')}")
print(f"   SIGNATURE_TYPE: {api_cfg.get('SIGNATURE_TYPE', 'NOT SET')} (type: {type(api_cfg.get('SIGNATURE_TYPE'))})")
print(f"   CHAIN_ID: {api_cfg.get('CHAIN_ID', 'NOT SET')}")

# Step 3: Fix config
print("\n3. Fixing config...")

# Update PRIVATE_KEY
old_pk = api_cfg.get("PRIVATE_KEY", "")
if old_pk != pk:
    config["api"]["PRIVATE_KEY"] = pk
    print(f"   ✓ Updated PRIVATE_KEY")
else:
    print(f"   ✓ PRIVATE_KEY already correct")

# Update PROXY_ADDRESS (checksum it)
old_proxy = api_cfg.get("PROXY_ADDRESS", "")
try:
    checksummed = Web3.to_checksum_address(proxy)
    if old_proxy != checksummed:
        config["api"]["PROXY_ADDRESS"] = checksummed
        print(f"   ✓ Updated PROXY_ADDRESS: {checksummed}")
    else:
        print(f"   ✓ PROXY_ADDRESS already correct: {checksummed}")
except Exception as e:
    print(f"   ✗ Failed to checksum PROXY_ADDRESS: {e}")
    config["api"]["PROXY_ADDRESS"] = proxy
    print(f"   ⚠ Using non-checksummed address (may cause issues)")

# Update SIGNATURE_TYPE (must be integer)
try:
    sig_type_int = int(sig_type)
    old_sig = api_cfg.get("SIGNATURE_TYPE")
    if old_sig != sig_type_int or not isinstance(old_sig, int):
        config["api"]["SIGNATURE_TYPE"] = sig_type_int
        print(f"   ✓ Updated SIGNATURE_TYPE: {sig_type_int} (was: {old_sig}, type: {type(old_sig)})")
    else:
        print(f"   ✓ SIGNATURE_TYPE already correct: {sig_type_int}")
except ValueError:
    print(f"   ✗ Invalid SIGNATURE_TYPE: {sig_type}, using 2 as default")
    config["api"]["SIGNATURE_TYPE"] = 2

# Ensure CHAIN_ID is set
if "CHAIN_ID" not in config["api"]:
    config["api"]["CHAIN_ID"] = 137
    print(f"   ✓ Set CHAIN_ID: 137")

# Step 4: Validate final config
print("\n4. Validating final config...")
api_cfg = config["api"]

issues = []
if not api_cfg.get("PRIVATE_KEY") or api_cfg.get("PRIVATE_KEY", "").upper() in ("API", "NOT SET", "NONE", ""):
    issues.append("PRIVATE_KEY is still a placeholder")
if not api_cfg.get("PROXY_ADDRESS") or api_cfg.get("PROXY_ADDRESS", "").upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
    issues.append("PROXY_ADDRESS is still a placeholder")
if not isinstance(api_cfg.get("SIGNATURE_TYPE"), int):
    issues.append(f"SIGNATURE_TYPE is not an integer (got: {type(api_cfg.get('SIGNATURE_TYPE'))})")

if issues:
    print("   ✗ Validation failed:")
    for issue in issues:
        print(f"      - {issue}")
    sys.exit(1)

print("   ✓ Config validation passed!")

# Step 5: Save config
print("\n5. Saving config...")
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
print(f"   ✓ Config saved to: {config_file}")

# Step 6: Show final config (without exposing private key)
print("\n6. Final config summary:")
print(f"   PRIVATE_KEY: {'✓ SET' if api_cfg.get('PRIVATE_KEY') else '✗ NOT SET'} (length: {len(api_cfg.get('PRIVATE_KEY', ''))})")
print(f"   PROXY_ADDRESS: {api_cfg.get('PROXY_ADDRESS')}")
print(f"   SIGNATURE_TYPE: {api_cfg.get('SIGNATURE_TYPE')} (type: {type(api_cfg.get('SIGNATURE_TYPE'))})")
print(f"   CHAIN_ID: {api_cfg.get('CHAIN_ID')}")

print("\n" + "="*70)
print("  ✓ CONFIG FIXED SUCCESSFULLY!")
print("="*70)
print("\n⚠️  IMPORTANT: You must RESTART the bot for changes to take effect!")
print("   Run: curl -X POST http://localhost:8000/mm-bot/restart")
print("="*70)

