#!/usr/bin/env python3
"""
Diagnostic script to verify wallet setup and identify signature issues.
Run this inside the Docker container: docker compose exec worker python /app/verify_wallet.py
"""
import os
import sys

# Try to load dotenv, but continue if not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not found. Using environment variables directly.")
    print("Make sure PK and BROWSER_ADDRESS are set in your environment.")

from web3 import Web3
from eth_account import Account

# Get credentials
pk = os.getenv("PK")
browser_address = os.getenv("BROWSER_ADDRESS")

print("="*60)
print("WALLET VERIFICATION DIAGNOSTIC")
print("="*60)

# 1. Check if PK is set
if not pk:
    print("❌ ERROR: PK environment variable is not set!")
    exit(1)
else:
    print(f"✅ PK is set (length: {len(pk)})")

# 2. Clean and validate PK
pk_clean = pk.strip()
if pk_clean.startswith('0x') or pk_clean.startswith('0X'):
    pk_clean = pk_clean[2:]
    print(f"⚠️  Removed '0x' prefix from PK")

if len(pk_clean) != 64:
    print(f"❌ ERROR: PK must be 64 hex characters (got {len(pk_clean)})")
    exit(1)

try:
    int(pk_clean, 16)
    print(f"✅ PK format is valid (64 hex characters)")
except ValueError:
    print(f"❌ ERROR: PK contains invalid hex characters")
    exit(1)

# 3. Derive wallet address from private key
try:
    account = Account.from_key(pk_clean)
    derived_address = account.address
    print(f"✅ Derived wallet address from PK: {derived_address}")
except Exception as e:
    print(f"❌ ERROR deriving address from PK: {e}")
    exit(1)

# 4. Check BROWSER_ADDRESS
if not browser_address:
    print("❌ ERROR: BROWSER_ADDRESS environment variable is not set!")
    exit(1)

browser_address_clean = browser_address.strip()
if browser_address_clean.startswith('0x') and len(browser_address_clean) > 42:
    browser_address_clean = browser_address_clean[:42]
    print(f"⚠️  Truncated BROWSER_ADDRESS to 42 characters")

try:
    browser_address_checksum = Web3.to_checksum_address(browser_address_clean)
    print(f"✅ BROWSER_ADDRESS format is valid: {browser_address_checksum}")
except Exception as e:
    print(f"❌ ERROR: Invalid BROWSER_ADDRESS format: {e}")
    exit(1)

# 5. Compare addresses
if derived_address.lower() != browser_address_checksum.lower():
    print(f"\n❌ CRITICAL MISMATCH:")
    print(f"   Address from PK:     {derived_address}")
    print(f"   BROWSER_ADDRESS:     {browser_address_checksum}")
    print(f"\n   These don't match! The private key doesn't belong to this wallet address.")
    print(f"   This will cause 'invalid signature' errors.")
    print(f"\n   SOLUTION:")
    print(f"   1. Get the private key for wallet {browser_address_checksum}")
    print(f"   2. OR update BROWSER_ADDRESS to {derived_address}")
    exit(1)
else:
    print(f"✅ Addresses match! PK belongs to wallet {derived_address}")

# 6. Test signature creation
print(f"\n{'='*60}")
print("TESTING SIGNATURE CREATION")
print("="*60)

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import POLYGON
    from py_clob_client.clob_types import OrderArgs
    
    host = "https://clob.polymarket.com"
    client = ClobClient(
        host=host,
        key=pk_clean,
        chain_id=POLYGON,
        funder=browser_address_checksum,
        signature_type=2
    )
    
    # Create API credentials
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds=creds)
    print(f"✅ ClobClient initialized successfully")
    print(f"✅ API credentials created")
    
    # Try to create a test order (we'll catch the error)
    print(f"\nAttempting to create a test order signature...")
    test_order = OrderArgs(
        token_id="12345678901234567890123456789012345678901234567890123456789012345678901234567890",
        price=0.5,
        size=1.0,
        side="BUY"
    )
    
    signed_order = client.create_order(test_order)
    print(f"✅ Order signature created successfully!")
    print(f"   This means the signature generation works.")
    print(f"\n   If you're still getting 'invalid signature' errors,")
    print(f"   it's likely because:")
    print(f"   1. The wallet hasn't done a manual trade on Polymarket")
    print(f"   2. The token ID or order parameters are invalid")
    
except Exception as e:
    error_str = str(e)
    print(f"❌ ERROR during signature test: {error_str}")
    if "invalid signature" in error_str.lower():
        print(f"\n   This confirms the signature issue.")
        print(f"   Most likely cause: Wallet hasn't done manual trade on Polymarket")
    else:
        print(f"\n   Unexpected error - may indicate other issues")

print(f"\n{'='*60}")
print("DIAGNOSTIC COMPLETE")
print("="*60)

